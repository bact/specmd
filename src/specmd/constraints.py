# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Parse class-level constraint expressions into a small AST.

A single parsed constraint feeds two consumers so they never drift:

- :mod:`specmd.generate.rdf` emits SHACL from the AST.
- the documentation generators render human-readable prose from the AST.

Supported syntax (one constraint per ``- `` list item in a ``## Constraints``
section):

- Conditional cardinality::

      if <prop> min <m> then <prop> min <n>

  "if the class has at least *m* ``<prop>``, it shall also have at least
  *n* ``<prop>``".

- Property-path value type::

      <term>(-> <term>)* type <class-term>(, <class-term>)*

  where each ``<class-term>`` is ``<term>`` (allowed) or ``not <term>``
  (forbidden). Every node reached by the property path must be an instance of
  one of the *positive* classes and of none of the *negative* ones. A single hop
  restricts the property's direct value; a multi-hop path joined with ``->``
  (e.g. ``customIdToLicense -> elementValue``) restricts a sub-property of the
  value.

  ``<path> not type <list>`` is an accepted alias meaning every class is
  negated.

  Each ``<term>`` -- a path hop or a class -- is either a bare local name
  (resolved in the owner's namespace) or a fully-qualified ``/Namespace/Name``.
  ``->`` separates path hops so that ``/`` is free to appear inside a qualified
  name, e.g. ``customIdToLicense -> /Core/elementValue type
  /ExpandedLicensing/CustomLicense, not SimpleLicensingText``.
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


Constraint = Predicate | Conditional


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
    if pred is None:
        logger.warning("Unrecognised constraint expression: %r", expr)
    return pred


def _parse_predicate(expr: str) -> Predicate | None:  # noqa: PLR0911
    """Parse a single (non-conditional) predicate, or ``None``."""
    m = _RE_CARD.match(expr)
    if m:
        return Cardinality(path=_split_path(m.group("path")), kind=m.group("kind"), count=int(m.group("count")))
    m = _RE_PRESENT.match(expr)
    if m:
        return Present(path=_split_path(m.group("path")), value=m.group("value"))
    m = _RE_PATH_TYPE.match(expr)
    if m:
        positives, negatives = _split_class_terms(m.group("classes"), alias_negate=bool(m.group("neg")))
        overlap = set(positives) & set(negatives)
        if overlap:
            logger.warning("Constraint class %s is both required and forbidden in %r", sorted(overlap), expr)
        return PathType(path=_split_path(m.group("path")), positives=positives, negatives=negatives)
    m = _RE_PATTERN.match(expr)
    if m:
        return Pattern(path=_split_path(m.group("path")), regex=m.group("regex"), flags=m.group("flags") or "")
    m = _RE_RANGE.match(expr)
    if m:
        return Range(path=_split_path(m.group("path")), lo=m.group("lo"), hi=m.group("hi"))
    m = _RE_FIXED.match(expr)
    if m:
        return Fixed(path=_split_path(m.group("path")), value=m.group("value"))
    return None


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


def _requirement_clause(ast: Predicate) -> str:  # noqa: PLR0911
    """Consequent phrasing, referring to the subject as 'it'/'its'."""
    if isinstance(ast, Cardinality):
        return f"it shall have {_rel_word(ast.kind)} {ast.count} {_path_text(ast.path)}"
    if isinstance(ast, Present):
        return f"its {_path_text(ast.path)} shall include {_short(ast.value)}"
    if isinstance(ast, Range):
        return f"its {_path_text(ast.path)} shall be between {ast.lo} and {ast.hi}"
    if isinstance(ast, Fixed):
        return f"its {_path_text(ast.path)} shall be {_short(ast.value)}"
    if isinstance(ast, PathType):
        return f"its {_path_text(ast.path)} {_type_body(ast)}"
    if isinstance(ast, Pattern):
        return f"its {_path_text(ast.path)} shall match `{ast.regex}`{_flag_suffix(ast.flags)}"
    return ""


def constraint_to_prose(ast: Constraint | None, subject: str) -> str:  # noqa: PLR0911
    """Render an AST node as a human-readable English sentence for documentation.

    *subject* names whatever the constraint hangs off: the class for a class
    constraint, or the owning property for a property-scoped path.
    """
    if isinstance(ast, Conditional):
        return f"If {_condition_clause(ast.antecedent, subject)}, then {_requirement_clause(ast.consequent)}."
    if isinstance(ast, Cardinality):
        return f"The {subject} shall have {_rel_word(ast.kind)} {ast.count} {_path_text(ast.path)}."
    if isinstance(ast, Present):
        return f"The {subject}'s {_path_text(ast.path)} shall include {_short(ast.value)}."
    if isinstance(ast, PathType):
        return f"Each {_path_text(ast.path)} {_type_body(ast)}."
    if isinstance(ast, Pattern):
        return f"Each {_path_text(ast.path)} shall match `{ast.regex}`{_flag_suffix(ast.flags)}."
    if isinstance(ast, Range):
        return f"Each {_path_text(ast.path)} shall be between {ast.lo} and {ast.hi}."
    if isinstance(ast, Fixed):
        return f"The {_path_text(ast.path)} shall be {_short(ast.value)}."
    return ""


def prepend_path(ast: Constraint | None, hop: str) -> Constraint | None:
    """Return a copy of a path-bearing constraint with *hop* prepended to its path.

    Used to scope a property's own constraint through the property name. Returns
    ``None`` for constraints with no path (e.g. :class:`CondCard`).
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


def property_constraint_to_prose(ast: Constraint | None, prop_name: str) -> str:
    """Render a property-level constraint, scoping the path through *prop_name*."""
    scoped = prepend_path(ast, prop_name)
    return constraint_to_prose(scoped if scoped is not None else ast, prop_name)
