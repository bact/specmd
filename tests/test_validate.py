# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for YAML section validation (specmd.commands.validate)."""

from __future__ import annotations

import logging
from pathlib import Path
from textwrap import dedent

import pytest

from specmd.commands.validate import _check_sections, validate_inplace, validate_yaml_sections

# ---------------------------------------------------------------------------
# _check_sections (pure-string API)
# ---------------------------------------------------------------------------


class TestCheckSections:
    def test_valid_entries_returns_empty(self) -> None:
        content = dedent("""\
            ## Entries

            - md5: MD5 hash algorithm.
            - sha256: SHA-256 hash algorithm.
        """)
        assert _check_sections(content) == []

    def test_block_scalar_entries_valid(self) -> None:
        content = dedent("""\
            ## Entries

            - blake3: >-
                [BLAKE3](https://github.com/BLAKE3-team/BLAKE3) hash algorithm.
            - sha256: >-
                SHA-256 as defined in NIST FIPS 180-4: Secure Hash Standard (SHS).
        """)
        assert _check_sections(content) == []

    def test_markdown_link_unquoted_returns_error(self) -> None:
        # '[' starts YAML flow sequence — raw unquoted form is invalid.
        content = dedent("""\
            ## Entries

            - blake3: [BLAKE3](https://github.com/BLAKE3-team) hash algorithm.
        """)
        errors = _check_sections(content)
        assert len(errors) == 1
        assert errors[0][0] == "Entries"

    def test_colon_space_unquoted_returns_error(self) -> None:
        content = dedent("""\
            ## Entries

            - sha256: SHA-256 as defined in NIST FIPS 180-4: Secure Hash Standard.
        """)
        errors = _check_sections(content)
        assert len(errors) == 1
        assert errors[0][0] == "Entries"

    def test_curly_brace_at_start_of_value_returns_error(self) -> None:
        # '{' at the *start* of a plain scalar is a YAML flow-mapping indicator.
        content = dedent("""\
            ## Entries

            - entry: {256} alternative encoding variant.
        """)
        errors = _check_sections(content)
        assert len(errors) == 1
        assert errors[0][0] == "Entries"

    def test_curly_brace_mid_string_is_valid_yaml(self) -> None:
        # '{' in the *middle* of a plain scalar is not a YAML special character;
        # the whole value parses as a string.  (migrate.py emits >- conservatively
        # for any '{' occurrence, but the raw form is still valid YAML.)
        content = dedent("""\
            ## Entries

            - sha3: SHA3 variant {256} as standardized by NIST in FIPS 202.
        """)
        assert _check_sections(content) == []

    def test_multiple_invalid_sections_all_reported(self) -> None:
        # Two Entries sections, both invalid.
        # Note: '[' and '{' only break YAML when at the *start* of a plain scalar.
        content = dedent("""\
            ## Entries

            - e1: [link](url) starts with bracket.

            ## Summary

            Plain prose.

            ## Entries

            - e2: colon: space mid-value.
        """)
        errors = _check_sections(content)
        assert len(errors) == 2
        assert all(name == "Entries" for name, _ in errors)

    def test_no_yaml_sections_returns_empty(self) -> None:
        content = "## Summary\n\nJust prose.\n"
        assert _check_sections(content) == []

    def test_empty_section_body_ignored(self) -> None:
        content = "## Entries\n\n## Summary\n\nProse.\n"
        assert _check_sections(content) == []

    def test_metadata_section_not_validated(self) -> None:
        # Metadata sections are not checked (they rarely have YAML-unsafe chars
        # and the Format section uses non-standard backtick quoting).
        # Confirm no error is returned even for an otherwise-invalid Metadata body.
        content = "## Metadata\n\n- name: MyClass\n- abstract: true\n"
        assert _check_sections(content) == []

    def test_multiline_block_scalar_valid(self) -> None:
        # >- spanning two content lines — should parse cleanly.
        content = dedent("""\
            ## Entries

            - sha512: >-
                SHA-512 as defined in NIST FIPS 180-4: Secure Hash Standard (SHS). Produces
                a 512-bit hash value.
        """)
        assert _check_sections(content) == []

    def test_error_message_is_single_line(self) -> None:
        # PyYAML errors are multi-line; validate.py condenses them.
        # '[' at value start triggers a YAML flow-sequence error.
        content = "## Entries\n\n- e: [link](url) description.\n"
        errors = _check_sections(content)
        assert errors
        _, msg = errors[0]
        assert "\n" not in msg


# ---------------------------------------------------------------------------
# validate_yaml_sections (file API)
# ---------------------------------------------------------------------------


class TestValidateYamlSections:
    def test_valid_file_returns_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "Valid.md"
        f.write_text("## Entries\n\n- md5: MD5 hash algorithm.\n", encoding="utf-8")
        assert validate_yaml_sections(f) == []

    def test_invalid_file_returns_errors(self, tmp_path: Path) -> None:
        f = tmp_path / "Bad.md"
        # '[' at start of value triggers YAML flow-sequence parse error.
        f.write_text("## Entries\n\n- e: [link](url) description.\n", encoding="utf-8")
        errors = validate_yaml_sections(f)
        assert len(errors) == 1
        assert errors[0][0] == "Entries"

    def test_nonexistent_file_returns_read_error(self, tmp_path: Path) -> None:
        f = tmp_path / "ghost.md"
        errors = validate_yaml_sections(f)
        assert len(errors) == 1
        assert errors[0][0] == "<read>"


# ---------------------------------------------------------------------------
# validate_inplace (directory API)
# ---------------------------------------------------------------------------


class TestValidateInplace:
    def test_all_valid_counts(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("## Entries\n\n- md5: MD5.\n", encoding="utf-8")
        (tmp_path / "b.md").write_text("## Summary\n\nJust prose.\n", encoding="utf-8")
        valid, invalid = validate_inplace(tmp_path)
        assert valid == 2
        assert invalid == 0

    def test_one_invalid_file_counted(self, tmp_path: Path) -> None:
        (tmp_path / "good.md").write_text("## Entries\n\n- md5: MD5.\n", encoding="utf-8")
        (tmp_path / "bad.md").write_text("## Entries\n\n- e: [link](url) desc.\n", encoding="utf-8")
        valid, invalid = validate_inplace(tmp_path)
        assert valid == 1
        assert invalid == 1

    def test_invalid_file_logs_warning(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        (tmp_path / "bad.md").write_text("## Entries\n\n- e: [link](url) desc.\n", encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="specmd.commands.validate"):
            validate_inplace(tmp_path)
        assert "bad.md" in caplog.text
        assert "Entries" in caplog.text

    def test_recurses_into_subdirectories(self, tmp_path: Path) -> None:
        sub = tmp_path / "Core" / "Vocabularies"
        sub.mkdir(parents=True)
        (sub / "Hash.md").write_text("## Entries\n\n- md5: MD5.\n", encoding="utf-8")
        valid, invalid = validate_inplace(tmp_path)
        assert valid == 1
        assert invalid == 0

    def test_new_format_fixture_all_valid(self) -> None:
        # The model fixture (new format) must pass raw YAML validation.
        fixture = Path(__file__).parent / "fixtures" / "model"
        _valid, invalid = validate_inplace(fixture)
        assert invalid == 0, f"{invalid} file(s) failed raw YAML validation in new-format fixture"

    def test_old_format_fixture_has_invalid_sections(self) -> None:
        # The old-format fixture deliberately contains unquoted YAML-unsafe characters.
        fixture = Path(__file__).parent / "fixtures" / "model-old-format"
        _valid, invalid = validate_inplace(fixture)
        assert invalid > 0, "Expected at least one invalid section in old-format fixture"


# ---------------------------------------------------------------------------
# _cmd_validate — CLI integration (single file, --strict, summary line)
# ---------------------------------------------------------------------------


class TestCmdValidateCli:
    """Integration tests for the validate subcommand via RunParams."""

    def _run(self, _tmp_path: Path, args: list[str]) -> tuple[int, list[str]]:
        """Run ``specmd validate <args>`` and return (exit_code, log_lines)."""
        from specmd.__main__ import _cmd_validate
        from specmd._logging import setup_logging
        from specmd._params import RunParams

        log_lines: list[str] = []

        class _CapHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                log_lines.append(self.format(record))

        root_logger, handler = setup_logging(level=logging.INFO)
        cap = _CapHandler()
        cap.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        root_logger.addHandler(cap)

        exit_code = 0
        try:
            cfg = RunParams.__new__(RunParams)  # pylint: disable=no-value-for-parameter
            cfg._ts = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)  # noqa: SLF001  # pylint: disable=protected-access
            cfg._parse_args(["validate", *args])  # noqa: SLF001  # pylint: disable=protected-access
            _cmd_validate(cfg, root_logger, handler)
        except SystemExit as exc:
            exit_code = int(exc.code or 0)
        finally:
            root_logger.removeHandler(cap)

        return exit_code, log_lines

    # ---- single file ----

    def test_single_valid_file_exit_zero(self, tmp_path: Path) -> None:
        f = tmp_path / "Good.md"
        f.write_text("## Entries\n\n- md5: MD5 hash.\n", encoding="utf-8")
        code, _ = self._run(tmp_path, [str(f)])
        assert code == 0

    def test_single_invalid_file_exit_zero_without_strict(self, tmp_path: Path) -> None:
        f = tmp_path / "Bad.md"
        f.write_text("## Entries\n\n- e: [link](url) desc.\n", encoding="utf-8")
        code, logs = self._run(tmp_path, [str(f)])
        assert code == 0
        assert any("WARNING" in line for line in logs)

    def test_single_invalid_file_exit_nonzero_with_strict(self, tmp_path: Path) -> None:
        f = tmp_path / "Bad.md"
        f.write_text("## Entries\n\n- e: [link](url) desc.\n", encoding="utf-8")
        code, _ = self._run(tmp_path, [str(f), "--strict"])
        assert code != 0

    def test_single_valid_file_summary_line(self, tmp_path: Path) -> None:
        f = tmp_path / "Good.md"
        f.write_text("## Entries\n\n- md5: MD5 hash.\n", encoding="utf-8")
        _, logs = self._run(tmp_path, [str(f)])
        assert any("1 file checked" in line for line in logs)

    def test_single_invalid_file_summary_shows_issue_count(self, tmp_path: Path) -> None:
        f = tmp_path / "Bad.md"
        f.write_text("## Entries\n\n- e: [link](url) desc.\n", encoding="utf-8")
        _, logs = self._run(tmp_path, [str(f)])
        assert any("1 section issue" in line for line in logs)

    # ---- directory: --strict ----

    def test_directory_valid_exit_zero(self, tmp_path: Path) -> None:
        (tmp_path / "Good.md").write_text("## Entries\n\n- md5: MD5.\n", encoding="utf-8")
        # Write a minimal specmd.yml so Model can load.
        (tmp_path / "specmd.yml").write_text("", encoding="utf-8")
        code, _ = self._run(tmp_path, [str(tmp_path)])
        assert code == 0

    def test_directory_invalid_exit_zero_without_strict(self, tmp_path: Path) -> None:
        (tmp_path / "specmd.yml").write_text("", encoding="utf-8")
        (tmp_path / "Bad.md").write_text("## Entries\n\n- e: [link](url) desc.\n", encoding="utf-8")
        code, _ = self._run(tmp_path, [str(tmp_path)])
        assert code == 0

    def test_directory_invalid_exit_nonzero_with_strict(self, tmp_path: Path) -> None:
        (tmp_path / "specmd.yml").write_text("", encoding="utf-8")
        (tmp_path / "Bad.md").write_text("## Entries\n\n- e: [link](url) desc.\n", encoding="utf-8")
        code, _ = self._run(tmp_path, [str(tmp_path), "--strict"])
        assert code != 0

    # ---- directory: summary line ----

    def test_directory_summary_shows_file_count(self, tmp_path: Path) -> None:
        (tmp_path / "specmd.yml").write_text("", encoding="utf-8")
        (tmp_path / "a.md").write_text("## Entries\n\n- md5: MD5.\n", encoding="utf-8")
        (tmp_path / "b.md").write_text("## Entries\n\n- sha256: SHA.\n", encoding="utf-8")
        _, logs = self._run(tmp_path, [str(tmp_path)])
        summary = " ".join(logs)
        # validate_inplace counts only .md files (not specmd.yml)
        assert "2 file(s) checked" in summary

    def test_directory_summary_shows_zero_issues_when_clean(self, tmp_path: Path) -> None:
        (tmp_path / "specmd.yml").write_text("", encoding="utf-8")
        (tmp_path / "a.md").write_text("## Entries\n\n- md5: MD5.\n", encoding="utf-8")
        _, logs = self._run(tmp_path, [str(tmp_path)])
        assert any("0 file(s) with issues" in line for line in logs)
