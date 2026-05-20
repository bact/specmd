---
SPDX-FileCopyrightText: 2026 Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SpecMD

[![PyPI - Version](https://img.shields.io/pypi/v/specmd)](https://pypi.org/project/specmd/)
![GitHub License](https://img.shields.io/github/license/bact/specmd)

Convert Markdown model definitions to RDF ontologies
and specification documents.

## Contents

- [Functionality](#functionality)
- [Installation](#installation)
- [Prerequisites](#prerequisites)
- [Usage](#usage)
  - [Validate](#validate)
  - [Generate](#generate)
  - [Migrate](#migrate)
  - [Export](#export)
  - [Common options](#common-options)
- [Model configuration](#model-configuration)
- [spec-parser compatibility](#spec-parser-compatibility)
- [Testing](#testing)
  - [shacl2code compatibility test](#shacl2code-compatibility-test)
- [Design notes](#design-notes)

## Functionality

SpecMD reads and validates the complete model directory before
generating output.
It can then generate one or more of the following outputs:

| Format | Description |
| - | - |
| `jsondump` | JSON dump of the parsed model |
| `mkdocs` | MkDocs source files for website generation |
| `plantuml` | PlantUML diagram source |
| `rdf` | OWL+SHACL ontology and JSON-LD context |
| `tex` | TeX source for printable specification |
| `singlefile` | Single Markdown file (suitable for conversion to Word, PDF, etc.) |
| `webpages` | Per-IRI web pages *(not yet implemented)* |

## Installation

```shell
pip install specmd
```

## Prerequisites

All Python dependencies are installed automatically with `pip install specmd`.
External tools required for specific formats:

| Format | External prerequisite |
| - | - |
| `tex` | [pandoc](https://pandoc.org/) -- used to convert Markdown fragments to LaTeX |
| All others | None |

## Usage

SpecMD uses subcommands:

```text
specmd <command> [options]

Commands:
  generate (gen)   Generate output artefacts from a model directory
  validate         Validate a model directory or a single .md file
  migrate          Convert spec-parser format to SpecMD format
  export           Export a SpecMD model to another format
```

### Validate

Check raw YAML syntax of every `.md` file, then fully parse the model:

```shell
specmd validate path/to/model
```

Validate a single file (raw YAML syntax check only):

```shell
specmd validate path/to/file.md
```

Use `--strict` to exit with a non-zero code when raw YAML issues are found
(without `--strict` they are reported as warnings but do not fail the command):

```shell
specmd validate --strict path/to/model
```

The validator runs two passes on a directory:

1. **Raw YAML check** — each `## Entries` and `## Properties` section is
   parsed with `yaml.safe_load` to catch characters and constructs
   that cause parse errors in strict YAML consumers (e.g. a value
   starting with `[` or `{`, or a bare `:` inside a plain scalar).
2. **Full model parse** — the complete model is loaded and cross-referenced,
   reporting semantic errors (unknown classes, missing metadata, etc.).

A summary line is always printed: `N file(s) checked, M file(s) with issues.`

### Generate

Generate all output formats into subdirectories under `./out/`:

```shell
specmd generate path/to/model --output ./out
```

Generate specific formats only:

```shell
specmd generate path/to/model --formats rdf,mkdocs --output ./out
```

Override the output directory for a single format:

```shell
specmd generate path/to/model --output ./out --rdf-dir ./ontology
```

Available formats:
`jsondump`, `mkdocs`, `plantuml`, `rdf`, `tex`, `singlefile`, `webpages`.

### Migrate

Convert a model written in the spec-parser format to SpecMD format:

```shell
specmd migrate path/to/old-model --output path/to/new-model
```

### Export

Export a SpecMD model back to the spec-parser format:

```shell
specmd export path/to/model --output path/to/exported --format legacy
```

### Common options

| Option | Commands | Description |
| - | - | - |
| `-o`/`--output DIR` | `generate`, `migrate`, `export` | Output directory |
| `-f`/`--force` | `generate`, `migrate`, `export` | Overwrite existing output |
| `--strict` | `validate` | Exit non-zero on raw YAML warnings |
| `-q`/`--quiet` | all | Warnings and errors only |
| `-v`/`--verbose` | all | Debug output |
| `-V`/`--version` | top-level | Show version and exit |

Full help:

```shell
specmd --help
specmd generate --help
```

## Model configuration

An optional `specmd.yml` file at the model root controls parsing and
generation.

Key settings:

```yaml
license: CC0-1.0           # SPDX license ID for generated output
base-uri: https://example.org/rdf/terms/  # ontology base URI
namespace-order: [Core]    # namespace processing order

ontology:                  # OWL ontology metadata
  preferred-namespace-prefix: myns
  label: My Model Ontology
  creator: My Organisation
  license-uri: https://example.org/licenses/my-license/

vocabulary:                # vocabulary / relationship defaults
  default-from: Element    # default vocab entry source class
  default-to: Element      # default vocab entry target class
  default-relationship-class: Relationship

rdf:
  filename: my-model       # output filename (no extension)
```

See [docs/format.md](docs/format.md#model-configuration-specmdyml) for
the full reference.

## spec-parser compatibility

A `main.py` compatibility shim is provided for existing CI/scripts that
invoke the [spdx/spec-parser] CLI.

It accepts spec-parser's original command-line arguments, internally runs
`specmd migrate` on the input, then `specmd generate` or `specmd validate`.

**Drop-in from a workflow perspective:** replacing `spec-parser` with `specmd`
requires only a one-line change in CI (see below), and SpecMD accepts the
original Markdown format as input via automatic migration.

**Output will differ:** the generated RDF/OWL/SHACL and MkDocs Markdown are
not byte-for-byte identical to spec-parser output. SpecMD incorporates
correctness fixes and improvements to the generated artefacts (see
[docs/design.md](docs/design.md)). Downstream consumers of the RDF or MkDocs output should
expect and review these differences.

Simply replace `python spec-parser/main.py` with `python specmd/main.py` in
existing workflows.

Or, in a GitHub workflow that checks out the repository, only the repository
name needs to change - the checkout path, the pip install command, and every
main.py option stay the same:

From:

```yaml
      - uses: actions/checkout@6
        with:
          repository: spdx/spec-parser
          path: spec-parser
      - run: |
          pip install -r spec-parser/requirements.txt
          python3 spec-parser/main.py --force --generate-mkdocs --output-mkdocs spdx-spec/docs/model spdx-3-model/model
```

To:

```yaml
      - uses: actions/checkout@6
        with:
          repository: bact/specmd  #changed
          path: spec-parser
      - run: |
          pip install -r spec-parser/requirements.txt
          python3 spec-parser/main.py --force --generate-mkdocs --output-mkdocs spdx-spec/docs/model spdx-3-model/model
```

## Testing

Run the standard test suite:

```bash
pip install pytest
pytest
```

### shacl2code compatibility test

`tests/test_shacl2code.py` verifies that SpecMD RDF output produces
**identical JSON schema** to upstream spec-parser when both are fed through
[shacl2code]. This test is skipped automatically when either dependency is
absent, so it will not block a plain `pytest` run.

To run it, both tools must be reachable:

```bash
# 1. Install shacl2code
pip install shacl2code

# 2. Point PYTHONPATH at your spec-parser checkout
#    (spec-parser cannot be pip-installed)
PYTHONPATH=/path/to/spec-parser pytest tests/test_shacl2code.py -v
```

Example with a sibling checkout:

```bash
PYTHONPATH=../spec-parser pytest tests/test_shacl2code.py -v
```

Expected output:

```text
tests/test_shacl2code.py::TestShacl2codeCompatibility::test_jsonschema_identical PASSED
```

## Design notes

SpecMD is built on the design of [spdx/spec-parser], targeting
compatibility with existing workflows. The Markdown input format is
nearly identical; key differences include standard YAML front matter,
camelCase metadata keys, a structured vocabulary entry format, and
structured deprecation fields.

The RDF/OWL/SHACL output makes a set of deliberate design decisions
around JSON-LD context correctness, SHACL shape simplification,
OWL version metadata, and abstract class disjointness.
The generated output is not byte-for-byte identical to spec-parser
output — existing SHACL validation results are preserved, but OWL
reasoning consumers should review the differences before updating.

Full details: [docs/design.md](docs/design.md).

***This project is not an official SPDX project.***

[spdx/spec-parser]: https://github.com/spdx/spec-parser/
[shacl2code]: https://github.com/bact/shacl2code
