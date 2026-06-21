---
SPDX-FileCopyrightText: 2026 Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SpecMD

[![PyPI - Version](https://img.shields.io/pypi/v/specmd)](https://pypi.org/project/specmd/)
![GitHub License](https://img.shields.io/github/license/bact/specmd)
[![DOI](https://img.shields.io/badge/doi-10.5281%2Fzenodo.20314484-blue)](https://doi.org/10.5281/zenodo.20314484)

Convert Markdown model definitions to RDF ontologies
and specification documents.

## Features

SpecMD reads and validates a complete model directory, then generates one or
more outputs:

| Format | Description |
| - | - |
| `jsondump` | JSON dump of the parsed model |
| `mkdocs` | MkDocs source files for website generation |
| `plantuml` | PlantUML diagram source |
| `rdf` | OWL+SHACL ontology and JSON-LD context |
| `tex` | TeX source for printable specification |
| `singlefile` | Single Markdown file (suitable for conversion to Word, PDF, etc.) |
| `webpages` | Per-IRI web pages *(not yet implemented)* |

A few SpecMD syntax additions capture validation rules that spec-parser can only
express as prose — type scoping, conditional cardinality, relationship endpoint
typing, numeric ranges, fixed values, and profile conformance — and compile them
to SHACL automatically. See [docs/constraints-spec.md](docs/constraints-spec.md)
for the rule catalogue and [docs/design.md](docs/design.md) for the SHACL
mapping.

## Installation

```shell
pip install specmd
```

All Python dependencies are installed automatically. The `tex` format
additionally requires [pandoc](https://pandoc.org/); all other formats need no
external tools.

## Quick start

```shell
# Validate a model directory
specmd validate path/to/model

# Generate all formats into ./out
specmd generate path/to/model --output ./out

# Generate specific formats only
specmd generate path/to/model --formats rdf,mkdocs --output ./out
```

See the [command-line reference](docs/cli.md) for every command and option.

## Configuration

An optional `specmd.yml` file at the model root controls parsing and generation
(base URI, namespace order, ontology metadata, vocabulary defaults, output
naming, and profile conformance). A worked example is in
[docs/specmd.yml.example](docs/specmd.yml.example); the full reference is in
[docs/format.md](docs/format.md#model-configuration-specmdyml).

Model files are linter-friendly: they survive a `markdownlint --fix` pass, and
IRI metadata such as `id:` accepts both a bare URL and the autolink form
(`id: <https://…>`).

## Documentation

| Document | Contents |
| - | - |
| [docs/cli.md](docs/cli.md) | Command-line reference (validate, generate, migrate, export) |
| [docs/format.md](docs/format.md) | Markdown input format and `specmd.yml` configuration |
| [docs/constraints-spec.md](docs/constraints-spec.md) | Constraint and profile-conformance syntax → SHACL |
| [docs/design.md](docs/design.md) | RDF/OWL/SHACL design decisions and rationale |
| [docs/translation.md](docs/translation.md) | Multilingual / translation support |
| [docs/spec-parser-compatibility.md](docs/spec-parser-compatibility.md) | Drop-in workflow shim and output differences |
| [docs/testing.md](docs/testing.md) | Running the test suite and optional-dependency tests |

## Compatibility

SpecMD targets compatibility with [spdx/spec-parser] workflows and accepts the
original Markdown format via automatic migration (`specmd migrate`, or the
`main.py` drop-in shim). Generated output is not byte-for-byte identical —
existing SHACL validation results are preserved, but RDF/OWL consumers should
review the differences. See
[docs/spec-parser-compatibility.md](docs/spec-parser-compatibility.md).

***This project is not an official SPDX project.***

[spdx/spec-parser]: https://github.com/spdx/spec-parser/
