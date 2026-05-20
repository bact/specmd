# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the migrate command, focusing on vocabulary entry conversion."""

from __future__ import annotations

from specmd.commands.migrate import _migrate_lines


def _migrate(src: str) -> str:
    """Migrate *src* (old-format content) and return the result as a string."""
    lines = src.splitlines(keepends=True)
    result = _migrate_lines(lines)
    assert result is not None, "Expected migration to produce output"
    return "".join(result)


class TestMigrateVocabEntries:
    _HEADER = "SPDX-License-Identifier: Community-Spec-1.0\n\n"

    def _wrap(self, entries_body: str) -> str:
        return self._HEADER + "# Vocab\n\n## Entries\n\n" + entries_body

    def test_simple_entry_unchanged(self) -> None:
        src = self._wrap("- noSupport: No support provided.\n")
        out = _migrate(src)
        assert "- noSupport: No support provided." in out

    def test_single_from_to_inline(self) -> None:
        src = self._wrap("- describes: The `from` Element describes the `to` Element.\n")
        out = _migrate(src)
        assert "  - from: Element" in out
        assert "  - to: Element" in out
        # single value must NOT produce a block list
        assert "    - Element" not in out

    def test_multi_from_produces_block_list(self) -> None:
        src = self._wrap("- affects: The `from` Vulnerability, Action or DefinedProcess affects `to` Element.\n")
        out = _migrate(src)
        assert "  - from:\n" in out
        assert "    - Vulnerability\n" in out
        assert "    - Action\n" in out
        assert "    - DefinedProcess\n" in out
        # comma-separated string must NOT appear
        assert "from: Vulnerability, Action" not in out

    def test_single_from_to_not_block_list(self) -> None:
        src = self._wrap("- describes: The `from` Agent describes `to` Artifact.\n")
        out = _migrate(src)
        # single item → inline, no block list
        lines = out.splitlines()
        from_lines = [line for line in lines if "from:" in line]
        assert len(from_lines) == 1
        assert from_lines[0].strip().startswith("- from: Agent")

    def test_relationship_class_extracted(self) -> None:
        src = self._wrap("- hasSomething: The `from` Agent has `to` Artifact. Shall be a `LifecycleRelationship`.\n")
        out = _migrate(src)
        assert "  - relationshipClass: LifecycleRelationship" in out

    def test_migrated_output_parseable_as_yaml_block_list(self) -> None:
        """Block-list output must be valid YAML that the parser accepts."""
        import yaml

        src = self._wrap("- affects: The `from` Vulnerability, Action affects `to` Element.\n")
        out = _migrate(src)
        # Extract just the Entries section content for YAML parsing
        entries_start = out.index("## Entries\n") + len("## Entries\n")
        entries_yaml = out[entries_start:].strip()
        data = yaml.safe_load(entries_yaml)
        assert isinstance(data, list)
        entry = data[0]
        assert "affects" in entry
        attrs = {next(iter(a.keys())): next(iter(a.values())) for a in entry["affects"]}
        assert attrs["from"] == ["Vulnerability", "Action"]
