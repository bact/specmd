---
SPDX-FileCopyrightText: 2026 Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SpecMD constraints — consolidated design spec

Status: **fully implemented** — all four tiers (predicates, `if … then …`,
vocabulary-driven, conformance), the **contextual type-walk resolver**,
**explicit-first-hop tolerance** on property files, and **AST-level dedup**;
tested and pySHACL-verified (including a full end-to-end Lite profile fixture).
Path hops resolve as properties of the class reached by the previous hop
(`Class.all_properties`, spanning namespaces), so bare names work cross-namespace
and only class/value terms need qualification. A property-file constraint scopes
through the property name automatically, but the author may also write that hop
explicitly (`prop -> …`) without it being doubled. Identical constraints are
never emitted twice on the same class node. Authored input survives a
`markdownlint --fix` pass: MD034 autolinks (`<https://…>`) are accepted wherever
a bare URL is, and markdownlint's list-indentation is valid YAML.
Unifies the constraint mechanisms (class `## Constraints`, property
`## Constraints`, vocabulary `from`/`to`, `## Profile conformance`) into one
model, and catalogs every rule with its SpecMD input, rendered prose, SHACL, and
provenance.

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
   `is` (fixed value). Each scopes the node(s) reached by a property path.
2. **`if … then …`** — a condition predicate implies a consequent predicate
   (incl. cardinality and value-presence).
3. **Vocabulary-driven** — a vocabulary entry carries a constraint
   (`from`/`to`, `pattern`) applied conditionally on a selector property.
4. **Conformance** — a profile-gated rule over a collection, in one of three
   modes: existential (`forEach`/`exists`), member-predicate (`forEach`+`where`),
   or collection-self (`appliesTo`+`where`).

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
constraint  = cond | predicate | selector ;

cond        = "if" predicate "then" predicate ;
predicate   = type-scope | pattern | range | fixed | card | present ;

type-scope  = path ("type" | "not" "type") class-list ;
pattern     = path "matches" regex [ "flags" letters ] ;   (* letters: i, m, s, x (sh:flags) *)
range       = path "in" number ".." number ;
fixed       = path "is" term ;
card        = prop ("min" | "max") int ;
present     = path "has" term ;
selector    = path "matches" prop ;   (* arg is a property (no backtick) -> vocab-entry pattern binding *)

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

Vocabulary `from`/`to` use the same `class-list` (with per-item `not`) as a YAML
scalar or block list. The conformance block (tier 4) is structured YAML:
`forEach` (or `appliesTo`), `in`, `exists`, `count`, `linkedBy`, `where`, and a
reserved `as` (superseded by `linkedBy`). `where:` is a list of the constraint
expressions above; it is applied to the existential, the member, or the
collection itself depending on the rule mode (see Tier 4).

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
  are nodes — `sh:class`); a `matches` / `in` / `is` path must end at a
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
| pattern | `Each <path> shall match`<regex>`.` |
| range | `Each <path> shall be between M and N.` |
| fixed | `The <path> shall be <value>.` |
| if/then | `If <cond>, then <consequent>.` |
| conformance | `If any <Collection> declares conformance to the <P> profile, then for every <T> among its members there shall exist <n> <C> …` |

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

- **Syntax:** `relationshipType is hasConcludedLicense`
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

- **Syntax:** `if cvssScore in 7.0..8.9 then cvssSeverity is high`
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

A `## Profile conformance` block is a YAML list of rules. Every rule is gated on
the profile (an `ElementCollection` whose `profileConformance` names it; an
omitted value defaults to the configured `default-profile`). A rule comes in one
of **three modes**, distinguished by its keys:

| Mode | Keys | Means |
| - | - | - |
| **existential** | `forEach` + `exists` + `linkedBy` (+ `in`, `count`, `where`) | for each member of type `forEach`, there must exist *count* `exists` instances linked back by `linkedBy` and satisfying `where` |
| **member-predicate** | `forEach` + `where` (+ `in`), **no** `exists` | each member of type `forEach` must itself satisfy `where` |
| **collection-self** | `appliesTo` + `where` | the collection, when it is an `appliesTo`, must satisfy `where` |

`where:` is a list of ordinary **constraint expressions** (the full predicate
algebra via `parse_constraint`), so cardinality, `if … then …`, type-scope,
ranges, etc. all apply. `as:` originally named the `forEach` subject so a `where`
predicate could anchor the existential (e.g. `from: artifact`); `linkedBy:` (the
inverse-path anchor) superseded it, so `as:` is now **reserved** — still parsed,
not emitted. Activation is implicit (it is this profile's block).

### 12. Profile conformance — existential (`forEach` / `exists`)

`exists` is any class; `linkedBy` is the property on it that points back to the
subject (the inverse-path anchor); `in:` names the collection's membership
property.

- **Syntax:**

```yaml
- forEach: /Software/SoftwareArtifact
  in: element
  exists: /Core/Relationship
  count: 1
  linkedBy: from
  where:
    - relationshipType is hasConcludedLicense
    - to type /SimpleLicensing/AnyLicenseInfo
```

`count:` accepts `N`, `N..*`, or `N..M` → `sh:qualifiedMinCount`/`MaxCount`.

- **Section/File:** `## Profile conformance` · [Licensing/Licensing.md][m-licensing]
- **Provenance:** authored (legacy = prose in `## Profile conformance`, parsed-but-unused today)
- **Refs:** [Licensing namespace][m-licensing] · [SoftwareArtifact][m-swartifact] · [Relationship][m-rel] · [AnyLicenseInfo][m-anylic] · [profileConformance][m-profconf] · [ElementCollection][m-elemcoll]
- **Prose:** *If any ElementCollection declares conformance to the Licensing profile, then for every SoftwareArtifact among its members there shall exist exactly 1 Relationship (linked by from) satisfying: the relationshipType shall be hasConcludedLicense; each to shall be of type AnyLicenseInfo.*
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

### 12b. Profile conformance — member-predicate (`forEach` + `where`, no `exists`)

Drop `exists`/`linkedBy` and `where:` applies to the **member** itself. Use it
for profile-gated mandatory properties on a member class (e.g. Lite's
"every Package shall have `copyrightText`").

- **Syntax:**

```yaml
- forEach: /Software/Package
  in: element
  where:
    - copyrightText min 1
    - packageVersion min 1
    - if downloadLocation max 0 then packageUrl min 1   # "at least one of … or …"
```

- **Prose:** *If any ElementCollection declares conformance to the Lite profile, then every Package among its members shall satisfy: the Package shall have at least 1 copyrightText; …*
- **SHACL:** per member, `sh:or ( [ sh:not [ sh:class :Package ] ] [ <where node shape> ] )` under `sh:path :element`, gated by the profile (same outer `sh:or` as 12).

### 12c. Profile conformance — collection-self (`appliesTo` + `where`)

No `forEach`; `where:` applies to the **collection itself** when it is an
`appliesTo`. Use it for constraints on the collection node (e.g. Lite's
"an SpdxDocument shall have at least one `element` and `rootElement`").

- **Syntax:**

```yaml
- appliesTo: /Core/SpdxDocument
  where:
    - element min 1
    - rootElement min 1
```

- **Prose:** *An SpdxDocument declaring conformance to the Lite profile shall satisfy: the SpdxDocument shall have at least 1 element; the SpdxDocument shall have at least 1 rootElement.*
- **SHACL:** targets `:SpdxDocument`; `sh:or ( [ <gate-not> ] [ <where node shape> ] )` — the active branch carries the `where` constraints directly (no membership wrapper).

These three modes together express the full Lite profile: licensing
existentials (12), mandatory member properties incl. "at least one of A or B"
(12b), and document/SBOM cardinality (12c). The NTIA SBOM Minimum Elements can
be authored the same way (member-predicate + collection-self rules gated on an
`ntia` profile entry).

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
  `not`; mixed-polarity prose; `scope_property_path` prepends the property as the
  first hop but tolerates an explicit one (`prop -> …`), shared by SHACL and prose.
- **rdf.py**: replace single-namespace resolution with the contextual
  type-walk; `_emit_class_choice` emits positives **and** negatives; new emitters
  for `pattern`/`range`/`fixed`/`present`; `from`/`to` gains per-item `not`; new
  vocabulary-`pattern` + binding emitter. New conformance (`forEach`) emitter
  (3B): target the configured collection class, gate on the profile property,
  universal over the `in:` membership filtered to `forEach`, inverse-path of
  `linkedBy`, `sh:qualifiedValueShape` whose body is `sh:class <exists>` plus the
  `where:` lines emitted via the existing `_emit_constraint`, and
  `sh:qualifiedMin/MaxCount` from `count` (`N` / `N..*` / `N..M`). Track a
  per-class set of already-emitted constraint ASTs and skip duplicates
  (decision 3).
- **model.py**: parse vocabulary entry `pattern`; parse the structured
  `## Profile conformance` block (3B/2B keys) into `Namespace.conformance_rules`;
  read the `conformance` config (`collection-class`, `profile-property`,
  `profile` map, `prose` mode) from `specmd.yml`; validate property-file first
  hop = the property.
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
   each class and skips repeats. AST-tuple equality (the frozen predicate
   dataclasses), not RDF graph comparison. See *Duplicate emission* below.
4. **Profile gate — CONFIG.** A namespace does not map 1:1 to a profile id by
   convention (e.g. the `Licensing` namespace relates to **both**
   `simpleLicensing` and `expandedLicensing`), so the gate value is configured.
   See *Conformance gate* below.

### Tier-4 (conformance) sub-decisions

1. **Count grammar — `N` / `N..*` / `N..M`** → `sh:qualifiedMinCount`/`MaxCount`
   (same convention as cardinality, `*` = unbounded).
2. **Membership property — 2B (per block `in:`).** Each conformance rule names
   the collection→members property it iterates; the collection class and gate
   property stay in config. Supports rules over different membership properties.
3. **Existential — 3B (generalized).** `exists` is any class; `linkedBy` is the
   inverse-path anchor; `where:` is a list of ordinary constraint expressions on
   the existential (reuses `parse_constraint` / `_emit_constraint`). `as:`
   (original subject binding, superseded by `linkedBy`) is reserved — parsed,
   not emitted. Two further modes drop `exists` (member-predicate) or replace
   `forEach`/`in` with `appliesTo` (collection-self); see Tier 4.
4. **Prose vs structured — config `conformance.prose`** = `structured`
   (default) | `prose` | `both`. SHACL always derives from the structured block.

All decisions are settled; the spec is implementation-ready.

## Conformance gate (decision 4)

The `## Profile conformance` SHACL gate is `sh:hasValue <ProfileIdentifierType
entry IRI>`. SpecMD needs to know *which* entry. Config maps each namespace's
conformance block to one (or more) `ProfileIdentifierType` entry **names** — the
full IRI is derived from `base-uri` + `Core/ProfileIdentifierType/<name>`, so the
config holds names, not IRIs:

```yaml
# specmd.yml
conformance:
  collection-class: /Core/ElementCollection   # target of conformance shapes (default)
  profile-property: /Core/profileConformance  # the gate property (default)
  default-profile: core                       # assumed when profileConformance is omitted
  prose: structured                           # structured (default) | prose | both
  # namespace -> the ProfileIdentifierType entry(ies) the block gates on
  profile:
    Licensing: expandedLicensing      # or: [simpleLicensing, expandedLicensing]
    Security: security
    Software: software
```

Decisions **2B** and **3B** apply: the collection **class** and **gate
property** are config (defaulting to SPDX, as above); the **membership
property** is named per block as `in:`; the existential is generalized via
`linkedBy` + a `where:` list of constraint expressions. `prose:` selects whether
the structured block, the legacy free prose, or both are rendered (SHACL always
comes from the structured block).

`profileConformance` has at least one of the listed entries → the rule activates.

**Default profile.** SPDX 3 states *"If the profileConformance property is not
provided, 'core' is to be assumed as the default."* When a rule gates on the
configured `default-profile`, the gate also requires `profileConformance` to be
**present** (`sh:not[hasValue …]` **and** `sh:minCount 1`), so an *omitted* value
— which defaults to the default profile — still activates the rule. A collection
that explicitly lists *other* profiles (and not the default) is not held to the
default rule. The rendered prose for a default-profile rule reads "In any
ElementCollection (the … profile applies even when profileConformance is
omitted), …" rather than the conditional "If any … declares …".
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
individuals of that class (and its subclasses)**. An unconditional `is` / `in` /
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
