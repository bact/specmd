# Agent instructions

## Project context

- Reads Markdown model files from structured directories; generates RDF/OWL/SHACL,
  MkDocs Markdown, PlantUML diagrams, TeX, and single-file Markdown.
- Test fixtures: `tests/fixtures/README.md`
- Design docs: `docs/design.md`
- Private alpha, one developer. No backward compat needed yet.

## specmd.yml configuration

Top-level scalar keys: `license` (SPDX ID), `base-uri`, `namespace-order`,
`include-unlisted-namespaces`.

Sub-blocks: `vocabulary`, `ontology`, `rdf`, `plantuml`.

Key points:

- Vocab/relationship defaults (`default-from`, `default-to`,
  `default-relationship-class`) live under `vocabulary:`, not at the top level.
- `ontology.license-uri` — URI of the ontology licence.
  Distinct from top-level `license`, which is an SPDX identifier string.

Internal variable convention:

- `cfg_*` prefix — scalar config value (`str | None`).
- `*_cfg` suffix — config sub-block (`dict`).

Canonical reference: `docs/specmd.yml.example`.

## CLI commands

Four subcommands: `generate` (alias `gen`), `validate`, `migrate`, `export`.

**`validate`** accepts a model directory OR a single `.md` file.

- Directory: two passes — (1) raw YAML check (`yaml.safe_load` on `## Entries`
  and `## Properties` sections), then (2) full `Model` load.
- Single file: raw YAML check only (no `Model` loading).
- `--strict`: exit non-zero if raw YAML issues found (default: warn only).
- Always prints a summary line: `N file(s) checked, M file(s) with issues.`
- Raw YAML check logic lives in `src/specmd/commands/validate.py`.
  `Format` sections are excluded — they use specmd backtick syntax
  (`- pattern: \`regex\``) which is not raw YAML.

**`migrate`** also validates its own output after generating it (`_warn_invalid_entries_yaml`).

## CLI output

- Unix philosophy: consistent, predictable, parseable.
- Errors: `ERROR: <short description>` to stderr.

## Markdown output

- Generated Markdown must pass markdownlint-cli2.
- Targets MkDocs (Python-Markdown). Avoid GitHub-specific extensions.
- `singlefile` outputs Markdown for downstream Pandoc conversion; specmd itself
  does not invoke Pandoc for it. `tex` does invoke Pandoc internally.
- Generated file headers: YAML front matter. Omit optional fields when empty.
- Do not hardcode license or metadata in templates; read from model
  (`Model.spdx_license`).
- markdownlint config at `src/specmd/generate/markdownlint-cli2.yaml`;
  written as `.markdownlint-cli2.yaml` (dot-prefixed) to each output directory.

## Jinja2 templates

Templates: `src/specmd/generate/templates/{format}/`.
All environments: `trim_blocks=True, lstrip_blocks=True`.

`trim_blocks` eats only the `\n` immediately after `%}`. Put blank separators
**inside** conditional blocks, not outside, to avoid unconditional blank lines.

List items: `{% endif %}` at end-of-line collapses items. Use capture pattern:

```jinja2
{% set extra %}{% if condition %} text{% endif %}{% endset %}
- item{{extra}}
```

Avoid `<br />` (requires MD033 allowlist). Use `&nbsp;` for indentation.

## Vocabulary qualifier syntax

`from`/`to` entries may carry qualifiers:

```
ClassName[propName=value]
ClassName[propName=v1,v2;otherProp=v3]
```

`;` separates properties; `,` separates values. Parsed by
`_parse_qualified_class` → `(base: str, qualifiers: dict[str, list[str]])`.

## Python

- Min version: Python 3.11.
- Full type annotations. Minimize `Any`. `if TYPE_CHECKING:` for heavy imports.
- Verify with mypy (`strict=true`).
- No `assert` in production code.

## Linting

Run before committing: `ruff check --fix`, `mypy`, `pylint`, `ruff format`.

Limits: return statements ≤ 6, arguments ≤ 5, local variables ≤ 15,
nested blocks ≤ 5, McCabe complexity ≤ 10.
Line length: max 88, target 80.

## File headers

All source files — SPDX tags, alphabetical order:

```text
SPDX-FileCopyrightText: <year> <name>
SPDX-FileType: SOURCE          # or DOCUMENTATION
SPDX-License-Identifier: Apache-2.0  # CC0-1.0 for docs
```

## Testing

- pytest patterns. `@pytest.mark.parametrize` for multiple inputs.
- Optional-dependency tests use `pytest.importorskip` at **module level** so
  they are silently skipped; never gate with `try/except ImportError` inside a
  test function.
- `spec_parser` is not pip-installable; expose via
  `PYTHONPATH=/path/to/spec-parser pytest tests/test_shacl2code.py`.
  See README for full invocation.

## Naming and IRIs

- Ontology terms: consult W3C, Schema.org, SEMIC Style Guide
  (<https://semiceu.github.io/style-guide/1.0.0/index.html>).
- IRIs: lowercase + hyphens. W3C Cool URIs: <https://www.w3.org/TR/cooluris/>.

## Writing style

- British English for docs and comments; American English in code only.
- IETF verbal forms (RFC 2119/8174) for RDF/web docs; ISO verbal forms for SPDX spec docs.

## Project metadata

Keep in sync: `pyproject.toml`, `codemeta.json`, `CITATION.cff`.

## Boundaries

**Ask before doing:** large cross-package refactors, new broad-impact
dependencies, destructive data or migration changes.

**Never:** commit secrets; edit generated files by hand when a generation
workflow exists; use destructive git operations unless explicitly requested.
