# Test fixtures

Quick map of what each fixture is for, so you don't need to scan every file.

## `model/`

Primary fixture, used by the session-scoped `model` / `rdf_graph` pytest
fixtures (`conftest.py`) and most of the test suite. One namespace, `Core`,
with a mix of classes/properties/vocabularies/datatypes/individuals chosen to
exercise specific generator/constraint code paths, not to mirror the real
SPDX 3 Core namespace 1:1.

Notable classes:

- `Element` -- abstract root.
- `Agent` -- abstract, direct subclass of `Element`.
- `SecretAgent` -- **fictional, not a real SPDX 3 term.** Concrete subclass
  of `Agent`, used only to test class-hierarchy behaviour (e.g. subsumption
  warnings in `rdf.py`). Never treat it as real modelling.
- `Collection` / `ElementCollection` -- conformance-rule and cardinality
  constraint tests.
- `Relationship` -- endpoint (`from`/`to`) typing tests, scoped by
  `RelationshipType` vocabulary entries.
- `ElementMap` / `AnyLicenseInfo` -- `customIdToLicense` path-type constraint
  (multi-hop `elementValue` path).

Notable vocabularies:

- `RelationshipType.md` -- structured (relationship) vocabulary entries:
  plain classes, `not X` negation, bracket qualifiers
  (`Relationship[relationshipType=invokedBy]`), an unresolvable
  `relationshipClass` (deliberately, to test the unknown-class warning), and
  an unknown qualifier property (`unknownQualifierProp`).
- `SupportType.md` -- simple (non-relationship) vocabulary.
- `HashAlgorithm.md` -- simple vocabulary with per-entry examples.
- `ProfileIdentifierType.md` -- gates the `## Profile conformance` rules
  below.

`Core.md`'s `## Profile conformance` block exercises all three conformance
rule modes: existential, member-predicate, and collection-self.

`specmd.yml`: `base-uri: https://example.org/rdf/terms/` (fictional --
real IRIs use `https://spdx.org/rdf/3/terms/`). Sets `ontology:`,
`rdf:`, `plantuml:`, and `conformance:` blocks.

## `model-lite/`

Used only by `test_lite_conformance.py`. Separate from `model/` because it
authors a *complete* SPDX Lite profile (`Core` + `Software` + `Lite`
namespaces) so generated SHACL can be validated end-to-end with `pyshacl`
against hand-built data graphs -- `model/`'s conformance rules are partial
and not meant to validate as a real profile.

## `model-old-format/`

Minimal fixture in upstream **spec-parser**'s original Markdown format
(pre-SpecMD), used by:

- `test_migrate.py` -- migrate old format → SpecMD format, check output.
- `test_shacl2code.py` -- load with spec-parser and with
  (migrated) SpecMD, assert both produce shacl2code-identical output.

Do not "fix" this fixture to SpecMD conventions -- being old-format is the
point.

## `spdx3-examples/`

Real downloaded `*.spdx3.json` / `*.json` example instance documents (not
model definitions) from the SPDX 3 spec, used by `test_examples.py` to
sanity-check example file structure. Parameterized per-file via the
`spdx3_example` fixture.
