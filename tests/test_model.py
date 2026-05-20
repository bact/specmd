# SPDX-License-Identifier: Apache-2.0

"""Tests for specmd model."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from specmd.parse.model import Model, _parse_qualified_class


class TestModelLoading:
    def test_namespace_count(self, model: Model) -> None:
        assert len(model.namespaces) == 1
        assert model.namespaces[0].name == "Core"

    def test_class_count(self, model: Model) -> None:
        assert len(model.classes) == 3

    def test_property_count(self, model: Model) -> None:
        assert len(model.properties) == 4

    def test_vocabulary_count(self, model: Model) -> None:
        assert len(model.vocabularies) == 3

    def test_simple_vocab_is_not_relationship_vocab(self, model: Model) -> None:
        vocab = model.vocabularies["/Core/SupportType"]
        assert vocab.is_relationship_vocab is False

    def test_relationship_vocab_detected(self, model: Model) -> None:
        vocab = model.vocabularies["/Core/RelationshipType"]
        assert vocab.is_relationship_vocab is True

    def test_datatype_count(self, model: Model) -> None:
        assert len(model.datatypes) == 1

    def test_individual_count(self, model: Model) -> None:
        assert len(model.individuals) == 1

    def test_base_uri(self, model: Model) -> None:
        # fixture specmd.yml sets base-uri: https://example.org/rdf/terms/
        assert model.base_uri == "https://example.org/rdf/terms/"

    def test_class_iris(self, model: Model) -> None:
        assert model.classes["/Core/Element"].iri == "https://example.org/rdf/terms/Core/Element"
        assert model.classes["/Core/Tool"].iri == "https://example.org/rdf/terms/Core/Tool"

    def test_namespace_iri(self, model: Model) -> None:
        # Real model stores namespace id without trailing slash (e.g. ".../Core").
        assert model.namespaces[0].iri == "https://example.org/rdf/terms/Core"


class TestInheritance:
    def test_tool_inherits_from_agent(self, model: Model) -> None:
        tool = model.classes["/Core/Tool"]
        assert tool.fqsupercname == "/Core/Agent"

    def test_agent_inherits_from_element(self, model: Model) -> None:
        agent = model.classes["/Core/Agent"]
        assert agent.fqsupercname == "/Core/Element"

    def test_element_has_no_parent(self, model: Model) -> None:
        element = model.classes["/Core/Element"]
        assert element.fqsupercname is None

    def test_tool_all_properties_includes_inherited(self, model: Model) -> None:
        tool = model.classes["/Core/Tool"]
        # spdxId and name come from Element, toolVersion and supportLevel from Tool.
        assert "spdxId" in tool.all_properties
        assert "name" in tool.all_properties
        assert "toolVersion" in tool.all_properties
        assert "supportLevel" in tool.all_properties

    def test_tool_inheritance_stack(self, model: Model) -> None:
        tool = model.classes["/Core/Tool"]
        assert "/Core/Agent" in tool.inheritance_stack
        assert "/Core/Element" in tool.inheritance_stack

    def test_direct_subclasses(self, model: Model) -> None:
        element = model.classes["/Core/Element"]
        assert "/Core/Agent" in element.direct_subclasses
        agent = model.classes["/Core/Agent"]
        assert "/Core/Tool" in agent.direct_subclasses

    def test_class_hierarchy(self, model: Model) -> None:
        assert "/Core/Agent" in model.class_hierarchy["/Core/Element"]
        assert "/Core/Tool" in model.class_hierarchy["/Core/Agent"]


class TestNamespaceOrder:
    def _model_with_config(self, tmp_path: Path, yaml: str) -> Model:
        import shutil

        from tests.conftest import FIXTURE_MODEL

        shutil.copytree(FIXTURE_MODEL, tmp_path / "model")
        # Always start without specmd.yml so each test controls config precisely.
        (tmp_path / "model" / "specmd.yml").unlink(missing_ok=True)
        (tmp_path / "model" / "specmd.yml").write_text(yaml)
        return Model(tmp_path / "model")

    def test_namespace_order_from_config(self, model: Model) -> None:
        # fixture model specmd.yml sets namespace-order: [Core]
        assert model.namespace_order() == ["Core"]

    def test_config_explicit_order(self, tmp_path: Path) -> None:
        m = self._model_with_config(tmp_path, "namespace-order:\n  - Core\n")
        assert m.namespace_order() == ["Core"]

    def test_config_excludes_unlisted_namespace(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        # Empty namespace-order → Core excluded, warning emitted
        m = self._model_with_config(tmp_path, "namespace-order: []\n")
        with caplog.at_level(logging.WARNING, logger="specmd.parse.model"):
            result = m.namespace_order()
        assert result == []
        assert "excluded" in caplog.text

    def test_include_unlisted_namespaces_appends_alphabetically(self, tmp_path: Path) -> None:
        m = self._model_with_config(
            tmp_path,
            "namespace-order: []\ninclude-unlisted-namespaces: true\n",
        )
        # Core not in namespace-order but include-unlisted-namespaces is true → appended
        assert m.namespace_order() == ["Core"]

    def test_include_unlisted_no_exclusion_warning(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        m = self._model_with_config(
            tmp_path,
            "namespace-order: []\ninclude-unlisted-namespaces: true\n",
        )
        with caplog.at_level(logging.WARNING, logger="specmd.parse.model"):
            m.namespace_order()
        assert "excluded" not in caplog.text

    def test_config_unknown_name_warns(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        m = self._model_with_config(tmp_path, "namespace-order:\n  - Core\n  - NonExistent\n")
        with caplog.at_level(logging.WARNING, logger="specmd.parse.model"):
            result = m.namespace_order()
        assert "NonExistent" in caplog.text
        assert result == ["Core"]


class TestInstantiability:
    def test_element_is_abstract(self, model: Model) -> None:
        assert model.classes["/Core/Element"].metadata.get("abstract") == "true"

    def test_tool_is_concrete(self, model: Model) -> None:
        assert model.classes["/Core/Tool"].metadata.get("abstract") != "true"

    def test_agent_is_abstract(self, model: Model) -> None:
        assert model.classes["/Core/Agent"].metadata.get("abstract") == "true"


class TestParseQualifiedClass:
    def test_bare_name(self) -> None:
        assert _parse_qualified_class("Element") == ("Element", {})

    def test_qualified_single_prop_single_value(self) -> None:
        base, q = _parse_qualified_class("Relationship[relationshipType=invokedBy]")
        assert base == "Relationship"
        assert q == {"relationshipType": ["invokedBy"]}

    def test_qualified_single_prop_multi_value(self) -> None:
        base, q = _parse_qualified_class("Relationship[relationshipType=a,b,c]")
        assert base == "Relationship"
        assert q == {"relationshipType": ["a", "b", "c"]}

    def test_qualified_multi_prop_semicolon(self) -> None:
        base, q = _parse_qualified_class("Relationship[relationshipType=a,b,c;scope=build]")
        assert base == "Relationship"
        assert q == {"relationshipType": ["a", "b", "c"], "scope": ["build"]}

    def test_qualified_multi_prop_single_values(self) -> None:
        base, q = _parse_qualified_class("Foo[a=1;b=2]")
        assert base == "Foo"
        assert q == {"a": ["1"], "b": ["2"]}

    def test_strips_whitespace(self) -> None:
        base, q = _parse_qualified_class("  Agent  ")
        assert base == "Agent"
        assert q == {}

    def test_whitespace_inside_qualifier(self) -> None:
        base, q = _parse_qualified_class("Foo[ a = x , y ; b = z ]")
        assert base == "Foo"
        assert q == {"a": ["x", "y"], "b": ["z"]}


class TestVocabEntryValidation:
    def test_known_class_no_warning(self, model: Model, caplog: pytest.LogCaptureFixture) -> None:
        # Agent exists in the fixture; used as from/to in RelationshipType entries
        with caplog.at_level(logging.WARNING, logger="specmd.parse.model"):
            model.validate_vocab_entries()
        # Only check that Agent itself doesn't trigger a warning
        assert "unknown class 'Agent'" not in caplog.text

    def test_unknown_class_warns(self, model: Model, caplog: pytest.LogCaptureFixture) -> None:
        # Vocabulary, Action, Artifact etc. are not in the minimal fixture
        with caplog.at_level(logging.WARNING, logger="specmd.parse.model"):
            model.validate_vocab_entries()
        assert "unknown class" in caplog.text

    def test_unknown_qualifier_prop_warns(self, model: Model, caplog: pytest.LogCaptureFixture) -> None:
        # 'relationshipType' is not a property in the fixture model
        with caplog.at_level(logging.WARNING, logger="specmd.parse.model"):
            model.validate_vocab_entries()
        assert "unknown property" in caplog.text
