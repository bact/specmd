# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Generate LaTeX input from the model, then optionally compile to PDF via latexmk."""

from __future__ import annotations

import logging
import subprocess
from typing import TYPE_CHECKING, Any

from jinja2 import Environment, PackageLoader, select_autoescape

from specmd.constraints import Conformance, conformance_to_prose, constraint_to_prose, parse_constraint, property_constraint_to_prose

if TYPE_CHECKING:
    from pathlib import Path

    from specmd.parse.model import Model

logger = logging.getLogger(__name__)


def gen_tex(model: Model, outpath: Path, cfg: Any) -> None:  # pylint: disable=unused-argument
    """Write per-term ``.tex`` files and a ``model-files.tex`` include list."""
    jinja = Environment(
        loader=PackageLoader("specmd.generate", package_path="templates/tex"),
        autoescape=select_autoescape(),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    jinja.globals = cfg.all_as_dict
    jinja.globals["not_none"] = lambda x: str(x) if x is not None else ""
    jinja.globals["tex_escape"] = tex_escape
    jinja.globals["markdown_to_tex"] = markdown_to_tex
    jinja.globals["constraint_prose"] = lambda raw, cname: constraint_to_prose(parse_constraint(raw), cname)
    jinja.globals["property_constraint_prose"] = lambda raw, pname: property_constraint_to_prose(parse_constraint(raw), pname)
    _conf_cfg = model.config.get("conformance", {})
    _coll = _conf_cfg.get("collection-class", "/Core/ElementCollection")
    _default_profile = _conf_cfg.get("default-profile")
    _profile_map = _conf_cfg.get("profile", {}) or {}

    def _conformance_prose(rules: list[Conformance], name: str) -> list[str]:
        entries = _profile_map.get(name, [])
        entries = [entries] if isinstance(entries, str) else entries
        is_default = _default_profile is not None and _default_profile in entries
        return [conformance_to_prose(r, name, _coll, is_default=is_default) for r in rules]

    jinja.globals["conformance_prose"] = _conformance_prose
    jinja.globals["conformance_mode"] = _conf_cfg.get("prose", "structured")

    for ns in model.namespaces:
        d = outpath / ns.name
        d.mkdir()
        f = d / f"{ns.name}.tex"
        template = jinja.get_template("namespace.tex.j2")
        f.write_text(template.render(vars(ns)))

    def _generate_in_dir(dirname: str, group: dict[str, Any], tmplfname: str) -> None:
        for s in group.values():
            d = outpath / s.ns.name / dirname
            d.mkdir(exist_ok=True)
            f = d / f"{s.name}.tex"
            template = jinja.get_template(tmplfname)
            f.write_text(template.render(vars(s)))

    _generate_in_dir("Classes", model.classes, "class.tex.j2")
    _generate_in_dir("Properties", model.properties, "property.tex.j2")
    _generate_in_dir("Vocabularies", model.vocabularies, "vocabulary.tex.j2")
    _generate_in_dir("Individuals", model.individuals, "individual.tex.j2")
    _generate_in_dir("Datatypes", model.datatypes, "datatype.tex.j2")

    def _gen_filelist(nsname: str, itemslist: dict[str, Any], heading: str) -> list[str]:
        nameslist = [c.name for c in itemslist.values()]
        if not nameslist:
            return []
        ret = [f"\\spdxcategory{{{heading}}}"]
        ret.extend(f"\\input{{model/{nsname}/{heading}/{n}}}" for n in sorted(nameslist))
        return ret

    files: dict[str, list[str]] = {}
    for ns in model.namespaces:
        nsn = ns.name
        files[nsn] = [f"\\input{{model/{nsn}/{nsn}}}"]
        files[nsn].extend(_gen_filelist(nsn, ns.classes, "Classes"))
        files[nsn].extend(_gen_filelist(nsn, ns.properties, "Properties"))
        files[nsn].extend(_gen_filelist(nsn, ns.vocabularies, "Vocabularies"))
        files[nsn].extend(_gen_filelist(nsn, ns.individuals, "Individuals"))
        files[nsn].extend(_gen_filelist(nsn, ns.datatypes, "Datatypes"))

    filelines: list[str] = []
    for nsname in model.namespace_order():
        filelines.extend(files[nsname])

    fn = outpath / "model-files.tex"
    fn.write_text("\n".join(filelines))


def tex_escape(s: str) -> str:
    """Escape special LaTeX characters in *s*."""
    s = s.replace("\\", "\\textbackslash{}")
    s = s.replace("_", "\\_")
    s = s.replace("&", "\\&")
    s = s.replace("#", "\\#")
    s = s.replace("^", "\\^")
    s = s.replace("$", "\\$")
    return s


def markdown_to_tex(s: str) -> str:
    """Convert *s* from Markdown to LaTeX via pandoc."""
    process = subprocess.run(["pandoc", "-f", "markdown", "-t", "latex"], input=s.encode("utf-8"), capture_output=True, check=False)
    return process.stdout.decode("utf-8")
