# SPDX-License-Identifier: Apache-2.0

"""Tests for constraint expression parsing and prose rendering."""

from __future__ import annotations

from specmd.constraints import CondCard, PathType, constraint_to_prose, parse_constraint
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

    def test_path_type_single_hop(self) -> None:
        ast = parse_constraint("element type Tool")
        assert ast == PathType(path=("element",), classes=("Tool",))

    def test_path_type_multi_hop_multi_class(self) -> None:
        ast = parse_constraint("customIdToLicense -> elementValue type CustomLicense, SimpleLicensingText")
        assert ast == PathType(
            path=("customIdToLicense", "elementValue"),
            classes=("CustomLicense", "SimpleLicensingText"),
        )

    def test_path_type_negated(self) -> None:
        ast = parse_constraint("element not type SpdxDocument")
        assert ast == PathType(path=("element",), classes=("SpdxDocument",), negated=True)

    def test_path_type_qualified_terms(self) -> None:
        ast = parse_constraint("customIdToLicense -> /Core/elementValue type /ExpandedLicensing/CustomLicense, SimpleLicensingText")
        assert ast == PathType(
            path=("customIdToLicense", "/Core/elementValue"),
            classes=("/ExpandedLicensing/CustomLicense", "SimpleLicensingText"),
        )

    def test_slash_is_no_longer_a_separator(self) -> None:
        # ``/`` now only delimits qualified names; it is not a path separator.
        assert parse_constraint("customIdToLicense / elementValue type Tool") is None

    def test_duplicate_classes_removed(self) -> None:
        # The class list is a set of alternatives; exact duplicates are dropped, order preserved.
        ast = parse_constraint("x type /Core/License, Tool, /Core/License")
        assert ast == PathType(path=("x",), classes=("/Core/License", "Tool"))


class TestConstraintProse:
    def test_cond_card_prose(self) -> None:
        ast = parse_constraint("if element min 1 then rootElement min 1")
        prose = constraint_to_prose(ast, "ElementCollection")
        assert prose == ("If the ElementCollection has at least 1 element, it shall also have at least 1 rootElement.")

    def test_none_renders_empty(self) -> None:
        assert constraint_to_prose(None, "Whatever") == ""

    def test_path_type_prose(self) -> None:
        ast = parse_constraint("customIdToLicense -> elementValue type CustomLicense, CustomLicenseAddition, SimpleLicensingText")
        assert constraint_to_prose(ast, "Anything") == (
            "Each customIdToLicense's elementValue shall be of type CustomLicense, CustomLicenseAddition, or SimpleLicensingText."
        )

    def test_path_type_negated_prose(self) -> None:
        ast = parse_constraint("element not type SpdxDocument")
        assert constraint_to_prose(ast, "Anything") == "Each element shall not be of type SpdxDocument."

    def test_qualified_terms_shortened_in_prose(self) -> None:
        # Qualified path hops and class names render with their local names only.
        ast = parse_constraint("customIdToLicense -> /Core/elementValue type /ExpandedLicensing/CustomLicense, SimpleLicensingText")
        assert constraint_to_prose(ast, "LicenseExpression") == (
            "Each customIdToLicense's elementValue shall be of type CustomLicense or SimpleLicensingText."
        )

    def test_ambiguous_class_short_names_fall_back_to_qualified(self) -> None:
        # Two classes shortening to "License" must stay qualified; the unique one stays short.
        ast = parse_constraint("x type /Core/License, /ExpandedLicensing/License, SimpleLicensingText")
        assert constraint_to_prose(ast, "C") == ("Each x shall be of type /Core/License, /ExpandedLicensing/License, or SimpleLicensingText.")

    def test_ambiguous_path_hops_fall_back_to_qualified(self) -> None:
        ast = parse_constraint("/Core/a -> /Software/a type Tool")
        assert constraint_to_prose(ast, "C") == "Each /Core/a's /Software/a shall be of type Tool."

    def test_duplicate_class_collapsed_before_prose(self) -> None:
        # Duplicates are removed at parse time, so the prose lists the class once.
        ast = parse_constraint("x type /Core/License, /Core/License")
        assert constraint_to_prose(ast, "C") == "Each x shall be of type License."


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
