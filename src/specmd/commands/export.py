# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Export specmd Markdown files to another format.

Currently supported target format:

``legacy``
    spec-parser format -- inverse of the migration performed by ``_migrate.py``.

Public API
----------
export_directory(src, dst, fmt)  -- copy *src* → *dst* and convert all .md files in *dst*.
export_inplace(root, fmt)        -- convert all .md files under *root* in place.
export_file(path, range_map)     -- convert a single file in place; returns True if changed.
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

RE_FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.DOTALL)
RE_SPDX_IN_FM = re.compile(r"^SPDX-License-Identifier:\s+(.+?)\s*$", re.MULTILINE)
RE_RANGE_LINE = re.compile(r"^-\s+range:\s+(.+?)\s*$", re.MULTILINE | re.IGNORECASE)
RE_SECTION_HEADER = re.compile(r"^## (.+)$")
RE_NESTED_TOP_NEW = re.compile(r"^(-\s+)([\w/]+):\s*$")
RE_QUOTED_STAR = re.compile(r'^(  -\s+\w+:\s+)"(\*)"(\s*)$')
RE_BACKTICK_KV = re.compile(r"^(-\s+\w[\w-]*:\s+)(``|`)(.+?)\2\s*$")
RE_META_KV = re.compile(r"^(-\s+)(\w+)(\s*:\s*)(.*)$")
RE_DEPRECATED_NOTICE = re.compile(
    r"^\*\*DEPRECATED(?:\s+in\s+(?:SPDX\s+)?([\d.]+(?:\.\d+)*))?\.\*\*\s*$",
    re.IGNORECASE,
)
RE_USE_INSTEAD = re.compile(
    r"^Use\s+\[([^\]]+)\]\([^)]+\)\s+instead\.\s*$",
    re.IGNORECASE,
)

NESTED_SECTIONS = {"Properties", "External properties restrictions"}
FORMAT_SECTIONS = {"Format"}
METADATA_SECTIONS = {"Metadata"}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _has_depr_notice(text: str) -> bool:
    in_desc = False
    for line in text.splitlines():
        m = RE_SECTION_HEADER.match(line)
        if m:
            in_desc = m.group(1).strip() == "Description"
            continue
        if in_desc and RE_DEPRECATED_NOTICE.match(line):
            return True
    return False


def _collect_depr_metadata(text: str) -> dict[str, str]:
    in_meta = False
    result: dict[str, str] = {}
    for line in text.splitlines():
        m = RE_SECTION_HEADER.match(line)
        if m:
            in_meta = m.group(1).strip() == "Metadata"
            continue
        if not in_meta:
            continue
        m_meta = RE_META_KV.match(line)
        if m_meta:
            kl = m_meta.group(2).lower()
            val = m_meta.group(4).strip()
            if kl == "deprecated":
                result["deprecated"] = val
            elif kl == "deprecatedversion":
                result["deprecatedVersion"] = val
            elif kl == "isreplacedby":
                result["isReplacedBy"] = val
    return result


def _build_range_map(root: Path) -> dict[str, str]:
    """Scan all ``Properties/*.md`` files and return ``{/NS/name: Range}``."""
    range_map: dict[str, str] = {}
    for prop_file in root.rglob("Properties/*.md"):
        content = prop_file.read_text(encoding="utf-8")
        ns_name = prop_file.parent.parent.name
        fqname = f"/{ns_name}/{prop_file.stem}"
        m = RE_RANGE_LINE.search(content)
        if m:
            range_map[fqname] = m.group(1).strip()
    return range_map


def _revert_lines(content: str, ns_name: str, range_map: dict[str, str]) -> str | None:
    """Return reverted content, or *None* if already old-format or unchanged."""
    fm_match = RE_FRONTMATTER.match(content)
    if not fm_match:
        return None

    spdx_m = RE_SPDX_IN_FM.search(fm_match.group(1))
    license_id = spdx_m.group(1) if spdx_m else "Community-Spec-1.0"

    result: list[str] = [f"SPDX-License-Identifier: {license_id}\n", "\n"]

    body = content[fm_match.end() :]

    _pre = _collect_depr_metadata(body)
    depr_val: str | None = _pre.get("deprecated")
    depr_ver: str | None = _pre.get("deprecatedVersion")
    repl_by: str | None = _pre.get("isReplacedBy")
    notice_already_present = _has_depr_notice(body)

    current_section: str | None = None
    meta_saw_abstract: bool = False
    depr_inject_pending: bool = False

    def _flush_metadata_defaults() -> None:
        if current_section in METADATA_SECTIONS and not meta_saw_abstract:
            result.append("- Instantiability: Concrete\n")

    for line in body.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")

        m_sec = RE_SECTION_HEADER.match(stripped)
        if m_sec:
            _flush_metadata_defaults()
            current_section = m_sec.group(1).strip()
            meta_saw_abstract = False
            depr_inject_pending = current_section == "Description" and depr_val == "true" and not notice_already_present
            result.append(line)
            continue

        if depr_inject_pending and current_section == "Description" and stripped:
            ver_part = f" in SPDX {depr_ver}" if depr_ver else ""
            result.append(f"**DEPRECATED{ver_part}.**\n")
            if repl_by:
                result.append(f"Use [{repl_by}]({repl_by}) instead.\n")
            result.append("\n")
            depr_inject_pending = False

        if current_section in METADATA_SECTIONS:
            m_meta = RE_META_KV.match(stripped)
            if m_meta:
                key = m_meta.group(2)
                value = m_meta.group(4).strip()
                kl = key.lower()
                renames_back = {
                    "subclassof": "SubclassOf",
                    "nature": "Nature",
                    "range": "Range",
                    "iri": "IRI",
                }
                if kl in renames_back:
                    result.append(f"{m_meta.group(1)}{renames_back[kl]}{m_meta.group(3)}{value}\n")
                    continue
                if kl == "abstract":
                    meta_saw_abstract = True
                    result.append("- Instantiability: Abstract\n" if value.lower() == "true" else "- Instantiability: Concrete\n")
                    continue
                if kl in ("deprecated", "deprecatedversion", "isreplacedby"):
                    continue  # converted back to Description text

        if current_section in NESTED_SECTIONS:
            m_star = RE_QUOTED_STAR.match(stripped)
            if m_star:
                result.append(f"{m_star.group(1)}*\n")
                continue
            m_top = RE_NESTED_TOP_NEW.match(stripped)
            if m_top:
                prop_name = m_top.group(2)
                result.append(f"{m_top.group(1)}{prop_name}\n")
                fqname = prop_name if prop_name.startswith("/") else f"/{ns_name}/{prop_name}"
                prop_range = range_map.get(fqname)
                if prop_range:
                    result.append(f"  - type: {prop_range}\n")
                else:
                    matches = [r for k, r in range_map.items() if k.endswith(f"/{prop_name}")]
                    if len(matches) == 1:
                        result.append(f"  - type: {matches[0]}\n")
                continue

        if current_section in FORMAT_SECTIONS:
            m_bt = RE_BACKTICK_KV.match(stripped)
            if m_bt:
                result.append(f"{m_bt.group(1)}{m_bt.group(3)}\n")
                continue

        result.append(line)

    _flush_metadata_defaults()
    return "".join(result)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def export_file(path: Path, range_map: dict[str, str]) -> bool:
    """Export *path* to legacy format in place. Returns ``True`` if changed."""
    content = path.read_text(encoding="utf-8")
    ns_name = path.parent.name if path.parent.name[0].isupper() else path.parent.parent.name
    new_content = _revert_lines(content, ns_name, range_map)
    if new_content is None or new_content == content:
        return False
    path.write_text(new_content, encoding="utf-8")
    return True


def export_inplace(root: Path, fmt: str = "legacy") -> tuple[int, int]:
    """Recursively export all ``.md`` files under *root* in place.

    Returns ``(changed, skipped)`` counts.
    """
    if fmt != "legacy":
        raise ValueError(f"Unsupported export format: {fmt!r}")
    range_map = _build_range_map(root)
    changed = skipped = 0
    for md_file in sorted(root.rglob("*.md")):
        if export_file(md_file, range_map):
            logger.info("  exported: %s", md_file.relative_to(root))
            changed += 1
        else:
            skipped += 1
    logger.info("%d file(s) exported, %d unchanged.", changed, skipped)
    return changed, skipped


def export_directory(src: Path, dst: Path, fmt: str = "legacy") -> tuple[int, int]:
    """Copy *src* to *dst* and export all ``.md`` files in *dst*.

    Returns ``(changed, skipped)`` counts.
    """
    shutil.copytree(src, dst, dirs_exist_ok=True)
    return export_inplace(dst, fmt)
