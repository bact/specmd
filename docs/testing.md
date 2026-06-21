---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Testing

Run the standard test suite:

```bash
pip install --group test    # or: pip install pyshacl pytest
pytest
```

## Optional dependencies

Several integration tests are skipped automatically when their tool is missing,
so a plain `pytest` run never fails for a missing optional dependency.

| Test | Needs | Notes |
| - | - | - |
| `test_lite_conformance.py` | `pyshacl` | Validates generated SHACL against data graphs. In the `test` dependency group. |
| `test_markdownlint.py` | `markdownlint-cli2` | Checks generated output passes, and that authored input survives `markdownlint --fix`. Install via npm. |
| `test_shacl2code.py` | `shacl2code` + a spec-parser checkout | See below. |

## shacl2code compatibility test

`tests/test_shacl2code.py` verifies that SpecMD RDF output produces an
**identical JSON schema** to upstream spec-parser when both are fed through
[shacl2code].

To run it, both tools must be reachable:

```bash
# 1. Install shacl2code into the same environment as specmd
pip install shacl2code

# 2. Point PYTHONPATH at your spec-parser checkout
#    (spec-parser cannot be pip-installed)
PYTHONPATH=/path/to/spec-parser pytest tests/test_shacl2code.py -v
```

Example with a sibling checkout:

```bash
PYTHONPATH=../spec-parser pytest tests/test_shacl2code.py -v
```

Expected:

```text
tests/test_shacl2code.py::TestShacl2codeCompatibility::test_jsonschema_identical PASSED
```

### Still identical for legacy input

The constraint and conformance features (type-scope, `if … then …`, profile
conformance, etc.) are *additive* and only activate on the `## Constraints` /
`## Profile conformance` sections, which legacy spec-parser Markdown does not
contain. shacl2code's `jsonschema` generator also consumes only the structural
shapes (class/property shapes, cardinality, datatype, `sh:in` enums) and ignores
the extra constraint shapes SpecMD emits. So for spec-parser's legacy Markdown
the two JSON schemas remain identical, and even a constraint-rich model would not
change the generated schema.

[shacl2code]: https://github.com/bact/shacl2code
