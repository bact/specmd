# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Migrate spec Markdown files from spec-parser format to specmd format.

Public API
----------
migrate_directory(src, dst)  -- copy *src* → *dst* and migrate all .md files in *dst*.
migrate_inplace(root)        -- migrate all .md files under *root* in place.
migrate_file(path)           -- migrate a single file in place; returns True if changed.
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

RE_SPDX_LINE = re.compile(r"^SPDX-License-Identifier:\s+(.+?)\s*$")
RE_SECTION_HEADER = re.compile(r"^## (.+)$")
RE_NESTED_TOP = re.compile(r"^(-\s+)([\w/]+)\s*$")
RE_TYPE_ATTR = re.compile(r"^  -\s+type:\s+.+$")
RE_STAR_VALUE = re.compile(r"^(  -\s+\w+:\s+)\*(\s*)$")
RE_META_KV = re.compile(r"^(-\s+)(\w+)(\s*:\s*)(.*)$")
RE_DEPRECATED_NOTICE = re.compile(
    r"^\*\*DEPRECATED(?:\s+in\s+(?:SPDX\s+)?([\d.]+(?:\.\d+)*))?\.\*\*\s*$",
    re.IGNORECASE,
)
RE_USE_INSTEAD = re.compile(
    r"^Use\s+\[([^\]]+)\]\([^)]+\)\s+instead\.\s*$",
    re.IGNORECASE,
)
RE_KV_LINE = re.compile(r"^(-\s+\w[\w-]*:\s+)(.+)$")
RE_ENTRY_LINE = re.compile(r"^(-\s+)([\w/]+)(\s*:\s*)(.+)$")
RE_HAS_FROM = re.compile(r"`from`\s+[A-Z]")
RE_FROM_TO_SPAN = re.compile(r"`from`\s+(.+?)`to`", re.IGNORECASE)
RE_TO_AFTER = re.compile(r"`to`\s+(?:each\s+|the\s+)?(.+)", re.IGNORECASE)
RE_PASCAL_NAME = re.compile(r"(?<![a-zA-Z])[A-Z][a-zA-Z0-9]*[a-z][a-zA-Z0-9]*")
RE_POSSESSIVE_SPLIT = re.compile(r"^[A-Z]\w+\s*'s\s+(.+)")
RE_CONSTRAINED_CLASS = re.compile(
    r"(?:constrained to|Shall be (?:a|an)|To be used with)\s+`([A-Z]\w+)`",
    re.IGNORECASE,
)

NESTED_SECTIONS = {"Properties", "External properties restrictions"}
METADATA_SECTIONS = {"Metadata"}
ENTRIES_SECTIONS = {"Entries"}
BACKTICK_SECTIONS = {"Format"}

_METADATA_RENAMES = {
    "subclassof": "subClassOf",
    "nature": "nature",
    "range": "range",
    "iri": "iri",
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_deprecation(lines: list[str]) -> dict[str, str]:
    in_desc = False
    result: dict[str, str] = {}
    after_depr = False

    for line in lines:
        stripped = line.rstrip("\r\n")
        m = RE_SECTION_HEADER.match(stripped)
        if m:
            in_desc = m.group(1).strip() == "Description"
            after_depr = False
            continue
        if not in_desc:
            continue
        if not result:
            m_dn = RE_DEPRECATED_NOTICE.match(stripped)
            if m_dn:
                result["deprecated"] = "true"
                if m_dn.group(1):
                    result["deprecatedVersion"] = m_dn.group(1)
                after_depr = True
        elif after_depr:
            if not stripped:
                continue
            m_ui = RE_USE_INSTEAD.match(stripped)
            if m_ui:
                result["isReplacedBy"] = m_ui.group(1).strip()
            after_depr = False

    return result


def _collect_class_names(text: str) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for raw in re.split(r"[\s,]+", text.strip()):
        sentence_end = raw.endswith(".")
        token = re.sub(r"\([^)]*\)$", "", raw.rstrip(".,;:"))
        if not token:
            if sentence_end:
                break
            continue
        if token.lower() in ("or", "and"):
            continue
        if RE_PASCAL_NAME.fullmatch(token):
            if token not in seen:
                seen.add(token)
                names.append(token)
            if sentence_end:
                break
        else:
            break
    return names


def _extract_rel_entry_fields(desc: str) -> dict[str, object]:
    if not RE_HAS_FROM.search(desc):
        return {}
    result: dict[str, object] = {}

    m_ft = RE_FROM_TO_SPAN.search(desc)
    if m_ft:
        from_text = m_ft.group(1).strip()
        m_poss = RE_POSSESSIVE_SPLIT.match(from_text)
        if m_poss:
            from_text = m_poss.group(1)
        names = RE_PASCAL_NAME.findall(from_text)
        if names:
            seen: set[str] = set()
            result["from"] = [n for n in names if not (n in seen or seen.add(n))]  # type: ignore[func-returns-value]

    m_to = RE_TO_AFTER.search(desc)
    if m_to:
        names = _collect_class_names(m_to.group(1))
        if names:
            result["to"] = names

    m_rc = RE_CONSTRAINED_CLASS.search(desc)
    if m_rc:
        result["relationshipClass"] = m_rc.group(1)

    if "from" not in result:
        return {}
    return result


def _migrate_lines(lines: list[str]) -> list[str] | None:
    """Return migrated lines, or *None* if the file is already new-format."""
    if not lines:
        return None

    first = lines[0].rstrip("\r\n")
    m = RE_SPDX_LINE.match(first)
    if not m:
        return None

    license_id = m.group(1)
    result: list[str] = ["---\n", f"SPDX-License-Identifier: {license_id}\n", "---\n", "\n"]

    i = 1
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    body = lines[i:]

    dep_info = _extract_deprecation(body)
    meta_dep_seen: set[str] = set()
    current_section: str | None = None
    desc_strip: str = "none"
    desc_skip_trailing_blank: bool = False

    def _flush_dep() -> None:
        for key in ("deprecated", "deprecatedVersion", "isReplacedBy"):
            if key in dep_info and key not in meta_dep_seen:
                result.append(f"- {key}: {dep_info[key]}\n")  # noqa: PERF401

    for line in body:
        stripped = line.rstrip("\r\n")

        m_sec = RE_SECTION_HEADER.match(stripped)
        if m_sec:
            if current_section in METADATA_SECTIONS:
                _flush_dep()
            current_section = m_sec.group(1).strip()
            desc_strip = "none"
            desc_skip_trailing_blank = False
            result.append(line)
            continue

        if current_section == "Description" and dep_info:
            skip = False
            if desc_strip == "none":
                if RE_DEPRECATED_NOTICE.match(stripped):
                    desc_strip = "saw_notice"
                    skip = True
            elif desc_strip == "saw_notice":
                if not stripped:
                    skip = True
                elif RE_USE_INSTEAD.match(stripped):
                    desc_strip = "done"
                    desc_skip_trailing_blank = True
                    skip = True
                else:
                    desc_strip = "done"
            if not skip and desc_skip_trailing_blank and not stripped:
                desc_skip_trailing_blank = False
                skip = True
            if skip:
                continue

        if current_section in METADATA_SECTIONS:
            m_meta = RE_META_KV.match(stripped)
            if m_meta:
                key = m_meta.group(2)
                value = m_meta.group(4).strip()
                kl = key.lower()
                if kl in ("deprecated", "deprecatedversion", "isreplacedby"):
                    meta_dep_seen.add(kl)
                if kl in _METADATA_RENAMES:
                    result.append(f"{m_meta.group(1)}{_METADATA_RENAMES[kl]}{m_meta.group(3)}{value}\n")
                    continue
                if kl == "instantiability":
                    if value.lower() == "abstract":
                        result.append(f"{m_meta.group(1)}abstract{m_meta.group(3)}true\n")
                    continue

        if current_section in NESTED_SECTIONS:
            if RE_TYPE_ATTR.match(stripped):
                continue
            m_top = RE_NESTED_TOP.match(stripped)
            if m_top:
                result.append(f"{m_top.group(1)}{m_top.group(2)}:\n")
                continue
            m_star = RE_STAR_VALUE.match(stripped)
            if m_star:
                result.append(f'{m_star.group(1)}"*"\n')
                continue

        if current_section in BACKTICK_SECTIONS:
            m_kv = RE_KV_LINE.match(stripped)
            if m_kv:
                value = m_kv.group(2)
                if not (value.startswith("`") and value.endswith("`")):
                    result.append(f"{m_kv.group(1)}`{value}`\n")
                    continue

        if current_section in ENTRIES_SECTIONS:
            m_entry = RE_ENTRY_LINE.match(stripped)
            if m_entry:
                prefix = m_entry.group(1)
                name = m_entry.group(2)
                desc = m_entry.group(4).strip()
                rel = _extract_rel_entry_fields(desc)
                if rel:
                    result.append(f"{prefix}{name}:\n")
                    result.append(f"  - description: {desc}\n")
                    for field in ("from", "to", "relationshipClass"):
                        if field in rel:
                            val = rel[field]
                            if isinstance(val, list) and len(val) > 1:
                                result.append(f"  - {field}:\n")
                                result.extend(f"    - {v}\n" for v in val)
                            elif isinstance(val, list):
                                result.append(f"  - {field}: {val[0]}\n")
                            else:
                                result.append(f"  - {field}: {val}\n")
                    continue

        result.append(line)

    if current_section in METADATA_SECTIONS:
        _flush_dep()

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def migrate_file(path: Path) -> bool:
    """Migrate *path* in place. Returns ``True`` if the file was changed."""
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    new_lines = _migrate_lines(lines)
    if new_lines is None:
        return False
    new_content = "".join(new_lines)
    if new_content == content:
        return False
    path.write_text(new_content, encoding="utf-8")
    return True


def migrate_inplace(root: Path) -> tuple[int, int]:
    """Recursively migrate all ``.md`` files under *root* in place.

    Returns ``(changed, skipped)`` counts.
    """
    changed = skipped = 0
    for md_file in sorted(root.rglob("*.md")):
        if migrate_file(md_file):
            logger.info("  migrated: %s", md_file.relative_to(root))
            changed += 1
        else:
            skipped += 1
    logger.info("%d file(s) migrated, %d already up-to-date.", changed, skipped)
    return changed, skipped


def migrate_directory(src: Path, dst: Path) -> tuple[int, int]:
    """Copy *src* to *dst* and migrate all ``.md`` files in *dst*.

    Returns ``(changed, skipped)`` counts.
    """
    shutil.copytree(src, dst, dirs_exist_ok=True)
    return migrate_inplace(dst)
