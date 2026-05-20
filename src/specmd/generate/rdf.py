# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Generate an OWL ontology with SHACL shapes and JSON-LD context from the parsed model."""

from __future__ import annotations

import logging
import re
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

import rfc8785
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SH, SKOS, VANN
from rdflib.tools.rdf2dot import rdf2dot

from specmd.parse.model import PropertyNature

if TYPE_CHECKING:
    from rdflib.term import Node

    from specmd.parse.model import Class, Model

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Markdown → plain text helper
# ---------------------------------------------------------------------------

_RE_MD_LINK_EXT = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
_RE_MD_LINK_INT = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_RE_MD_CODE_BLOCK = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_RE_MD_INLINE_CODE = re.compile(r"`([^`]+)`")


def _md_to_text(md: str | None) -> str:
    """Strip Markdown markup to produce readable plain text for RDF literals."""
    if not md:
        return ""
    text = _RE_MD_CODE_BLOCK.sub(r"\1", md)
    text = _RE_MD_LINK_EXT.sub(r"\1 <\2>", text)
    text = _RE_MD_LINK_INT.sub(r"\1", text)
    text = _RE_MD_INLINE_CODE.sub(r"\1", text)
    return text.strip()


# ---------------------------------------------------------------------------
# XSD range resolution
# ---------------------------------------------------------------------------


def _resolve_ref_iri(ref: str, ns_iri: str, base_uri: str) -> str:
    """Resolve a local term reference to a full IRI.

    Supports absolute IRIs (``http://…``), fully-qualified slash paths
    (``/NS/Term``), and bare local names (resolved within *ns_iri*).
    """
    if ref.startswith(("http://", "https://")):
        return ref
    if ref.startswith("/"):
        parts = ref.lstrip("/").split("/", 1)
        if len(parts) == 2:
            return f"{base_uri}{parts[0]}/{parts[1]}"
    return f"{ns_iri}/{ref}"


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
    "license": "https://spdx.org/licenses/Community-Spec-1.0.html",
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
    ont = _ont_cfg(model)

    g.bind(ont["preferred-namespace-prefix"], Namespace(uri_base))

    # Per-namespace prefix bindings with VANN annotations.
    for ns in model.namespaces:
        prefix = ns.metadata.get("preferredNamespacePrefix") or "spdx-" + ns.name.lower()
        ns_iri = Namespace(ns.iri)
        g.bind(prefix, ns_iri)
        ns_node = URIRef(ns.iri)
        g.add((ns_node, VANN.preferredNamespacePrefix, Literal(prefix)))
        g.add((ns_node, VANN.preferredNamespaceUri, Literal(str(ns_iri))))
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
    # versionIRI is a distinct versioned URI (<base-uri><version>/), not the ontology IRI.
    version_str: str | None = None
    for ns in model.namespaces:
        v = ns.metadata.get("version") or ns.metadata.get("Version")
        if v:
            version_str = v
            break
    if version_str:
        g.add((ont_node, OWL.versionInfo, Literal(version_str)))
        versioned_iri = URIRef(uri_base.rstrip("/") + "/" + version_str + "/")
        g.add((ont_node, OWL.versionIRI, versioned_iri))

    # vann:preferredNamespacePrefix / vann:preferredNamespaceUri (W3C BCP for vocab publishing).
    g.add((ont_node, VANN.preferredNamespacePrefix, Literal(ont["preferred-namespace-prefix"])))
    g.add((ont_node, VANN.preferredNamespaceUri, Literal(uri_base)))

    g.add((ont_node, RDFS.label, Literal(ont["label"], lang="en")))
    g.add((ont_node, DCTERMS.abstract, Literal(ont["abstract"], lang="en")))
    g.add((ont_node, DCTERMS.creator, Literal(ont["creator"], lang="en")))
    g.add((ont_node, DCTERMS.license, URIRef(ont["license"])))
    g.add((ont_node, DCTERMS.references, URIRef(ont["references"])))
    g.add((ont_node, DCTERMS.title, Literal(ont["title"], lang="en")))
    g.add((ont_node, OMG_ANN.copyright, Literal(ont["copyright"], lang="en")))

    _gen_classes(model, g)
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


def _gen_classes(model: Model, g: Graph) -> None:
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
