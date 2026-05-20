---
SPDX-FileCopyrightText: 2026 Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SpecMD design notes

SpecMD is built on the design of [spdx/spec-parser], targeting
compatibility with existing SPDX workflows while making a set of
deliberate format and output decisions.
This document records those decisions and the reasoning behind them.

## Markdown format

The SpecMD Markdown input format is nearly identical to the spec-parser
format. The differences are listed below.

### Front matter

SpecMD uses a standard `---`-delimited YAML front matter block for
per-file metadata (license identifier, etc.).
The earlier convention used a bare `SPDX-License-Identifier:` line
before the first heading, which is non-standard Markdown and flagged
by markdownlint.

### Section headings

SpecMD normalises section headings to Sentence case internally at parse
time (first character capitalised, rest lowercased), so source files
may use any capitalisation. The earlier convention required exact Title
Case in source files.

### Properties section

SpecMD uses `- propName:` (trailing colon, no separate `type:` line)
for property entries. This aligns with YAML syntax and allows PyYAML
to parse the section without a custom parser. The earlier format used
a bare `- propName` line followed by a `- type: ...` sub-line.

### Format section values

Format section values (e.g. regex patterns) are backtick-wrapped:
`` - pattern: `regex` ``. This enables correct display in Markdown
previewers (e.g. GitHub). The earlier format stored the value as a
plain string, which could be misread as prose.

### Metadata keys

Metadata keys are camelCase (e.g. `subClassOf`), aligning with the
standard vocabulary terms they represent (e.g. `rdfs:subClassOf`).
The earlier format used mixed casing (e.g. `SubclassOf`).

### Abstract class marker

Abstract classes use `- abstract: true` in the Metadata section.
The earlier format used `- Instantiability: Abstract`.

### Deprecation fields

Deprecation information (`deprecated`, `deprecatedVersion`,
`isReplacedBy`) is expressed as structured Metadata fields, with
corresponding RDF/OWL predicates. The earlier format encoded this
information as bold prose in the Description section, requiring a
custom parser and producing no structured RDF output.

### Vocabulary entries

SpecMD supports a structured vocabulary entry format with `from`, `to`,
and `relationshipClass` sub-fields for relationship type vocabularies.
This enables SHACL validation rules and specialised rendering of
relationship types. The earlier format used only prose descriptions.
The `specmd migrate` command extracts these fields automatically from
existing prose descriptions where possible.

### Additional metadata fields

`example` and `sinceVersion` are supported across all element types.

---

## RDF/OWL/SHACL design decisions

The generated ontology separates two concerns:

- **OWL** — open-world inference: class hierarchy, property
  declarations, object/datatype property ranges, ontology metadata.
- **SHACL** — closed-world validation: mandatory properties,
  cardinality, value constraints, abstract-class enforcement,
  enumeration enforcement.

This follows the standard usage of the two standards and avoids
relying on OWL reasoning for validation tasks that OWL was not
designed to perform.

### Comparison with spec-parser output

The generated RDF/OWL/SHACL is **not byte-for-byte identical** to
spec-parser output and is **not a drop-in equivalent for OWL
reasoning**. The following summarises where outputs are equivalent
in practice, where SpecMD emits additional triples, and where the
outputs intentionally differ.

**Equivalent in practice:**

- **SHACL validation** — documents conforming against the original
  SHACL shapes remain conforming. Vocabulary enumeration and
  abstract-class enforcement use the same SHACL mechanisms (`sh:in`,
  `sh:not`/`sh:hasValue`).
- **JSON-LD expansion** — compliant JSON-LD processors expand both
  context formats to identical IRIs. `@protected` is transparent for
  documents that do not layer additional contexts.
- **Class hierarchy and property declarations** — `rdfs:subClassOf`,
  `owl:ObjectProperty`, `owl:DatatypeProperty`, and `rdfs:range`
  triples are unchanged.

**SpecMD emits additional triples:**

- `owl:AllDisjointClasses` for direct subclasses of each abstract
  class (see [Abstract class disjointness](#abstract-class-disjointness)).
- `sh:NodeShape` typed on every OWL class, not only those with own
  properties.
- Richer per-element metadata: `skos:definition`, `skos:note`,
  `dcterms:isReplacedBy`, `owl:deprecated`, `vann:example`,
  `rdfs:isDefinedBy`, `rdfs:label`, and per-namespace VANN
  annotations.

**Intentional differences (design choices):**

- JSON-LD `@type` for class-range properties changed from `@vocab`
  to `@id` (see [JSON-LD context: `@type`](#json-ld-context-type-for-class-range-properties)).
- Redundant SHACL constraints on vocabulary property shapes removed
  (see [Vocabulary property shapes](#vocabulary-property-shapes-shin-only)).
- `owl:versionIRI` emitted only when a version string is present
  (see [`owl:versionIRI`](#owlversioniri-distinct-from-ontology-iri)).

### JSON-LD context: `@type` for class-range properties

Properties whose range is an OWL class use `"@type": "@id"` in the
generated context. This expands values directly to full IRIs, which
is correct for references to class instances. Only enumeration-range
properties use `"@type": "@vocab"` with a local `@context` that maps
entry names to their IRIs.

The earlier approach used `"@type": "@vocab"` for all object
properties, which causes incorrect IRI expansion for class-range
properties.

**Reference:** [spdx/spec-parser#205]

### JSON-LD context: `@protected` on all terms

Every term in the generated context carries `"@protected": true`.
Compliant JSON-LD processors raise an error on attempted redefinition,
preserving term semantics when additional vocabularies are layered on
top via extra `@context` entries.

**Reference:** [spdx/spdx-spec#1312]

### JSON-LD context: compact vocabulary alias entries

Vocabulary entries are defined once at the top level of the context as
`"ClassName_entryName": {"@id": "...", "@protected": true}`.
Each property's local `@context` then maps entry names to these
top-level aliases by string reference, rather than inlining the full
IRI repeatedly. The semantics are identical; the context file is
significantly smaller when multiple properties share the same
vocabulary range.

**Reference:** [spdx/spdx-3-model#1167]

### Abstract class disjointness

SpecMD uses the same SHACL pattern as spec-parser for abstract-class
instantiation enforcement (`sh:not [ sh:hasValue <AbstractClass> ]`
on `sh:path rdf:type`), and additionally emits `owl:AllDisjointClasses`
with `owl:members` listing the direct subclasses of each abstract class.

This axiom is valid in OWL 2 EL, QL, and RL. It expresses that no
individual can simultaneously belong to two sibling subclasses, enabling
OWL-based consistency checking without requiring OWL 2 DL reasoners.

**Reference:** [RDF/OWL/SHACL discussions][rdf-issues] in spdx/spdx-3-model

### Vocabulary property shapes: `sh:in` only

SpecMD emits only `sh:in` on vocabulary property shapes. `sh:class`
and `sh:nodeKind sh:IRI` are redundant when `sh:in` already enumerates
the exact set of valid IRI members. The validation outcome is identical;
the shape is simpler.

**shacl2code compatibility:** Tools that resolve property types via
`sh:class` → `rdfs:range` fallback continue to work correctly.
SpecMD sets `rdfs:range` on all property IRIs, so the fallback produces
the same class binding. This is verified by an integration test that
feeds the same model through both spec-parser and specmd into shacl2code
and asserts identical JSON schema output.

### `owl:versionIRI` distinct from ontology IRI

SpecMD emits neither `owl:versionIRI` nor `owl:versionInfo` unless a
version string is present in the model's namespace metadata. When
present, both are emitted: `owl:versionInfo` carries the version string,
and `owl:versionIRI` is a distinct sibling IRI, following
[W3C OWL 2 best practice][owl2-syntax]. Each release gets a distinct
IRI while the ontology IRI remains stable across minor versions.

### Base URI: explicit configuration, not derived

Users set `base-uri` in `specmd.yml` to declare the ontology base URI
explicitly — recommended for any non-SPDX model. If omitted, SpecMD
derives the base URI from the Core namespace IRI (the SPDX 3
convention, as proposed in [spdx/spec-parser#206]). When no Core
namespace is present either, SpecMD falls back to the longest common
prefix of all namespace IRIs and logs a warning advising the user to
set `base-uri` explicitly.

### External annotation property declarations

Every external annotation property used in the graph (SKOS, DCTERMS,
VANN, OMG Annotation Vocabulary) is explicitly declared as
`owl:AnnotationProperty`. This makes the ontology structurally
well-formed and self-contained under OWL 2 without requiring
`owl:imports` directives.

---

***This project is not an official SPDX project.***

[spdx/spec-parser]: https://github.com/spdx/spec-parser/
[rdf-issues]: https://github.com/spdx/spdx-3-model/issues?q=is%3Aissue+label%3ARDF%2FOWL%2FSHACL
[spdx/spec-parser#205]: https://github.com/spdx/spec-parser/pull/205
[spdx/spec-parser#206]: https://github.com/spdx/spec-parser/pull/206
[spdx/spdx-spec#1312]: https://github.com/spdx/spdx-spec/issues/1312
[spdx/spdx-3-model#1167]: https://github.com/spdx/spdx-3-model/issues/1167
[owl2-syntax]: https://www.w3.org/TR/owl2-syntax/#Ontology_IRI_and_Version_IRI
