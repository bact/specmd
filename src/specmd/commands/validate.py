# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""YAML syntax validation for specmd Markdown files.

Public API
----------
validate_yaml_sections(path)  -- validate YAML-bearing sections in one .md file;
                                  returns a list of (section_name, error) pairs.
validate_inplace(root)         -- validate all .md files under *root*;
                                  returns (valid, invalid) file counts.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

# Matches the body of sections whose content must be valid YAML.
#
# ``Format`` sections are intentionally excluded: they use specmd's backtick-
# quoting convention (``- pattern: `regex` ``) which is pre-processed by the
# parser before YAML loading and is therefore not valid raw YAML.
#
# Captures: group(1) = section heading name, group(2) = body until next ## or EOF.
_RE_YAML_SECTION = re.compile(
    r"^## (Entries|Properties)[ \t]*\n(.*?)(?=^##|\Z)",
    re.MULTILINE | re.DOTALL,
)


def validate_yaml_sections(path: Path) -> list[tuple[str, str]]:
    """Return ``(section_name, error_message)`` pairs for every invalid YAML section in *path*.

    An empty list means all sections parsed successfully.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [("<read>", str(exc))]
    return _check_sections(content)


def _check_sections(content: str) -> list[tuple[str, str]]:
    """Run ``yaml.safe_load`` on each YAML-bearing section body in *content*."""
    errors: list[tuple[str, str]] = []
    for m in _RE_YAML_SECTION.finditer(content):
        section_name = m.group(1)
        body = m.group(2).strip()
        if not body:
            continue
        try:
            yaml.safe_load(body)
        except yaml.YAMLError as exc:
            # Condense multi-line PyYAML messages to a single line.
            errors.append((section_name, str(exc).replace("\n", " ").strip()))
    return errors


def validate_inplace(root: Path) -> tuple[int, int]:
    """Validate YAML sections in all ``.md`` files under *root*.

    Logs a warning for every invalid section found.
    Returns ``(valid_files, invalid_files)`` counts.
    """
    valid = invalid = 0
    for md_file in sorted(root.rglob("*.md")):
        errors = validate_yaml_sections(md_file)
        if errors:
            for section_name, msg in errors:
                logger.warning(
                    "  %s [%s]: %s",
                    md_file.relative_to(root),
                    section_name,
                    msg,
                )
            invalid += 1
        else:
            valid += 1
    return valid, invalid
