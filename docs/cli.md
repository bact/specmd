---
SPDX-FileCopyrightText: 2026 Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Command-line reference

SpecMD uses subcommands:

```text
specmd <command> [options]

Commands:
  generate (gen)   Generate output artefacts from a model directory
  validate         Validate a model directory or a single .md file
  migrate          Convert spec-parser format to SpecMD format
  export           Export a SpecMD model to another format
```

Full help is available from the CLI:

```shell
specmd --help
specmd generate --help
```

## Validate

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

## Generate

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

## Migrate

Convert a model written in the spec-parser format to SpecMD format:

```shell
specmd migrate path/to/old-model --output path/to/new-model
```

See [spec-parser-compatibility.md](spec-parser-compatibility.md) for the
drop-in workflow shim.

## Export

Export a SpecMD model back to the spec-parser format:

```shell
specmd export path/to/model --output path/to/exported --format legacy
```

## Common options

| Option | Commands | Description |
| - | - | - |
| `-o`/`--output DIR` | `generate`, `migrate`, `export` | Output directory |
| `-f`/`--force` | `generate`, `migrate`, `export` | Overwrite existing output |
| `--strict` | `validate` | Exit non-zero on raw YAML warnings |
| `-q`/`--quiet` | all | Warnings and errors only |
| `-v`/`--verbose` | all | Debug output |
| `-V`/`--version` | top-level | Show version and exit |
