# SPDX-License-Identifier: Apache-2.0

"""Tests that the documentation generators render class-level constraints as prose."""

from __future__ import annotations

from types import SimpleNamespace

from jinja2 import Environment, PackageLoader, select_autoescape

from specmd.constraints import constraint_to_prose, parse_constraint
from specmd.generate.singlefile import gen_singlefile
from specmd.generate.tex import tex_escape
from specmd.parse.model import Model

COND_CARD_PROSE = "If the Collection has at least 1 element, it shall also have at least 1 rootElement."
NEGATED_PROSE = "Each element shall not be of type Agent."
PATH_TYPE_PROSE = "Each customIdToLicense's elementValue shall be of type Tool or ElementMap."


class TestSinglefileConstraints:
    def test_constraints_rendered_as_prose(self, model: Model, tmp_path) -> None:
        cfg = SimpleNamespace(all_as_dict={}, autogen_header="AUTOGEN", spdx_license="CC0-1.0")
        gen_singlefile(model, tmp_path, cfg)
        page = (tmp_path / "files" / "Core" / "Classes" / "Collection.md").read_text()
        assert "#### Constraints" in page
        assert COND_CARD_PROSE in page
        assert NEGATED_PROSE in page
        assert PATH_TYPE_PROSE in page


class TestTexConstraints:
    def _render_class(self, model: Model, fqname: str) -> str:
        jinja = Environment(
            loader=PackageLoader("specmd.generate", package_path="templates/tex"),
            autoescape=select_autoescape(),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        jinja.globals = {}
        jinja.globals["not_none"] = lambda x: str(x) if x is not None else ""
        jinja.globals["tex_escape"] = tex_escape
        jinja.globals["markdown_to_tex"] = lambda s: s  # stub out pandoc
        jinja.globals["constraint_prose"] = lambda raw, cname: constraint_to_prose(parse_constraint(raw), cname)
        return jinja.get_template("class.tex.j2").render(vars(model.classes[fqname]))

    def test_constraints_rendered_as_prose(self, model: Model) -> None:
        out = self._render_class(model, "/Core/Collection")
        assert "\\spdxpagepart{Constraints}" in out
        assert COND_CARD_PROSE in out
        assert NEGATED_PROSE in out
        assert PATH_TYPE_PROSE in out
