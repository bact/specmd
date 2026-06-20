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

      <term>(-> <term>)* type <term>(, <term>)*
      <term>(-> <term>)* not type <term>(, <term>)*

  "every node reached by following the property path shall (``type``) / shall
  not (``not type``) be an instance of one of the named classes". A single hop
  is a type restriction on the property's direct value; a multi-hop path joined
  with ``->`` (e.g. ``customIdToLicense -> elementValue``) restricts the type of
  a sub-property of the value.

  Each ``<term>`` -- a path hop or a class -- is either a bare local name
  (resolved in the owner's namespace) or a fully-qualified ``/Namespace/Name``.
  ``->`` separates path hops so that ``/`` is free to appear inside a qualified
  name, e.g. ``customIdToLicense -> /Core/elementValue type
  /ExpandedLicensing/CustomLicense, SimpleLicensingText``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ``if element min 1 then rootElement min 1``
_RE_COND_CARD = re.compile(r"^if\s+(?P<ante>\w+)\s+min\s+(?P<amin>\d+)\s+then\s+(?P<cons>\w+)\s+min\s+(?P<cmin>\d+)$")

# A term is a bare local name or a fully-qualified ``/Namespace/Name``.
_TERM = r"/\w+/\w+|\w+"

# ``customIdToLicense -> /Core/elementValue type /ExpandedLicensing/CustomLicense, SimpleLicensingText``
# ``element not type SpdxDocument``
_RE_PATH_TYPE = re.compile(
    rf"^(?P<path>(?:{_TERM})(?:\s*->\s*(?:{_TERM}))*)\s+(?P<neg>not\s+)?type\s+(?P<classes>(?:{_TERM})(?:\s*,\s*(?:{_TERM}))*)$"
)


@dataclass(frozen=True)
class CondCard:
    """Conditional cardinality: if *ante_prop* >= *ante_min* then *cons_prop* >= *cons_min*."""

    ante_prop: str
    ante_min: int
    cons_prop: str
    cons_min: int


@dataclass(frozen=True)
class PathType:
    """Type restriction on nodes reached via the property *path*.

    When *negated* is false, every reached node must be an instance of one of
    *classes*; when true, none of them may be.
    """

    path: tuple[str, ...]
    classes: tuple[str, ...]
    negated: bool = False


Constraint = CondCard | PathType


def parse_constraint(expr: str) -> Constraint | None:
    """Parse a single constraint expression into an AST node, or ``None`` if unrecognised."""
    expr = expr.strip()
    m = _RE_COND_CARD.match(expr)
    if m:
        return CondCard(
            ante_prop=m.group("ante"),
            ante_min=int(m.group("amin")),
            cons_prop=m.group("cons"),
            cons_min=int(m.group("cmin")),
        )
    m = _RE_PATH_TYPE.match(expr)
    if m:
        path = tuple(p.strip() for p in m.group("path").split("->") if p.strip())
        # Classes are a set of alternatives: drop duplicates, preserving first-seen order.
        # (The path is an ordered sequence, so its hops are not de-duplicated.)
        classes = tuple(dict.fromkeys(c.strip() for c in m.group("classes").split(",") if c.strip()))
        return PathType(path=path, classes=classes, negated=bool(m.group("neg")))
    logger.warning("Unrecognised constraint expression: %r", expr)
    return None


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


def constraint_to_prose(ast: Constraint | None, subject: str) -> str:
    """Render an AST node as a human-readable English sentence for documentation.

    *subject* names whatever the constraint hangs off: the class for a
    :class:`CondCard`, or the owning property for a property-scoped path.
    """
    if isinstance(ast, CondCard):
        return f"If the {subject} has at least {ast.ante_min} {ast.ante_prop}, it shall also have at least {ast.cons_min} {ast.cons_prop}."
    if isinstance(ast, PathType):
        path_text = "'s ".join(_render_terms(ast.path))
        modal = "shall not be" if ast.negated else "shall be"
        return f"Each {path_text} {modal} of type {_join_or(tuple(_render_terms(ast.classes)))}."
    return ""


def property_constraint_to_prose(ast: Constraint | None, prop_name: str) -> str:
    """Render a property-level constraint, scoping the path through *prop_name*.

    A property constraint applies to the property's value, so the property name
    is prepended to a path-type constraint's path before rendering.
    """
    if isinstance(ast, PathType):
        scoped = PathType(path=(prop_name, *ast.path), classes=ast.classes, negated=ast.negated)
        return constraint_to_prose(scoped, prop_name)
    return constraint_to_prose(ast, prop_name)
