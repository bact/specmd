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

      <prop>(/<prop>)* type <Class>(, <Class>)*
      <prop>(/<prop>)* not type <Class>(, <Class>)*

  "every node reached by following the property path shall (``type``) / shall
  not (``not type``) be an instance of one of the named classes". A single
  ``<prop>`` makes this a type restriction on the property's direct value; a
  multi-hop path (e.g. ``customIdToLicense / elementValue``) restricts the type
  of a sub-property of the value.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ``if element min 1 then rootElement min 1``
_RE_COND_CARD = re.compile(r"^if\s+(?P<ante>\w+)\s+min\s+(?P<amin>\d+)\s+then\s+(?P<cons>\w+)\s+min\s+(?P<cmin>\d+)$")

# ``customIdToLicense / elementValue type CustomLicense, SimpleLicensingText``
# ``element not type SpdxDocument``
_RE_PATH_TYPE = re.compile(r"^(?P<path>\w+(?:\s*/\s*\w+)*)\s+(?P<neg>not\s+)?type\s+(?P<classes>\w[\w/]*(?:\s*,\s*\w[\w/]*)*)$")


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
        path = tuple(p.strip() for p in m.group("path").split("/") if p.strip())
        classes = tuple(c.strip() for c in m.group("classes").split(",") if c.strip())
        return PathType(path=path, classes=classes, negated=bool(m.group("neg")))
    logger.warning("Unrecognised constraint expression: %r", expr)
    return None


def _join_or(items: tuple[str, ...]) -> str:
    """Join names as an English alternative list: 'A', 'A or B', or 'A, B, or C'."""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:  # noqa: PLR2004
        return f"{items[0]} or {items[1]}"
    return ", ".join(items[:-1]) + ", or " + items[-1]


def constraint_to_prose(ast: Constraint | None, class_name: str) -> str:
    """Render an AST node as a human-readable English sentence for documentation."""
    if isinstance(ast, CondCard):
        return f"If the {class_name} has at least {ast.ante_min} {ast.ante_prop}, it shall also have at least {ast.cons_min} {ast.cons_prop}."
    if isinstance(ast, PathType):
        subject = "'s ".join(ast.path)
        modal = "shall not be" if ast.negated else "shall be"
        return f"Each {subject} {modal} of type {_join_or(ast.classes)}."
    return ""
