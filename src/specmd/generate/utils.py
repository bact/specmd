# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared Jinja filter for wrapping long identifiers in narrow table columns."""

from __future__ import annotations

import re

_WORD_BREAK_RE = re.compile(r"[a-z](?=[A-Z])|(?=/)")


def word_break(text: str | None) -> str | None:
    """Insert ``<wbr>`` at camelCase boundaries and before slashes, so long names wrap in narrow table columns."""
    if not text:
        return text
    return _WORD_BREAK_RE.sub(lambda m: m.group() + "<wbr>", text)
