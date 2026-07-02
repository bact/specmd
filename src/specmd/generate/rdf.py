# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Generate an OWL ontology with SHACL shapes and JSON-LD context from the parsed model."""

from __future__ import annotations

import logging
import re
import warnings
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

import rfc8785
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SH, SKOS, VANN
from rdflib.tools.rdf2dot import rdf2dot

from specmd.constraints import (
    Cardinality,
    Conditional,
    Conformance,
    Fixed,
    PathType,
    Pattern,
    Present,
    Range,
    SelectorPattern,
    count_bounds,
    parse_constraint,
    scope_property_path,
)
from specmd.parse.model import PropertyNature, parse_qualified_class  # reuse the single qualifier-syntax parser

if TYPE_CHECKING:
    from rdflib.term import Node

    from specmd.parse.model import Class, Model, Property

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Markdown → plain text helper
# ---------------------------------------------------------------------------

_RE_MD_LINK_EXT = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
_RE_MD_LINK_INT = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_RE_MD_CODE_BLOCK = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_RE_MD_INLINE_CODE = re.compile(r"`([^`]+)`")
# CommonMark autolink ``<scheme:...>`` (markdownlint MD034 rewrites bare URLs into this).
_RE_MD_AUTOLINK = re.compile(r"<([a-zA-Z][a-zA-Z0-9+.-]*:[^>\s]+)>")


def _md_to_text(md: str | None) -> str:
    """Strip Markdown markup to produce readable plain text for RDF literals."""
    if not md:
        return ""
    text = _RE_MD_CODE_BLOCK.sub(r"\1", md)
    text = _RE_MD_AUTOLINK.sub(r"\1", text)  # unwrap MD034 autolinks before re-emitting links below
    text = _RE_MD_LINK_EXT.sub(r"\1 <\2>", text)
    text = _RE_MD_LINK_INT.sub(r"\1", text)
    text = _RE_MD_INLINE_CODE.sub(r"\1", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_ref_iri(ref: str, ns_iri: str, base_uri: str) -> str:
    """Resolve a local term reference to a full IRI.

    Supports absolute IRIs (``http://…``), fully-qualified slash paths
    (``/NS/Term``), and bare local names (resolved within *ns_iri*).

    *ns_iri* and *base_uri* are namespace IRIs and always carry a trailing slash
    (see ``Namespace.iri`` / ``Model.base_uri``), so no separator is inserted here.
    """
    if ref.startswith(("http://", "https://")):
        return ref
    if ref.startswith("/"):
        parts = ref.lstrip("/").split("/", 1)
        if len(parts) == 2:
            return f"{base_uri}{parts[0]}/{parts[1]}"
    return f"{ns_iri}{ref}"


def _emit_example(g: Graph, node: URIRef, value: str) -> None:
    """Emit ``vann:example`` for *value* -- as a URIRef if it looks like a URI, else as a Literal."""
    if value.startswith(("http://", "https://")):
        g.add((node, VANN.example, URIRef(value)))
    else:
        g.add((node, VANN.example, Literal(value)))


def _xsd_range(rng: str, propname: str) -> URIRef | None:
    if rng.startswith("xsd:"):
        return URIRef("http://www.w3.org/2001/XMLSchema#" + rng[4:])
    logger.warning("Unknown namespace in range <%s> of property %s", rng, propname)
    return None


def _resolve_class_iri(model: Model, ns_name: str, name: str) -> str | None:
    """Resolve a class name (bare or ``/NS/Name``) to its IRI, or ``None`` if unknown."""
    fq = name if name.startswith("/") else f"/{ns_name}/{name}"
    cls = model.classes.get(fq)
    if cls is None:
        logger.warning("Constraint references unknown class %r", name)
        return None
    return cls.iri


def _resolve_prop_iri(model: Model, ns_name: str, name: str) -> str | None:
    """Resolve a property name (bare or ``/NS/name``) to its IRI, or ``None`` if unknown."""
    fq = name if name.startswith("/") else f"/{ns_name}/{name}"
    prop = model.properties.get(fq)
    if prop is None:
        logger.warning("Constraint references unknown property %r", name)
        return None
    return prop.iri


def _range_class_fq(model: Model, prop_fq: str) -> str | None:
    """The fully-qualified class a property's range points at, or ``None`` for a datatype range."""
    prop = model.properties.get(prop_fq)
    if prop is None:
        return None
    rng = prop.metadata.get("range", "")
    if not rng or rng.startswith("xsd:"):
        return None
    fq = rng if rng.startswith("/") else f"/{prop.ns.name}/{rng}"
    return fq if fq in model.classes else None


def _walk_path(model: Model, ns_name: str, path: tuple[str, ...], start_cls: str | None = None) -> tuple[list[str] | None, str | None]:
    """Resolve path hops to ``(hop_iris, last_prop_fq)`` via a contextual type-walk.

    Each bare hop is resolved as a property of the class reached by the previous hop
    (``Class.all_properties``, which spans namespaces), anchored at *start_cls*; a
    ``/NS/name`` hop overrides. When a hop is not found contextually (no class context,
    or absent there), it falls back to single-namespace resolution in *ns_name*.
    Returns ``(None, None)`` if any hop is unresolvable.
    """
    iris: list[str] = []
    last_fq: str | None = None
    cls_fq = start_cls
    for hop in path:
        prop_fq: str | None = None
        if hop.startswith("/"):
            prop_fq = hop
        elif cls_fq is not None:
            cls = model.classes.get(cls_fq)
            if cls is not None and hop in cls.all_properties:
                prop_fq = cls.all_properties[hop]["fullname"]
        if prop_fq is None:
            prop_fq = f"/{ns_name}/{hop}"
        prop = model.properties.get(prop_fq)
        if prop is None:
            logger.warning("Constraint references unknown property %r", hop)
            return None, None
        iris.append(prop.iri)
        last_fq = prop_fq
        cls_fq = _range_class_fq(model, prop_fq)
    return iris, last_fq


def _resolve_prop_ctx(model: Model, ns_name: str, name: str, start_cls: str | None = None) -> str | None:
    """Resolve a single property reference with the contextual type-walk (see :func:`_walk_path`)."""
    iris, _ = _walk_path(model, ns_name, (name,), start_cls)
    return iris[0] if iris else None


def _class_fq(ns_name: str, name: str) -> str:
    """The fully-qualified ``/NS/Name`` form of a class reference (bare names use *ns_name*)."""
    return name if name.startswith("/") else f"/{ns_name}/{name}"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def gen_rdf(model: Model, outpath: Path, cfg: Any) -> None:  # pylint: disable=unused-argument
    """Serialise the ontology to all supported RDF formats and write the JSON-LD context."""
    g = gen_rdf_ontology(model)

    rdf_cfg = model.config.get("rdf", {})
    filename = rdf_cfg.get("filename", "spdx-model")
    context_filename = rdf_cfg.get("context-filename", "spdx-context")

    # rdflib's PrettyXMLSerializer unconditionally warns for every RDF list head
    # BNode even when no extra assertions exist. Filter that spurious warning.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"Assertions on .* other than RDF\.first and RDF\.rest are ignored",
            category=UserWarning,
            module=r"rdflib\.plugins\.serializers\.rdfxml",
        )
        for ext in ["hext", "json-ld", "longturtle", "n3", "nt", "pretty-xml", "trig", "ttl", "xml"]:
            f = outpath / f"{filename}.{ext}"
            g.serialize(f, format=ext, encoding="utf-8")

    ctx = _jsonld_context(g, model.base_uri)
    fn = outpath / f"{context_filename}.jsonld"
    fn.write_bytes(rfc8785.dumps(ctx))

    fn = outpath / f"{filename}.dot"
    with fn.open("w") as fh:
        rdf2dot(g, fh)


# ---------------------------------------------------------------------------
# Ontology graph construction
# ---------------------------------------------------------------------------

_ONT_DEFAULTS: dict[str, str] = {
    "preferred-namespace-prefix": "spdx",
    "label": "System Package Data Exchange™ (SPDX®) Ontology",
    "title": "System Package Data Exchange (SPDX) Ontology",
    "abstract": "This ontology defines the terms and relationships used in the SPDX specification to describe system packages",
    "creator": "SPDX Project",
    "license-uri": "https://spdx.org/licenses/Community-Spec-1.0.html",
    "references": "https://spdx.dev/specifications/",
    "copyright": "Copyright (C) SPDX Project",
}


def _ont_cfg(model: Model) -> dict[str, str]:
    """Merge ``specmd.yml`` ``ontology:`` block with built-in defaults."""
    ont = model.config.get("ontology", {})
    return {k: ont.get(k, v) for k, v in _ONT_DEFAULTS.items()}


def gen_rdf_ontology(model: Model) -> Graph:
    """Build and return an rdflib Graph containing the full OWL+SHACL ontology."""
    g = Graph()

    uri_base = model.base_uri
    ontology_cfg = _ont_cfg(model)

    g.bind(ontology_cfg["preferred-namespace-prefix"], Namespace(uri_base))

    # Per-namespace prefix bindings with VANN annotations.
    for ns in model.namespaces:
        prefix = ns.metadata.get("preferredNamespacePrefix") or "spdx-" + ns.name.lower()
        # ns.iri always carries a trailing slash (Namespace.iri is canonicalized at parse
        # time) so that it matches the term IRIs minted against it (f"{ns.iri}{name}"),
        # letting rdflib's serializers recognize the bound prefix and reuse it -- rather
        # than failing to match and minting their own ns1, ns2, ... for the same namespace.
        ns_iri = Namespace(ns.iri)
        g.bind(prefix, ns_iri)
        ns_node = URIRef(ns.iri)
        g.add((ns_node, VANN.preferredNamespacePrefix, Literal(prefix)))
        g.add((ns_node, VANN.preferredNamespaceUri, Literal(ns.iri)))
        if ns.metadata.get("deprecated") == "true":
            g.add((ns_node, OWL.deprecated, Literal(True)))
            dv = ns.metadata.get("deprecatedVersion")
            if dv:
                g.add((ns_node, OWL.versionInfo, Literal(f"Deprecated since version {dv}", lang="en")))
        replaced_by = ns.metadata.get("isReplacedBy")
        if replaced_by:
            g.add((ns_node, DCTERMS.isReplacedBy, URIRef(_resolve_ref_iri(replaced_by, ns.iri, uri_base))))
        example = ns.metadata.get("example")
        if example:
            _emit_example(g, ns_node, example)

    OMG_ANN = Namespace("https://www.omg.org/spec/Commons/AnnotationVocabulary/")
    g.bind("omg-ann", OMG_ANN)
    g.bind("vann", VANN)

    # Declare all non-built-in annotation properties used in this graph so the
    # ontology is structurally well-formed under OWL 2 (no owl:imports required).
    for _ap in (
        VANN.preferredNamespacePrefix,
        VANN.preferredNamespaceUri,
        VANN.example,
        SKOS.definition,
        SKOS.note,
        DCTERMS.abstract,
        DCTERMS.creator,
        DCTERMS.license,
        DCTERMS.references,
        DCTERMS.title,
        DCTERMS.isReplacedBy,
        OMG_ANN.copyright,
    ):
        g.add((_ap, RDF.type, OWL.AnnotationProperty))

    # Ontology node.
    ont_node = URIRef(uri_base)
    g.add((ont_node, RDF.type, OWL.Ontology))

    # owl:versionInfo / owl:versionIRI from namespace metadata.
    # W3C OWL 2 §3.1 permits the version IRI to equal the ontology IRI, but
    # a self-referential version IRI conveys no version information and makes
    # it impossible to distinguish releases by IRI. We therefore emit
    # owl:versionIRI only when a version string is present, constructing a
    # distinct versioned IRI that identifies the specific release.
    # https://www.w3.org/TR/owl2-syntax/#Ontology_IRI_and_Version_IRI
    for ns in model.namespaces:
        v = ns.metadata.get("version") or ns.metadata.get("Version")
        if v:
            g.add((ont_node, OWL.versionInfo, Literal(v)))
            # If the major version appears as a path segment (e.g. /3/ in SPDX IRIs),
            # replace it with the full version to get a stable sibling IRI
            # (https://spdx.org/rdf/3/terms/ → https://spdx.org/rdf/3.1/terms/).
            # Otherwise append the version as a sub-path (generic fallback).
            major = v.split(".")[0]
            if f"/{major}/" in uri_base:
                versioned_iri = URIRef(uri_base.replace(f"/{major}/", f"/{v}/", 1))
            else:
                versioned_iri = URIRef(uri_base.rstrip("/") + "/" + v + "/")
            g.add((ont_node, OWL.versionIRI, versioned_iri))
            break

    # vann:preferredNamespacePrefix / vann:preferredNamespaceUri (W3C BCP for vocab publishing).
    g.add((ont_node, VANN.preferredNamespacePrefix, Literal(ontology_cfg["preferred-namespace-prefix"])))
    g.add((ont_node, VANN.preferredNamespaceUri, Literal(uri_base)))

    g.add((ont_node, RDFS.label, Literal(ontology_cfg["label"], lang="en")))
    g.add((ont_node, DCTERMS.abstract, Literal(ontology_cfg["abstract"], lang="en")))
    g.add((ont_node, DCTERMS.creator, Literal(ontology_cfg["creator"], lang="en")))
    g.add((ont_node, DCTERMS.license, URIRef(ontology_cfg["license-uri"])))
    g.add((ont_node, DCTERMS.references, URIRef(ontology_cfg["references"])))
    g.add((ont_node, DCTERMS.title, Literal(ontology_cfg["title"], lang="en")))
    g.add((ont_node, OMG_ANN.copyright, Literal(ontology_cfg["copyright"], lang="en")))

    # Shared across the class-property and class-constraint passes so an identical
    # constraint is never emitted twice on the same class node.
    seen: set[tuple[str, object]] = set()
    _gen_classes(model, g, seen)
    _gen_class_constraints(model, g, seen)
    _gen_relationship_constraints(model, g)
    _gen_conformance(model, g)
    _gen_properties(model, g)
    _gen_vocabularies(model, g)
    _gen_individuals(model, g)

    return g


# ---------------------------------------------------------------------------
# Per-element generators
# ---------------------------------------------------------------------------


def _get_parent(model: Model, c: Class) -> Class | None:
    parent = c.metadata.get("subClassOf")
    if parent:
        pns = "" if parent.startswith("/") else f"/{c.ns.name}/"
        return model.classes[pns + parent]
    return None


def _gen_classes(model: Model, g: Graph, seen: set[tuple[str, object]]) -> None:
    for c in model.classes.values():
        node = URIRef(c.iri)
        ns_node = URIRef(c.ns.iri)

        g.add((node, RDF.type, OWL.Class))
        g.add((node, RDFS.isDefinedBy, ns_node))
        g.add((node, RDFS.label, Literal(c.name, lang="en")))

        if c.summary:
            plain_summary = _md_to_text(c.summary)
            g.add((node, RDFS.comment, Literal(plain_summary, lang="en")))
            g.add((node, SKOS.definition, Literal(plain_summary, lang="en")))

        if c.description:
            g.add((node, SKOS.note, Literal(_md_to_text(c.description), lang="en")))

        if c.metadata.get("deprecated") == "true":
            g.add((node, OWL.deprecated, Literal(True)))
            dv = c.metadata.get("deprecatedVersion")
            if dv:
                g.add((node, OWL.versionInfo, Literal(f"Deprecated since version {dv}", lang="en")))
        replaced_by = c.metadata.get("isReplacedBy")
        if replaced_by:
            g.add((node, DCTERMS.isReplacedBy, URIRef(_resolve_ref_iri(replaced_by, c.ns.iri, model.base_uri))))
        example = c.metadata.get("example")
        if example:
            _emit_example(g, node, example)

        parent = _get_parent(model, c)
        if parent is not None:
            g.add((node, RDFS.subClassOf, URIRef(parent.iri)))

        if c.metadata.get("abstract") == "true":
            # SHACL layer: reject instances typed directly as this abstract class.
            bnode = BNode()
            g.add((node, SH.property, bnode))
            g.add((bnode, SH.path, RDF.type))
            not_node = BNode()
            g.add((bnode, SH["not"], not_node))
            g.add((not_node, SH["hasValue"], node))
            g.add(
                (
                    bnode,
                    SH.message,
                    Literal(
                        f"{node} is abstract and must not be instantiated directly.",
                        lang="en",
                    ),
                )
            )
            # OWL 2 EL/QL/RL-compatible disjointness among direct subclasses.
            if c.direct_subclasses:
                dc_node = BNode()
                g.add((dc_node, RDF.type, OWL.AllDisjointClasses))
                members_list = Collection(g, None)  # type: ignore[arg-type]
                for fq in c.direct_subclasses:
                    members_list.append(URIRef(model.classes[fq].iri))
                g.add((dc_node, OWL.members, members_list.uri))

        # Every class is also a sh:NodeShape so all constraints are visible to SHACL processors.
        g.add((node, RDF.type, SH.NodeShape))
        if "spdxId" in c.all_properties:
            g.add((node, SH.nodeKind, SH.IRI))
        else:
            g.add((node, SH.nodeKind, SH.BlankNodeOrIRI))

        if c.properties:
            for p in c.properties:
                fqprop = c.properties[p]["fqname"]
                if fqprop == "/Core/spdxId":
                    continue
                bnode = BNode()
                g.add((node, SH.property, bnode))
                prop = model.properties[fqprop]
                g.add((bnode, SH.path, URIRef(prop.iri)))

                prop_rng = prop.metadata["range"]
                typename = prop_rng if ":" in prop_rng else (prop_rng if prop_rng.startswith("/") else f"/{prop.ns.name}/{prop_rng}")

                if typename in model.classes:
                    dt = model.classes[typename]
                    if typename == "/Extension/Extension":
                        # Extension subclasses cannot be fully validated.
                        ext_node = BNode()
                        lst = Collection(g, None)  # type: ignore[arg-type]
                        for cls in model.classes.values():
                            if cls.metadata.get("abstract") == "true":
                                continue
                            cls_parent = _get_parent(model, cls)
                            if cls_parent is not None and cls_parent.fqname == "/Extension/Extension":
                                continue
                            cls_node = BNode()
                            g.add((cls_node, SH["class"], URIRef(cls.iri)))
                            lst.append(cls_node)
                        not_node = BNode()
                        g.add((ext_node, SH["not"], not_node))
                        g.add((not_node, SH["or"], lst.uri))
                        g.add((ext_node, SH.message, Literal("Class is known to not derive from Extension and cannot be used", lang="en")))
                        g.add((ext_node, SH.path, URIRef(prop.iri)))
                        g.add((node, SH.property, ext_node))
                    else:
                        g.add((bnode, SH["class"], URIRef(dt.iri)))

                    # sh:nodeKind distinguishes IRI-identified from blank-node resources.
                    if "spdxId" in dt.all_properties:
                        g.add((bnode, SH.nodeKind, SH.IRI))
                    else:
                        g.add((bnode, SH.nodeKind, SH.BlankNodeOrIRI))

                elif typename in model.vocabularies:
                    dt_v = model.vocabularies[typename]
                    # sh:in enumerates exactly the valid IRIs; sh:class is redundant.
                    lst = Collection(g, None)  # type: ignore[arg-type]
                    for e in dt_v.entries:
                        lst.append(URIRef(dt_v.iri + "/" + e))
                    g.add((bnode, SH["in"], lst.uri))

                elif typename in model.datatypes:
                    dt_d = model.datatypes[typename]
                    if "pattern" in dt_d.format:
                        g.add((bnode, SH.pattern, Literal(dt_d.format["pattern"])))
                    t = _xsd_range(dt_d.metadata["subClassOf"], prop.iri)
                    if t:
                        g.add((bnode, SH.datatype, t))

                else:
                    t = _xsd_range(typename, prop.iri)
                    if t:
                        g.add((bnode, SH.datatype, t))

                mincount = c.properties[p]["minCount"]
                if int(mincount) != 0:
                    g.add((bnode, SH.minCount, Literal(int(mincount))))
                maxcount = c.properties[p]["maxCount"]
                if maxcount != "*":
                    g.add((bnode, SH.maxCount, Literal(int(maxcount))))

                # Property-level constraints apply to the property's value, so they
                # propagate to every using class with the property name prepended.
                _emit_property_constraints(model, g, node, prop, seen)


def _emit_property_constraints(model: Model, g: Graph, c_node: URIRef, prop: Property, seen: set[tuple[str, object]]) -> None:
    """Emit a property's own ``## Constraints`` on *c_node*, scoped through the property.

    Only path-bearing constraints (``type`` / ``not type`` / ``matches``) are valid
    on a property. The property name is prepended as the first hop so the SHACL
    targets the property's value (e.g. ``customIdToLicense -> elementValue``) --
    unless the author already wrote the property as an explicit first hop. Each
    ``(class node, scoped AST)`` is emitted at most once.
    """
    for expr in getattr(prop, "constraints", []):
        ast = parse_constraint(expr)
        scoped = scope_property_path(ast, prop.name)
        if scoped is None:
            if ast is not None:
                logger.warning("Property %s: only path constraints are supported on a property, got %r", prop.iri, expr)
            continue
        key = (str(c_node), scoped)
        if key in seen:
            continue
        seen.add(key)
        _emit_constraint(_EmitCtx(model, g, prop.ns.name), c_node, scoped)


class _EmitCtx(NamedTuple):
    """Shared context threaded through every SHACL emitter."""

    model: Model
    g: Graph
    ns_name: str


class _GateCtx(NamedTuple):
    """Conformance-rule gate parameters."""

    coll_node: URIRef
    coll_ref: str
    gate_iris: list[str]
    prof_iri: str


def _emit_cardinality(ctx: _EmitCtx, c_node: URIRef | BNode, ast: Cardinality, start_cls: str | None = None) -> None:
    """Emit a property shape with ``sh:minCount``/``sh:maxCount`` on *ast.path*."""
    hop_iris, _ = _walk_path(ctx.model, ctx.ns_name, ast.path, start_cls)
    if hop_iris is None:
        return
    pshape = BNode()
    ctx.g.add((c_node, SH.property, pshape))
    _emit_path(ctx.g, pshape, hop_iris)
    ctx.g.add((pshape, SH.minCount if ast.kind == "min" else SH.maxCount, Literal(ast.count)))


def _emit_present(ctx: _EmitCtx, c_node: URIRef | BNode, ast: Present, start_cls: str | None = None) -> None:
    """Emit a property shape requiring *ast.path* to include *ast.value* (``sh:hasValue``)."""
    hop_iris, last_fq = _walk_path(ctx.model, ctx.ns_name, ast.path, start_cls)
    if hop_iris is None:
        return
    value_iri = _resolve_value_iri(ctx.model, last_fq, ast.value)
    if value_iri is None:
        return
    pshape = BNode()
    ctx.g.add((c_node, SH.property, pshape))
    _emit_path(ctx.g, pshape, hop_iris)
    ctx.g.add((pshape, SH["hasValue"], URIRef(value_iri)))


def _emit_conditional(ctx: _EmitCtx, c_node: URIRef | BNode, ast: Conditional, start_cls: str | None = None) -> None:
    """Emit ``if A then B`` as ``sh:or ( [ sh:not [A] ] [B] )``."""
    ante_shape = BNode()
    _emit_constraint(ctx, ante_shape, ast.antecedent, start_cls)
    not_branch = BNode()
    ctx.g.add((not_branch, SH["not"], ante_shape))
    cons_branch = BNode()
    _emit_constraint(ctx, cons_branch, ast.consequent, start_cls)
    or_list = Collection(ctx.g, None)  # type: ignore[arg-type]
    or_list.append(not_branch)
    or_list.append(cons_branch)
    ctx.g.add((c_node, SH["or"], or_list.uri))


def _emit_class_choice(g: Graph, node: BNode, cls_iris: list[str]) -> None:
    """Restrict *node* to the given class(es): ``sh:class`` for one, ``sh:or`` of classes for several."""
    if len(cls_iris) == 1:
        g.add((node, SH["class"], URIRef(cls_iris[0])))
    else:
        or_list = Collection(g, None)  # type: ignore[arg-type]
        for ci in cls_iris:
            cnode = BNode()
            g.add((cnode, SH["class"], URIRef(ci)))
            or_list.append(cnode)
        g.add((node, SH["or"], or_list.uri))


def _emit_pos_neg(g: Graph, pshape: BNode, pos_iris: list[str], neg_iris: list[str]) -> None:
    """Put positive classes on *pshape* (``sh:class``/``sh:or``); each negative as ``sh:not [ sh:class ]``."""
    if pos_iris:
        _emit_class_choice(g, pshape, pos_iris)
    for ni in neg_iris:
        not_node = BNode()
        g.add((not_node, SH["class"], URIRef(ni)))
        g.add((pshape, SH["not"], not_node))


def _emit_path(g: Graph, pshape: BNode, hop_iris: list[str]) -> None:
    """Set ``sh:path`` on *pshape*: a plain IRI for one hop, a sequence-path list for many."""
    if len(hop_iris) == 1:
        g.add((pshape, SH.path, URIRef(hop_iris[0])))
    else:
        path_list = Collection(g, None)  # type: ignore[arg-type]
        for hop in hop_iris:
            path_list.append(URIRef(hop))
        g.add((pshape, SH.path, path_list.uri))


def _emit_path_type(ctx: _EmitCtx, c_node: URIRef | BNode, ast: PathType, start_cls: str | None = None) -> None:
    """Emit a property shape restricting the type of nodes reached by *ast.path*.

    Positive classes go on the property shape (``sh:class`` / ``sh:or``); each
    negative class is wrapped in its own ``sh:not [ sh:class ]``.
    """
    hop_iris, _ = _walk_path(ctx.model, ctx.ns_name, ast.path, start_cls)
    pos_iris = [_resolve_class_iri(ctx.model, ctx.ns_name, c) for c in ast.positives]
    neg_iris = [_resolve_class_iri(ctx.model, ctx.ns_name, c) for c in ast.negatives]
    if hop_iris is None or any(i is None for i in (*pos_iris, *neg_iris)):
        return

    pshape = BNode()
    ctx.g.add((c_node, SH.property, pshape))
    _emit_path(ctx.g, pshape, hop_iris)
    _emit_pos_neg(ctx.g, pshape, pos_iris, neg_iris)  # type: ignore[arg-type]


def _emit_pattern(ctx: _EmitCtx, c_node: URIRef | BNode, ast: Pattern, start_cls: str | None = None) -> None:
    """Emit a property shape constraining the literal reached by *ast.path* to ``sh:pattern``."""
    hop_iris, _ = _walk_path(ctx.model, ctx.ns_name, ast.path, start_cls)
    if hop_iris is None:
        return
    pshape = BNode()
    ctx.g.add((c_node, SH.property, pshape))
    _emit_path(ctx.g, pshape, hop_iris)
    ctx.g.add((pshape, SH["pattern"], Literal(ast.regex)))
    if ast.flags:
        ctx.g.add((pshape, SH["flags"], Literal(ast.flags)))


def _numeric_literal(s: str) -> Literal:
    """A SHACL-comparable numeric literal: ``xsd:decimal`` if it has a point, else ``xsd:integer``."""
    return Literal(Decimal(s)) if "." in s else Literal(int(s))


def _emit_range(ctx: _EmitCtx, c_node: URIRef | BNode, ast: Range, start_cls: str | None = None) -> None:
    """Emit a property shape bounding the numeric literal reached by *ast.path* (inclusive)."""
    hop_iris, _ = _walk_path(ctx.model, ctx.ns_name, ast.path, start_cls)
    if hop_iris is None:
        return
    pshape = BNode()
    ctx.g.add((c_node, SH.property, pshape))
    _emit_path(ctx.g, pshape, hop_iris)
    ctx.g.add((pshape, SH.minInclusive, _numeric_literal(ast.lo)))
    ctx.g.add((pshape, SH.maxInclusive, _numeric_literal(ast.hi)))


def _resolve_value_iri(model: Model, prop_fq: str | None, value: str) -> str | None:
    """Resolve a fixed value to an IRI: a ``/NS/Vocab/entry`` form, or a bare entry of *prop_fq*'s range vocabulary."""
    if value.startswith("/"):
        return model.base_uri + value.lstrip("/")
    prop = model.properties.get(prop_fq) if prop_fq else None
    if prop is None:
        logger.warning("Fixed-value constraint references unknown property %r", prop_fq)
        return None
    rng = prop.metadata.get("range", "")
    vocab_fq = rng if rng.startswith("/") else f"/{prop.ns.name}/{rng}"
    vocab = model.vocabularies.get(vocab_fq)
    if vocab is None:
        logger.warning("Fixed-value %r: property %s has no vocabulary range", value, prop_fq)
        return None
    return f"{vocab.iri}/{value}"


def _emit_fixed(ctx: _EmitCtx, c_node: URIRef | BNode, ast: Fixed, start_cls: str | None = None) -> None:
    """Emit a property shape pinning the node reached by *ast.path* to a fixed value (``sh:hasValue``)."""
    hop_iris, last_fq = _walk_path(ctx.model, ctx.ns_name, ast.path, start_cls)
    if hop_iris is None:
        return
    value_iri = _resolve_value_iri(ctx.model, last_fq, ast.value)
    if value_iri is None:
        return
    pshape = BNode()
    ctx.g.add((c_node, SH.property, pshape))
    _emit_path(ctx.g, pshape, hop_iris)
    ctx.g.add((pshape, SH["hasValue"], URIRef(value_iri)))


def _emit_selector_pattern(ctx: _EmitCtx, c_node: URIRef | BNode, ast: SelectorPattern, start_cls: str | None = None) -> None:
    """Emit, per entry of the selector's range vocabulary that has a ``pattern``, a guarded
    ``sh:or ( [ sh:not [ selector hasValue entry ] ] [ path sh:pattern entry-pattern ] )``."""
    hop_iris, _ = _walk_path(ctx.model, ctx.ns_name, ast.path, start_cls)
    sel_iri = _resolve_prop_ctx(ctx.model, ctx.ns_name, ast.selector, start_cls)
    if hop_iris is None or sel_iri is None:
        return
    # The selector is a property of the subject class; resolve its FQ the same way.
    sel_walk, sel_fq = _walk_path(ctx.model, ctx.ns_name, (ast.selector,), start_cls)
    if sel_walk is None:
        return
    sel_prop = ctx.model.properties.get(sel_fq)  # type: ignore[arg-type]
    rng = sel_prop.metadata.get("range", "") if sel_prop else ""
    vocab_fq = rng if rng.startswith("/") else f"/{sel_prop.ns.name}/{rng}" if sel_prop else ""
    vocab = ctx.model.vocabularies.get(vocab_fq)
    if vocab is None:
        logger.warning("matches-selector %r: %s has no vocabulary range", ast.selector, sel_fq)
        return
    for entry_name, entry in vocab.entries.items():
        pattern = entry.get("pattern")
        if not pattern:
            continue
        antecedent = BNode()
        ant_ps = BNode()
        ctx.g.add((antecedent, SH.property, ant_ps))
        ctx.g.add((ant_ps, SH.path, URIRef(sel_iri)))
        ctx.g.add((ant_ps, SH["hasValue"], URIRef(f"{vocab.iri}/{entry_name}")))
        not_branch = BNode()
        ctx.g.add((not_branch, SH["not"], antecedent))
        consequent = BNode()
        cons_ps = BNode()
        ctx.g.add((consequent, SH.property, cons_ps))
        _emit_path(ctx.g, cons_ps, hop_iris)
        ctx.g.add((cons_ps, SH["pattern"], Literal(str(pattern))))
        or_list = Collection(ctx.g, None)  # type: ignore[arg-type]
        or_list.append(not_branch)
        or_list.append(consequent)
        ctx.g.add((c_node, SH["or"], or_list.uri))


def _emit_constraint(ctx: _EmitCtx, c_node: URIRef | BNode, ast: object, start_cls: str | None = None) -> None:
    """Dispatch a parsed constraint to its SHACL emitter.

    *start_cls* is the fully-qualified class that the path is rooted at (the
    constraint's subject), enabling the contextual type-walk in :func:`_walk_path`.
    """
    if isinstance(ast, Conditional):
        _emit_conditional(ctx, c_node, ast, start_cls)
    elif isinstance(ast, SelectorPattern):
        _emit_selector_pattern(ctx, c_node, ast, start_cls)
    elif isinstance(ast, Cardinality):
        _emit_cardinality(ctx, c_node, ast, start_cls)
    elif isinstance(ast, Present):
        _emit_present(ctx, c_node, ast, start_cls)
    elif isinstance(ast, PathType):
        _emit_path_type(ctx, c_node, ast, start_cls)
    elif isinstance(ast, Pattern):
        _emit_pattern(ctx, c_node, ast, start_cls)
    elif isinstance(ast, Range):
        _emit_range(ctx, c_node, ast, start_cls)
    elif isinstance(ast, Fixed):
        _emit_fixed(ctx, c_node, ast, start_cls)


def _gen_class_constraints(model: Model, g: Graph, seen: set[tuple[str, object]]) -> None:
    """Emit SHACL for class-level constraints declared in ``## Constraints`` sections.

    *seen* (shared with the property-constraint pass) skips a constraint already
    emitted on the same class node -- e.g. a class restating a property's own rule.
    """
    for c in model.classes.values():
        constraints = getattr(c, "constraints", None)
        if not constraints:
            continue
        c_node = URIRef(c.iri)
        for expr in constraints:
            ast = parse_constraint(expr)
            if ast is None:
                continue
            key = (str(c_node), ast)
            if key in seen:
                continue
            seen.add(key)
            _emit_constraint(_EmitCtx(model, g, c.ns.name), c_node, ast, start_cls=c.fqname)


class _EndpointClass(NamedTuple):
    """One resolved ``from``/``to`` endpoint class option.

    ``fq`` is kept alongside ``iri`` because qualifier properties (e.g. ``relationshipType``
    on a ``Relationship`` endpoint) are resolved contextually, rooted at this class.
    """

    iri: str
    fq: str
    qualifiers: dict[str, list[str]]


def _is_ancestor(model: Model, ancestor_fq: str, descendant_fq: str) -> bool:
    """Whether *ancestor_fq* is a (transitive, proper) superclass of *descendant_fq*."""
    descendant = model.classes.get(descendant_fq)
    return descendant is not None and ancestor_fq in descendant.inheritance_stack


def _warn_endpoint_subsumptions(class_names: list[str], items: list[_EndpointClass], model: Model, polarity: str) -> None:
    """Warn about every ancestor/descendant pair within *items* (one polarity group: all
    positive, or all negative, from the same ``from``/``to`` list).

    SHACL's ``sh:class`` follows ``rdfs:subClassOf*`` in the data graph, so within a single
    polarity group an ancestor class already matches everything a listed descendant would:

    - Among **positives** (``sh:or``), the ancestor branch alone matches every instance the
      descendant branch would, making the descendant redundant -- and, worse, making any
      qualifier on the descendant vacuous, since an instance can satisfy the ``sh:or`` via the
      unqualified ancestor branch without ever being checked against the qualifier.
    - Among **negatives** (``sh:not`` conjuncts), excluding the ancestor already excludes every
      instance the descendant exclusion would, making the descendant's ``sh:not`` redundant.

    Nothing is dropped (removing a branch could discard a qualifier the author still wants
    enforced on that specific class), only warned about.
    """
    for a in items:
        for b in items:
            if a.fq == b.fq or not _is_ancestor(model, a.fq, b.fq):
                continue
            note = ""
            if b.qualifiers:
                note = " Its qualifier has no effect: any instance can satisfy the OR via the unqualified superclass branch instead."
            logger.warning(
                "Relationship endpoint %s list %r: %r is a superclass of %r, so listing both is redundant "
                "(%r already matches everything %r would).%s",
                polarity,
                class_names,
                a.fq,
                b.fq,
                a.fq,
                b.fq,
                note,
            )


def _endpoint_class_iris(model: Model, ns_name: str, class_names: list[str]) -> tuple[list[_EndpointClass], list[_EndpointClass]]:
    """Resolve relationship endpoint classes to ``(positives, negatives)`` endpoint options.

    Each item may carry a per-item ``not`` and a bracket qualifier
    (``Relationship[relationshipType=invokedBy]``). The qualifier constrains a property of the
    endpoint instance itself and is enforced via a nested ``sh:property`` shape (see
    :func:`_emit_qualifier_shapes`) rather than discarded.

    The universal ``Element`` root is dropped only when it is the *sole* item in the list --
    it is already the range of ``from``/``to``, so on its own it adds no constraint. Any other
    ancestor/descendant pair within the same list (e.g. ``/Software/Package`` alongside its
    subclass ``/AI/AIPackage``) is kept -- dropping either could discard a real per-branch
    qualifier -- but flagged via :func:`_warn_endpoint_subsumptions`, using the model's actual
    class hierarchy rather than special-casing ``Element``.
    """
    pos: list[_EndpointClass] = []
    neg: list[_EndpointClass] = []
    for cn in class_names:
        raw = str(cn).strip()
        negated = raw.startswith("not ")
        if negated:
            raw = raw[4:].strip()
        base, qualifiers = parse_qualified_class(raw)
        if not base:
            continue
        if base == "Element" and len(class_names) == 1:
            continue
        iri = _resolve_class_iri(model, ns_name, base)
        if iri:
            (neg if negated else pos).append(_EndpointClass(iri, _class_fq(ns_name, base), qualifiers))
    _warn_endpoint_subsumptions(class_names, pos, model, "positive")
    _warn_endpoint_subsumptions(class_names, neg, model, "negative")
    return pos, neg


def _emit_qualifier_shapes(ctx: _EmitCtx, cls_fq: str, qualifiers: dict[str, list[str]]) -> list[BNode]:
    """Build one ``sh:property`` shape per qualifier (``propName`` restricted to its values),
    rooted at *cls_fq* -- the endpoint's own class, since a qualifier constrains a property of
    the endpoint instance itself (e.g. a ``Relationship``'s own ``relationshipType``).
    """
    shapes: list[BNode] = []
    for prop_name, values in qualifiers.items():
        if not values:
            # `Foo[prop]` or `Foo[prop=]` (no "=value"): parse_qualified_class yields an empty
            # value list. There's nothing to constrain the property to, so skip it -- building a
            # shape here would emit an unsatisfiable `sh:in ()`, silently invalidating the branch.
            logger.warning("Qualifier %r on class %s has no value(s); skipping", prop_name, cls_fq)
            continue
        hop_iris, prop_fq = _walk_path(ctx.model, ctx.ns_name, (prop_name,), cls_fq)
        if hop_iris is None:
            logger.warning("Qualifier %r on class %s: cannot resolve property", prop_name, cls_fq)
            continue
        value_iris = [_resolve_value_iri(ctx.model, prop_fq, v) for v in values]
        if any(vi is None for vi in value_iris):
            continue
        pshape = BNode()
        ctx.g.add((pshape, SH.path, URIRef(hop_iris[0])))
        if len(value_iris) == 1:
            ctx.g.add((pshape, SH["hasValue"], URIRef(value_iris[0])))  # type: ignore[arg-type]
        else:
            lst = Collection(ctx.g, None)  # type: ignore[arg-type]
            for vi in value_iris:
                lst.append(URIRef(vi))  # type: ignore[arg-type]
            ctx.g.add((pshape, SH["in"], lst.uri))
        shapes.append(pshape)
    return shapes


def _emit_endpoint_class_choice(ctx: _EmitCtx, node: BNode, items: list[_EndpointClass]) -> None:
    """Restrict *node* to the given endpoint class option(s), applying each option's own
    qualifier constraints (if any) only to its own branch.

    A single option's ``sh:class`` (and qualifier shapes) attach directly to *node*; multiple
    options become an ``sh:or`` of per-option shapes, so e.g. an unqualified option in the same
    list is not accidentally restricted by another option's qualifier.
    """
    if len(items) == 1:
        item = items[0]
        ctx.g.add((node, SH["class"], URIRef(item.iri)))
        for qshape in _emit_qualifier_shapes(ctx, item.fq, item.qualifiers):
            ctx.g.add((node, SH.property, qshape))
    else:
        or_list = Collection(ctx.g, None)  # type: ignore[arg-type]
        for item in items:
            cnode = BNode()
            ctx.g.add((cnode, SH["class"], URIRef(item.iri)))
            for qshape in _emit_qualifier_shapes(ctx, item.fq, item.qualifiers):
                ctx.g.add((cnode, SH.property, qshape))
            or_list.append(cnode)
        ctx.g.add((node, SH["or"], or_list.uri))


def _emit_endpoint_pos_neg(ctx: _EmitCtx, pshape: BNode, pos_items: list[_EndpointClass], neg_items: list[_EndpointClass]) -> None:
    """Put positive endpoint options on *pshape* (``sh:class``/``sh:or``, with qualifiers);
    each negative option as ``sh:not [ sh:class + qualifier shapes ]``."""
    if pos_items:
        _emit_endpoint_class_choice(ctx, pshape, pos_items)
    for item in neg_items:
        not_node = BNode()
        ctx.g.add((not_node, SH["class"], URIRef(item.iri)))
        for qshape in _emit_qualifier_shapes(ctx, item.fq, item.qualifiers):
            ctx.g.add((not_node, SH.property, qshape))
        ctx.g.add((pshape, SH["not"], not_node))


def _emit_endpoint(model: Model, g: Graph, parent: BNode, ns_name: str, side: tuple[str, list[str]]) -> bool:
    """Resolve and emit one endpoint shape; return ``True`` when a shape was emitted."""
    prop_name, class_names = side
    pos, neg = _endpoint_class_iris(model, ns_name, class_names)
    if not pos and not neg:
        return False
    prop_iri = _resolve_prop_iri(model, ns_name, prop_name)
    if not prop_iri:
        return False
    pshape = BNode()
    g.add((parent, SH.property, pshape))
    g.add((pshape, SH.path, URIRef(prop_iri)))
    _emit_endpoint_pos_neg(_EmitCtx(model, g, ns_name), pshape, pos, neg)
    return True


def _gen_relationship_constraints(model: Model, g: Graph) -> None:
    """Emit SHACL scoping the ``from``/``to`` endpoint classes per relationship type.

    For each entry of a relationship-type vocabulary, the relationship class is
    constrained so that *if* its ``relationshipType`` is that entry, *then* its
    ``from``/``to`` values must be instances of the entry's declared classes.
    This is encoded as ``sh:or ( [not this type] [endpoints conform] )``.
    """
    for vocab in model.vocabularies.values():
        if not getattr(vocab, "is_relationship_vocab", False):
            continue
        ns_name = vocab.ns.name
        rtype_prop = _resolve_prop_iri(model, ns_name, "relationshipType")
        if not rtype_prop:
            continue
        for entry_name, entry in vocab.entries.items():
            rel_base = str(entry.get("relationshipClass", "")).split("[", 1)[0].strip()
            rel_class_iri = _resolve_class_iri(model, ns_name, rel_base) if rel_base else None
            if not rel_class_iri:
                continue

            from_classes = entry.get("from") if isinstance(entry.get("from"), list) else []
            to_classes = entry.get("to") if isinstance(entry.get("to"), list) else []
            consequent = BNode()
            emitted = _emit_endpoint(model, g, consequent, ns_name, ("from", from_classes))  # type: ignore[arg-type]
            emitted = _emit_endpoint(model, g, consequent, ns_name, ("to", to_classes)) or emitted  # type: ignore[arg-type]
            if not emitted:
                continue

            # Antecedent shape: the relationship has this entry as its relationshipType value.
            antecedent = BNode()
            ant_ps = BNode()
            g.add((antecedent, SH.property, ant_ps))
            g.add((ant_ps, SH.path, URIRef(rtype_prop)))
            g.add((ant_ps, SH["hasValue"], URIRef(vocab.iri + "/" + entry_name)))

            not_node = BNode()
            g.add((not_node, SH["not"], antecedent))

            or_list = Collection(g, None)  # type: ignore[arg-type]
            or_list.append(not_node)
            or_list.append(consequent)
            g.add((URIRef(rel_class_iri), SH["or"], or_list.uri))


def _emit_gate_not(g: Graph, prof_iri: str, gate_iris: list[str], *, require_present: bool = False) -> BNode:
    """Return a node shape that conforms iff the gate property has *none* of *gate_iris*.

    When *require_present* is true (the rule's profile is the **default**, so an
    omitted ``profileConformance`` is treated as that profile), the shape also
    requires the property to be present -- so an omitted value is *not* treated as
    inactive, and the rule still applies.
    """
    if len(gate_iris) == 1:
        inner = BNode()
        ips = BNode()
        g.add((inner, SH.property, ips))
        g.add((ips, SH.path, URIRef(prof_iri)))
        g.add((ips, SH["hasValue"], URIRef(gate_iris[0])))
    else:
        or_list = Collection(g, None)  # type: ignore[arg-type]
        for gi in gate_iris:
            b = BNode()
            bps = BNode()
            g.add((b, SH.property, bps))
            g.add((bps, SH.path, URIRef(prof_iri)))
            g.add((bps, SH["hasValue"], URIRef(gi)))
            or_list.append(b)
        inner = BNode()
        g.add((inner, SH["or"], or_list.uri))
    gate_not = BNode()
    g.add((gate_not, SH["not"], inner))
    if require_present:
        present = BNode()
        g.add((gate_not, SH.property, present))
        g.add((present, SH.path, URIRef(prof_iri)))
        g.add((present, SH["minCount"], Literal(1)))
    return gate_not


def _emit_where_shape(ctx: _EmitCtx, where: tuple[str, ...], start_cls: str | None = None) -> BNode:
    """Build a node shape (BNode) carrying every ``where`` line as a constraint rooted at *start_cls*."""
    shape = BNode()
    for w in where:
        _emit_constraint(ctx, shape, parse_constraint(w), start_cls)
    return shape


def _emit_existential(ctx: _EmitCtx, rule: Conformance) -> BNode | None:
    """Build a node shape requiring *count* linked *exists* instances satisfying *where*."""
    exists_fq = _class_fq(ctx.ns_name, rule.exists)
    exists = _resolve_class_iri(ctx.model, ctx.ns_name, rule.exists)
    # `where` and `linkedBy` are rooted at the existential class.
    linked = _resolve_prop_ctx(ctx.model, ctx.ns_name, rule.linked_by, start_cls=exists_fq)
    if exists is None or linked is None:
        return None
    qvs = _emit_where_shape(ctx, rule.where, start_cls=exists_fq)
    ctx.g.add((qvs, SH["class"], URIRef(exists)))
    inv = BNode()
    ctx.g.add((inv, SH["inversePath"], URIRef(linked)))
    exist_ps = BNode()
    ctx.g.add((exist_ps, SH.path, inv))
    ctx.g.add((exist_ps, SH["qualifiedValueShape"], qvs))
    qmin, qmax = count_bounds(rule.count)
    if qmin is not None:
        ctx.g.add((exist_ps, SH["qualifiedMinCount"], Literal(qmin)))
    if qmax is not None:
        ctx.g.add((exist_ps, SH["qualifiedMaxCount"], Literal(qmax)))
    shape = BNode()
    ctx.g.add((shape, SH.property, exist_ps))
    return shape


def _emit_conformance_rule(ctx: _EmitCtx, gate_ctx: _GateCtx, rule: Conformance, *, is_default: bool = False) -> None:
    """Emit one conformance rule (collection-self, existential, or member-predicate)."""
    gate = _emit_gate_not(ctx.g, gate_ctx.prof_iri, gate_ctx.gate_iris, require_present=is_default)

    # collection-self mode: the collection, when an <applies_to>, must satisfy where.
    if rule.applies_to:
        target = _resolve_class_iri(ctx.model, ctx.ns_name, rule.applies_to)
        if target is None:
            return
        active = _emit_where_shape(ctx, rule.where, start_cls=_class_fq(ctx.ns_name, rule.applies_to))
        target_node: URIRef = URIRef(target)
    else:
        for_each = _resolve_class_iri(ctx.model, ctx.ns_name, rule.for_each)
        # `in:` is a property of the collection class; `where` is rooted at the member class.
        membership = _resolve_prop_ctx(ctx.model, ctx.ns_name, rule.membership, start_cls=gate_ctx.coll_ref)
        if for_each is None or membership is None:
            return
        inner = (
            _emit_existential(ctx, rule) if rule.exists else _emit_where_shape(ctx, rule.where, start_cls=_class_fq(ctx.ns_name, rule.for_each))
        )
        if inner is None:
            return
        # Per member: not a <for_each>  OR  the inner shape holds.
        nf_cls = BNode()
        ctx.g.add((nf_cls, SH["class"], URIRef(for_each)))
        not_for_each = BNode()
        ctx.g.add((not_for_each, SH["not"], nf_cls))
        member_or = Collection(ctx.g, None)  # type: ignore[arg-type]
        member_or.append(not_for_each)
        member_or.append(inner)
        member_ps = BNode()
        ctx.g.add((member_ps, SH.path, URIRef(membership)))
        ctx.g.add((member_ps, SH["or"], member_or.uri))
        active = BNode()
        ctx.g.add((active, SH.property, member_ps))
        target_node = gate_ctx.coll_node

    top = Collection(ctx.g, None)  # type: ignore[arg-type]
    top.append(gate)
    top.append(active)
    ctx.g.add((target_node, SH["or"], top.uri))


def _gen_conformance(model: Model, g: Graph) -> None:
    """Emit SHACL for structured ``## Profile conformance`` blocks (tier 4)."""
    namespaces_with_rules = [ns for ns in model.namespaces if getattr(ns, "conformance_rules", None)]
    if not namespaces_with_rules:
        return
    cfg = model.config.get("conformance", {})
    coll_ref = cfg.get("collection-class", "/Core/ElementCollection")
    prof_ref = cfg.get("profile-property", "/Core/profileConformance")
    profile_map = cfg.get("profile", {}) or {}

    coll_iri = _resolve_class_iri(model, "", coll_ref)
    prof_iri = _resolve_prop_iri(model, "", prof_ref)
    prof_prop = model.properties.get(prof_ref)
    if coll_iri is None or prof_iri is None or prof_prop is None:
        logger.warning("conformance: cannot resolve collection-class %r or profile-property %r", coll_ref, prof_ref)
        return
    rng = prof_prop.metadata.get("range", "")
    gate_vocab = model.vocabularies.get(rng if rng.startswith("/") else f"/{prof_prop.ns.name}/{rng}")
    if gate_vocab is None:
        logger.warning("conformance: profile-property %s has no vocabulary range", prof_ref)
        return

    default_profile = cfg.get("default-profile")
    default_iri = f"{gate_vocab.iri}/{default_profile}" if default_profile else None

    coll_node = URIRef(coll_iri)
    for ns in namespaces_with_rules:
        entries = profile_map.get(ns.name)
        if entries is None:
            logger.warning("conformance: namespace %s has rules but no conformance.profile mapping", ns.name)
            continue
        gate_iris = [f"{gate_vocab.iri}/{e}" for e in ([entries] if isinstance(entries, str) else entries)]
        # When the rule gates on the default profile, an omitted profileConformance still applies.
        is_default = default_iri is not None and default_iri in gate_iris
        ctx = _EmitCtx(model, g, ns.name)
        gate_ctx = _GateCtx(coll_node, coll_ref, gate_iris, prof_iri)
        for rule in ns.conformance_rules:
            _emit_conformance_rule(ctx, gate_ctx, rule, is_default=is_default)


def _gen_properties(model: Model, g: Graph) -> None:
    for fqname, p in model.properties.items():
        if fqname == "/Core/spdxId":
            continue
        node = URIRef(p.iri)
        ns_node = URIRef(p.ns.iri)

        g.add((node, RDFS.isDefinedBy, ns_node))
        g.add((node, RDFS.label, Literal(p.name, lang="en")))

        if p.summary:
            plain_summary = _md_to_text(p.summary)
            g.add((node, RDFS.comment, Literal(plain_summary, lang="en")))
            g.add((node, SKOS.definition, Literal(plain_summary, lang="en")))

        if p.description:
            g.add((node, SKOS.note, Literal(_md_to_text(p.description), lang="en")))

        if p.metadata.get("deprecated") == "true":
            g.add((node, OWL.deprecated, Literal(True)))
            dv = p.metadata.get("deprecatedVersion")
            if dv:
                g.add((node, OWL.versionInfo, Literal(f"Deprecated since version {dv}", lang="en")))
        replaced_by = p.metadata.get("isReplacedBy")
        if replaced_by:
            g.add((node, DCTERMS.isReplacedBy, URIRef(_resolve_ref_iri(replaced_by, p.ns.iri, model.base_uri))))
        example = p.metadata.get("example")
        if example:
            _emit_example(g, node, example)

        match p.metadata["nature"]:
            case PropertyNature.OBJECT_PROPERTY:
                g.add((node, RDF.type, OWL.ObjectProperty))
            case PropertyNature.DATA_PROPERTY:
                g.add((node, RDF.type, OWL.DatatypeProperty))

        rng = p.metadata["range"]
        if ":" in rng:
            t = _xsd_range(rng, p.name)
            if t:
                g.add((node, RDFS.range, t))
        else:
            typename = rng if rng.startswith("/") else f"/{p.ns.name}/{rng}"
            if typename in model.datatypes:
                t = _xsd_range(model.datatypes[typename].metadata["subClassOf"], p.name)
                if t:
                    g.add((node, RDFS.range, t))
            else:
                dt = model.types[typename]
                g.add((node, RDFS.range, URIRef(dt.iri)))


def _gen_vocabularies(model: Model, g: Graph) -> None:
    for v in model.vocabularies.values():
        node = URIRef(v.iri)
        ns_node = URIRef(v.ns.iri)

        g.add((node, RDF.type, OWL.Class))
        g.add((node, RDFS.isDefinedBy, ns_node))
        g.add((node, RDFS.label, Literal(v.name, lang="en")))

        if v.summary:
            plain_summary = _md_to_text(v.summary)
            g.add((node, RDFS.comment, Literal(plain_summary, lang="en")))
            g.add((node, SKOS.definition, Literal(plain_summary, lang="en")))

        if v.metadata.get("deprecated") == "true":
            g.add((node, OWL.deprecated, Literal(True)))
            dv = v.metadata.get("deprecatedVersion")
            if dv:
                g.add((node, OWL.versionInfo, Literal(f"Deprecated since version {dv}", lang="en")))
        replaced_by = v.metadata.get("isReplacedBy")
        if replaced_by:
            g.add((node, DCTERMS.isReplacedBy, URIRef(_resolve_ref_iri(replaced_by, v.ns.iri, model.base_uri))))
        example = v.metadata.get("example")
        if example:
            _emit_example(g, node, example)

        # Enum membership via rdf:type on each entry; closed-world enforcement via SHACL sh:in.
        for e, d in v.entries.items():
            enode = URIRef(v.iri + "/" + e)
            g.add((enode, RDF.type, OWL.NamedIndividual))
            g.add((enode, RDF.type, node))
            g.add((enode, RDFS.isDefinedBy, ns_node))
            g.add((enode, RDFS.label, Literal(e, lang="en")))
            desc = str(d.get("description", "")) if isinstance(d, dict) else str(d)
            if desc:
                g.add((enode, RDFS.comment, Literal(_md_to_text(desc), lang="en")))
                g.add((enode, SKOS.definition, Literal(_md_to_text(desc), lang="en")))
            entry_example = d.get("example") if isinstance(d, dict) else None
            if entry_example:
                _emit_example(g, enode, str(entry_example))


def _gen_individuals(model: Model, g: Graph) -> None:
    uri_base = model.base_uri

    def _ci_ref(s: str) -> URIRef:
        return URIRef(uri_base + "Core/" + s)

    for i in model.individuals.values():
        ns_node = URIRef(i.ns.iri)
        ci_node = URIRef(uri_base + "creationInfo_" + i.name)
        g.add((ci_node, RDF.type, _ci_ref("CreationInfo")))
        g.add((ci_node, RDFS.comment, Literal("This individual element was defined by the spec.", lang="en")))
        g.add((ci_node, _ci_ref("createdBy"), _ci_ref("SpdxOrganization")))

        node = URIRef(i.iri)
        g.add((node, RDF.type, OWL.NamedIndividual))
        g.add((node, RDFS.isDefinedBy, ns_node))
        g.add((node, _ci_ref("creationInfo"), ci_node))

        if i.summary:
            g.add((node, RDFS.comment, Literal(_md_to_text(i.summary), lang="en")))
            g.add((node, SKOS.definition, Literal(_md_to_text(i.summary), lang="en")))

        typ = i.metadata["type"]
        typename = typ if typ.startswith("/") else f"/{i.ns.name}/{typ}"
        dt = model.types[typename]
        g.add((node, RDF.type, URIRef(dt.iri)))

        custom_iri = i.metadata.get("iri")
        if custom_iri and custom_iri != i.iri:
            g.add((node, OWL.sameAs, URIRef(custom_iri)))

        if i.metadata.get("deprecated") == "true":
            g.add((node, OWL.deprecated, Literal(True)))
            dv = i.metadata.get("deprecatedVersion")
            if dv:
                g.add((node, OWL.versionInfo, Literal(f"Deprecated since version {dv}", lang="en")))
        replaced_by = i.metadata.get("isReplacedBy")
        if replaced_by:
            g.add((node, DCTERMS.isReplacedBy, URIRef(_resolve_ref_iri(replaced_by, i.ns.iri, model.base_uri))))
        example = i.metadata.get("example")
        if example:
            _emit_example(g, node, example)
        same_as = i.metadata.get("sameAs")
        if same_as:
            g.add((node, OWL.sameAs, URIRef(same_as)))


# ---------------------------------------------------------------------------
# JSON-LD context generation
# ---------------------------------------------------------------------------


def _jsonld_context(g: Graph, uri_base: str) -> dict[str, Any]:
    uri_base_stripped = uri_base.rstrip("/")

    terms: dict[str, dict[str, Any]] = {}

    # Collect vocabulary classes (those with sh:in enumerations).
    vocab_named_individuals: set[Node] = set()
    vocab_classes: set[Node] = set()
    for lst in g.objects(None, SH["in"]):
        c = Collection(g, lst)
        for e in c:
            vocab_named_individuals.add(e)
            for typ in g.objects(e, RDF.type):
                if typ != OWL.NamedIndividual:
                    vocab_classes.add(typ)

    # Build per-vocabulary-class enum entries and top-level alias keys.
    #
    # Each vocab class gets entries like:
    #   vocab_entries["https://.../SupportType"] = {"noSupport": "https://.../noSupport", ...}
    #   vocab_aliases["https://.../SupportType"] = {"noSupport": "SupportType_noSupport", ...}
    #
    # Top-level alias terms ("SupportType_noSupport": {"@id": ..., "@protected": true}) are
    # emitted once and referenced by name from each property's local @context, avoiding
    # repeated inline expansion for vocab classes shared across multiple properties.
    vocab_entries: dict[str, dict[str, str]] = {}
    vocab_aliases: dict[str, dict[str, str]] = {}
    for v_cls in vocab_classes:
        entries: dict[str, str] = {}
        for ind in vocab_named_individuals:
            if (ind, RDF.type, v_cls) in g:
                entry_name = str(ind).rsplit("/", 1)[-1]
                entries[entry_name] = str(ind)
        v_cls_iri = str(v_cls)
        cls_name = v_cls_iri.rsplit("/", 1)[-1]
        vocab_entries[v_cls_iri] = entries
        vocab_aliases[v_cls_iri] = {name: f"{cls_name}_{name}" for name in entries}

    def _get_subject_term(subject: URIRef) -> dict[str, Any]:
        if (subject, RDF.type, OWL.ObjectProperty) in g:
            for _, _, o in g.triples((subject, RDFS.range, None)):
                o_str = str(o)
                if o in vocab_classes:
                    # Enum range: @type:@vocab with a local @context that maps each entry
                    # name to its top-level alias (defined once, referenced here by name).
                    local_ctx: dict[str, Any] = dict(vocab_aliases.get(o_str, {}))
                    return {
                        "@id": str(subject),
                        "@type": "@vocab",
                        "@context": local_ctx,
                        "@protected": True,
                    }
                if (o, RDF.type, OWL.Class) in g:
                    # Class range: @type:@id so the value expands to a full IRI, not @vocab.
                    return {
                        "@id": str(subject),
                        "@type": "@id",
                        "@protected": True,
                    }
        elif (subject, RDF.type, OWL.DatatypeProperty) in g:
            for _, _, o in g.triples((subject, RDFS.range, None)):
                return {
                    "@id": str(subject),
                    "@type": str(o),
                    "@protected": True,
                }

        # Class, vocabulary class, named individual, or untyped property --
        # protect to prevent redefinition when additional contexts are layered.
        return {"@id": str(subject), "@protected": True}

    # Emit one top-level alias entry per vocab entry (e.g. "SupportType_noSupport").
    # Properties reference these by alias name in their local @context.
    for v_cls_iri, entries in vocab_entries.items():
        aliases = vocab_aliases[v_cls_iri]
        for entry_name, entry_iri in sorted(entries.items()):
            alias_key = aliases[entry_name]
            if alias_key not in terms:
                terms[alias_key] = {"@id": entry_iri, "@protected": True}

    for subject in sorted(g.subjects(unique=True), key=str):
        if not isinstance(subject, URIRef):
            continue

        # Skip named individuals in vocabularies.
        if (subject, RDF.type, OWL.NamedIndividual) in g and subject in vocab_named_individuals:
            continue

        s = str(subject)
        if not s.startswith(uri_base_stripped + "/"):
            continue

        remainder = s[len(uri_base_stripped) + 1 :]
        parts = remainder.split("/", 1)
        if len(parts) != 2:
            continue
        ns, name = parts

        key = name if ns == "Core" else ns.lower() + "_" + name

        if key in terms:
            _existing = terms[key]
            current = _existing["@id"]
            logger.error(
                "Duplicate JSON-LD context key %r: <%s> conflicts with already-mapped <%s>. "
                "Rename one term or move it to a different namespace.",
                key,
                subject,
                current,
            )
            continue

        terms[key] = _get_subject_term(subject)

    # Well-known aliases: protected so additional contexts cannot redefine them.
    terms["spdx"] = {"@id": uri_base, "@prefix": True, "@protected": True}
    terms["spdxId"] = {"@id": "@id", "@protected": True}
    terms["type"] = {"@id": "@type", "@protected": True}

    return {"@context": terms}
