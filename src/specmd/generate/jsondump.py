# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Serialise the parsed model to clean JSON using only the stdlib."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import rfc8785

if TYPE_CHECKING:
    from pathlib import Path

    from specmd.parse.model import Model

logger = logging.getLogger(__name__)


def _to_serialisable(obj: Any, _seen: set[int] | None = None) -> Any:
    """Recursively convert *obj* to a JSON-serialisable structure.

    Circular references are replaced with a ``{"$ref": "<ClassName>"}`` sentinel
    so the output stays finite and readable without losing structural context.
    """
    if _seen is None:
        _seen = set()
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if isinstance(obj, (list, tuple)):
        return [_to_serialisable(v, _seen) for v in obj]
    if isinstance(obj, dict):
        return {k: _to_serialisable(v, _seen) for k, v in obj.items()}
    if hasattr(obj, "__dict__"):
        oid = id(obj)
        if oid in _seen:
            return {"$ref": type(obj).__name__}
        _seen.add(oid)
        result = {k: _to_serialisable(v, _seen) for k, v in vars(obj).items() if not k.startswith("_")}
        _seen.discard(oid)
        return result
    return str(obj)


# pylint: disable=unused-argument
def gen_jsondump(model: Model, outpath: Path, cfg: Any) -> None:
    """Write the full model as a canonical JSON file (RFC 8785 / JCS)."""
    f = outpath / "model.json"
    f.write_bytes(rfc8785.dumps(_to_serialisable(model)))
