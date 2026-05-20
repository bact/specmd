# SPDX-License-Identifier: Apache-2.0

"""Tests for specmd Markdown parsing."""

from __future__ import annotations

import logging
from pathlib import Path
from textwrap import dedent

import pytest

from specmd.parse.markdown import (
    ContentSection,
    NestedListSection,
    SingleListSection,
    SpecFile,
    VocabDefaults,
    VocabularySection,
    _split_class_list,
)


class TestSpecFile:
    def test_loads_valid_file(self, fixture_model_path: Path) -> None:
        sf = SpecFile(fixture_model_path / "Core" / "Core.md")
        assert sf.name == "Core"
        assert sf.license == "CC0-1.0"
        assert "Summary" in sf.sections
        assert "Metadata" in sf.sections

    def test_frontmatter_populated(self, fixture_model_path: Path) -> None:
        sf = SpecFile(fixture_model_path / "Core" / "Core.md")
        assert sf.frontmatter.get("SPDX-License-Identifier") == "CC0-1.0"

    def test_missing_frontmatter_logs_error(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        f = tmp_path / "Bad.md"
        f.write_text("# Bad\n\n## Summary\n\nSome summary.\n\n## Metadata\n\n- name: Bad\n")
        with caplog.at_level(logging.ERROR, logger="specmd.mdparsing"):
            SpecFile(f)
        assert any("frontmatter" in msg.lower() for msg in caplog.messages)

    def test_unparseable_section_logs_error(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        f = tmp_path / "Broken.md"
        # A section heading with no content body cannot satisfy the fullmatch.
        f.write_text("---\nSPDX-License-Identifier: Apache-2.0\n---\n\n# Broken\n\n## EmptySection\n\n")
        with caplog.at_level(logging.ERROR, logger="specmd.mdparsing"):
            SpecFile(f)
        assert any("cannot parse" in msg for msg in caplog.messages)

    def test_loads_class_file(self, fixture_model_path: Path) -> None:
        sf = SpecFile(fixture_model_path / "Core" / "Classes" / "Tool.md")
        assert sf.name == "Tool"
        assert "Properties" in sf.sections
        assert "Metadata" in sf.sections


class TestFrontmatter:
    def _write(self, tmp_path: Path, content: str) -> SpecFile:
        f = tmp_path / "Test.md"
        f.write_text(content)
        return SpecFile(f)

    def test_frontmatter_license_parsed(self, tmp_path: Path) -> None:
        sf = self._write(
            tmp_path,
            dedent("""\
            ---
            SPDX-License-Identifier: Apache-2.0
            ---

            # Test

            ## Metadata

            - name: Test
        """),
        )
        assert sf.license == "Apache-2.0"
        assert sf.frontmatter["SPDX-License-Identifier"] == "Apache-2.0"

    def test_frontmatter_name_and_sections_parsed(self, tmp_path: Path) -> None:
        sf = self._write(
            tmp_path,
            dedent("""\
            ---
            SPDX-License-Identifier: Apache-2.0
            ---

            # MyThing

            ## Summary

            A summary.

            ## Metadata

            - name: MyThing
        """),
        )
        assert sf.name == "MyThing"
        assert "Summary" in sf.sections
        assert "Metadata" in sf.sections

    def test_frontmatter_extra_keys_stored(self, tmp_path: Path) -> None:
        sf = self._write(
            tmp_path,
            dedent("""\
            ---
            SPDX-License-Identifier: Apache-2.0
            version: 1.2.3
            author: Test Suite
            ---

            # X

            ## Metadata

            - name: X
        """),
        )
        assert sf.frontmatter.get("version") == "1.2.3"
        assert sf.frontmatter.get("author") == "Test Suite"

    def test_frontmatter_lone_spdx_line_treated_as_text(self, tmp_path: Path) -> None:
        sf = self._write(
            tmp_path,
            dedent("""\
            ---
            SPDX-License-Identifier: Apache-2.0
            ---

            # X

            ## Summary

            SPDX-License-Identifier: something-else

            ## Metadata

            - name: X
        """),
        )
        assert sf.license == "Apache-2.0"
        assert "SPDX-License-Identifier: something-else" in sf.sections.get("Summary", "")

    def test_frontmatter_missing_license_logs_error(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        f = tmp_path / "NoLicense.md"
        f.write_text("---\nauthor: Someone\n---\n\n# X\n\n## Metadata\n\n- name: X\n")
        with caplog.at_level(logging.ERROR, logger="specmd.mdparsing"):
            SpecFile(f)
        assert any("license" in msg.lower() for msg in caplog.messages)


class TestContentSection:
    def test_preserves_content(self) -> None:
        s = ContentSection("Hello world.\n\nSecond paragraph.")
        assert s.content == "Hello world.\n\nSecond paragraph."

    def test_empty_content(self) -> None:
        s = ContentSection("")
        assert s.content == ""

    def test_none_content(self) -> None:
        s = ContentSection(None)
        assert s.content == ""


class TestSingleListSection:
    def test_parses_key_value(self) -> None:
        s = SingleListSection("- name: MyClass\n- Instantiability: Concrete")
        assert s.kv == {"name": "MyClass", "Instantiability": "Concrete"}

    def test_logs_error_for_bad_content(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.ERROR, logger="specmd.mdparsing"):
            SingleListSection("this is not a list", filename="test.md", context="metadata")
        assert caplog.messages

    def test_strips_whitespace_from_value(self) -> None:
        s = SingleListSection("- key: value with spaces")
        assert s.kv["key"] == "value with spaces"

    def test_values_are_strings(self) -> None:
        s = SingleListSection("- count: 42\n- flag: true")
        assert s.kv["count"] == "42"
        assert s.kv["flag"] == "true"

    def test_backtick_wrapping_stripped(self) -> None:
        s = SingleListSection("- pattern: `^(0|[1-9][0-9]*).*$`")
        assert s.kv["pattern"] == "^(0|[1-9][0-9]*).*$"

    def test_backtick_already_absent_leaves_value(self) -> None:
        s = SingleListSection("- name: SemVer")
        assert s.kv["name"] == "SemVer"

    def test_double_backtick_wrapping_with_inner_backtick(self) -> None:
        s = SingleListSection("- pattern: ``has`backtick``")
        assert s.kv["pattern"] == "has`backtick"


class TestNestedListSection:
    def test_parses_nested(self) -> None:
        content = dedent("""\
            - propName:
              - minCount: 1
        """)
        s = NestedListSection(content)
        assert "propName" in s.ikv
        assert s.ikv["propName"]["minCount"] == "1"

    def test_multiple_properties(self) -> None:
        content = dedent("""\
            - alpha:
              - minCount: 0
            - beta:
              - minCount: 1
              - maxCount: 3
        """)
        s = NestedListSection(content)
        assert set(s.ikv.keys()) == {"alpha", "beta"}
        assert s.ikv["beta"]["minCount"] == "1"
        assert s.ikv["beta"]["maxCount"] == "3"

    def test_cross_namespace_property(self) -> None:
        content = dedent("""\
            - /Core/name:
              - minCount: 0
              - maxCount: 1
        """)
        s = NestedListSection(content)
        assert "/Core/name" in s.ikv
        assert s.ikv["/Core/name"]["maxCount"] == "1"

    def test_values_are_strings(self) -> None:
        content = dedent("""\
            - prop:
              - minCount: 0
              - maxCount: 1
        """)
        s = NestedListSection(content)
        assert isinstance(s.ikv["prop"]["minCount"], str)
        assert isinstance(s.ikv["prop"]["maxCount"], str)

    def test_empty_property_no_attrs(self) -> None:
        # Property with no sub-attributes (e.g. only - type: line was dropped
        # during migration). BaseLoader yields '' for empty mapping values.
        content = "- seeAlso:\n"
        s = NestedListSection(content)
        assert "seeAlso" in s.ikv
        assert s.ikv["seeAlso"] == {}

    def test_empty_property_mixed(self) -> None:
        # Empty property alongside one with attributes -- both must parse.
        content = dedent("""\
            - seeAlso:
            - name:
              - minCount: 1
        """)
        s = NestedListSection(content)
        assert s.ikv["seeAlso"] == {}
        assert s.ikv["name"]["minCount"] == "1"


class TestVocabularySection:
    def test_simple_entry(self) -> None:
        s = VocabularySection("- noSupport: No support is provided.")
        assert "noSupport" in s.entries
        assert s.entries["noSupport"]["description"] == "No support is provided."

    def test_simple_entry_defaults_applied(self) -> None:
        s = VocabularySection("- noSupport: No support is provided.")
        entry = s.entries["noSupport"]
        assert entry["from"] == ["Element"]
        assert entry["to"] == ["Element"]
        assert entry["relationshipClass"] == "Relationship"

    def test_multiple_simple_entries(self) -> None:
        content = dedent("""\
            - alpha: First entry.
            - beta: Second entry.
        """)
        s = VocabularySection(content)
        assert set(s.entries.keys()) == {"alpha", "beta"}
        assert s.entries["alpha"]["description"] == "First entry."

    def test_structured_entry(self) -> None:
        content = dedent("""\
            - hasRoleIn:
              - description: Agent has a role in Element.
              - from: Agent, Tool
              - to: Element
              - relationshipClass: RoleRelationship
        """)
        s = VocabularySection(content)
        assert "hasRoleIn" in s.entries
        entry = s.entries["hasRoleIn"]
        assert entry["description"] == "Agent has a role in Element."
        assert entry["from"] == ["Agent", "Tool"]
        assert entry["to"] == ["Element"]
        assert entry["relationshipClass"] == "RoleRelationship"

    def test_structured_entry_partial_defaults(self) -> None:
        content = dedent("""\
            - describes:
              - description: A describes B.
              - relationshipClass: DescribesRelationship
        """)
        s = VocabularySection(content)
        entry = s.entries["describes"]
        assert entry["from"] == ["Element"]
        assert entry["to"] == ["Element"]
        assert entry["relationshipClass"] == "DescribesRelationship"

    def test_structured_missing_description_defaults_empty(self) -> None:
        content = dedent("""\
            - uses:
              - from: Tool
              - to: Element
        """)
        s = VocabularySection(content)
        assert s.entries["uses"]["description"] == ""

    def test_from_to_yaml_block_list(self) -> None:
        content = dedent("""\
            - rel:
              - description: Desc.
              - from:
                  - Agent
                  - Tool
              - to:
                  - Artifact
        """)
        s = VocabularySection(content)
        assert s.entries["rel"]["from"] == ["Agent", "Tool"]
        assert s.entries["rel"]["to"] == ["Artifact"]

    def test_from_to_yaml_inline_list(self) -> None:
        content = dedent("""\
            - rel:
              - description: Desc.
              - from: [Agent, Tool]
              - to: [Artifact]
        """)
        s = VocabularySection(content)
        assert s.entries["rel"]["from"] == ["Agent", "Tool"]
        assert s.entries["rel"]["to"] == ["Artifact"]

    def test_from_to_bracket_constraint_in_list(self) -> None:
        content = dedent("""\
            - rel:
              - description: Desc.
              - from: Agent
              - to:
                  - Relationship[relationshipType=invokedBy]
        """)
        s = VocabularySection(content)
        assert s.entries["rel"]["to"] == ["Relationship[relationshipType=invokedBy]"]

    def test_from_to_single_string_no_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        content = dedent("""\
            - rel:
              - description: Desc.
              - from: Agent
              - to: Artifact
        """)
        with caplog.at_level(logging.WARNING):
            s = VocabularySection(content)
        assert s.entries["rel"]["from"] == ["Agent"]
        assert "commas" not in caplog.text

    def test_from_to_comma_string_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        content = dedent("""\
            - rel:
              - description: Desc.
              - from: Agent, Tool
        """)
        with caplog.at_level(logging.WARNING):
            VocabularySection(content)
        assert "commas" in caplog.text
        assert "YAML list" in caplog.text

    def test_custom_default_relationship_class(self) -> None:
        content = "- plain: A description."
        s = VocabularySection(content, defaults=VocabDefaults(default_relationship_class="LifecycleRelationship"))
        assert s.entries["plain"]["relationshipClass"] == "LifecycleRelationship"

    def test_explicit_relationship_class_overrides_default(self) -> None:
        content = dedent("""\
            - rel:
              - description: Desc.
              - relationshipClass: RoleRelationship
        """)
        s = VocabularySection(content, defaults=VocabDefaults(default_relationship_class="LifecycleRelationship"))
        assert s.entries["rel"]["relationshipClass"] == "RoleRelationship"

    def test_custom_default_from(self) -> None:
        content = "- plain: A description."
        s = VocabularySection(content, defaults=VocabDefaults(default_from=["Agent", "Tool"]))
        assert s.entries["plain"]["from"] == ["Agent", "Tool"]

    def test_custom_default_to(self) -> None:
        content = "- plain: A description."
        s = VocabularySection(content, defaults=VocabDefaults(default_to=["Artifact"]))
        assert s.entries["plain"]["to"] == ["Artifact"]

    def test_explicit_from_to_override_defaults(self) -> None:
        content = dedent("""\
            - rel:
              - description: Desc.
              - from: Element
              - to: Element
        """)
        s = VocabularySection(content, defaults=VocabDefaults(default_from=["Agent"], default_to=["Artifact"]))
        assert s.entries["rel"]["from"] == ["Element"]
        assert s.entries["rel"]["to"] == ["Element"]

    def test_mixed_simple_and_structured(self) -> None:
        content = dedent("""\
            - plain: A plain description.
            - fancy:
              - description: A fancy one.
              - relationshipClass: FancyRelationship
        """)
        s = VocabularySection(content)
        assert s.entries["plain"]["description"] == "A plain description."
        assert s.entries["plain"]["relationshipClass"] == "Relationship"
        assert s.entries["fancy"]["relationshipClass"] == "FancyRelationship"


class TestSplitClassList:
    def test_simple_single(self) -> None:
        assert _split_class_list("Element") == ["Element"]

    def test_simple_multiple(self) -> None:
        assert _split_class_list("Agent, Tool, Element") == ["Agent", "Tool", "Element"]

    def test_bracket_single(self) -> None:
        assert _split_class_list("Relationship[type=invokedBy]") == ["Relationship[type=invokedBy]"]

    def test_bracket_comma_inside_not_split(self) -> None:
        assert _split_class_list("Foo[a=1, b=2]") == ["Foo[a=1, b=2]"]

    def test_bracket_mixed_with_bare(self) -> None:
        assert _split_class_list("Foo[a=1, b=2], Bar") == ["Foo[a=1, b=2]", "Bar"]

    def test_empty_string(self) -> None:
        assert _split_class_list("") == []

    def test_strips_whitespace(self) -> None:
        assert _split_class_list("  Agent ,  Tool  ") == ["Agent", "Tool"]
