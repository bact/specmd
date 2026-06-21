# SPDX-License-Identifier: Apache-2.0

"""Tests for constraint expression parsing and prose rendering."""

from __future__ import annotations

from specmd.constraints import (
    Cardinality,
    Conditional,
    Conformance,
    Fixed,
    PathType,
    Pattern,
    Present,
    Range,
    SelectorPattern,
    conformance_to_prose,
    constraint_to_prose,
    count_bounds,
    parse_constraint,
    scope_property_path,
)
from specmd.parse.markdown import ConstraintsSection


class TestParseConstraint:
    def test_conditional_cardinality(self) -> None:
        ast = parse_constraint("if element min 1 then rootElement min 1")
        assert ast == Conditional(
            antecedent=Cardinality(path=("element",), kind="min", count=1),
            consequent=Cardinality(path=("rootElement",), kind="min", count=1),
        )

    def test_conditional_value_presence(self) -> None:
        ast = parse_constraint("if to has /Core/NoneElement then to max 1")
        assert ast == Conditional(
            antecedent=Present(path=("to",), value="/Core/NoneElement"),
            consequent=Cardinality(path=("to",), kind="max", count=1),
        )

    def test_conditional_range_then_fixed(self) -> None:
        ast = parse_constraint("if cvssScore in 7.0..8.9 then cvssSeverity is high")
        assert ast == Conditional(
            antecedent=Range(path=("cvssScore",), lo="7.0", hi="8.9"),
            consequent=Fixed(path=("cvssSeverity",), value="high"),
        )

    def test_unrecognised_returns_none(self) -> None:
        assert parse_constraint("element shall be unique") is None

    def test_path_type_single_hop(self) -> None:
        ast = parse_constraint("element type Tool")
        assert ast == PathType(path=("element",), positives=("Tool",))

    def test_path_type_multi_hop_multi_class(self) -> None:
        ast = parse_constraint("customIdToLicense -> elementValue type CustomLicense, SimpleLicensingText")
        assert ast == PathType(
            path=("customIdToLicense", "elementValue"),
            positives=("CustomLicense", "SimpleLicensingText"),
        )

    def test_path_type_negated_alias(self) -> None:
        ast = parse_constraint("element not type SpdxDocument")
        assert ast == PathType(path=("element",), negatives=("SpdxDocument",))

    def test_path_type_per_item_not(self) -> None:
        ast = parse_constraint("element type Tool, not /Core/SpdxDocument")
        assert ast == PathType(path=("element",), positives=("Tool",), negatives=("/Core/SpdxDocument",))

    def test_path_type_qualified_terms(self) -> None:
        ast = parse_constraint("customIdToLicense -> /Core/elementValue type /ExpandedLicensing/CustomLicense, SimpleLicensingText")
        assert ast == PathType(
            path=("customIdToLicense", "/Core/elementValue"),
            positives=("/ExpandedLicensing/CustomLicense", "SimpleLicensingText"),
        )

    def test_slash_is_no_longer_a_separator(self) -> None:
        # ``/`` now only delimits qualified names; it is not a path separator.
        assert parse_constraint("customIdToLicense / elementValue type Tool") is None

    def test_duplicate_classes_removed(self) -> None:
        # The class list is a set of alternatives; exact duplicates are dropped, order preserved.
        ast = parse_constraint("x type /Core/License, Tool, /Core/License")
        assert ast == PathType(path=("x",), positives=("/Core/License", "Tool"))

    def test_pattern_simple(self) -> None:
        ast = parse_constraint("packageVerificationCodeExcludedFile matches `^\\./`")
        assert ast == Pattern(path=("packageVerificationCodeExcludedFile",), regex="^\\./")

    def test_pattern_path_and_flags(self) -> None:
        ast = parse_constraint("customIdToLicense -> key matches `^(LicenseRef-|AdditionRef-)` flags i")
        assert ast == Pattern(path=("customIdToLicense", "key"), regex="^(LicenseRef-|AdditionRef-)", flags="i")

    def test_range_decimal(self) -> None:
        assert parse_constraint("cvssScore in 0..10") == Range(path=("cvssScore",), lo="0", hi="10")
        assert parse_constraint("cvssScore in 7.0..8.9") == Range(path=("cvssScore",), lo="7.0", hi="8.9")

    def test_fixed_value(self) -> None:
        assert parse_constraint("relationshipType is hasConcludedLicense") == Fixed(path=("relationshipType",), value="hasConcludedLicense")

    def test_selector_pattern(self) -> None:
        ast = parse_constraint("identifier matches externalIdentifierType")
        assert ast == SelectorPattern(path=("identifier",), selector="externalIdentifierType")

    def test_selector_pattern_not_confused_with_literal(self) -> None:
        # A backtick arg is a literal Pattern, not a selector binding.
        assert isinstance(parse_constraint("identifier matches `^x`"), Pattern)


class TestConstraintProse:
    def test_cond_card_prose(self) -> None:
        ast = parse_constraint("if element min 1 then rootElement min 1")
        prose = constraint_to_prose(ast, "ElementCollection")
        assert prose == "If the ElementCollection has at least 1 element, then it shall have at least 1 rootElement."

    def test_conditional_presence_prose(self) -> None:
        ast = parse_constraint("if to has /Core/NoneElement then to max 1")
        assert constraint_to_prose(ast, "Relationship") == ("If the Relationship's to includes NoneElement, then it shall have at most 1 to.")

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

    def test_path_type_mixed_prose(self) -> None:
        ast = parse_constraint("element type Agent, not /Core/SpdxDocument")
        assert constraint_to_prose(ast, "Anything") == "Each element shall be of type Agent, and not SpdxDocument."

    def test_pattern_prose_case_insensitive(self) -> None:
        ast = parse_constraint("customIdToLicense -> key matches `^(LicenseRef-|AdditionRef-)` flags i")
        assert constraint_to_prose(ast, "Anything") == (
            "Each customIdToLicense's key shall match `^(LicenseRef-|AdditionRef-)` (case-insensitive)."
        )

    def test_range_prose(self) -> None:
        ast = parse_constraint("cvssScore in 0..10")
        assert constraint_to_prose(ast, "Anything") == "Each cvssScore shall be between 0 and 10."

    def test_fixed_prose(self) -> None:
        ast = parse_constraint("relationshipType is /Core/RelationshipType/hasConcludedLicense")
        assert constraint_to_prose(ast, "Anything") == "The relationshipType shall be hasConcludedLicense."

    def test_selector_pattern_prose(self) -> None:
        ast = parse_constraint("identifier matches externalIdentifierType")
        assert constraint_to_prose(ast, "ExternalIdentifier") == ("Each identifier shall match the pattern of its externalIdentifierType.")

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


class TestScopePropertyPath:
    """Property-file constraints scope through the property name, tolerating an explicit first hop."""

    def test_prepends_property_name(self) -> None:
        ast = parse_constraint("key matches `^x`")
        assert scope_property_path(ast, "customIdToLicense") == Pattern(path=("customIdToLicense", "key"), regex="^x")

    def test_explicit_first_hop_not_doubled(self) -> None:
        ast = parse_constraint("customIdToLicense -> key matches `^x`")
        assert scope_property_path(ast, "customIdToLicense") == Pattern(path=("customIdToLicense", "key"), regex="^x")

    def test_explicit_qualified_first_hop_not_doubled(self) -> None:
        ast = parse_constraint("/Core/customIdToLicense -> key matches `^x`")
        assert scope_property_path(ast, "customIdToLicense") == Pattern(path=("/Core/customIdToLicense", "key"), regex="^x")

    def test_non_path_constraint_returns_none(self) -> None:
        ast = parse_constraint("if element min 1 then rootElement min 1")
        assert scope_property_path(ast, "element") is None


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


class TestConformance:
    def test_count_bounds(self) -> None:
        assert count_bounds("1") == (1, 1)
        assert count_bounds("1..*") == (1, None)
        assert count_bounds("0..1") == (None, 1)
        assert count_bounds("2..5") == (2, 5)

    def test_conformance_prose(self) -> None:
        rule = Conformance(
            for_each="/Core/SoftwareArtifact",
            membership="element",
            exists="/Core/Relationship",
            count="1",
            linked_by="from",
            where=("relationshipType is hasConcludedLicense", "to type /Core/AnyLicenseInfo"),
        )
        assert conformance_to_prose(rule, "Core") == (
            "If any collection declares conformance to the Core profile, then for every SoftwareArtifact among its "
            "members there shall exist exactly 1 Relationship (linked by from) satisfying: the relationshipType "
            "shall be hasConcludedLicense; each to shall be of type AnyLicenseInfo."
        )

    def test_conformance_prose_default_profile(self) -> None:
        rule = Conformance(
            for_each="/Core/SoftwareArtifact",
            membership="element",
            exists="/Core/Relationship",
            count="1",
            linked_by="from",
            where=("relationshipType is hasConcludedLicense",),
        )
        prose = conformance_to_prose(rule, "Core", "/Core/ElementCollection", is_default=True)
        assert prose.startswith("In any ElementCollection (the Core profile applies even when profileConformance is omitted), for every")

    def test_conformance_prose_member_predicate(self) -> None:
        rule = Conformance(for_each="/Core/SoftwareArtifact", membership="element", where=("name min 1",))
        assert conformance_to_prose(rule, "Lite", "/Core/ElementCollection") == (
            "If any ElementCollection declares conformance to the Lite profile, then every SoftwareArtifact among "
            "its members shall satisfy: the SoftwareArtifact shall have at least 1 name."
        )

    def test_conformance_prose_collection_self(self) -> None:
        rule = Conformance(applies_to="/Core/SpdxDocument", where=("element min 1", "rootElement min 1"))
        assert conformance_to_prose(rule, "Lite") == (
            "An SpdxDocument declaring conformance to the Lite profile shall satisfy: the SpdxDocument shall have "
            "at least 1 element; the SpdxDocument shall have at least 1 rootElement."
        )
