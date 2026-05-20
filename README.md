# specmd

Parse Markdown model definitions into RDF, diagrams, and docs.

## Functionality

specmd always reads and validates the complete model directory.
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

## Usage

specmd uses subcommands:

```text
specmd <command> [options]

Commands:
  generate (gen)   Generate output artefacts from a model directory
  validate         Validate a model directory without generating output
  migrate          Convert spec-parser format to specmd format
  export           Export a specmd model to another format
```

### Validate

Check that a model directory is correctly formatted:

```shell
specmd validate path/to/model
```

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

Convert a model written in the spec-parser format to specmd format:

```shell
specmd migrate path/to/old-model --output path/to/new-model
```

### Export

Export a specmd model back to the spec-parser format:

```shell
specmd export path/to/model --output path/to/exported --format legacy
```

### Common options

| Option | Commands | Description |
| - | - | - |
| `-o`/`--output DIR` | `generate`, `migrate`, `export` | Output directory |
| `-f`/`--force` | `generate`, `migrate`, `export` | Overwrite existing output |
| `-q`/`--quiet` | all | Warnings and errors only |
| `-v`/`--verbose` | all | Debug output |
| `-V`/`--version` | top-level | Show version and exit |

Full help:

```shell
specmd --help
specmd generate --help
```

## Prerequisites

All Python dependencies are installed automatically with `pip install specmd`.
External tools required for specific formats:

| Format | External prerequisite |
| - | - |
| `tex` | [pandoc](https://pandoc.org/) -- used to convert Markdown fragments to LaTeX |
| All others | None |

## spec-parser compatibility

A `main.py` compatibility shim is provided for existing CI/scripts that
invoke the [spdx/spec-parser] CLI.

It accepts spec-parser's original command-line arguments, internally runs
`specmd migrate` on the input, then `specmd generate` or `specmd validate`.

Simply replace `python spec-parser/main.py` with `python specmd/main.py` in
existing workflows.

Or, in a GitHub workflow that checks out the repository, only the repository
name needs to change - the checkout path, the pip install command, and ever
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

## History

specmd is built on the design of [spdx/spec-parser], with a goal of being
a drop-in replacement. Several features originate from proposals that were
filed as issues or submitted as pull requests there but never merged.

The Markdown input format is nearly identical, with the following changes:

- **Front matter** is now a standard `---`-delimited YAML block.
  spec-parser used a bare `SPDX-License-Identifier:` line before the first
  heading -- non-standard Markdown and flagged by markdownlint.
- **Section headings** are read case-insensitively; specmd normalises them at
  parse time. spec-parser required exact Title Case.
- **Properties section** format changed: spec-parser used a bare `- propName`
  entry followed by a `- type: ...` sub-line;
  specmd uses `- propName:` (trailing colon, no `type:` line).
  Aligned with YAML format (allowed us to use PyYAML to handle this without
  the need of custom parser) and less typing/less error-prone.
- **Format section** values are now backtick-wrapped
  (e.g. `` - pattern: `regex` ``), to allow correct display in Markdown
  (e.g. when review it on GitHub "preview" view).
- **Metadata keys** are now camelCase (e.g. `subClassOf`) instead of Title Case
  or custom casing (e.g. `SubclassOf`), aligning with standard vocabulary terms
  such as `rdfs:subClassOf`.
- **Instantiability** field replaced: spec-parser used
  `- Instantiability: Abstract`; specmd uses `- abstract: true`.
- **Deprecation** information (`deprecated`, `deprecatedVersion`,
  `isReplacedBy`) moved from inline bold prose in the Description section to
  structured metadata fields, with corresponding RDF/OWL predicates.
- **Vocabulary entries** support a structured format with `from`, `to`, and
  `relationshipClass` sub-fields for relationship type vocabularies,
  extracted automatically from prose descriptions during migration.
  This information enables SHACL validation rules and enables specialised
  rendering of relationship types on the specification website (future work).
- **New metadata fields**: `example` and `sinceVersion` are supported across
  all element types.

Models written in the original spec-parser format
(such as [spdx/spdx-3-model](https://github.com/spdx/spdx-3-model))
can be converted to specmd format using `specmd migrate`.
specmd models can be converted back using `specmd export --format legacy`.

[spdx/spec-parser]: https://github.com/spdx/spec-parser/
