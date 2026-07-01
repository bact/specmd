# SPDX-License-Identifier: Apache-2.0
# pylint: disable=redefined-outer-name  # pytest fixture injection shadows module-level names

"""End-to-end Lite profile conformance: Markdown -> SHACL -> pySHACL validation.

The ``model-lite`` fixture authors the full Lite profile using all three
conformance modes (existential, member-predicate, collection-self). This module
generates SHACL from it and runs pySHACL against hand-built data graphs to prove
each Lite requirement is actually enforced.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, XSD

from specmd.generate.rdf import gen_rdf_ontology
from specmd.parse.model import Model

pyshacl = pytest.importorskip("pyshacl")

FIXTURE = Path(__file__).parent / "fixtures" / "model-lite"
BASE = "https://example.org/rdf/terms/"
CORE = BASE + "Core/"
SW = BASE + "Software/"


@pytest.fixture(scope="module")
def lite_shapes() -> Graph:
    return gen_rdf_ontology(Model(FIXTURE))


def c(name: str) -> URIRef:
    return URIRef(CORE + name)


def s(name: str) -> URIRef:
    return URIRef(SW + name)


def _conforms(shacl: Graph, data: Graph) -> tuple[bool, str]:
    conforms, _, text = pyshacl.validate(data, shacl_graph=shacl, ont_graph=shacl, inference="rdfs", advanced=True)
    return conforms, text


def _good_graph() -> Graph:
    """A fully Lite-conforming SpdxDocument with one Package and its licenses."""
    g = Graph()
    doc = URIRef("urn:doc")
    pkg = URIRef("urn:pkg")
    lic = URIRef("urn:lic")
    agent = URIRef("urn:agent")
    rc = URIRef("urn:rel-concluded")
    rd = URIRef("urn:rel-declared")

    # Collection conforming to Lite, with element + rootElement (collection-self rule).
    g.add((doc, RDF.type, c("SpdxDocument")))
    g.add((doc, c("profileConformance"), c("ProfileIdentifierType/lite")))
    g.add((doc, c("element"), pkg))
    g.add((doc, c("rootElement"), pkg))

    # Package member with all mandatory properties (member-predicate rule).
    g.add((pkg, RDF.type, s("Package")))
    g.add((pkg, s("copyrightText"), Literal("(c) ACME")))
    g.add((pkg, s("packageVersion"), Literal("1.0.0")))
    g.add((pkg, c("suppliedBy"), agent))
    g.add((pkg, s("downloadLocation"), Literal("https://example.org/pkg.tgz", datatype=XSD.anyURI)))

    g.add((agent, RDF.type, c("Agent")))
    g.add((agent, c("name"), Literal("ACME Corp")))
    g.add((lic, RDF.type, c("AnyLicenseInfo")))

    # Exactly one concluded and one declared license relationship (existential rule).
    for rel, kind in ((rc, "hasConcludedLicense"), (rd, "hasDeclaredLicense")):
        g.add((rel, RDF.type, c("Relationship")))
        g.add((rel, c("from"), pkg))
        g.add((rel, c("relationshipType"), c(f"RelationshipType/{kind}")))
        g.add((rel, c("to"), lic))
    return g


def test_fully_conforming_passes(lite_shapes: Graph) -> None:
    conforms, text = _conforms(lite_shapes, _good_graph())
    assert conforms, text


def test_missing_copyright_text_fails(lite_shapes: Graph) -> None:
    g = _good_graph()
    g.remove((URIRef("urn:pkg"), s("copyrightText"), None))
    conforms, text = _conforms(lite_shapes, g)
    assert not conforms
    assert "copyrightText" in text


def test_missing_download_and_purl_fails(lite_shapes: Graph) -> None:
    # "at least one of downloadLocation or packageUrl" -> if downloadLocation max 0 then packageUrl min 1.
    g = _good_graph()
    g.remove((URIRef("urn:pkg"), s("downloadLocation"), None))
    conforms, text = _conforms(lite_shapes, g)
    assert not conforms
    assert "packageUrl" in text


def test_packageurl_satisfies_disjunction(lite_shapes: Graph) -> None:
    # Dropping downloadLocation but supplying packageUrl must still conform.
    g = _good_graph()
    g.remove((URIRef("urn:pkg"), s("downloadLocation"), None))
    g.add((URIRef("urn:pkg"), s("packageUrl"), Literal("pkg:generic/acme@1.0.0", datatype=XSD.anyURI)))
    conforms, text = _conforms(lite_shapes, g)
    assert conforms, text


def test_missing_root_element_fails(lite_shapes: Graph) -> None:
    # collection-self rule on SpdxDocument requires rootElement min 1.
    g = _good_graph()
    g.remove((URIRef("urn:doc"), c("rootElement"), None))
    conforms, text = _conforms(lite_shapes, g)
    assert not conforms
    assert "rootElement" in text


def test_missing_declared_license_fails(lite_shapes: Graph) -> None:
    # existential rule: exactly one hasDeclaredLicense relationship per Package.
    g = _good_graph()
    g.remove((URIRef("urn:rel-declared"), None, None))
    conforms, _ = _conforms(lite_shapes, g)
    assert not conforms


def test_agent_member_without_name_fails(lite_shapes: Graph) -> None:
    # An Agent that is itself a collection member must have a name (member-predicate).
    g = _good_graph()
    nameless = URIRef("urn:agent2")
    g.add((nameless, RDF.type, c("Agent")))
    g.add((URIRef("urn:doc"), c("element"), nameless))
    conforms, text = _conforms(lite_shapes, g)
    assert not conforms
    assert "name" in text


def test_non_lite_collection_is_unconstrained(lite_shapes: Graph) -> None:
    # Without lite conformance, none of the Lite rules apply (no default-core rules here).
    g = Graph()
    doc = URIRef("urn:doc")
    g.add((doc, RDF.type, c("SpdxDocument")))
    pkg = URIRef("urn:pkg")
    g.add((doc, c("element"), pkg))
    g.add((pkg, RDF.type, s("Package")))  # bare Package, no mandatory props
    conforms, text = _conforms(lite_shapes, g)
    assert conforms, text


def test_autolinked_namespace_id_resolves_clean() -> None:
    # Lite.md was formatted by markdownlint, so its `id:` is an MD034 autolink
    # (`<https://…>`); the parsed namespace IRI must not keep the angle brackets.
    model = Model(FIXTURE)
    lite = next(ns for ns in model.namespaces if ns.name == "Lite")
    assert lite.iri == "https://example.org/rdf/terms/Lite/"


class TestContextualTypeWalk:
    """``_walk_path`` resolves bare hops as properties of the class reached so far."""

    def test_bare_hop_in_subject_namespace(self) -> None:
        from specmd.generate.rdf import _walk_path

        model = Model(FIXTURE)
        iris, last = _walk_path(model, "Lite", ("copyrightText",), start_cls="/Software/Package")
        assert iris == [SW + "copyrightText"]
        assert last == "/Software/copyrightText"

    def test_bare_hop_resolves_cross_namespace(self) -> None:
        # `suppliedBy` is declared on SoftwareArtifact as the Core property -- the
        # walk must reach it even though the subject class lives in Software.
        from specmd.generate.rdf import _walk_path

        model = Model(FIXTURE)
        iris, last = _walk_path(model, "Lite", ("suppliedBy",), start_cls="/Software/Package")
        assert iris == [CORE + "suppliedBy"]
        assert last == "/Core/suppliedBy"

    def test_unknown_hop_without_context_fails(self) -> None:
        # No class context and not a property of the file namespace -> unresolved.
        from specmd.generate.rdf import _walk_path

        model = Model(FIXTURE)
        iris, last = _walk_path(model, "Lite", ("copyrightText",))
        assert iris is None
        assert last is None
