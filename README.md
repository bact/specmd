# SpecMD

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
- [History](#history)
- [RDF/OWL/SHACL design notes](#rdfowlshacl-design-notes)
  - [Relationship to spec-parser-generated RDF](#relationship-to-spec-parser-generated-rdf)
  - [JSON-LD context: `@type` for class-range properties](#json-ld-context-type-for-class-range-properties)
  - [JSON-LD context: `@protected` on all terms](#json-ld-context-protected-on-all-terms)
  - [JSON-LD context: compact vocabulary alias entries](#json-ld-context-compact-vocabulary-alias-entries)
  - [Abstract class enforcement: SHACL + `owl:AllDisjointClasses`](#abstract-class-enforcement-shacl--owlalldisjointclasses)
  - [Vocabulary property shapes: `sh:in` only](#vocabulary-property-shapes-shin-only)
  - [`owl:versionIRI` distinct from ontology IRI](#owlversioniri-distinct-from-ontology-iri)
  - [Base URI: explicit configuration, not derived](#base-uri-explicit-configuration-not-derived)
  - [External annotation property declarations](#external-annotation-property-declarations)

## Functionality

SpecMD always reads and validates the complete model directory.
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
  validate         Validate a model directory without generating output
  migrate          Convert spec-parser format to SpecMD format
  export           Export a SpecMD model to another format
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
[History](#history)). Downstream consumers of the RDF or MkDocs output should
expect and review these differences.

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

## History

SpecMD is built on the design of [spdx/spec-parser], with a goal of being
a drop-in replacement. Several features originate from proposals that were
filed as issues or submitted as pull requests there.
RDF/OWL/SHACL output design decision has been a recurring discussion topic in
the [spdx/spdx-3-model issue tracker][rdf-issues]; a number of those
improvements are implemented here.

The Markdown input format is nearly identical, with the following changes:

- **Front matter** is now a standard `---`-delimited YAML block.
  spec-parser used a bare `SPDX-License-Identifier:` line before the first
  heading -- non-standard Markdown and flagged by markdownlint.
- **Section headings** are read case-insensitively; SpecMD normalises them at
  parse time. spec-parser required exact Title Case.
- **Properties section** format changed: spec-parser used a bare `- propName`
  entry followed by a `- type: ...` sub-line;
  SpecMD uses `- propName:` (trailing colon, no `type:` line).
  Aligned with YAML format (allowed us to use PyYAML to handle this without
  the need of custom parser) and less typing/less error-prone.
- **Format section** values are now backtick-wrapped
  (e.g. `` - pattern: `regex` ``), to allow correct display in Markdown
  (e.g. when review it on GitHub "preview" view).
- **Metadata keys** are now camelCase (e.g. `subClassOf`) instead of Title Case
  or custom casing (e.g. `SubclassOf`), aligning with standard vocabulary terms
  such as `rdfs:subClassOf`.
- **Instantiability** field replaced: spec-parser used
  `- Instantiability: Abstract`; SpecMD uses `- abstract: true`.
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

The generated RDF differs from spec-parser output in several ways:

- **Base URI configurable, not hard-coded.**
  Set `base-uri` in `specmd.yml` to declare the ontology base URI explicitly --
  recommended for any non-SPDX model. When not set, SpecMD falls back to
  deriving it from the Core namespace IRI (SPDX 3 convention, as proposed in
  [spdx/spec-parser#206]), so existing SPDX 3 workflows need no change.
- **JSON-LD context `@type` corrected for class-range properties.**
  Properties whose range is a class now get `"@type": "@id"` instead of
  `"@type": "@vocab"` in the generated context file, which is semantically
  correct and avoids incorrect blank-node expansion by JSON-LD processors.
  (Proposed in [spdx/spec-parser#205].)
- **JSON-LD context terms protected with `@protected`.**
  Every term in the generated context file carries `"@protected": true`,
  preventing redefinition when additional context files are layered on top.
  This allows SPDX documents to safely mix in other vocabularies via extra
  `@context` entries without risking hijacking of SPDX term names.
  (Discussed in [spdx/spdx-spec#1312].)
- **Compact vocabulary alias entries in the JSON-LD context.**
  Vocabulary enum entries are emitted once at the top level as
  `"VocabClass_entry": {"@id": "...", "@protected": true}` and referenced
  by alias in each property's local `@context`, rather than inlining the
  full IRI repeatedly. Properties that share the same vocabulary range
  (common with large models) produce a significantly smaller context file.
  (Proposed in [spdx/spdx-3-model#1167].)
- **Subclass disjointness asserted for abstract classes.**
  spec-parser emits no OWL disjointness axiom for abstract class hierarchies.
  SpecMD adds `owl:AllDisjointClasses` over the direct subclasses, which is
  valid in OWL 2 EL/QL/RL and allows OWL reasoning tools to detect when an
  individual is incorrectly typed as two sibling subclasses simultaneously.
  Instantiation enforcement (rejecting direct instances of the abstract class)
  uses the same SHACL `sh:not`/`sh:hasValue` pattern as spec-parser.
- **Redundant SHACL constraints removed from vocabulary property shapes.**
  spec-parser emits `sh:class`, `sh:nodeKind sh:IRI`, and `sh:in` together on
  property shapes that range over a vocabulary. `sh:class` and `sh:nodeKind
  sh:IRI` are redundant when `sh:in` already enumerates the exact set of valid
  IRI members. SpecMD emits only `sh:in`.
- **All OWL classes typed as `sh:NodeShape`.**
  spec-parser adds the `sh:NodeShape` type only to classes that declare own
  properties, leaving `sh:nodeKind` constraints on property-less classes
  invisible to SHACL processors. SpecMD types every class as `sh:NodeShape`
  unconditionally.
- **`owl:versionIRI` and `owl:versionInfo` added correctly.**
  spec-parser unconditionally emits `owl:versionIRI` as a self-reference
  (the ontology IRI pointing to itself) and never emits `owl:versionInfo`.
  SpecMD emits neither unless a version string is present in the model's
  namespace metadata; when it is, both are emitted -- `owl:versionInfo` as
  the version string and `owl:versionIRI` as a distinct versioned IRI,
  following W3C OWL 2 best practice.

The `docs/format.md` and `docs/translation.md` documents are based on the
documents of the same name in
[spdx/spdx-3-model](https://github.com/spdx/spdx-3-model/tree/develop/docs),
adapted and extended for SpecMD.

Models written in the original spec-parser format
(such as [spdx/spdx-3-model](https://github.com/spdx/spdx-3-model))
can be converted to SpecMD format using `specmd migrate`.
SpecMD models can be converted back using `specmd export --format legacy`.

## RDF/OWL/SHACL design notes

The generated ontology separates two concerns that are often conflated:

- **OWL** handles the open-world inference layer: class hierarchy,
  property declarations, object/datatype property ranges, and
  ontology metadata.
- **SHACL** handles the closed-world validation layer: mandatory
  properties, cardinality, value constraints, abstract-class
  enforcement, and enumeration enforcement.

This separation reflects the standard usage of the two standards
and avoids relying on OWL reasoning for validation tasks that OWL
was not designed to perform.

The decisions below differ from [spdx/spec-parser] and are documented
with references to the upstream SPDX discussions that motivated them.

### Relationship to spec-parser-generated RDF

The new output is **not byte-for-byte identical** to spec-parser output
and is **not a drop-in equivalent for OWL reasoning**.

Where the outputs are equivalent in practice:

- **SHACL validation:** documents that were conforming against the old
  SHACL shapes remain conforming; non-conforming documents remain
  non-conforming. Vocabulary enumeration and abstract-class enforcement
  use the same SHACL mechanisms as spec-parser (`sh:in` for enumerations,
  `sh:not`/`sh:hasValue` for abstract classes).
- **JSON-LD expansion (compact alias entries, `@protected`):**
  compliant JSON-LD processors expand both context formats to identical
  IRIs. `@protected` is transparent for documents that do not layer
  additional contexts.
- **Class hierarchy and property declarations:** `rdfs:subClassOf`,
  `owl:ObjectProperty`, `owl:DatatypeProperty`, and `rdfs:range` triples
  are unchanged.

Where SpecMD emits additional triples:

- **`owl:AllDisjointClasses`** for direct subclasses of each abstract
  class. spec-parser emits no OWL disjointness axiom; this is a new
  addition that enables OWL reasoning tools to check sibling-subclass
  disjointness. The axiom uses OWL 2 EL-compatible vocabulary.
- **`sh:NodeShape`** typed on every OWL class, not only those with own
  properties. This makes `sh:nodeKind` constraints on property-less
  classes visible to SHACL processors.
- **Richer metadata** per element: `skos:definition`, `skos:note`,
  `dcterms:isReplacedBy`, `owl:deprecated`, `vann:example`,
  `rdfs:isDefinedBy`, `rdfs:label`, and per-namespace VANN annotations.
  spec-parser emits a subset of these.

Where the outputs intentionally differ (correctness fixes):

- **JSON-LD `@type` for class-range properties:** the old `@type: @vocab`
  was incorrect and caused wrong IRI expansion. The new `@type: @id` is
  a bug fix; consumers that relied on the old (incorrect) expansion will
  need to update.
- **Redundant SHACL constraints on vocabulary property shapes:**
  spec-parser emits `sh:class`, `sh:nodeKind sh:IRI`, and `sh:in`
  together; SpecMD emits only `sh:in`, which is sufficient.
- **`owl:versionIRI` / `owl:versionInfo`:** spec-parser unconditionally
  emits `owl:versionIRI` as a self-reference and never emits
  `owl:versionInfo`. SpecMD emits both only when a version string is
  present -- `owl:versionInfo` as the string, `owl:versionIRI` as a
  distinct versioned IRI.

### JSON-LD context: `@type` for class-range properties

**Problem:** spec-parser used `"@type": "@vocab"` for all object
properties, including those whose range is an OWL class (not an
enumeration). `@vocab` expansion maps term strings against the active
vocabulary prefix, producing incorrect or ambiguous IRIs when the value
is meant to be a bare IRI reference to a class instance.

**Decision:** Properties with a class range use `"@type": "@id"`,
which expands values directly to full IRIs. Only enumeration-range
properties use `"@type": "@vocab"` with a local `@context` that maps
enum entry names to their IRIs.

**Reference:** [spdx/spec-parser#205]

### JSON-LD context: `@protected` on all terms

**Problem:** Without protection, a downstream consumer that extends
the SPDX JSON-LD context by prepending or appending their own
`@context` entries can silently redefine SPDX terms, causing values
to expand to wrong IRIs without any error.

**Decision:** Every term in the generated context carries
`"@protected": true`. Compliant JSON-LD processors raise an error
on attempted redefinition, so SPDX term semantics are preserved when
additional vocabularies are layered on top.

**Reference:** [spdx/spdx-spec#1312]

### JSON-LD context: compact vocabulary alias entries

**Problem:** When multiple properties share the same vocabulary range
(e.g., several AI/Dataset properties all use `PresenceType`),
spec-parser inlined the full set of enum-entry IRIs in each property's
local `@context`. With large vocabularies or many properties sharing
a range, this produces significant redundancy and a large context file.

**Decision:** Vocabulary entries are defined once at the top level of
the context as `"ClassName_entryName": {"@id": "...", "@protected": true}`.
Each property's local `@context` then maps entry names to these
top-level aliases by string reference, not by inlining the IRI.
The semantics are identical; the context file is significantly smaller.

**Reference:** [spdx/spdx-3-model#1167]

### Abstract class enforcement: SHACL + `owl:AllDisjointClasses`

**Background:** spec-parser enforces abstract classes with a SHACL
constraint -- `sh:not [ sh:hasValue <AbstractClass> ]` on
`sh:path rdf:type` -- but emits no OWL-level disjointness axiom for
sibling subclasses. An OWL reasoning tool therefore cannot detect when
an individual is erroneously typed as two sibling subclasses at once.

**Decision:** SpecMD uses the same SHACL pattern as spec-parser for
instantiation enforcement, and additionally emits
`owl:AllDisjointClasses` + `owl:members` over the direct subclasses of
each abstract class. This axiom is valid in OWL 2 EL, QL, and RL and
expresses that no individual can simultaneously belong to two sibling
subclasses, enabling OWL-based consistency checking without requiring
OWL 2 DL reasoners.

**Reference:** [RDF/OWL/SHACL discussions][rdf-issues] in
spdx/spdx-3-model

### Vocabulary property shapes: `sh:in` only

**Background:** spec-parser already enforces vocabulary property values
with SHACL `sh:in`, enumerating the valid IRIs. It also emits
`sh:class <VocabClass>` and `sh:nodeKind sh:IRI` on the same property
shape. Both are redundant: `sh:in` already restricts values to the
listed IRIs, all of which are typed as members of the vocabulary class
and are IRIs by construction.

**Decision:** SpecMD emits only `sh:in` on vocabulary property shapes,
dropping `sh:class` and `sh:nodeKind sh:IRI`. The validation outcome is
identical; the shape is simpler and avoids redundant checks.

**shacl2code compatibility:** Tools such as [shacl2code] that resolve
property types via `sh:class` → `rdfs:range` fallback continue to work
correctly. SpecMD sets `rdfs:range` on all property IRIs, so the fallback
path produces the same class binding as the explicit `sh:class` triple.
This is verified by an integration test that feeds the same model through
both spec-parser and specmd (via `specmd migrate`) into shacl2code and
asserts identical JSON schema output.

### `owl:versionIRI` distinct from ontology IRI

**Problem:** spec-parser unconditionally emits `owl:versionIRI` set to
the ontology IRI itself (a self-reference), and never emits
`owl:versionInfo`. The self-referential IRI carries no version
information — it is the same regardless of which version of the model
is being published — and the [W3C OWL 2 specification][owl2-syntax]
notes that a self-referential version IRI conveys no version
information — it is the same regardless of which version of the model
is being published. Tools that dereference `owl:versionIRI` to retrieve
a specific historical snapshot will simply retrieve the current version.

**Decision:** Neither `owl:versionIRI` nor `owl:versionInfo` is emitted
unless a version string is present in the model's namespace metadata.
When present, both are emitted: `owl:versionInfo` carries the version
string, and `owl:versionIRI` is a distinct sibling IRI. When the major
version appears as a path segment in the base URI, it is replaced by the
full version string (e.g., `https://spdx.org/rdf/3/terms/` + `3.1` →
`https://spdx.org/rdf/3.1/terms/`); otherwise the version is appended
as a sub-path. Either way each release gets a distinct IRI while the
ontology IRI stays stable across minor versions.

**Reference:** [W3C OWL 2 Structural Specification §3.1][owl2-syntax]

### Base URI: explicit configuration, not derived

**Problem:** spec-parser derived the ontology base URI by stripping
`/Core` from the Core namespace IRI. This works for SPDX 3 (which
always has a `Core` namespace) but silently produces a wrong base URI
for any other model.

**Decision:** Users set `base-uri` in `specmd.yml` explicitly.
If omitted, SpecMD falls back to the SPDX 3 heuristic for backward
compatibility and logs a warning advising non-SPDX users to set the
key.

### External annotation property declarations

**Problem:** Using terms from external vocabularies (SKOS, DCTERMS,
VANN, OMG Annotation Vocabulary) without declaration can cause OWL
tools to treat them as undeclared entities, producing warnings or
incorrect results.

**Decision:** Every external annotation property used in the graph
is explicitly declared as `owl:AnnotationProperty`. This makes the
ontology structurally well-formed and self-contained under OWL 2
without requiring `owl:imports` directives.

***This project is not an official SPDX project.***

[spdx/spec-parser]: https://github.com/spdx/spec-parser/
[rdf-issues]: https://github.com/spdx/spdx-3-model/issues?q=is%3Aissue+label%3ARDF%2FOWL%2FSHACL
[spdx/spec-parser#205]: https://github.com/spdx/spec-parser/pull/205
[spdx/spec-parser#206]: https://github.com/spdx/spec-parser/pull/206
[spdx/spdx-spec#1312]: https://github.com/spdx/spdx-spec/issues/1312
[spdx/spdx-3-model#1167]: https://github.com/spdx/spdx-3-model/issues/1167
[owl2-syntax]: https://www.w3.org/TR/owl2-syntax/#Ontology_IRI_and_Version_IRI
[shacl2code]: https://github.com/bact/shacl2code
