---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# spec-parser compatibility

SpecMD is built on the design of [spdx/spec-parser] and targets compatibility
with existing workflows. The Markdown input format is nearly identical; key
differences include standard YAML front matter, camelCase metadata keys, a
structured vocabulary entry format, and structured deprecation fields.

## Drop-in workflow shim

A `main.py` compatibility shim is provided for existing CI/scripts that invoke
the [spdx/spec-parser] CLI. It accepts spec-parser's original command-line
arguments, internally runs `specmd migrate` on the input, then `specmd generate`
or `specmd validate`.

Replacing `spec-parser` with `specmd` requires only a one-line change in CI, and
SpecMD accepts the original Markdown format as input via automatic migration.
Simply replace `python spec-parser/main.py` with `python specmd/main.py`.

In a GitHub workflow that checks out the repository, only the repository name
needs to change -- the checkout path, the pip install command, and every
`main.py` option stay the same:

```yaml
      - uses: actions/checkout@6
        with:
          repository: bact/specmd  # changed from spdx/spec-parser
          path: spec-parser
      - run: |
          pip install -r spec-parser/requirements.txt
          python3 spec-parser/main.py --force --generate-mkdocs --output-mkdocs spdx-spec/docs/model spdx-3-model/model
```

## Output differences

The generated RDF/OWL/SHACL and MkDocs Markdown are **not byte-for-byte
identical** to spec-parser output. SpecMD makes deliberate design decisions
around JSON-LD context correctness, SHACL shape simplification, OWL version
metadata, and abstract class disjointness, and adds SHACL coverage for rules
that spec-parser can only express as prose.

Existing SHACL validation results are preserved, but OWL reasoning consumers
should review the differences before updating. See [design.md](design.md) for
the full rationale, and
[spec-parser-compatibility test](testing.md#shacl2code-compatibility-test) for
the automated check that the two outputs remain interchangeable for legacy
input.

[spdx/spec-parser]: https://github.com/spdx/spec-parser/
