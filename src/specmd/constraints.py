# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Parse constraint expressions into a small AST.

A single parsed constraint feeds two consumers so they never drift:

- :mod:`specmd.generate.rdf` emits SHACL from the AST.
- the documentation generators render human-readable prose from the AST.

A *path* is one or more terms joined with ``->`` (a SHACL sequence path); a
*term* is a bare local name (resolved in the owner's namespace) or a
fully-qualified ``/Namespace/Name`` (``/`` is reserved for qualified names, so
it is not a path separator).

Predicate forms (each usable standalone, or inside ``if … then …``)::

    <path> type <class>(, <class>)*       allowed value class(es)
    <path> not type <class>(, <class>)*   forbidden (alias for an all-``not`` list)
    <path> type A, not B                  per-item ``not`` mixes the two
    <path> matches `<regex>` [flags i]    literal pattern (sh:pattern / sh:flags)
    <path> in <lo>..<hi>                  numeric range (sh:minInclusive/maxInclusive)
    <path> is <value>                     fixed value (sh:hasValue)
    <prop> (min | max) <int>              cardinality
    <path> has <value>                    value-presence

Compound forms::

    if <predicate> then <predicate>       conditional (sh:or)
    <path> matches <selectorProperty>     per-entry pattern from the selector's vocab

Conformance blocks (``## Profile conformance``) are structured YAML, parsed in
:mod:`specmd.parse.model` into :class:`Conformance`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# A term is a bare local name or a fully-qualified ``/Namespace/Name``.
_TERM = r"/\w+/\w+|\w+"
# A class term may carry a per-item ``not``.
_CLASS = rf"(?:not\s+)?(?:{_TERM})"

# A property path: one or more terms joined with ``->``.
_PATH = rf"(?:{_TERM})(?:\s*->\s*(?:{_TERM}))*"

# ``customIdToLicense -> /Core/elementValue type /ExpandedLicensing/CustomLicense, not SimpleLicensingText``
# ``element not type SpdxDocument``  (alias: every class negated)
_RE_PATH_TYPE = re.compile(rf"^(?P<path>{_PATH})\s+(?P<neg>not\s+)?type\s+(?P<classes>(?:{_CLASS})(?:\s*,\s*(?:{_CLASS}))*)$")

# ``packageVerificationCodeExcludedFile matches `^\./` ``
# ``customIdToLicense -> key matches `^(LicenseRef-|AdditionRef-)` flags i``
_RE_PATTERN = re.compile(rf"^(?P<path>{_PATH})\s+matches\s+`(?P<regex>[^`]*)`(?:\s+flags\s+(?P<flags>[a-z]+))?$")

# ``cvssScore in 0..10``  ``cvssScore in 7.0..8.9``
_NUM = r"-?\d+(?:\.\d+)?"
_RE_RANGE = re.compile(rf"^(?P<path>{_PATH})\s+in\s+(?P<lo>{_NUM})\s*\.\.\s*(?P<hi>{_NUM})$")

# ``relationshipType is hasConcludedLicense``  (``is`` reads as a requirement, not assignment)
# A value: a bare name, a 2-segment individual (``/NS/Name``), or a 3-segment vocab entry.
_VALUE = r"/\w+/\w+(?:/\w+)?|\w+"
_RE_FIXED = re.compile(rf"^(?P<path>{_PATH})\s+is\s+(?P<value>{_VALUE})$")

# ``element min 1``  ``to max 1``  (a cardinality predicate, used standalone or inside if/then)
_RE_CARD = re.compile(rf"^(?P<path>{_PATH})\s+(?P<kind>min|max)\s+(?P<count>\d+)$")

# ``to has /Core/NoneElement``  (a value-presence predicate)
_RE_PRESENT = re.compile(rf"^(?P<path>{_PATH})\s+has\s+(?P<value>{_VALUE})$")

# ``identifier matches externalIdentifierType``  (selector binding: the value matches the
# pattern carried by the entry that *selector* currently has; the selector arg is a bare
# property, not a backtick regex, which distinguishes it from a literal ``matches``).
_RE_MATCHES_SELECTOR = re.compile(rf"^(?P<path>{_PATH})\s+matches\s+(?P<selector>{_TERM})$")


@dataclass(frozen=True)
class Cardinality:
    """A count bound on *path*: ``min`` -> ``sh:minCount``, ``max`` -> ``sh:maxCount``."""

    path: tuple[str, ...]
    kind: str  # "min" | "max"
    count: int


@dataclass(frozen=True)
class Present:
    """The node reached via *path* includes the value *value* (``sh:hasValue``)."""

    path: tuple[str, ...]
    value: str


@dataclass(frozen=True)
class PathType:
    """Type restriction on nodes reached via the property *path*.

    Every reached node must be an instance of one of *positives* (if any) and of
    none of *negatives*.
    """

    path: tuple[str, ...]
    positives: tuple[str, ...] = ()
    negatives: tuple[str, ...] = ()


@dataclass(frozen=True)
class Pattern:
    """The literal reached via *path* must match *regex* (with optional ``sh:flags``)."""

    path: tuple[str, ...]
    regex: str
    flags: str = ""


@dataclass(frozen=True)
class Range:
    """The number reached via *path* must lie in the inclusive range [*lo*, *hi*]."""

    path: tuple[str, ...]
    lo: str
    hi: str


@dataclass(frozen=True)
class Fixed:
    """The node reached via *path* must equal the individual/value *value* (``sh:hasValue``)."""

    path: tuple[str, ...]
    value: str


# A predicate constrains the nodes reached by a property path.
Predicate = Cardinality | Present | PathType | Pattern | Range | Fixed


@dataclass(frozen=True)
class Conditional:
    """``if <antecedent> then <consequent>`` -- both sides are predicates."""

    antecedent: Predicate
    consequent: Predicate


@dataclass(frozen=True)
class SelectorPattern:
    """The literal at *path* must match the ``pattern`` of the vocabulary entry that *selector* has.

    Expands per entry of the selector's range vocabulary that declares a ``pattern``.
    """

    path: tuple[str, ...]
    selector: str


@dataclass(frozen=True)
class Conformance:
    """A profile-conformance rule (tier 4), in one of three modes.

    - **existential** (``forEach`` + ``exists`` + ``linked_by``): for each
      *for_each* among a collection's *membership* values there must exist *count*
      instances of *exists* whose *linked_by* points back at it (inverse path)
      and which satisfy *where*.
    - **member predicate** (``forEach`` + ``where``, no ``exists``): each
      *for_each* member must itself satisfy *where*.
    - **collection-self** (``applies_to`` + ``where``): the collection, when it is
      an *applies_to*, must satisfy *where*.
    """

    for_each: str = ""
    membership: str = ""
    applies_to: str = ""
    exists: str = ""
    count: str = "1"
    linked_by: str = ""
    where: tuple[str, ...] = ()
    binding: str = ""  # `as:` — original subject name (now superseded by `linked_by`); reserved for `where` references


Constraint = Predicate | Conditional | SelectorPattern


def parse_constraint(expr: str) -> Constraint | None:
    """Parse a single constraint expression into an AST node, or ``None`` if unrecognised."""
    expr = expr.strip()
    if expr.startswith("if "):
        rest = expr[3:]
        sep = rest.find(" then ")
        if sep == -1:
            logger.warning("Conditional constraint missing 'then': %r", expr)
            return None
        antecedent = _parse_predicate(rest[:sep].strip())
        consequent = _parse_predicate(rest[sep + len(" then ") :].strip())
        if antecedent is None or consequent is None:
            logger.warning("Unrecognised predicate in conditional: %r", expr)
            return None
        return Conditional(antecedent=antecedent, consequent=consequent)
    pred = _parse_predicate(expr)
    if pred is not None:
        return pred
    # A selector binding (``path matches <selectorProp>``) has no backtick, so the literal
    # ``matches`` predicate above did not claim it.
    m = _RE_MATCHES_SELECTOR.match(expr)
    if m:
        return SelectorPattern(path=_split_path(m.group("path")), selector=m.group("selector"))
    logger.warning("Unrecognised constraint expression: %r", expr)
    return None


def _parse_predicate(expr: str) -> Predicate | None:
    """Parse a single (non-conditional) predicate, or ``None``."""
    result: Predicate | None = None
    if m := _RE_CARD.match(expr):
        result = Cardinality(path=_split_path(m.group("path")), kind=m.group("kind"), count=int(m.group("count")))
    elif m := _RE_PRESENT.match(expr):
        result = Present(path=_split_path(m.group("path")), value=m.group("value"))
    elif m := _RE_PATH_TYPE.match(expr):
        positives, negatives = _split_class_terms(m.group("classes"), alias_negate=bool(m.group("neg")))
        if overlap := set(positives) & set(negatives):
            logger.warning("Constraint class %s is both required and forbidden in %r", sorted(overlap), expr)
        result = PathType(path=_split_path(m.group("path")), positives=positives, negatives=negatives)
    elif m := _RE_PATTERN.match(expr):
        result = Pattern(path=_split_path(m.group("path")), regex=m.group("regex"), flags=m.group("flags") or "")
    elif m := _RE_RANGE.match(expr):
        result = Range(path=_split_path(m.group("path")), lo=m.group("lo"), hi=m.group("hi"))
    elif m := _RE_FIXED.match(expr):
        result = Fixed(path=_split_path(m.group("path")), value=m.group("value"))
    return result


def _split_path(raw: str) -> tuple[str, ...]:
    """Split a ``a -> b -> c`` path into its hops."""
    return tuple(p.strip() for p in raw.split("->") if p.strip())


def _split_class_terms(raw: str, *, alias_negate: bool) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split a class list into ``(positives, negatives)``, honouring per-item ``not`` and the alias.

    Duplicates within each bucket are dropped, first-seen order preserved.
    """
    positives: list[str] = []
    negatives: list[str] = []
    for item in (c.strip() for c in raw.split(",") if c.strip()):
        name, negated = (item[4:].strip(), True) if item.startswith("not ") else (item, False)
        (negatives if (negated or alias_negate) else positives).append(name)
    return tuple(dict.fromkeys(positives)), tuple(dict.fromkeys(negatives))


def _short(term: str) -> str:
    """Local name of a term: ``/Core/elementValue`` -> ``elementValue``, bare names unchanged."""
    return term.rsplit("/", 1)[-1]


def _render_terms(terms: tuple[str, ...]) -> list[str]:
    """Render terms by local name, keeping the full form where a local name is ambiguous.

    If two distinct terms share a local name (e.g. ``/Core/License`` and
    ``/ExpandedLicensing/License`` both shorten to ``License``), every term in
    that collision is shown fully-qualified so the prose stays unambiguous.
    """
    shorts = [_short(t) for t in terms]
    distinct: dict[str, set[str]] = {}
    for term, short in zip(terms, shorts, strict=True):
        distinct.setdefault(short, set()).add(term)
    return [term if len(distinct[short]) > 1 else short for term, short in zip(terms, shorts, strict=True)]


def _join_or(items: tuple[str, ...]) -> str:
    """Join names as an English alternative list: 'A', 'A or B', or 'A, B, or C'."""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:  # noqa: PLR2004
        return f"{items[0]} or {items[1]}"
    return ", ".join(items[:-1]) + ", or " + items[-1]


def _path_text(path: tuple[str, ...]) -> str:
    """Possessive-joined local names of a path: ``customIdToLicense's elementValue``."""
    return "'s ".join(_render_terms(path))


def _rel_word(kind: str) -> str:
    return "at least" if kind == "min" else "at most"


def _type_body(ast: PathType) -> str:
    """The ``shall (not) be of type …`` clause for a :class:`PathType`."""
    pos = _join_or(tuple(_render_terms(ast.positives))) if ast.positives else ""
    neg = _join_or(tuple(_render_terms(ast.negatives))) if ast.negatives else ""
    if pos and neg:
        return f"shall be of type {pos}, and not {neg}"
    if neg:
        return f"shall not be of type {neg}"
    return f"shall be of type {pos}"


def _flag_suffix(flags: str) -> str:
    if "i" in flags:
        return " (case-insensitive)"
    return f" (flags: {flags})" if flags else ""


def _condition_clause(ast: Predicate, subject: str) -> str:
    """Antecedent phrasing: 'the X has at least 1 element', 'the X's to includes NoneElement', …."""
    if isinstance(ast, Cardinality):
        return f"the {subject} has {_rel_word(ast.kind)} {ast.count} {_path_text(ast.path)}"
    if isinstance(ast, Present):
        return f"the {subject}'s {_path_text(ast.path)} includes {_short(ast.value)}"
    if isinstance(ast, Range):
        return f"the {subject}'s {_path_text(ast.path)} is between {ast.lo} and {ast.hi}"
    if isinstance(ast, Fixed):
        return f"the {subject}'s {_path_text(ast.path)} is {_short(ast.value)}"
    sentence = constraint_to_prose(ast, subject)
    return sentence[:1].lower() + sentence[1:].rstrip(".") if sentence else ""


def _requirement_clause(ast: Predicate) -> str:
    """Consequent phrasing, referring to the subject as 'it'/'its'."""
    result = ""
    if isinstance(ast, Cardinality):
        result = f"it shall have {_rel_word(ast.kind)} {ast.count} {_path_text(ast.path)}"
    elif isinstance(ast, Present):
        result = f"its {_path_text(ast.path)} shall include {_short(ast.value)}"
    elif isinstance(ast, Range):
        result = f"its {_path_text(ast.path)} shall be between {ast.lo} and {ast.hi}"
    elif isinstance(ast, Fixed):
        result = f"its {_path_text(ast.path)} shall be {_short(ast.value)}"
    elif isinstance(ast, PathType):
        result = f"its {_path_text(ast.path)} {_type_body(ast)}"
    elif isinstance(ast, Pattern):
        result = f"its {_path_text(ast.path)} shall match `{ast.regex}`{_flag_suffix(ast.flags)}"
    return result


def constraint_to_prose(ast: Constraint | None, subject: str) -> str:
    """Render an AST node as a human-readable English sentence for documentation.

    *subject* names whatever the constraint hangs off: the class for a class
    constraint, or the owning property for a property-scoped path.
    """
    result = ""
    if isinstance(ast, Conditional):
        result = f"If {_condition_clause(ast.antecedent, subject)}, then {_requirement_clause(ast.consequent)}."
    elif isinstance(ast, Cardinality):
        result = f"The {subject} shall have {_rel_word(ast.kind)} {ast.count} {_path_text(ast.path)}."
    elif isinstance(ast, Present):
        result = f"The {subject}'s {_path_text(ast.path)} shall include {_short(ast.value)}."
    elif isinstance(ast, PathType):
        result = f"Each {_path_text(ast.path)} {_type_body(ast)}."
    elif isinstance(ast, Pattern):
        result = f"Each {_path_text(ast.path)} shall match `{ast.regex}`{_flag_suffix(ast.flags)}."
    elif isinstance(ast, Range):
        result = f"Each {_path_text(ast.path)} shall be between {ast.lo} and {ast.hi}."
    elif isinstance(ast, Fixed):
        result = f"The {_path_text(ast.path)} shall be {_short(ast.value)}."
    elif isinstance(ast, SelectorPattern):
        result = f"Each {_path_text(ast.path)} shall match the pattern of its {_short(ast.selector)}."
    return result


def prepend_path(ast: Constraint | None, hop: str) -> Constraint | None:
    """Return a copy of a path-bearing constraint with *hop* prepended to its path.

    Used to scope a property's own constraint through the property name. Returns
    ``None`` for constraints with no single path (e.g. :class:`Conditional`).
    """
    if isinstance(ast, PathType):
        return PathType(path=(hop, *ast.path), positives=ast.positives, negatives=ast.negatives)
    if isinstance(ast, Pattern):
        return Pattern(path=(hop, *ast.path), regex=ast.regex, flags=ast.flags)
    if isinstance(ast, Range):
        return Range(path=(hop, *ast.path), lo=ast.lo, hi=ast.hi)
    if isinstance(ast, Fixed):
        return Fixed(path=(hop, *ast.path), value=ast.value)
    if isinstance(ast, Present):
        return Present(path=(hop, *ast.path), value=ast.value)
    return None


def _ast_path(ast: Constraint | None) -> tuple[str, ...] | None:
    """The path of a single-path constraint, or ``None`` for one without (e.g. :class:`Conditional`)."""
    if isinstance(ast, (PathType, Pattern, Range, Fixed, Present, SelectorPattern)):
        return ast.path
    return None


def scope_property_path(ast: Constraint | None, prop_name: str) -> Constraint | None:
    """Scope a property's own constraint through *prop_name*.

    The property name is prepended as the path's first hop — unless the author
    already wrote it explicitly (``prop_name -> …``), in which case the AST is
    returned unchanged. Returns ``None`` for constraints with no single path.
    """
    path = _ast_path(ast)
    if path is None:
        return None
    if path and _short(path[0]) == prop_name:
        return ast
    return prepend_path(ast, prop_name)


def property_constraint_to_prose(ast: Constraint | None, prop_name: str) -> str:
    """Render a property-level constraint, scoping the path through *prop_name*."""
    scoped = scope_property_path(ast, prop_name)
    return constraint_to_prose(scoped if scoped is not None else ast, prop_name)


def count_bounds(count: str) -> tuple[int | None, int | None]:
    """Parse a conformance ``count`` (``N`` / ``N..*`` / ``N..M``) into ``(min, max)``.

    A zero minimum and a ``*`` maximum are returned as ``None`` (omit the bound).
    """
    s = count.strip()
    if ".." in s:
        lo, hi = (p.strip() for p in s.split("..", 1))
        qmin = int(lo) if lo and lo != "0" else None
        qmax = None if hi == "*" else int(hi)
    else:
        qmin = qmax = int(s)
    return qmin, qmax


def _count_phrase(count: str) -> str:
    s = count.strip()
    if ".." in s:
        lo, hi = (p.strip() for p in s.split("..", 1))
        if hi == "*":
            return f"at least {lo}"
        if lo == "0":
            return f"at most {hi}"
        return f"between {lo} and {hi}"
    return f"exactly {count}"


def _where_clauses(where: tuple[str, ...], subject: str) -> str:
    """Render *where* constraints as a ``;``-joined clause list scoped to *subject*."""
    clauses = []
    for w in where:
        sentence = constraint_to_prose(parse_constraint(w), subject)
        if sentence:
            clauses.append(sentence[:1].lower() + sentence[1:].rstrip("."))
    return "; ".join(clauses)


def conformance_to_prose(rule: Conformance, profile: str, collection: str = "collection", *, is_default: bool = False) -> str:
    """Render a :class:`Conformance` rule as an English sentence for the namespace page.

    *collection* is the configured collection class's local name (e.g. ``ElementCollection``).
    *is_default* indicates the profile applies even when ``profileConformance`` is omitted.
    """
    coll = _short(collection)

    # collection-self mode: the collection, when it is an applies_to, must satisfy where.
    if rule.applies_to:
        subj = _short(rule.applies_to)
        clauses = _where_clauses(rule.where, subj)
        if is_default:
            head = f"Every {subj} (the {profile} profile applies even when profileConformance is omitted)"
        else:
            head = f"An {subj} declaring conformance to the {profile} profile"
        return f"{head} shall satisfy: {clauses}." if clauses else f"{head} conforms."

    if is_default:
        # The default profile applies to every collection (omitted profileConformance means it).
        lead = f"In any {coll} (the {profile} profile applies even when profileConformance is omitted), "
    else:
        lead = f"If any {coll} declares conformance to the {profile} profile, then "

    # existential mode: forEach member there must exist linked instances.
    if rule.exists:
        clauses = _where_clauses(rule.where, _short(rule.exists))
        base = (
            f"{lead}for every {_short(rule.for_each)} among its members there shall exist {_count_phrase(rule.count)} "
            f"{_short(rule.exists)} (linked by {_short(rule.linked_by)})"
        )
        return base + (f" satisfying: {clauses}." if clauses else ".")

    # member-predicate mode: each member must itself satisfy where.
    subj = _short(rule.for_each)
    clauses = _where_clauses(rule.where, subj)
    base = f"{lead}every {subj} among its members shall satisfy"
    return base + (f": {clauses}." if clauses else " its constraints.")
