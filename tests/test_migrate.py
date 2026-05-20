# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the migrate command, focusing on vocabulary entry conversion."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from specmd.commands.migrate import _migrate_lines, migrate_file


def _migrate(src: str) -> str:
    """Migrate *src* (old-format content) and return the result as a string."""
    lines = src.splitlines(keepends=True)
    result = _migrate_lines(lines)
    assert result is not None, "Expected migration to produce output"
    return "".join(result)


def _assert_entries_yaml_valid(out: str) -> None:
    """Assert every ``## Entries`` section body in *out* is valid YAML.

    Raises ``yaml.YAMLError`` on the first invalid section found.
    """
    for m in re.finditer(r"^## Entries[ \t]*\n(.*?)(?=^##|\Z)", out, re.MULTILINE | re.DOTALL):
        body = m.group(1).strip()
        if body:
            yaml.safe_load(body)  # raises on invalid YAML


class TestMigrateVocabEntries:
    _HEADER = "SPDX-License-Identifier: Community-Spec-1.0\n\n"

    def _wrap(self, entries_body: str) -> str:
        return self._HEADER + "# Vocab\n\n## Entries\n\n" + entries_body

    def test_simple_entry_unchanged(self) -> None:
        src = self._wrap("- noSupport: No support provided.\n")
        out = _migrate(src)
        assert "- noSupport: No support provided." in out
        _assert_entries_yaml_valid(out)

    def test_single_from_to_inline(self) -> None:
        src = self._wrap("- describes: The `from` Element describes the `to` Element.\n")
        out = _migrate(src)
        assert "  - from: Element" in out
        assert "  - to: Element" in out
        # single value must NOT produce a block list
        assert "    - Element" not in out
        _assert_entries_yaml_valid(out)

    def test_multi_from_produces_block_list(self) -> None:
        src = self._wrap("- affects: The `from` Vulnerability, Action or DefinedProcess affects `to` Element.\n")
        out = _migrate(src)
        assert "  - from:\n" in out
        assert "    - Vulnerability\n" in out
        assert "    - Action\n" in out
        assert "    - DefinedProcess\n" in out
        # comma-separated string must NOT appear
        assert "from: Vulnerability, Action" not in out
        _assert_entries_yaml_valid(out)

    def test_single_from_to_not_block_list(self) -> None:
        src = self._wrap("- describes: The `from` Agent describes `to` Artifact.\n")
        out = _migrate(src)
        # single item → inline, no block list
        lines = out.splitlines()
        from_lines = [line for line in lines if "from:" in line]
        assert len(from_lines) == 1
        assert from_lines[0].strip().startswith("- from: Agent")
        _assert_entries_yaml_valid(out)

    def test_relationship_class_extracted(self) -> None:
        src = self._wrap("- hasSomething: The `from` Agent has `to` Artifact. Shall be a `LifecycleRelationship`.\n")
        out = _migrate(src)
        assert "  - relationshipClass: LifecycleRelationship" in out
        _assert_entries_yaml_valid(out)

    def test_migrated_output_parseable_as_yaml_block_list(self) -> None:
        """Block-list output must be valid YAML that the parser accepts."""
        src = self._wrap("- affects: The `from` Vulnerability, Action affects `to` Element.\n")
        out = _migrate(src)
        _assert_entries_yaml_valid(out)
        # Extract just the Entries section content for YAML parsing
        entries_start = out.index("## Entries\n") + len("## Entries\n")
        entries_yaml = out[entries_start:].strip()
        data = yaml.safe_load(entries_yaml)
        assert isinstance(data, list)
        entry = data[0]
        assert "affects" in entry
        attrs = {next(iter(a.keys())): next(iter(a.values())) for a in entry["affects"]}
        assert attrs["from"] == ["Vulnerability", "Action"]


class TestMigrateBlockScalar:
    """Migration must emit >- block scalars for YAML-unsafe or long descriptions."""

    _HEADER = "SPDX-License-Identifier: Community-Spec-1.0\n\n"

    def _entries(self, body: str) -> str:
        return self._HEADER + "# Vocab\n\n## Entries\n\n" + body

    def _entries_yaml(self, out: str) -> list:
        start = out.index("## Entries\n") + len("## Entries\n")
        return yaml.safe_load(out[start:].strip())

    # ---- block scalar triggered ----

    def test_colon_space_in_desc_emits_block_scalar(self) -> None:
        src = self._entries("- sha256: SHA-256 as defined in NIST FIPS 180-4: Secure Hash Standard.\n")
        out = _migrate(src)
        assert "- sha256: >-\n" in out
        assert "180-4:" in out
        _assert_entries_yaml_valid(out)

    def test_markdown_link_in_desc_emits_block_scalar(self) -> None:
        src = self._entries("- blake3: [BLAKE3](https://github.com/BLAKE3-team/BLAKE3) hash algorithm.\n")
        out = _migrate(src)
        assert "- blake3: >-\n" in out
        assert "[BLAKE3]" in out
        _assert_entries_yaml_valid(out)

    def test_curly_brace_in_desc_emits_block_scalar(self) -> None:
        src = self._entries("- sha3: SHA3 variant {256} as standardized by NIST.\n")
        out = _migrate(src)
        assert "- sha3: >-\n" in out
        assert "{256}" in out
        _assert_entries_yaml_valid(out)

    def test_long_desc_emits_block_scalar(self) -> None:
        # 81-char description (prefix "- longEntry: " + desc > 79 chars total)
        long_desc = "A" * 70
        src = self._entries(f"- longEntry: {long_desc}\n")
        out = _migrate(src)
        assert "- longEntry: >-\n" in out
        _assert_entries_yaml_valid(out)

    # ---- inline kept for short clean desc ----

    def test_short_clean_desc_stays_inline(self) -> None:
        src = self._entries("- md5: MD5 hash algorithm.\n")
        out = _migrate(src)
        assert "- md5: MD5 hash algorithm." in out
        assert ">-" not in out
        _assert_entries_yaml_valid(out)

    # ---- output is valid YAML and preserves description text ----

    def test_colon_desc_yaml_parseable(self) -> None:
        src = self._entries("- sha256: SHA-256 as defined in NIST FIPS 180-4: Secure Hash Standard (SHS).\n")
        out = _migrate(src)
        data = self._entries_yaml(out)
        item = next(i for i in data if i is not None and "sha256" in i)
        assert item["sha256"] == "SHA-256 as defined in NIST FIPS 180-4: Secure Hash Standard (SHS)."

    def test_markdown_link_desc_yaml_parseable(self) -> None:
        src = self._entries("- blake3: [BLAKE3](https://github.com/BLAKE3-team/BLAKE3) hash algorithm.\n")
        out = _migrate(src)
        data = self._entries_yaml(out)
        item = next(i for i in data if i is not None and "blake3" in i)
        assert item["blake3"] == "[BLAKE3](https://github.com/BLAKE3-team/BLAKE3) hash algorithm."

    def test_curly_brace_desc_yaml_parseable(self) -> None:
        src = self._entries("- sha3: SHA3 variant {256} as standardized by NIST in FIPS 202.\n")
        out = _migrate(src)
        data = self._entries_yaml(out)
        item = next(i for i in data if i is not None and "sha3" in i)
        assert item["sha3"] == "SHA3 variant {256} as standardized by NIST in FIPS 202."

    def test_long_desc_lines_within_79_chars(self) -> None:
        long_desc = "word " * 20  # 100 chars, all breakable
        src = self._entries(f"- entry: {long_desc.strip()}\n")
        out = _migrate(src)
        for line in out.splitlines():
            assert len(line) <= 79, f"Line exceeds 79 chars: {line!r}"

    # ---- newline handling ----

    def test_multiline_block_scalar_folds_to_single_string(self) -> None:
        # After migration the two content lines of the >- block must fold to one
        # space-joined string with no embedded \n.
        desc = "SHA-512 as defined in NIST FIPS 180-4: Secure Hash Standard (SHS). Produces a 512-bit hash value."
        src = self._entries(f"- sha512: {desc}\n")
        out = _migrate(src)
        assert "- sha512: >-\n" in out
        data = self._entries_yaml(out)
        item = next(i for i in data if i is not None and "sha512" in i)
        assert "\n" not in item["sha512"]
        assert item["sha512"] == desc

    def test_block_scalar_lines_have_no_trailing_newline_in_value(self) -> None:
        # >- strips the trailing newline; YAML value must not end with \n.
        src = self._entries("- sha256: SHA-256 as defined in NIST FIPS 180-4: Secure Hash Standard.\n")
        out = _migrate(src)
        data = self._entries_yaml(out)
        item = next(i for i in data if i is not None and "sha256" in i)
        assert not item["sha256"].endswith("\n")

    def test_url_in_desc_not_broken_by_wrap(self) -> None:
        # A long URL cannot be broken (break_long_words=False); it stays on one
        # line even if it pushes past 79 chars.
        long_url = "https://example.org/specifications/hash-algorithms/sha-512-specification-document"
        desc = f"See {long_url} for the full specification."
        src = self._entries(f"- sha512: {desc}\n")
        out = _migrate(src)
        assert "- sha512: >-\n" in out
        # The URL must appear intact in the output.
        assert long_url in out
        # And YAML still parses correctly.
        data = self._entries_yaml(out)
        item = next(i for i in data if i is not None and "sha512" in i)
        assert long_url in item["sha512"]

    # ---- migrate old-format fixture file ----

    def test_migrate_fixture_file(self, tmp_path: Path) -> None:
        """Migrating the old-format HashAlgorithm fixture must produce valid YAML entries."""
        fixture = Path(__file__).parent / "fixtures" / "model-old-format" / "Core" / "Vocabularies" / "HashAlgorithm.md"
        dest = tmp_path / "HashAlgorithm.md"
        dest.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
        changed = migrate_file(dest)
        assert changed
        out = dest.read_text(encoding="utf-8")
        # All three unsafe entries must use block scalars.
        assert "- blake3: >-\n" in out
        assert "- sha256: >-\n" in out
        assert "- sha3: >-\n" in out
        # Plain entry stays inline.
        assert "- md5: MD5 hash algorithm." in out
        # Full output must be parseable YAML in Entries section.
        start = out.index("## Entries\n") + len("## Entries\n")
        data = yaml.safe_load(out[start:].strip())
        entries = {k: v for item in data if item for k, v in item.items()}
        assert entries["blake3"] == "[BLAKE3](https://github.com/BLAKE3-team/BLAKE3) hash algorithm."
        assert "180-4:" in entries["sha256"]
        assert "{256}" in entries["sha3"]
        # sha512: two-line >- block folds to a single string without \n
        assert "\n" not in entries["sha512"]
        assert entries["sha512"] == ("SHA-512 as defined in NIST FIPS 180-4: Secure Hash Standard (SHS). Produces a 512-bit hash value.")
