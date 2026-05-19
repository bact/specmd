# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Generate PlantUML class diagram input from the model."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from specmd.parse.model import Model

logger = logging.getLogger(__name__)


# pylint: disable=unused-argument
def gen_plantuml(model: Model, outpath: Path, cfg: Any) -> None:
    """Write a single ``model.plantuml`` file describing the full class diagram."""
    f = outpath / "model.plantuml"

    pu_cfg = model.config.get("plantuml", {})
    title = pu_cfg.get("title", "SPDXv3 model")
    scale = pu_cfg.get("scale", "4000*4000")

    s = f"""
@startuml
'{cfg.autogen_header}

title {title}
scale {scale}
hide methods
skinparam packageStyle folder

"""
    for ns in model.namespaces:
        s += f"package {ns.name} {{\n}}\n"

    inheritances: list[tuple[str, str]] = []
    prop2class: list[tuple[str, str]] = []
    for c in model.classes.values():
        if c.metadata.get("abstract") == "true":
            s += "abstract "
        else:
            s += "class "
        s += f"{c.ns.name}.{c.name} {{\n"
        if "subClassOf" in c.metadata:
            parent = c.metadata["subClassOf"]
            inheritances.append((f"{c.ns.name}.{c.name}", parent.split("/")[-1]))
        for p in sorted(c.properties):
            pkv = c.properties[p]
            s += f"\t{p} {pkv['minCount']}:{pkv['maxCount']}\n"
            prop_obj = model.properties.get(pkv["fqname"])
            if prop_obj:
                rng = prop_obj.metadata.get("range", "")
                if rng and ":" not in rng:
                    prop2class.append((f"{c.ns.name}.{c.name}::{p}", rng.split("/")[-1]))
        s += "}\n"

    for v in model.vocabularies.values():
        s += f"enum {v.ns.name}.{v.name} {{\n}}\n"

    for d in model.datatypes.values():
        s += f"class {d.ns.name}.{d.name} {{\n}}\n"

    for l, r in inheritances:
        s += f"{l} --|> {r}\n"
    for l, r in prop2class:
        s += f"{l} --> {r}\n"

    s += "\n@enduml\n"

    f.write_text(s)
