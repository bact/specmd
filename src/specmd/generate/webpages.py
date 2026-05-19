# SPDX-License-Identifier: Apache-2.0

"""Generate standalone web pages from the model (stub)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from specmd.parse.model import Model


# pylint: disable=unused-argument
def gen_webpages(model: Model, outpath: Path, cfg: Any) -> None:
    """Stub"""
    # Does nothing
