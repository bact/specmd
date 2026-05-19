# SPDX-License-Identifier: Apache-2.0
"""Serialise the model as a single concatenated Markdown document."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jinja2 import Environment, PackageLoader, select_autoescape

if TYPE_CHECKING:
    from specmd.parse.model import Model

logger = logging.getLogger(__name__)


def gen_singlefile(model: Model, outpath: Path, cfg: Any) -> None:  # pylint: disable=unused-argument
    """Render every model element through Jinja2 templates and concatenate into ``model.md``."""
    jinja = Environment(
        loader=PackageLoader("specmd.generate", package_path="templates/singlefile"),
        autoescape=select_autoescape(),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    jinja.globals = cfg.all_as_dict
    jinja.globals["show_name"] = show_name
    jinja.globals["ext_property_name"] = ext_property_name
    jinja.globals["not_none"] = lambda x: str(x) if x is not None else ""

    output_file = outpath / "model.md"
    p = outpath / "files"
    p.mkdir()

    for ns in model.namespaces:
        d = p / ns.name
        d.mkdir()
        f = d / f"{ns.name}.md"
        template = jinja.get_template("namespace.md.j2")
        f.write_text(template.render(vars(ns)))

    def _generate_in_dir(dirname: str, group: dict[str, Any], tmplfname: str) -> None:
        for s in group.values():
            d = p / s.ns.name / dirname
            d.mkdir(exist_ok=True)
            f = d / f"{s.name}.md"
            template = jinja.get_template(tmplfname)
            f.write_text(template.render(vars(s)))

    _generate_in_dir("Classes", model.classes, "class.md.j2")
    _generate_in_dir("Properties", model.properties, "property.md.j2")
    _generate_in_dir("Vocabularies", model.vocabularies, "vocabulary.md.j2")
    _generate_in_dir("Individuals", model.individuals, "individual.md.j2")
    _generate_in_dir("Datatypes", model.datatypes, "datatype.md.j2")

    def _add_content(f: Path) -> None:
        with output_file.open("a", encoding="utf-8") as of:
            of.write(f.read_text(encoding="utf-8"))
            of.write("\n")

    def _add_string(s: str) -> None:
        with output_file.open("a", encoding="utf-8") as of:
            of.write(s)

    _write_markdownlint_config(outpath)
    license_id = model.spdx_license
    license_line = f"SPDX-License-Identifier: {license_id}\n" if license_id and license_id.strip() else ""
    frontmatter = f"---\n# {cfg.autogen_header}\n{license_line}---\n\n"
    output_file.write_text(frontmatter, encoding="utf-8")

    for nsname in model.namespace_order():
        f = p / nsname / f"{nsname}.md"
        _add_content(f)
        for subdirname in ["Classes", "Properties", "Vocabularies", "Individuals", "Datatypes"]:
            subdir = p / nsname / subdirname
            if subdir.is_dir():
                _add_string(f"## {subdirname}\n\n")
                for f in sorted(subdir.glob("*.md")):
                    _add_content(f)

    # Ensure file ends with exactly one newline (avoid double-blank at EOF)
    assembled = output_file.read_text(encoding="utf-8")
    output_file.write_text(assembled.rstrip("\n") + "\n", encoding="utf-8")


def _write_markdownlint_config(outpath: Path) -> None:
    """Write the bundled markdownlint-cli2 config into the output directory.

    Consumers of the generated docs can run ``markdownlint-cli2 "**/*.md"``
    without supplying their own config — intentional patterns (HTML hierarchy
    tree, long table lines, etc.) are already accounted for.
    """
    src = Path(__file__).parent / "markdownlint-cli2.yaml"
    (outpath / ".markdownlint-cli2.yaml").write_bytes(src.read_bytes())


def show_name(name: str, *, showshort: bool = False) -> str:
    """Format a fully-qualified name for display.

    If *showshort* is True, returns only the local part; otherwise the full ``/ns/Name`` form.
    """
    if name.startswith("/"):
        _, other_ns, name = name.split("/")
        return name if showshort else f"/{other_ns}/{name}"
    return name


def ext_property_name(name: str) -> str:
    """Return a human-readable label for an external property restriction path ``/ns/Class/prop``."""
    _, pns, pclass, pname = name.split("/")
    return f"{pname} from /{pns}/{pclass}"
