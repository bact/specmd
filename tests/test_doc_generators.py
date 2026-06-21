# SPDX-License-Identifier: Apache-2.0

"""Tests that the documentation generators render constraints as prose.

Class-level constraints render on the class page; property-level constraints
(e.g. the ``customIdToLicense`` value-type restriction) render on the property
page, scoped through the property name.
"""

from __future__ import annotations

from types import SimpleNamespace

from jinja2 import Environment, PackageLoader, select_autoescape

from specmd.constraints import constraint_to_prose, parse_constraint, property_constraint_to_prose
from specmd.generate.singlefile import gen_singlefile
from specmd.generate.tex import tex_escape
from specmd.parse.model import Model

COND_CARD_PROSE = "If the Collection has at least 1 element, then it shall have at least 1 rootElement."
NEGATED_PROSE = "Each element shall not be of type Agent."
PATH_TYPE_PROSE = "Each customIdToLicense's elementValue shall be of type Tool or ElementMap."


class TestSinglefileConstraints:
    def test_class_constraints_on_class_page(self, model: Model, tmp_path) -> None:
        cfg = SimpleNamespace(all_as_dict={}, autogen_header="AUTOGEN", spdx_license="CC0-1.0")
        gen_singlefile(model, tmp_path, cfg)
        page = (tmp_path / "files" / "Core" / "Classes" / "Collection.md").read_text()
        assert "#### Constraints" in page
        assert COND_CARD_PROSE in page
        assert NEGATED_PROSE in page

    def test_property_constraints_on_property_page(self, model: Model, tmp_path) -> None:
        cfg = SimpleNamespace(all_as_dict={}, autogen_header="AUTOGEN", spdx_license="CC0-1.0")
        gen_singlefile(model, tmp_path, cfg)
        page = (tmp_path / "files" / "Core" / "Properties" / "customIdToLicense.md").read_text()
        assert "#### Constraints" in page
        assert PATH_TYPE_PROSE in page


class TestTexConstraints:
    def _jinja(self) -> Environment:
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
        jinja.globals["property_constraint_prose"] = lambda raw, pname: property_constraint_to_prose(parse_constraint(raw), pname)
        return jinja

    def test_class_constraints_on_class_page(self, model: Model) -> None:
        out = self._jinja().get_template("class.tex.j2").render(vars(model.classes["/Core/Collection"]))
        assert "\\spdxpagepart{Constraints}" in out
        assert COND_CARD_PROSE in out
        assert NEGATED_PROSE in out

    def test_property_constraints_on_property_page(self, model: Model) -> None:
        out = self._jinja().get_template("property.tex.j2").render(vars(model.properties["/Core/customIdToLicense"]))
        assert "\\spdxpagepart{Constraints}" in out
        assert PATH_TYPE_PROSE in out
