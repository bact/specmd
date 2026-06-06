# SPDX-License-Identifier: Apache-2.0

"""Tests for constraint expression parsing and prose rendering."""

from __future__ import annotations

from specmd.constraints import CondCard, constraint_to_prose, parse_constraint
from specmd.parse.markdown import ConstraintsSection


class TestParseConstraint:
    def test_conditional_cardinality(self) -> None:
        ast = parse_constraint("if element min 1 then rootElement min 1")
        assert ast == CondCard(ante_prop="element", ante_min=1, cons_prop="rootElement", cons_min=1)

    def test_conditional_with_larger_counts(self) -> None:
        ast = parse_constraint("if  foo   min 2 then bar min 3")
        assert ast == CondCard(ante_prop="foo", ante_min=2, cons_prop="bar", cons_min=3)

    def test_unrecognised_returns_none(self) -> None:
        assert parse_constraint("element shall be unique") is None


class TestConstraintProse:
    def test_cond_card_prose(self) -> None:
        ast = parse_constraint("if element min 1 then rootElement min 1")
        prose = constraint_to_prose(ast, "ElementCollection")
        assert prose == (
            "If the ElementCollection has at least 1 element, "
            "it shall also have at least 1 rootElement."
        )

    def test_none_renders_empty(self) -> None:
        assert constraint_to_prose(None, "Whatever") == ""


class TestConstraintsSection:
    def test_collects_top_level_items(self) -> None:
        content = "- if element min 1 then rootElement min 1\n- if a min 1 then b min 1\n"
        sec = ConstraintsSection(content)
        assert sec.constraints == [
            "if element min 1 then rootElement min 1",
            "if a min 1 then b min 1",
        ]

    def test_ignores_blank_and_nonitems(self) -> None:
        sec = ConstraintsSection("\nsome prose\n- one constraint\n")
        assert sec.constraints == ["one constraint"]
