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
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ``if element min 1 then rootElement min 1``
_RE_COND_CARD = re.compile(
    r"^if\s+(?P<ante>\w+)\s+min\s+(?P<amin>\d+)\s+then\s+(?P<cons>\w+)\s+min\s+(?P<cmin>\d+)$"
)


@dataclass(frozen=True)
class CondCard:
    """Conditional cardinality: if *ante_prop* >= *ante_min* then *cons_prop* >= *cons_min*."""

    ante_prop: str
    ante_min: int
    cons_prop: str
    cons_min: int


Constraint = CondCard


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
    logger.warning("Unrecognised constraint expression: %r", expr)
    return None


def constraint_to_prose(ast: Constraint | None, class_name: str) -> str:
    """Render an AST node as a human-readable English sentence for documentation."""
    if isinstance(ast, CondCard):
        return (
            f"If the {class_name} has at least {ast.ante_min} {ast.ante_prop}, "
            f"it shall also have at least {ast.cons_min} {ast.cons_prop}."
        )
    return ""
