---
SPDX-FileCopyrightText: 2026 Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SpecMD constraints — consolidated design spec

Status: **proposal** (not yet implemented). Unifies the constraint mechanisms
(class `## Constraints`, property `## Constraints`, vocabulary `from`/`to`,
`## Profile conformance`) into one model, and catalogs every proposed rule with
its SpecMD input, rendered prose, SHACL, and provenance.

## Layers — keep these three apart

| Layer | What it is | Produced by |
| - | - | - |
| **Legacy prose** | natural-language "shall…" text in upstream spec-parser model files (conformance sections, property/entry descriptions) | written by SPDX editors |
| **SpecMD syntax** | the structured input SpecMD parses (every "Syntax" in the catalog) | authored by hand, or `specmd migrate` from legacy prose |
| **Rendered prose** | human-readable sentences regenerated for the docs site | `specmd generate` |

Flow: `legacy prose --migrate--> SpecMD syntax --generate--> rendered prose + SHACL`.

**Every rule is authored by hand** in SpecMD syntax. Independently, the
relationship `from`/`to`/`relationshipClass` fields (rule 10) are the **only**
ones with an *implemented* migrate path (legacy prose → structured vocabulary
entry). That migration is a **heuristic convenience**: it may miss cases or
guess wrong (imperfect precision/recall), so its output is meant to be reviewed
and hand-edited, and an author can equally write rule 10 from scratch without
migrating. For every other rule, no converter exists today — the legacy
counterpart is prose a human transcribes (or a future migrate could be taught
to). The `## Profile conformance` prose is already parsed-but-unused
(`Namespace.conformance`); the conformance block gives it teeth but is still
authored.

## Tiers

1. **Predicates** — `type` (class), `matches` (pattern), `in` (numeric range),
   `=` (fixed value). Each scopes the node(s) reached by a property path.
2. **`if … then …`** — a condition predicate implies a consequent predicate
   (incl. cardinality and value-presence).
3. **Vocabulary-driven** — a vocabulary entry carries a constraint
   (`from`/`to`, `pattern`) applied conditionally on a selector property.
4. **Conformance** — a quantified `forEach`/`exists` rule, gated by profile.

## Scope-by-location

Identical syntax; **where it is written decides what it constrains.**

| Authored in | Section | File | Applies to |
| - | - | - | - |
| Class | `## Constraints` | `<NS>/Classes/<Class>.md` | that class; first path hop is a property of the class |
| Property | `## Constraints` | `<NS>/Properties/<prop>.md` | every class using the property; first hop = the property |
| Vocabulary | `## Entries` | `<NS>/Vocabularies/<Vocab>.md` | the selector's class, conditional on the entry value |
| Namespace (profile) | `## Profile conformance` | `<NS>/<NS>.md` | `ElementCollection` whose `profileConformance` names this profile |

## Grammar

```ebnf
constraint  = cond | type-scope | pattern | range | fixed | quantified ;

cond        = "if" predicate "then" predicate ;
predicate   = type-scope | pattern | range | fixed | card | present ;

type-scope  = path ("type" | "not" "type") class-list ;
pattern     = path "matches" regex [ "flags" letters ] ;   (* letters: i, m, s, x (sh:flags) *)
range       = path "in" number ".." number ;
fixed       = path "=" term ;
card        = prop ("min" | "max") int ;
present     = path "has" term ;

path        = term { "->" term } ;
class-list  = class-term { "," class-term } ;
class-term  = [ "not" ] term ;
term        = name | "/" ns "/" name ;        (* bare or fully-qualified *)
```

- `->` joins path hops (sequence/dereference); `/` is reserved for qualified
  names, so it is not a separator.
- Per-item `not` is the single negation rule; `not type <list>` is an alias
  meaning every item negated.
- Exact-duplicate class terms are removed (order preserved).

Vocabulary `from`/`to` use the same `class-list` as YAML scalar or block list.
The conformance block is structured YAML (`forEach`/`as`/`exists`/`count`/`where`).

## Resolution

- **Path hops — contextual type-walk.** Each hop is resolved as a property of
  the class reached by the previous hop (`class.all_properties`, which spans
  namespaces). First hop: a property of the class (class file) or the property
  itself (property file). Bare hops are therefore correct across namespaces
  (e.g. bare `suppliedBy` on an `AIPackage`-typed node → `/Core/suppliedBy`);
  `/Ns/Name` overrides.
- **Class / value terms — owner namespace.** Leaf references (class targets,
  `from`/`to` classes) resolve bare in the file's namespace; qualify for
  cross-namespace.
- **Endpoint kind.** A `type` path must end at an object property (its values
  are nodes — `sh:class`); a `matches` / `in` / `=` path must end at a
  datatype-valued property (its values are literals — `sh:pattern` /
  `sh:minInclusive` / `sh:hasValue`). A datatype range on a non-final hop is an
  error.

## Prose

One renderer. Terms show local names, falling back to qualified on collision.

| Form | Prose |
| - | - |
| type (pos) | `Each <path> shall be of type A, B, or C.` |
| type (neg) | `Each <path> shall not be of type A.` |
| type (mixed) | `Each <path> shall be of type A or B, and not C.` |
| pattern | `Each <path> shall match `<regex>`.` |
| range | `Each <path> shall be between M and N.` |
| fixed | `The <path> shall be <value>.` |
| if/then | `If <cond>, then <consequent>.` |
| conformance | `For every <T> in a collection conforming to this profile, there shall exist exactly <n> <C> with …` |

---

# Rule catalog

Each rule: **Syntax** (SpecMD Markdown) · **Section/File** · **Provenance** ·
**SPDX refs** · **Prose** (rendered) · **SHACL**. SHACL uses a single `:`
prefix for brevity. SPDX deep links target `develop` and are best-effort.

## Tier 1 — predicates

### 1. Type-scope (positive)
- **Syntax:** `from type /Security/Vulnerability`
- **Section/File:** `## Constraints` · [Security/Classes/VulnAssessmentRelationship.md][m-vulnassess]
- **Provenance:** authored (new)
- **Refs:** [VulnAssessmentRelationship][m-vulnassess] · [from][m-from] · [Vulnerability][m-vuln] · [issue #987][i987]
- **Prose:** *Each from shall be of type Vulnerability.*
- **SHACL:** `sh:property [ sh:path :from ; sh:class :Vulnerability ] .`

### 2. Type-scope (negative)
- **Syntax:** `element type not /Core/SpdxDocument`
- **Section/File:** `## Constraints` · [Core/Classes/ElementCollection.md][m-elemcoll]
- **Provenance:** authored (new)
- **Refs:** [ElementCollection][m-elemcoll] · [element][m-element] · [SpdxDocument][m-spdxdoc]
- **Prose:** *Each element shall not be of type SpdxDocument.*
- **SHACL:** `sh:property [ sh:path :element ; sh:not [ sh:class :SpdxDocument ] ] .`

### 3. Type-scope (path, mixed)
- **Syntax:** `customIdToLicense -> elementValue type /ExpandedLicensing/CustomLicense, /ExpandedLicensing/CustomLicenseAddition, SimpleLicensingText`
- **Section/File:** `## Constraints` · [SimpleLicensing/Properties/customIdToLicense.md][m-cidtolic] (or [LicenseExpression][m-licexpr] class)
- **Provenance:** authored (new)
- **Refs:** [customIdToLicense][m-cidtolic] · [ElementMap][m-elemmap] · [elementValue][m-elemval] · [CustomLicense][m-customlic]
- **Prose:** *Each customIdToLicense's elementValue shall be of type CustomLicense, CustomLicenseAddition, or SimpleLicensingText.*
- **SHACL:**
```turtle
sh:property [ sh:path ( :customIdToLicense :elementValue ) ;
    sh:or ( [ sh:class :CustomLicense ] [ sh:class :CustomLicenseAddition ] [ sh:class :SimpleLicensingText ] ) ] .
```

### 4. Pattern
A `matches` predicate constrains a **literal** value (the path must end at a
datatype-valued property). An optional `flags` clause maps to `sh:flags`
(`i` case-insensitive, `m`, `s`, `x`).

- **Syntax:** `` packageVerificationCodeExcludedFile matches `^\./` ``
- **Section/File:** `## Constraints` · [Core/Classes/PackageVerificationCode.md][m-pvc]
- **Provenance:** authored (new)
- **Refs:** [PackageVerificationCode][m-pvc] · [packageVerificationCodeExcludedFile][m-pvcef] · [issue #980][i980]
- **Prose:** *Each packageVerificationCodeExcludedFile shall match `^\./`.*
- **SHACL:** `sh:property [ sh:path :packageVerificationCodeExcludedFile ; sh:pattern "^\\./" ] .`

#### 4b. Pattern over a path, case-insensitive (`customIdToLicense -> key`)
The `ElementMap` `key` reached through `customIdToLicense` is a license-expression
reference, so it must begin with `LicenseRef-` or `AdditionRef-` — and the whole
license expression is case-insensitive.

- **Syntax:** `` customIdToLicense -> key matches `^(LicenseRef-|AdditionRef-)` flags i ``
- **Section/File:** `## Constraints` · [SimpleLicensing/Properties/customIdToLicense.md][m-cidtolic] (alongside the rule 3 line)
- **Provenance:** authored (new)
- **Refs:** [customIdToLicense][m-cidtolic] · [ElementMap][m-elemmap] · [key][m-key]
- **Prose:** *Each customIdToLicense's key shall match `^(LicenseRef-|AdditionRef-)` (case-insensitive).*
- **SHACL:**
```turtle
sh:property [ sh:path ( :customIdToLicense :key ) ;
    sh:pattern "^(LicenseRef-|AdditionRef-)" ; sh:flags "i" ] .
```

### 5. Numeric range
- **Syntax:** `cvssScore in 0..10` · `epssPercentile in 0..1`
- **Section/File:** `## Constraints` · [Security/Classes/CvssV3VulnAssessmentRelationship.md][m-cvss3], [EpssVulnAssessmentRelationship][m-epss]
- **Provenance:** authored (new)
- **Refs:** [CvssV3VulnAssessmentRelationship][m-cvss3] · [EpssVulnAssessmentRelationship][m-epss] · [issue #988][i988]
- **Prose:** *Each cvssScore shall be between 0 and 10.*
- **SHACL:** `sh:property [ sh:path :cvssScore ; sh:minInclusive 0 ; sh:maxInclusive 10 ] .`

### 6. Fixed value
- **Syntax:** `relationshipType = hasConcludedLicense`
- **Section/File:** `## Constraints` · [Security/Classes/VexAffectedVulnAssessmentRelationship.md][m-vexaff]
- **Provenance:** authored (new)
- **Refs:** [VexAffectedVulnAssessmentRelationship][m-vexaff] · [relationshipType][m-reltype] · [issue #987][i987]
- **Prose:** *The relationshipType shall be hasConcludedLicense.*
- **SHACL:** `sh:property [ sh:path :relationshipType ; sh:hasValue :hasConcludedLicense ] .`

## Tier 2 — `if … then …`

### 7. Conditional cardinality
- **Syntax:** `if element min 1 then rootElement min 1`
- **Section/File:** `## Constraints` · [Core/Classes/ElementCollection.md][m-elemcoll]
- **Provenance:** authored (new)
- **Refs:** [ElementCollection][m-elemcoll] · [element][m-element] · [rootElement][m-rootelem]
- **Prose:** *If the ElementCollection has at least 1 element, it shall also have at least 1 rootElement.*
- **SHACL:**
```turtle
sh:or ( [ sh:property [ sh:path :element ; sh:maxCount 0 ] ]
        [ sh:property [ sh:path :rootElement ; sh:minCount 1 ] ] ) .
```

### 8. Value-presence → cardinality
- **Syntax:** `if to has /Core/NoneElement then to max 1`
- **Section/File:** `## Constraints` · [Core/Classes/Relationship.md][m-rel]
- **Provenance:** authored (new)
- **Refs:** [Relationship][m-rel] · [to][m-to] · [NoneElement][m-none] · [issue #981][i981]
- **Prose:** *If to includes NoneElement, to shall have at most 1 value.*
- **SHACL:**
```turtle
sh:or ( [ sh:not [ sh:property [ sh:path :to ; sh:hasValue :NoneElement ] ] ]
        [ sh:property [ sh:path :to ; sh:maxCount 1 ] ] ) .
```

### 9. Conditional over predicates
- **Syntax:** `if cvssScore in 7.0..8.9 then cvssSeverity = high`
- **Section/File:** `## Constraints` · [Security/Classes/CvssV3VulnAssessmentRelationship.md][m-cvss3]
- **Provenance:** authored (new) — one line per CVSS band
- **Refs:** [CvssV3VulnAssessmentRelationship][m-cvss3] · [issue #988][i988]
- **Prose:** *If cvssScore is between 7.0 and 8.9, then cvssSeverity shall be high.*
- **SHACL:**
```turtle
sh:or ( [ sh:not [ sh:property [ sh:path :cvssScore ; sh:minInclusive 7.0 ; sh:maxInclusive 8.9 ] ] ]
        [ sh:property [ sh:path :cvssSeverity ; sh:hasValue :high ] ] ) .
```

## Tier 3 — vocabulary-driven

### 10. Relationship `from` / `to`
- **Syntax** (per vocabulary entry):
```yaml
- amendedBy:
  - from: Element, not /Core/SpdxDocument
  - to: /Core/Annotation
```
- **Section/File:** `## Entries` · [Core/Vocabularies/RelationshipType.md][m-reltypevocab]
- **Provenance:** authored — and the **only** rule with an implemented (heuristic) `specmd migrate` assist from legacy prose; migrate output is reviewed/edited, not exact
- **Refs:** [RelationshipType][m-reltypevocab] · [Relationship][m-rel] · [from][m-from] · [to][m-to]
- **Prose:** *An amendedBy relationship's from shall be of type Element and not SpdxDocument; its to shall be of type Annotation.*
- **SHACL:**
```turtle
:Relationship sh:or (
    [ sh:not [ sh:property [ sh:path :relationshipType ; sh:hasValue :amendedBy ] ] ]
    [ sh:property [ sh:path :from ; sh:class :Element ; sh:not [ sh:class :SpdxDocument ] ] ;
      sh:property [ sh:path :to   ; sh:class :Annotation ] ] ) .
```

### 11. Per-entry `pattern` + selector binding
- **Syntax** (entry pattern + class binding):
```yaml
# ExternalIdentifierType  ## Entries
- cve:
  - pattern: `^CVE-\d{4}-\d{4,}$`
```
```markdown
# ExternalIdentifier  ## Constraints
- identifier matches externalIdentifierType
```
- **Section/File:** `## Entries` · [Core/Vocabularies/ExternalIdentifierType.md][m-extidtype] **and** `## Constraints` · [Core/Classes/ExternalIdentifier.md][m-extid]
- **Provenance:** authored (new entry field + binding)
- **Refs:** [ExternalIdentifier][m-extid] · [ExternalIdentifierType][m-extidtype] · [ContentIdentifier][m-contentid] · [issue #989][i989] · [issue #986][i986]
- **Prose:** *Each identifier shall match the pattern of its externalIdentifierType.*
- **SHACL** (one `sh:or` per entry):
```turtle
:ExternalIdentifier sh:or (
    [ sh:not [ sh:property [ sh:path :externalIdentifierType ; sh:hasValue :cve ] ] ]
    [ sh:property [ sh:path :identifier ; sh:pattern "^CVE-\\d{4}-\\d{4,}$" ] ] ) .
```

## Tier 4 — conformance

### 12. Profile conformance (`forEach` / `exists`)
- **Syntax** (activation implicit — it is this profile's conformance block):
```yaml
- forEach: /Software/SoftwareArtifact
  as: artifact
  exists: /Core/Relationship
  count: 1
  where:
    - relationshipType: hasConcludedLicense
    - from: artifact
    - to: /SimpleLicensing/AnyLicenseInfo
```
- **Section/File:** `## Profile conformance` · [Licensing/Licensing.md][m-licensing]
- **Provenance:** authored (legacy = prose in `## Profile conformance`, parsed-but-unused today)
- **Refs:** [Licensing namespace][m-licensing] · [SoftwareArtifact][m-swartifact] · [Relationship][m-rel] · [AnyLicenseInfo][m-anylic] · [profileConformance][m-profconf] · [ElementCollection][m-elemcoll]
- **Prose:** *For every SoftwareArtifact in a collection conforming to this profile, there shall exist exactly one Relationship of type hasConcludedLicense with that artifact as its from and an AnyLicenseInfo as its to.*
- **SHACL:**
```turtle
:LicensingConformanceShape a sh:NodeShape ;
  sh:targetClass :ElementCollection ;
  sh:or (
    [ sh:not [ sh:property [ sh:path :profileConformance ; sh:hasValue :licensing ] ] ]
    [ sh:property [ sh:path :element ; sh:or (
        [ sh:not [ sh:class :SoftwareArtifact ] ]
        [ sh:property [ sh:path [ sh:inversePath :from ] ;
            sh:qualifiedValueShape [ sh:class :Relationship ;
              sh:property [ sh:path :relationshipType ; sh:hasValue :hasConcludedLicense ] ;
              sh:property [ sh:path :to ; sh:class :AnyLicenseInfo ] ] ;
            sh:qualifiedMinCount 1 ; sh:qualifiedMaxCount 1 ] ] ) ] ] ) ) .
```

## Issue coverage

| Issue | Rule(s) |
| - | - |
| [#987][i987] from=Vulnerability / relationshipType fixed | 1, 6 |
| [#980][i980] `^\./` | 4 |
| [#981][i981] NoneElement alone | 8 |
| [#988][i988] numeric ranges / severity bands | 5, 9 |
| [#986][i986], [#989][i989] pattern per type | 11 |
| Licensing conformance | 12 |

---

# Changes from current code

(Unchanged from the prior revision — summarized.)

- **constraints.py**: `PathType(path, positives, negatives)` (drop whole-list
  `negated`); add `pattern`, `range`, `fixed`, `present` predicate ASTs; per-item
  `not`; mixed-polarity prose; delete `property_constraint_to_prose` + the
  auto-prepend (first hop is now explicit).
- **rdf.py**: replace single-namespace resolution with the contextual
  type-walk; `_emit_class_choice` emits positives **and** negatives; new emitters
  for `pattern`/`range`/`fixed`/`present`; `from`/`to` gains per-item `not`; new
  vocabulary-`pattern` + binding emitter; new conformance (`forEach`) emitter
  (target `ElementCollection`, profile gate, qualified value shape). Track a
  per-class set of already-emitted constraint ASTs and skip duplicates
  (decision 3).
- **model.py**: parse vocabulary entry `pattern`; parse structured
  `## Profile conformance`; read the `conformance.profile` map from
  `specmd.yml`; validate property-file first hop = the property.
- **templates**: property pages use the same `constraint_prose` as classes;
  render conformance prose on the namespace page.
- **fixtures/tests/docs**: add a 2-namespace fixture; per-construct tests;
  fold this spec into `format.md`/`design.md`.

# Decisions

1. **`not type` alias — KEEP.** `path not type <list>` stays as a readable alias
   for an all-negative class list, alongside per-item `not`.
2. **Cross-namespace class target — REQUIRE qualification.** A bare class name
   resolves only in the file's namespace; cross-namespace targets must be
   written `/Ns/Name`. No global search (avoids silent ambiguity). *(Path hops
   still resolve contextually via the type-walk — this rule is only for leaf
   class/value targets.)*
3. **Duplicate emission — DEDUPE (AST level).** When the same constraint is
   authored on both a property and a class that uses it, the generator emits the
   shape once per class: it tracks the set of constraint ASTs already emitted on
   each class and skips repeats. AST-tuple equality (the `PathType`/`CondCard`
   dataclasses), not RDF graph comparison. See *Duplicate emission* below.
4. **Profile gate — CONFIG.** A namespace does not map 1:1 to a profile id by
   convention (e.g. the `Licensing` namespace relates to **both**
   `simpleLicensing` and `expandedLicensing`), so the gate value is configured.
   See *Conformance gate* below.

All four decisions are settled; the spec is implementation-ready.

## Conformance gate (decision 4)

The `## Profile conformance` SHACL gate is `sh:hasValue <ProfileIdentifierType
entry IRI>`. SpecMD needs to know *which* entry. Config maps each namespace's
conformance block to one (or more) `ProfileIdentifierType` entry **names** — the
full IRI is derived from `base-uri` + `Core/ProfileIdentifierType/<name>`, so the
config holds names, not IRIs:

```yaml
# specmd.yml
conformance:
  # namespace -> the ProfileIdentifierType entry(ies) the block gates on
  profile:
    Licensing: expandedLicensing      # or: [simpleLicensing, expandedLicensing]
    Security: security
    Software: software
```

`profileConformance` has at least one of the listed entries → the rule activates.
*(Alternative considered: name the profile inside the block as a term reference,
`profile: /Core/ProfileIdentifierType/expandedLicensing`, needing no config — kept
config per the decision, but the in-block form remains a clean fallback if a
namespace ever needs different gates per rule.)*

**Upstream gap.** The `Licensing` namespace has no matching
`ProfileIdentifierType` entry today — there are `simpleLicensing` and
`expandedLicensing`, but no bare `licensing` — so its conformance rule has no
single canonical profile id to gate on. How licensing profiles should be counted
/ identified is tracked in [spdx/spdx-3-model#1238][i1238] and is expected to be
resolved. The `conformance.profile` config bridges the gap in the meantime (map
`Licensing` to whichever entry, or both), and stays useful afterwards for any
namespace whose name differs from its profile id.

## Duplicate emission (decision 3 — explanation)

A **property-file** constraint is emitted on *every class that uses the
property*; a **class-file** constraint is emitted on *that class*. If the same
constraint line is written in **both** places — e.g.
`customIdToLicense -> elementValue type …` in both
`customIdToLicense.md` and a `LicenseExpression.md` that uses it — then
`LicenseExpression`'s node shape receives **two identical `sh:property`
shapes**.

- **Semantically harmless.** SHACL is conjunctive; two identical constraints
  validate exactly the same as one. Only the graph is slightly larger.
- **Cheap to dedupe.** Track, per class, the set of constraint **ASTs** already
  emitted and skip a repeat. This is AST-tuple equality (e.g. the `PathType`
  dataclass), *not* RDF blank-node graph comparison, so it is trivial — the same
  kind of equality the parser already relies on.

**Decision: dedupe at the AST level.** Per class, the generator keeps a set of
already-emitted constraint ASTs and skips any repeat before emitting its
`sh:property` shape. Clean output, near-zero cost, no false positives — only
constraints that resolve to the identical AST collapse.

## Interaction: constraints vs. model individuals

SpecMD emits named individuals (`Individuals/*.md`) into the same graph the
SHACL shapes validate, so **a class constraint must hold for the model's own
individuals of that class (and its subclasses)**. An unconditional `=` / `in` /
`matches` on a class is violated by any individual of that class that lacks the
value.

SPDX limits this blast radius by design: every individual is typed as the
neutral, property-free `IndividualElement` (Core) or `IndividualLicensingInfo`
(ExpandedLicensing) rather than a domain class like `Tool` or `Package`. So a
constraint on `Tool` does **not** touch `NoneElement` (which is an
`IndividualElement`). Authors should still keep this in mind when constraining
`Element` itself or `IndividualElement`/`IndividualLicensingInfo`, and can scope
with `if … then …` to exempt the individual case.

<!-- SPDX 3 model (develop) -->
[m-elemcoll]: https://github.com/spdx/spdx-3-model/blob/develop/model/Core/Classes/ElementCollection.md
[m-elemmap]: https://github.com/spdx/spdx-3-model/blob/develop/model/Core/Classes/ElementMap.md
[m-rel]: https://github.com/spdx/spdx-3-model/blob/develop/model/Core/Classes/Relationship.md
[m-extid]: https://github.com/spdx/spdx-3-model/blob/develop/model/Core/Classes/ExternalIdentifier.md
[m-spdxdoc]: https://github.com/spdx/spdx-3-model/blob/develop/model/Core/Classes/SpdxDocument.md
[m-reltypevocab]: https://github.com/spdx/spdx-3-model/blob/develop/model/Core/Vocabularies/RelationshipType.md
[m-extidtype]: https://github.com/spdx/spdx-3-model/blob/develop/model/Core/Vocabularies/ExternalIdentifierType.md
[m-none]: https://github.com/spdx/spdx-3-model/blob/develop/model/Core/Individuals/NoneElement.md
[m-element]: https://github.com/spdx/spdx-3-model/blob/develop/model/Core/Properties/element.md
[m-rootelem]: https://github.com/spdx/spdx-3-model/blob/develop/model/Core/Properties/rootElement.md
[m-elemval]: https://github.com/spdx/spdx-3-model/blob/develop/model/Core/Properties/elementValue.md
[m-key]: https://github.com/spdx/spdx-3-model/blob/develop/model/Core/Properties/key.md
[m-from]: https://github.com/spdx/spdx-3-model/blob/develop/model/Core/Properties/from.md
[m-to]: https://github.com/spdx/spdx-3-model/blob/develop/model/Core/Properties/to.md
[m-reltype]: https://github.com/spdx/spdx-3-model/blob/develop/model/Core/Properties/relationshipType.md
[m-profconf]: https://github.com/spdx/spdx-3-model/blob/develop/model/Core/Properties/profileConformance.md
[m-cidtolic]: https://github.com/spdx/spdx-3-model/blob/develop/model/SimpleLicensing/Properties/customIdToLicense.md
[m-licexpr]: https://github.com/spdx/spdx-3-model/blob/develop/model/SimpleLicensing/Classes/LicenseExpression.md
[m-anylic]: https://github.com/spdx/spdx-3-model/blob/develop/model/SimpleLicensing/Classes/AnyLicenseInfo.md
[m-customlic]: https://github.com/spdx/spdx-3-model/blob/develop/model/ExpandedLicensing/Classes/CustomLicense.md
[m-licensing]: https://github.com/spdx/spdx-3-model/blob/develop/model/Licensing/Licensing.md
[m-swartifact]: https://github.com/spdx/spdx-3-model/blob/develop/model/Software/Classes/SoftwareArtifact.md
[m-pvc]: https://github.com/spdx/spdx-3-model/blob/develop/model/Core/Classes/PackageVerificationCode.md
[m-pvcef]: https://github.com/spdx/spdx-3-model/blob/develop/model/Core/Properties/packageVerificationCodeExcludedFile.md
[m-contentid]: https://github.com/spdx/spdx-3-model/blob/develop/model/Software/Classes/ContentIdentifier.md
[m-vuln]: https://github.com/spdx/spdx-3-model/blob/develop/model/Security/Classes/Vulnerability.md
[m-vulnassess]: https://github.com/spdx/spdx-3-model/blob/develop/model/Security/Classes/VulnAssessmentRelationship.md
[m-vexaff]: https://github.com/spdx/spdx-3-model/blob/develop/model/Security/Classes/VexAffectedVulnAssessmentRelationship.md
[m-cvss3]: https://github.com/spdx/spdx-3-model/blob/develop/model/Security/Classes/CvssV3VulnAssessmentRelationship.md
[m-epss]: https://github.com/spdx/spdx-3-model/blob/develop/model/Security/Classes/EpssVulnAssessmentRelationship.md

<!-- issues -->
[i980]: https://github.com/spdx/spdx-3-model/issues/980
[i981]: https://github.com/spdx/spdx-3-model/issues/981
[i986]: https://github.com/spdx/spdx-3-model/issues/986
[i987]: https://github.com/spdx/spdx-3-model/issues/987
[i988]: https://github.com/spdx/spdx-3-model/issues/988
[i989]: https://github.com/spdx/spdx-3-model/issues/989
[i1238]: https://github.com/spdx/spdx-3-model/issues/1238
