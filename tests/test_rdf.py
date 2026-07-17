# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for RDF generation."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SH, SKOS, VANN

from specmd.generate.rdf import _EmitCtx, _emit_qualifier_shapes, _endpoint_class_iris, gen_rdf, gen_rdf_ontology
from specmd.parse.model import Model

BASE = "https://example.org/rdf/terms/"
CORE = BASE + "Core/"


class TestRDFGraph:
    def test_graph_non_empty(self, rdf_graph: Graph) -> None:
        assert len(rdf_graph) > 0

    def test_ontology_node(self, rdf_graph: Graph) -> None:
        ont = URIRef(BASE)
        assert (ont, RDF.type, OWL.Ontology) in rdf_graph

    def test_all_classes_present(self, rdf_graph: Graph, model: Model) -> None:
        for c in model.classes.values():
            node = URIRef(c.iri)
            assert (node, RDF.type, OWL.Class) in rdf_graph, f"Missing owl:Class for {c.iri}"

    def test_vocabularies_present(self, rdf_graph: Graph, model: Model) -> None:
        for v in model.vocabularies.values():
            node = URIRef(v.iri)
            assert (node, RDF.type, OWL.Class) in rdf_graph

    def test_properties_present(self, rdf_graph: Graph, model: Model) -> None:
        for fq, p in model.properties.items():
            if fq == "/Core/spdxId":
                continue
            node = URIRef(p.iri)
            types = set(rdf_graph.objects(node, RDF.type))
            assert OWL.ObjectProperty in types or OWL.DatatypeProperty in types, f"{p.iri} missing property type"


class TestRDFLabels:
    def test_rdfs_label_on_classes(self, rdf_graph: Graph, model: Model) -> None:
        for c in model.classes.values():
            node = URIRef(c.iri)
            labels = list(rdf_graph.objects(node, RDFS.label))
            assert labels, f"No rdfs:label on {c.iri}"

    def test_rdfs_label_on_vocabularies(self, rdf_graph: Graph, model: Model) -> None:
        for v in model.vocabularies.values():
            node = URIRef(v.iri)
            labels = list(rdf_graph.objects(node, RDFS.label))
            assert labels, f"No rdfs:label on {v.iri}"

    def test_skos_definition_on_classes(self, rdf_graph: Graph, model: Model) -> None:
        for c in model.classes.values():
            if not c.summary:
                continue
            node = URIRef(c.iri)
            defs = list(rdf_graph.objects(node, SKOS.definition))
            assert defs, f"No skos:definition on {c.iri}"

    def test_skos_note_on_class_with_description(self, rdf_graph: Graph, model: Model) -> None:
        for c in model.classes.values():
            if not c.description:
                continue
            node = URIRef(c.iri)
            notes = list(rdf_graph.objects(node, SKOS.note))
            assert notes, f"No skos:note on {c.iri}"


class TestRDFIsDefinedBy:
    def test_classes_have_is_defined_by(self, rdf_graph: Graph, model: Model) -> None:
        for c in model.classes.values():
            node = URIRef(c.iri)
            defined_by = list(rdf_graph.objects(node, RDFS.isDefinedBy))
            assert defined_by, f"No rdfs:isDefinedBy on {c.iri}"
            assert URIRef(c.ns.iri) in defined_by

    def test_properties_have_is_defined_by(self, rdf_graph: Graph, model: Model) -> None:
        for fq, p in model.properties.items():
            if fq == "/Core/spdxId":
                continue
            node = URIRef(p.iri)
            defined_by = list(rdf_graph.objects(node, RDFS.isDefinedBy))
            assert defined_by, f"No rdfs:isDefinedBy on {p.iri}"

    def test_vocabularies_have_is_defined_by(self, rdf_graph: Graph, model: Model) -> None:
        for v in model.vocabularies.values():
            node = URIRef(v.iri)
            defined_by = list(rdf_graph.objects(node, RDFS.isDefinedBy))
            assert defined_by, f"No rdfs:isDefinedBy on {v.iri}"


class TestRDFVocabularies:
    def test_no_owl_one_of_on_vocabulary(self, rdf_graph: Graph, model: Model) -> None:
        """owl:equivalentClass+owl:oneOf removed: not in OWL 2 EL/QL/RL profiles.
        Enum semantics are handled by SHACL sh:in; membership via rdf:type."""
        for v in model.vocabularies.values():
            node = URIRef(v.iri)
            equiv_classes = list(rdf_graph.objects(node, OWL.equivalentClass))
            assert not equiv_classes, f"Unexpected owl:equivalentClass on vocabulary {v.iri}"

    def test_vocabulary_entries_are_named_individuals(self, rdf_graph: Graph, model: Model) -> None:
        for v in model.vocabularies.values():
            for entry in v.entries:
                enode = URIRef(v.iri + "/" + entry)
                assert (enode, RDF.type, OWL.NamedIndividual) in rdf_graph

    def test_no_sh_node_kind_iri_with_sh_in(self, rdf_graph: Graph) -> None:
        """sh:nodeKind sh:IRI must not appear alongside sh:in."""
        for bnode in rdf_graph.subjects(SH["in"], None):
            assert (bnode, SH.nodeKind, SH.IRI) not in rdf_graph, "Superfluous sh:nodeKind sh:IRI alongside sh:in"

    def test_no_sh_class_with_sh_in(self, rdf_graph: Graph) -> None:
        """sh:class is redundant alongside sh:in and must not be emitted."""
        for bnode in rdf_graph.subjects(SH["in"], None):
            assert (bnode, SH["class"], None) not in rdf_graph, "Redundant sh:class alongside sh:in"


class TestRDFSHACL:
    def test_abstract_class_has_not_constraint(self, rdf_graph: Graph, model: Model) -> None:
        """Abstract classes get sh:not sh:hasValue for SHACL validators."""
        for c in model.classes.values():
            if c.metadata.get("abstract") != "true":
                continue
            node = URIRef(c.iri)
            sh_props = list(rdf_graph.objects(node, SH.property))
            found_not = any((sp, SH["not"], None) in rdf_graph for sp in sh_props)
            assert found_not, f"Abstract class {c.iri} missing sh:not constraint"

    def test_abstract_class_has_all_disjoint_classes(self, rdf_graph: Graph, model: Model) -> None:
        """Abstract classes with subclasses use owl:AllDisjointClasses (OWL 2 EL-compatible).
        owl:disjointUnionOf is not in OWL 2 EL/QL/RL profiles."""
        from rdflib.collection import Collection

        for c in model.classes.values():
            if c.metadata.get("abstract") != "true" or not c.direct_subclasses:
                continue
            # Expect a blank node typed owl:AllDisjointClasses whose owl:members
            # contains all direct subclasses.
            found = False
            for adc in rdf_graph.subjects(RDF.type, OWL.AllDisjointClasses):
                members_list = rdf_graph.value(adc, OWL.members)
                if members_list:
                    members = list(Collection(rdf_graph, members_list))
                    sub_iris = {URIRef(model.classes[fq].iri) for fq in c.direct_subclasses}
                    if sub_iris == set(members):
                        found = True
                        break
            assert found, f"Abstract class {c.iri} missing owl:AllDisjointClasses for {c.direct_subclasses}"

    def test_no_sh_node_kind_literal_with_sh_datatype(self, rdf_graph: Graph) -> None:
        """sh:nodeKind sh:Literal must not appear alongside sh:datatype (issue #1152)."""
        for bnode in rdf_graph.subjects(SH.datatype, None):
            assert (bnode, SH.nodeKind, SH.Literal) not in rdf_graph, "Superfluous sh:nodeKind sh:Literal alongside sh:datatype"

    def test_all_classes_are_node_shapes(self, rdf_graph: Graph, model: Model) -> None:
        """All classes are sh:NodeShape so sh:nodeKind and sh:property constraints are seen."""
        for c in model.classes.values():
            node = URIRef(c.iri)
            assert (node, RDF.type, SH.NodeShape) in rdf_graph

    def test_element_class_has_iri_node_kind(self, rdf_graph: Graph) -> None:
        # Element has spdxId → sh:IRI.
        element = URIRef(CORE + "Element")
        assert (element, SH.nodeKind, SH.IRI) in rdf_graph

    def test_agent_class_has_iri_node_kind_inherited(self, rdf_graph: Graph) -> None:
        # Agent inherits spdxId from Element → sh:IRI.
        agent = URIRef(CORE + "Agent")
        assert (agent, SH.nodeKind, SH.IRI) in rdf_graph


class TestJSONLDContext:
    @staticmethod
    @pytest.fixture(scope="class")
    def ctx(rdf_graph: Graph, model: Model) -> dict:
        from specmd.generate.rdf import _jsonld_context

        return _jsonld_context(rdf_graph, model.base_uri)

    def test_context_has_spdx_key(self, ctx: dict) -> None:
        assert "spdx" in ctx["@context"]
        spdx = ctx["@context"]["spdx"]
        assert isinstance(spdx, dict)
        assert spdx["@id"] == BASE
        assert spdx.get("@protected") is True

    def test_spdx_id_maps_to_at_id(self, ctx: dict) -> None:
        entry = ctx["@context"]["spdxId"]
        assert isinstance(entry, dict)
        assert entry["@id"] == "@id"
        assert entry.get("@protected") is True

    def test_type_maps_to_at_type(self, ctx: dict) -> None:
        entry = ctx["@context"]["type"]
        assert isinstance(entry, dict)
        assert entry["@id"] == "@type"
        assert entry.get("@protected") is True

    def test_data_property_has_at_type(self, ctx: dict) -> None:
        # name is DataProperty → should have @type pointing to xsd:string.
        name_entry = ctx["@context"].get("name")
        assert name_entry is not None
        assert "@type" in name_entry

    def test_class_object_property_uses_at_id_not_at_vocab(self, ctx: dict) -> None:
        """Object properties whose range is a class use @type: @id, not @vocab (PR #205)."""
        # No class object property in fixture since SecretAgent→Agent uses SupportType vocab.
        # Test indirectly: confirm no entry with @type: @vocab and missing @context.
        for key, val in ctx["@context"].items():
            if isinstance(val, dict) and val.get("@type") == "@vocab":
                # Any @vocab entry must have a @context (explicit enum mapping).
                assert "@context" in val, f"'{key}' uses @type:@vocab but has no @context (should enumerate enum values)"

    def test_vocab_property_has_explicit_enum_context(self, ctx: dict) -> None:
        # supportLevel range is SupportType (vocabulary) → @type: @vocab + @context with entries.
        support_entry = ctx["@context"].get("supportLevel")
        assert support_entry is not None
        assert support_entry.get("@type") == "@vocab"
        local_ctx = support_entry.get("@context", {})
        # Each SupportType entry should appear in the local context.
        assert "developerSupport" in local_ctx
        assert "noSupport" in local_ctx


class TestRDFPrefixes:
    def test_ontology_prefix_bound(self, rdf_graph: Graph) -> None:
        # fixture specmd.yml sets preferred-namespace-prefix: core
        prefixes = dict(rdf_graph.namespaces())
        assert "core" in prefixes

    def test_namespace_prefix_bound(self, rdf_graph: Graph) -> None:
        prefixes = dict(rdf_graph.namespaces())
        assert "spdx-core" in prefixes

    def test_vann_prefix_on_ontology(self, rdf_graph: Graph) -> None:
        ont = URIRef(BASE)
        assert (ont, VANN.preferredNamespacePrefix, None) in rdf_graph
        assert (ont, VANN.preferredNamespaceUri, None) in rdf_graph

    def test_vann_prefix_on_namespace(self, rdf_graph: Graph) -> None:
        ns = URIRef(CORE)
        assert (ns, VANN.preferredNamespacePrefix, None) in rdf_graph


class TestOntologyConfig:
    """Ontology metadata is driven by specmd.yml ontology: block."""

    def _make_model(self, tmp_path, extra_yaml: str = "") -> Model:
        import shutil

        from tests.conftest import FIXTURE_MODEL

        shutil.copytree(FIXTURE_MODEL, tmp_path / "model")
        cfg_text = "namespace-order:\n  - Core\n" + extra_yaml
        (tmp_path / "model" / "specmd.yml").write_text(cfg_text)
        return Model(tmp_path / "model")

    def test_default_ontology_label(self, tmp_path) -> None:
        m = self._make_model(tmp_path)
        g = gen_rdf_ontology(m)
        ont = URIRef(BASE)
        labels = [str(o) for _, _, o in g.triples((ont, RDFS.label, None))]
        assert any("SPDX" in lbl for lbl in labels)

    def test_custom_ontology_label(self, tmp_path) -> None:
        m = self._make_model(tmp_path, "ontology:\n  label: My Custom Ontology\n")
        g = gen_rdf_ontology(m)
        ont = URIRef(BASE)
        labels = [str(o) for _, _, o in g.triples((ont, RDFS.label, None))]
        assert "My Custom Ontology" in labels

    def test_custom_preferred_namespace_prefix(self, tmp_path) -> None:
        m = self._make_model(tmp_path, "ontology:\n  preferred-namespace-prefix: myns\n")
        g = gen_rdf_ontology(m)
        prefixes = dict(g.namespaces())
        assert "myns" in prefixes
        ont = URIRef(BASE)
        pnp = [str(o) for _, _, o in g.triples((ont, VANN.preferredNamespacePrefix, None))]
        assert "myns" in pnp

    def test_custom_rdf_filename(self, tmp_path) -> None:
        m = self._make_model(tmp_path / "m", "rdf:\n  filename: my-model\n  context-filename: my-context\n")
        outpath = tmp_path / "out"
        outpath.mkdir()

        cfg = SimpleNamespace(all_as_dict={})
        gen_rdf(m, outpath, cfg)
        assert (outpath / "my-model.ttl").exists()
        assert (outpath / "my-context.jsonld").exists()
        assert not (outpath / "spdx-model.ttl").exists()


class TestRDFSerialization:
    def test_turtle_serialization(self, rdf_graph: Graph, tmp_path) -> None:
        out = tmp_path / "test.ttl"
        rdf_graph.serialize(out, format="ttl", encoding="utf-8")
        content = out.read_text()
        assert "spdx-core" in content or "example.org" in content

    def test_jsonld_serialization(self, rdf_graph: Graph, tmp_path) -> None:
        out = tmp_path / "test.jsonld"
        rdf_graph.serialize(out, format="json-ld", encoding="utf-8")
        data = json.loads(out.read_text())
        assert "@graph" in data or isinstance(data, list)


class TestNegatedPathType:
    """Class-level ``<prop> not type <Class>`` -> ``sh:not [ sh:class ... ]`` on a property shape."""

    def test_not_type_emits_sh_not_class(self, rdf_graph: Graph) -> None:
        coll = URIRef(CORE + "Collection")
        agent = URIRef(CORE + "Agent")
        forbidden_paths: set[URIRef] = set()
        for pshape in rdf_graph.objects(coll, SH.property):
            for not_node in rdf_graph.objects(pshape, SH["not"]):
                if (not_node, SH["class"], agent) in rdf_graph:
                    forbidden_paths |= set(rdf_graph.objects(pshape, SH.path))  # type: ignore[arg-type]
        assert URIRef(CORE + "element") in forbidden_paths
        assert URIRef(CORE + "rootElement") in forbidden_paths


class TestConditionalValuePresence:
    """``if to has NoneElement then to max 1`` -> ``sh:or([sh:not[hasValue]], [maxCount 1])``."""

    def test_presence_conditional(self, rdf_graph: Graph) -> None:
        from rdflib.collection import Collection as RDFList

        rel = URIRef(CORE + "Relationship")
        none = URIRef(CORE + "NoneElement")
        to = URIRef(CORE + "to")
        found_ante = found_cons = False
        for or_list in rdf_graph.objects(rel, SH["or"]):
            for b in RDFList(rdf_graph, or_list):
                for inner in rdf_graph.objects(b, SH["not"]):
                    for ps in rdf_graph.objects(inner, SH.property):
                        if to in set(rdf_graph.objects(ps, SH.path)) and (ps, SH["hasValue"], none) in rdf_graph:
                            found_ante = True
                for ps in rdf_graph.objects(b, SH.property):
                    if to in set(rdf_graph.objects(ps, SH.path)) and [int(str(m)) for m in rdf_graph.objects(ps, SH.maxCount)] == [1]:
                        found_cons = True
        assert found_ante, "missing sh:not[to hasValue NoneElement]"
        assert found_cons, "missing to maxCount 1 consequent"


class TestConditionalCardinality:
    """Class-level ``if X min m then Y min n`` -> ``sh:or``."""

    def test_cond_card_emits_sh_or(self, rdf_graph: Graph) -> None:
        from rdflib.collection import Collection as RDFList

        def _min1(ps: Any, prop: str) -> bool:
            return URIRef(CORE + prop) in set(rdf_graph.objects(ps, SH.path)) and [int(str(m)) for m in rdf_graph.objects(ps, SH.minCount)] == [
                1
            ]

        coll = URIRef(CORE + "Collection")
        found_ante = found_cons = False
        for or_list in rdf_graph.objects(coll, SH["or"]):
            for b in RDFList(rdf_graph, or_list):
                # antecedent: sh:not [ element minCount 1 ]
                for inner in rdf_graph.objects(b, SH["not"]):
                    if any(_min1(ps, "element") for ps in rdf_graph.objects(inner, SH.property)):
                        found_ante = True
                # consequent: rootElement minCount 1
                if any(_min1(ps, "rootElement") for ps in rdf_graph.objects(b, SH.property)):
                    found_cons = True
        assert found_ante, "missing antecedent branch sh:not[element minCount 1]"
        assert found_cons, "missing consequent branch rootElement minCount 1"


class TestPathTypeConstraint:
    """Class-level ``<prop>/<prop> type <Class>...`` -> sequence path + ``sh:or sh:class``."""

    def test_sequence_path_and_class_or(self, rdf_graph: Graph) -> None:
        from rdflib.collection import Collection as RDFList

        coll = URIRef(CORE + "Collection")
        found = None
        for ps in rdf_graph.objects(coll, SH.property):
            for path in rdf_graph.objects(ps, SH.path):
                # sequence path is an RDF list (its head has rdf:first)
                if (path, RDF.first, None) in rdf_graph:
                    seq = [str(x) for x in RDFList(rdf_graph, path)]
                    if seq == [CORE + "customIdToLicense", CORE + "elementValue"]:
                        found = ps
        assert found is not None, "no sequence path customIdToLicense/elementValue"

        allowed = set()
        for or_list in rdf_graph.objects(found, SH["or"]):
            for branch in RDFList(rdf_graph, or_list):
                allowed |= set(rdf_graph.objects(branch, SH["class"]))
        assert URIRef(CORE + "SecretAgent") in allowed
        assert URIRef(CORE + "ElementMap") in allowed


class TestConformanceShape:
    """Structured ``## Profile conformance`` -> inverse-path + qualified value shape on ElementCollection."""

    def test_qualified_existential(self, rdf_graph: Graph) -> None:
        rel = URIRef(CORE + "Relationship")
        from_p = URIRef(CORE + "from")
        found = False
        for ps, qvs in rdf_graph.subject_objects(SH["qualifiedValueShape"]):
            paths = list(rdf_graph.objects(ps, SH.path))
            inverse = bool(paths) and (paths[0], SH["inversePath"], from_p) in rdf_graph
            is_rel = (qvs, SH["class"], rel) in rdf_graph
            qmin = [int(str(m)) for m in rdf_graph.objects(ps, SH["qualifiedMinCount"])]
            qmax = [int(str(m)) for m in rdf_graph.objects(ps, SH["qualifiedMaxCount"])]
            if inverse and is_rel and qmin == [1] and qmax == [1]:
                found = True
        assert found, "no inverse-from qualifiedValueShape(Relationship) with exactly-one count"

    def test_default_profile_gate_requires_presence(self, rdf_graph: Graph) -> None:
        # conformance.default-profile=core -> the gate also requires profileConformance present,
        # so an omitted value (defaulting to core) still activates the rule.
        pc = URIRef(CORE + "profileConformance")
        found = any([int(str(m)) for m in rdf_graph.objects(ps, SH.minCount)] == [1] for ps in rdf_graph.subjects(SH.path, pc))
        assert found, "default-profile gate missing sh:minCount 1 on profileConformance"

    def test_member_predicate_rule(self, rdf_graph: Graph) -> None:
        # `forEach SoftwareArtifact in element where name min 1` (no `exists`) ->
        # per-member sh:or([not SoftwareArtifact], [sh:property name minCount 1]).
        from rdflib.collection import Collection as RDFList

        sa = URIRef(CORE + "SoftwareArtifact")
        element = URIRef(CORE + "element")
        name = URIRef(CORE + "name")
        found = False
        for member_ps in rdf_graph.subjects(SH.path, element):
            for or_list in rdf_graph.objects(member_ps, SH["or"]):
                branches = list(RDFList(rdf_graph, or_list))
                negates_sa = any((cls, SH["class"], sa) in rdf_graph for b in branches for cls in rdf_graph.objects(b, SH["not"]))
                requires_name = any(
                    name in set(rdf_graph.objects(ps, SH.path)) and [int(str(c)) for c in rdf_graph.objects(ps, SH.minCount)] == [1]
                    for b in branches
                    for ps in rdf_graph.objects(b, SH.property)
                )
                if negates_sa and requires_name:
                    found = True
        assert found, "no member-predicate rule: SoftwareArtifact member requires name minCount 1"

    def test_collection_self_rule(self, rdf_graph: Graph) -> None:
        # `appliesTo ElementCollection where element min 1; rootElement min 1` ->
        # an sh:or branch on ElementCollection requiring both directly (no membership wrapper).
        from rdflib.collection import Collection as RDFList

        ec = URIRef(CORE + "ElementCollection")
        element = URIRef(CORE + "element")
        root = URIRef(CORE + "rootElement")
        found = False
        for or_list in rdf_graph.objects(ec, SH["or"]):
            for branch in RDFList(rdf_graph, or_list):
                mins = {
                    path: [int(str(c)) for c in rdf_graph.objects(ps, SH.minCount)]
                    for ps in rdf_graph.objects(branch, SH.property)
                    for path in rdf_graph.objects(ps, SH.path)
                }
                if mins.get(element) == [1] and mins.get(root) == [1]:
                    found = True
        assert found, "no collection-self rule requiring element and rootElement minCount 1"


class TestSelectorPattern:
    """``identifier matches externalIdentifierType`` -> per-entry guarded ``sh:pattern``."""

    def test_pattern_per_entry(self, rdf_graph: Graph) -> None:
        from rdflib.collection import Collection as RDFList

        ei = URIRef(CORE + "ExternalIdentifier")
        cve = URIRef(CORE + "ExternalIdentifierType/cve")
        identifier = URIRef(CORE + "identifier")
        found = False
        for or_list in rdf_graph.objects(ei, SH["or"]):
            branches = list(RDFList(rdf_graph, or_list))
            keys_off_cve = any(
                (ps, SH["hasValue"], cve) in rdf_graph
                for b in branches
                for n in rdf_graph.objects(b, SH["not"])
                for ps in rdf_graph.objects(n, SH.property)
            )
            has_identifier_pattern = any(
                identifier in set(rdf_graph.objects(ps, SH.path)) and list(rdf_graph.objects(ps, SH["pattern"]))
                for b in branches
                for ps in rdf_graph.objects(b, SH.property)
            )
            if keys_off_cve and has_identifier_pattern:
                found = True
        assert found, "no per-entry sh:pattern guarded by externalIdentifierType = cve"


class TestPatternConstraint:
    """``<path> matches `regex` flags i`` -> sequence path + ``sh:pattern`` + ``sh:flags``."""

    def test_pattern_with_flags_on_path(self, rdf_graph: Graph) -> None:
        from rdflib.collection import Collection as RDFList

        coll = URIRef(CORE + "Collection")
        found = None
        for ps in rdf_graph.objects(coll, SH.property):
            for path in rdf_graph.objects(ps, SH.path):
                if (path, RDF.first, None) in rdf_graph:
                    seq = [str(x) for x in RDFList(rdf_graph, path)]
                    if seq == [CORE + "customIdToLicense", CORE + "key"]:
                        found = ps
        assert found is not None, "no sequence path customIdToLicense -> key"
        patterns = {str(p) for p in rdf_graph.objects(found, SH["pattern"])}
        flags = {str(f) for f in rdf_graph.objects(found, SH["flags"])}
        assert patterns == {"^(LicenseRef-|AdditionRef-)"}
        assert flags == {"i"}

    def test_duplicate_constraint_emitted_once(self, rdf_graph: Graph) -> None:
        # Collection restates the property's own `customIdToLicense -> key` rule in its
        # `## Constraints` (explicit first hop). AST-level dedup must keep a single shape.
        from rdflib.collection import Collection as RDFList

        coll = URIRef(CORE + "Collection")
        matches = 0
        for ps in rdf_graph.objects(coll, SH.property):
            for path in rdf_graph.objects(ps, SH.path):
                if (path, RDF.first, None) in rdf_graph:
                    seq = [str(x) for x in RDFList(rdf_graph, path)]
                    if seq == [CORE + "customIdToLicense", CORE + "key"] and list(rdf_graph.objects(ps, SH["pattern"])):
                        matches += 1
        assert matches == 1, f"expected one customIdToLicense -> key pattern shape, got {matches}"


class TestRangeAndFixedConstraints:
    """``<path> in M..N`` -> ``sh:minInclusive``/``sh:maxInclusive``; ``<path> = v`` -> ``sh:hasValue``."""

    def test_numeric_range(self, rdf_graph: Graph) -> None:
        coll = URIRef(CORE + "Collection")
        bounds = set()
        for ps in rdf_graph.objects(coll, SH.property):
            if URIRef(CORE + "score") in set(rdf_graph.objects(ps, SH.path)):
                lo = list(rdf_graph.objects(ps, SH.minInclusive))
                hi = list(rdf_graph.objects(ps, SH.maxInclusive))
                if lo and hi:
                    bounds.add((int(str(lo[0])), int(str(hi[0]))))
        assert bounds == {(0, 10)}

    def test_fixed_value(self, rdf_graph: Graph) -> None:
        coll = URIRef(CORE + "Collection")
        none_support = URIRef(CORE + "SupportType/noSupport")
        found = any(
            URIRef(CORE + "supportLevel") in set(rdf_graph.objects(ps, SH.path)) and (ps, SH["hasValue"], none_support) in rdf_graph
            for ps in rdf_graph.objects(coll, SH.property)
        )
        assert found, "no sh:hasValue noSupport on supportLevel"


class TestRelationshipConstraints:
    """Relationship-vocab ``from``/``to`` -> SHACL endpoint typing scoped by ``relationshipType``."""

    def test_endpoint_typing_scoped_by_relationship_type(self, rdf_graph: Graph) -> None:
        from rdflib.collection import Collection as RDFList

        rel = URIRef(CORE + "Relationship")
        rtype = URIRef(CORE + "RelationshipType/secretAgentUsedBy")

        # Find the sh:or whose negated branch keys off relationshipType = secretAgentUsedBy.
        target = None
        for or_list in rdf_graph.objects(rel, SH["or"]):
            branches = list(RDFList(rdf_graph, or_list))
            keys_off = any(
                (ps, SH["hasValue"], rtype) in rdf_graph
                for b in branches
                for n in rdf_graph.objects(b, SH["not"])
                for ps in rdf_graph.objects(n, SH.property)
            )
            if keys_off:
                target = branches
        assert target is not None, "no relationship constraint scoped to secretAgentUsedBy"

        # The consequent branch must require from -> SecretAgent, to -> Agent, and to NOT Collection.
        endpoints = {}
        to_neg = set()
        for b in target:
            for ps in rdf_graph.objects(b, SH.property):
                paths = set(rdf_graph.objects(ps, SH.path))
                classes = set(rdf_graph.objects(ps, SH["class"]))
                if URIRef(CORE + "from") in paths:
                    endpoints["from"] = classes
                if URIRef(CORE + "to") in paths:
                    endpoints["to"] = classes
                    to_neg = {cl for n in rdf_graph.objects(ps, SH["not"]) for cl in rdf_graph.objects(n, SH["class"])}
        assert endpoints.get("from") == {URIRef(CORE + "SecretAgent")}
        assert endpoints.get("to") == {URIRef(CORE + "Agent")}
        assert to_neg == {URIRef(CORE + "Collection")}

    def test_narrower_relationship_class_attaches_to_default_not_narrower(self, rdf_graph: Graph) -> None:
        # `delegatedTo` names `relationshipClass: LifecycleScopedRelationship` (narrower than the
        # vocabulary default `Relationship`). Option B: the shape must still attach to the
        # *default* class -- :Relationship -- so every instance with this relationshipType is
        # checked, not only ones already typed as the narrower class. Nothing should attach
        # directly to :LifecycleScopedRelationship.
        from rdflib.collection import Collection as RDFList

        rel = URIRef(CORE + "Relationship")
        lsr = URIRef(CORE + "LifecycleScopedRelationship")
        rtype = URIRef(CORE + "RelationshipType/delegatedTo")

        assert list(rdf_graph.objects(lsr, SH["or"])) == [], "must not attach directly to the narrower class"

        target = None
        for or_list in rdf_graph.objects(rel, SH["or"]):
            branches = list(RDFList(rdf_graph, or_list))
            keys_off = any(
                (ps, SH["hasValue"], rtype) in rdf_graph
                for b in branches
                for n in rdf_graph.objects(b, SH["not"])
                for ps in rdf_graph.objects(n, SH.property)
            )
            if keys_off:
                target = branches
        assert target is not None, "no relationship constraint scoped to delegatedTo, attached to :Relationship"

        # The consequent branch (the one without sh:not) must carry sh:class LifecycleScopedRelationship
        # directly on the focus node -- conjunctive with (not nested inside) the endpoint typing.
        consequent = next(b for b in target if (b, SH["not"], None) not in rdf_graph)
        assert (consequent, SH["class"], lsr) in rdf_graph, "consequent must require rdf:type LifecycleScopedRelationship"
        assert any(rdf_graph.objects(consequent, SH.property)), "consequent must also carry endpoint typing"

    def test_bracket_qualifier_is_enforced_not_dropped(self, model: Model) -> None:
        # `Relationship[relationshipType=invokedBy]` must constrain the endpoint's own
        # relationshipType, not just reduce to a bare `sh:class Relationship`.
        pos, _neg = _endpoint_class_iris(model, "Core", ["Relationship[relationshipType=invokedBy]"])
        assert len(pos) == 1
        assert pos[0].iri == CORE + "Relationship"
        assert pos[0].qualifiers == {"relationshipType": ["invokedBy"]}

        g = Graph()
        ctx = _EmitCtx(model, g, "Core")
        shapes = _emit_qualifier_shapes(ctx, pos[0].fq, pos[0].qualifiers)
        assert len(shapes) == 1
        shape = shapes[0]
        assert (shape, SH.path, URIRef(CORE + "relationshipType")) in g
        assert (shape, SH["hasValue"], URIRef(CORE + "RelationshipType/invokedBy")) in g

    def test_bracket_qualifier_with_no_value_is_skipped_not_unsatisfiable(self, model: Model, caplog: pytest.LogCaptureFixture) -> None:
        # `Relationship[relationshipType]` (no "=value") parses to an empty value list. Building
        # a shape from it would emit an unsatisfiable `sh:in ()`, silently invalidating the whole
        # branch -- it must be skipped (with a warning) instead.
        pos, _neg = _endpoint_class_iris(model, "Core", ["Relationship[relationshipType]"])
        g = Graph()
        ctx = _EmitCtx(model, g, "Core")
        with caplog.at_level("WARNING"):
            shapes = _emit_qualifier_shapes(ctx, pos[0].fq, pos[0].qualifiers)
        assert shapes == []
        assert any("no value" in r.message for r in caplog.records)

    def test_bracket_qualifier_multi_value_uses_sh_in(self, model: Model) -> None:
        pos, _neg = _endpoint_class_iris(model, "Core", ["Relationship[relationshipType=invokedBy,affects]"])
        g = Graph()
        ctx = _EmitCtx(model, g, "Core")
        shapes = _emit_qualifier_shapes(ctx, pos[0].fq, pos[0].qualifiers)
        assert len(shapes) == 1
        shape = shapes[0]
        (in_list,) = list(g.objects(shape, SH["in"]))
        from rdflib.collection import Collection as RDFList

        values = set(RDFList(g, in_list))
        assert values == {URIRef(CORE + "RelationshipType/invokedBy"), URIRef(CORE + "RelationshipType/affects")}

    def test_element_kept_when_not_sole_endpoint_item(self, model: Model, caplog: pytest.LogCaptureFixture) -> None:
        # A single-item ["Element"] list is still dropped (it's the universal default, a no-op).
        pos_alone, _ = _endpoint_class_iris(model, "Core", ["Element"])
        assert pos_alone == []

        # But Element listed alongside another class must NOT be silently dropped -- doing so
        # would flip "no restriction" into an unintended restriction to just the other class.
        with caplog.at_level("WARNING"):
            pos_mixed, _ = _endpoint_class_iris(model, "Core", ["Element", "Agent"])
        assert {item.iri for item in pos_mixed} == {CORE + "Element", CORE + "Agent"}
        assert any("superclass" in r.message for r in caplog.records)

    def test_subsumption_warning_uses_class_hierarchy_not_just_element(self, model: Model, caplog: pytest.LogCaptureFixture) -> None:
        # SecretAgent subClassOf Agent in the fixture model (a fictional, test-only class --
        # not part of the real SPDX 3 model): any ancestor/descendant pair should be flagged,
        # not only the special-cased universal root ("Element").
        with caplog.at_level("WARNING"):
            pos, _ = _endpoint_class_iris(model, "Core", ["Agent", "SecretAgent"])
        assert {item.iri for item in pos} == {CORE + "Agent", CORE + "SecretAgent"}
        assert any("/Core/Agent' is a superclass of '/Core/SecretAgent'" in r.message for r in caplog.records)

        # Unrelated classes (no ancestor/descendant relationship) must not warn.
        caplog.clear()
        with caplog.at_level("WARNING"):
            _endpoint_class_iris(model, "Core", ["Agent", "Collection"])
        assert not caplog.records

        # A qualifier on the subsumed (more specific) class is flagged as vacuous, since an
        # instance can satisfy the sh:or via the unqualified superclass branch instead.
        caplog.clear()
        with caplog.at_level("WARNING"):
            _endpoint_class_iris(model, "Core", ["Agent", "SecretAgent[toolVersion=1.0]"])
        assert any("qualifier has no effect" in r.message for r in caplog.records)
