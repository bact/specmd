# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
# pylint: disable=redefined-outer-name  # pytest fixture injection shadows module-level names

"""End-to-end relationship-vocab constraints: Markdown -> SHACL -> pySHACL validation.

Small hand-built positive/negative data graphs, run through pySHACL against the
shared ``model`` fixture's generated SHACL, proving each relationship-vocab
constraint actually fires -- not just that the expected triples appear in the
shape graph (that's what the structural tests in ``test_rdf.py`` cover).

Two vocabulary entries carry the interesting cases:

- ``secretAgentUsedBy`` (``from: SecretAgent``, ``to: [Agent, not Collection]``,
  ``relationshipClass: Relationship`` -- the default): plain endpoint typing.
- ``delegatedTo`` (``from: Agent``, ``to: [Relationship[relationshipType=invokedBy]]``,
  ``relationshipClass: LifecycleScopedRelationship`` -- narrower than the
  default): endpoint typing *and* the Option B ``rdf:type`` requirement (see
  ``_gen_relationship_constraints`` in ``generate/rdf.py``) -- a plain
  ``Relationship`` instance with this ``relationshipType`` must be rejected,
  not silently exempted from the check.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rdflib import Graph, URIRef
from rdflib.namespace import RDF

from specmd.generate.rdf import gen_rdf_ontology
from specmd.parse.model import Model

pyshacl = pytest.importorskip("pyshacl")

FIXTURE = Path(__file__).parent / "fixtures" / "model"
BASE = "https://example.org/rdf/terms/"
CORE = BASE + "Core/"


@pytest.fixture(scope="module")
def shapes() -> Graph:
    return gen_rdf_ontology(Model(FIXTURE))


def c(name: str) -> URIRef:
    return URIRef(CORE + name)


def _conforms(shacl: Graph, data: Graph) -> tuple[bool, str]:
    # No RDFS inference: this fixture marks `Element` abstract, and RDFS closure would
    # materialise `rdf:type Element` for every concrete instance (via subClassOf),
    # tripping the unrelated abstract-instantiation shape. `sh:class` already walks
    # `rdfs:subClassOf` per the SHACL spec, so endpoint-type subsumption (e.g. a
    # SecretAgent satisfying `to: Agent`) still works correctly without it.
    conforms, _, text = pyshacl.validate(data, shacl_graph=shacl, ont_graph=shacl, inference="none", advanced=True)
    return conforms, text


# ---------------------------------------------------------------------------
# secretAgentUsedBy: from SecretAgent, to [Agent, not Collection]
# ---------------------------------------------------------------------------


def _secret_agent_used_by_graph() -> Graph:
    """A conforming ``secretAgentUsedBy`` relationship: SecretAgent -> SecretAgent.

    The ``to`` endpoint is typed ``SecretAgent`` (a concrete subclass of the
    abstract ``Agent``) rather than ``Agent`` directly -- Agent instances are
    rejected outright by the abstract-class shape, independent of this test.
    """
    g = Graph()
    rel = URIRef("urn:rel")
    frm = URIRef("urn:from-agent")
    to = URIRef("urn:to-agent")
    g.add((rel, RDF.type, c("Relationship")))
    g.add((rel, c("relationshipType"), c("RelationshipType/secretAgentUsedBy")))
    g.add((rel, c("from"), frm))
    g.add((rel, c("to"), to))
    g.add((frm, RDF.type, c("SecretAgent")))
    g.add((to, RDF.type, c("SecretAgent")))
    return g


def test_secret_agent_used_by_conforming_passes(shapes: Graph) -> None:
    conforms, text = _conforms(shapes, _secret_agent_used_by_graph())
    assert conforms, text


def test_secret_agent_used_by_wrong_from_type_fails(shapes: Graph) -> None:
    # `from` must be a SecretAgent; retype it as an unrelated concrete class.
    g = _secret_agent_used_by_graph()
    frm = URIRef("urn:from-agent")
    g.remove((frm, RDF.type, None))
    g.add((frm, RDF.type, c("Collection")))
    conforms, text = _conforms(shapes, g)
    assert not conforms
    assert "SecretAgent" in text


def test_secret_agent_used_by_forbidden_collection_to_fails(shapes: Graph) -> None:
    # `to` is typed Agent (via SecretAgent) *and* Collection -- the `not Collection`
    # branch must fire even though the positive Agent requirement is satisfied.
    g = _secret_agent_used_by_graph()
    to = URIRef("urn:to-agent")
    g.add((to, RDF.type, c("Collection")))
    conforms, text = _conforms(shapes, g)
    assert not conforms
    assert "Collection" in text


# ---------------------------------------------------------------------------
# delegatedTo: from Agent, to [Relationship[relationshipType=invokedBy]],
# relationshipClass: LifecycleScopedRelationship (narrower than the default)
# ---------------------------------------------------------------------------


def _delegated_to_graph() -> Graph:
    """A fully conforming ``delegatedTo`` relationship.

    The subject is typed ``LifecycleScopedRelationship`` (required, since that
    differs from the vocabulary's default ``relationshipClass``); its `to` is
    itself a ``Relationship`` whose own ``relationshipType`` is ``invokedBy``,
    satisfying the bracket qualifier.
    """
    g = Graph()
    rel = URIRef("urn:delegation")
    frm = URIRef("urn:delegating-agent")
    to = URIRef("urn:invoked-by-rel")
    g.add((rel, RDF.type, c("LifecycleScopedRelationship")))
    g.add((rel, c("relationshipType"), c("RelationshipType/delegatedTo")))
    g.add((rel, c("from"), frm))
    g.add((rel, c("to"), to))
    g.add((frm, RDF.type, c("SecretAgent")))
    g.add((to, RDF.type, c("Relationship")))
    g.add((to, c("relationshipType"), c("RelationshipType/invokedBy")))
    g.add((to, c("from"), frm))
    return g


def test_delegated_to_conforming_passes(shapes: Graph) -> None:
    conforms, text = _conforms(shapes, _delegated_to_graph())
    assert conforms, text


def test_delegated_to_plain_relationship_type_fails(shapes: Graph) -> None:
    # Option B: a `delegatedTo` relationship that is only a plain `Relationship`
    # (not `LifecycleScopedRelationship`) must be rejected. Under the pre-fix
    # scheme (Option A, shape relocated to the narrower class) this graph would
    # incorrectly conform, since the shape would never even target it.
    g = _delegated_to_graph()
    rel = URIRef("urn:delegation")
    g.remove((rel, RDF.type, c("LifecycleScopedRelationship")))
    g.add((rel, RDF.type, c("Relationship")))
    conforms, text = _conforms(shapes, g)
    assert not conforms
    assert "LifecycleScopedRelationship" in text


def test_delegated_to_wrong_endpoint_relationship_type_fails(shapes: Graph) -> None:
    # `to` must itself carry relationshipType invokedBy; give it a different one.
    g = _delegated_to_graph()
    to = URIRef("urn:invoked-by-rel")
    g.remove((to, c("relationshipType"), None))
    g.add((to, c("relationshipType"), c("RelationshipType/secretAgentUsedBy")))
    conforms, _text = _conforms(shapes, g)
    assert not conforms


def test_delegated_to_missing_from_type_fails(shapes: Graph) -> None:
    # `from` must be an Agent (satisfied here via SecretAgent); drop the type.
    g = _delegated_to_graph()
    frm = URIRef("urn:delegating-agent")
    g.remove((frm, RDF.type, None))
    conforms, _text = _conforms(shapes, g)
    assert not conforms
