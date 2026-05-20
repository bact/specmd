---
SPDX-FileCopyrightText: 2024-2025 SPDX Project
SPDX-FileCopyrightText: 2026 Arthit Suriyawongkul
SPDX-License-Identifier: Community-Spec-1.0
---

# Markdown for model specification

SpecMD Markdown is a constrained subset of Markdown, with
predefined headings and a YAML frontmatter block.

This document provides guidelines for writing model files in the specific
syntax used by SpecMD.

Following these guidelines ensures consistency and avoids rendering issues when
using SpecMD and MkDocs to generate model ontologies and model textual
specifications.

## Table of contents

- [Overview](#overview)
- [Directory organisation](#directory-organisation)
- [Naming convention](#naming-convention)
- [File content structure and formatting](#file-content-structure-and-formatting)
  - [Model file example](#model-file-example)
- [Syntax](#syntax)
  - [Common optional metadata fields](#common-optional-metadata-fields)
  - [Classes](#classes)
  - [Datatypes](#datatypes)
  - [Individuals](#individuals)
  - [Properties](#properties)
  - [Vocabularies](#vocabularies)
- [Model configuration (specmd.yml)](#model-configuration-specmdyml)
- [Verbal forms for expressions of provisions](#verbal-forms-for-expressions-of-provisions)
- [Writing style](#writing-style)
- [Translation](#translation)
- [Migrating from the old format](#migrating-from-the-old-format)
- [Checking if everything is ok](#checking-if-everything-is-ok)

## Overview

Each model element (class, datatype, individual, property, and vocabulary)
is defined in a distinct file.

Specific headings and formatting are used to provide information for the
generation of a machine-readable specification, in
[Resource Description Framework (RDF)](https://en.wikipedia.org/wiki/Resource_Description_Framework)
data model, by SpecMD.

For instance, a summary listed under the "Summary" heading will be represented
as a `rdfs:comment` in the RDF file. Likewise, a value specified for the
`minCount` of a property under the "Properties" heading will be
translated into a `sh:minCount` in the RDF file.
See [an example](#model-file-example).

Descriptions provided under the "Description" heading are intended for human
reference and will not be incorporated into the RDF file.

## Directory organisation

Apart from the content in each individual file, the file itself has to be
placed in a specific location, as SpecMD implies some model semantic
from the location of the file:

- Each element (class, datatype, individual, property, and vocabulary)
  is defined in a distinct file.
- Model file names are case-sensitive and shall be identical to the element they
  represent.
- All model files are placed under a single root directory, which is passed
  directly to `specmd`. The name of that directory is not constrained by the
  tool; `model/` is a common convention.
- Namespaces should be organised into subdirectories (e.g., `Core/`, `Physics/`).
- Elements should be categorised by their type in subdirectories (e.g.,
  `Classes/`, `Datatypes/`, `Individuals/`, `Properties/`, `Vocabularies/`).

File and directory organisation:

```text
.
├── model                  ← root directory passed to specmd
:   :
│   ├── Core               ← namespace
│   │   ├── Classes
:   :   :   :
│   │   │   └── Tool.md
│   │   ├── Datatypes
:   :   :   :
│   │   │   └── SemVer.md
│   │   ├── Individuals
:   :   :   :
│   │   │   └── NoneElement.md
│   │   ├── Properties
:   :   :   :
│   │   │   └── verifiedUsing.md
│   │   └── Vocabularies
:   :       :
│   │       └── SupportType.md
│   ├── Physics            ← another namespace
:   :
```

> **SPDX 3 model:** The root directory is `model/`. Namespaces correspond to
> SPDX profiles: `Core/`, `Dataset/`, `Software/`, etc.

## Naming convention

- Use the singular form (e.g., use `import` and not `imports`).
- Use `UpperCamelCase` format for the names of classes, datatypes, individuals,
  and vocabularies.
- Use `lowerCamelCase` format for the names of properties and
  vocabulary entries.
- Metadata keys use `lowerCamelCase` format (e.g., `sinceVersion`, `deprecatedVersion`).
  Exception: `subClassOf` matches the capitalisation of `rdfs:subClassOf`.

## File content structure and formatting

Each model file shall adhere to a strict content structure:

- All files shall be encoded in UTF-8.
- Each file shall start with a YAML frontmatter block containing the
  license identifier:

  ```markdown
  ---
  SPDX-License-Identifier: <license-id>
  ---
  ```

  > **SPDX 3 model:** Use `SPDX-License-Identifier: Community-Spec-1.0`.

- The content immediately after the frontmatter shall begin with an H1 heading
  containing the element's name.
- Each element type has a predefined set of [allowed H2 headings](#syntax) and
  labeled lists that shall be used to structure its content.
- Headings shall be in sentence case (i.e., only the first letter of the first
  word is capitalized).

Additionally, since MkDocs uses a strict
[Python-Markdown](https://python-markdown.github.io/#differences),
each model file shall adhere to specific formatting guidelines:

- Blank lines:
  - There shall be a blank line before and after a heading.
  - There shall be a blank line before and after a list.
- Indentation:
  - Use spaces instead of tabs.
  - When a list item consists of multiple paragraphs, each subsequent paragraph
    in a list item shall be indented by 4 spaces.

### Model file example

This example shows a `Tool` class with one property.
Its name and location in the repository would be
`model/Core/Classes/Tool.md`.

```markdown
---
SPDX-License-Identifier: Apache-2.0
---

# Tool

## Summary

A software tool.

## Description

A Tool is a piece of software used to produce or analyse an artefact.

## Metadata

- name: Tool
- subClassOf: /Core/Agent

## Properties

- toolVersion:
  - minCount: 0
  - maxCount: 1
```

will give this RDF graph
(in [Turtle syntax](https://en.wikipedia.org/wiki/Turtle_(syntax))):

```ttl
<https://example.org/rdf/terms/Core/Tool> a owl:Class,
        sh:NodeShape ;
    rdfs:comment "A software tool."@en ;
    rdfs:subClassOf <https://example.org/rdf/terms/Core/Agent> ;
    sh:nodeKind sh:IRI ;
    sh:property [ sh:maxCount 1 ;
            sh:minCount 0 ;
            sh:path <https://example.org/rdf/terms/Core/toolVersion> ] .
```

> **SPDX 3 model:** A real example is `SimpleLicensingText` in
> [`model/SimpleLicensing/Classes/SimpleLicensingText.md`][simple-license],
> where the IRI base is `https://spdx.org/rdf/3/terms/` and
> the license identifier is `Community-Spec-1.0`.

[simple-license]: https://github.com/spdx/spdx-3-model/blob/develop/model/SimpleLicensing/Classes/SimpleLicensingText.md

## Syntax

### Common optional metadata fields

The following metadata fields are available on all element types (class,
datatype, individual, property, and vocabulary) and on vocabulary entries:

| Field | Type | Description | RDF mapping |
| - | - | - | - |
| `sinceVersion` | string | The version of the specification in which this element was introduced. | `owl:versionInfo "Since version X"@en` |
| `deprecated` | boolean (`true`) | Marks this element as deprecated. | `owl:deprecated true` |
| `deprecatedVersion` | string | The version in which deprecation was announced. | `owl:versionInfo "Deprecated since version X"@en` |
| `isReplacedBy` | string | The fully-qualified name or IRI of the recommended replacement. | `dcterms:isReplacedBy` |
| `example` | URI or inline string | A usage example -- either a URI pointing to a JSON-LD/TTL file or an inline JSON-LD/TTL snippet. | `vann:example` |

Example:

```markdown
## Metadata

- name: startTime
- nature: DataProperty
- range: DateTime
- sinceVersion: 2.0
- deprecated: true
- deprecatedVersion: 2.1
- isReplacedBy: /Core/creationInfo
```

### Classes

The name of a class shall be in `UpperCamelCase` format.

Allowed headings:

- Summary
- Description
- Metadata
  - `name`: \<class_name\>
  - `subClassOf`: \<class_name\> OR `/Namespace/ClassName` OR `none`
    *(Required unless class has no parent)*
  - `abstract`: `true` *(Omit for concrete classes; default is concrete)*
  - `sinceVersion`: \<version_string\> *(Optional)*
  - `deprecated`: `true` *(Optional)*
  - `deprecatedVersion`: \<version_string\> *(Optional)*
  - `isReplacedBy`: \<fqname_or_IRI\> *(Optional)*
- Properties *(Optional)*
  - `propName:` *(colon after name; type looked up from property definition)*
    - `minCount`: \<number\> *(Optional)*
    - `maxCount`: \<number\> *(Optional)*
  - ...
- External properties restrictions *(Optional)*
  - `/Namespace/propName:` *(colon after fully-qualified name)*
    - `minCount`: \<number\> *(Optional)*
    - `maxCount`: \<number\> *(Optional)*
  - ...

`minCount` and `maxCount` indicate the minimum and maximum number of times
a property may appear in a class (cardinality):

- The minimum possible occurrence is zero (`0`).
- An unbounded maximum occurrence is represented by a star/asterisk (`*`).
- If `minCount` is omitted, it defaults to `0`.
- If `maxCount` is omitted, it defaults to `*`.

> **Note:** The `type:` line that appeared in the old format under each
> property in the Properties section is no longer used. The type is derived
> automatically from the property definition's `range` field.
>
> **SPDX 3 model:** See the
> [Conformance section](https://spdx.github.io/spdx-spec/v3.0.1/conformance/)
> of the SPDX 3 specification for cardinality requirements on each class.

#### Class example

```markdown
---
SPDX-License-Identifier: Community-Spec-1.0
---

# Bot

## Summary

An automated agent.

## Description

A class example.

## Metadata

- name: Bot
- subClassOf: Agent
- sinceVersion: 2.1

## Properties

- prohibitedTask:
  - minCount: 1

## External properties restrictions

- /Core/Element/name:
  - minCount: 1
```

#### Abstract class example

```markdown
## Metadata

- name: Agent
- subClassOf: Element
- abstract: true
```

Output label in generated documents: **Instantiability: Abstract**

### Datatypes

The name of a datatype shall be in `UpperCamelCase` format.

Allowed headings:

- Summary
- Description
- Metadata
  - `name`: \<datatype_name\>
  - `subClassOf`: \<xsd_type\> OR \<class_name\>
  - `sinceVersion`, `deprecated`, `deprecatedVersion`, `isReplacedBy` *(Optional)*
- Format
  - `pattern`: \<regular_expression\>

The pattern value shall be wrapped in backticks to protect special characters
(such as `*` and `?`) from being interpreted as Markdown syntax:

```markdown
## Format

- pattern: `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`
```

#### Datatype example

```markdown
---
SPDX-License-Identifier: Community-Spec-1.0
---

# DateTime

## Summary

A string representing a specific date and time.

## Description

A DateTime is a string representation of a specific date and time.

## Metadata

- name: DateTime
- subClassOf: xsd:dateTimeStamp

## Format

- pattern: `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`
```

### Individuals

The name of an individual shall be in `UpperCamelCase` format.

Allowed headings:

- Summary
- Description
- Metadata
  - `name`: \<individual_name\>
  - `type`: \<class_name\>
  - `iri`: \<IRI\> *(Optional; overrides the default IRI derived from name)*
  - `sameAs`: \<IRI\> *(Optional; declares `owl:sameAs` to an external IRI)*
  - `sinceVersion`, `deprecated`, `deprecatedVersion`, `isReplacedBy` *(Optional)*
- Property Values
  - \<property_name\>: \<property_value\>
  - ...

#### Individual example

```markdown
---
SPDX-License-Identifier: Community-Spec-1.0
---

# NoneElement

## Summary

A named individual example.

## Description

A named individual of Element class representing none.

## Metadata

- name: NoneElement
- type: IndividualElement

## Property Values

- name: "NONE"
```

### Properties

The name of a property shall be in `lowerCamelCase` format.

Allowed headings:

- Summary
- Description
- Metadata
  - `name`: \<property_name\>
  - `nature`: `DataProperty` OR `ObjectProperty`
  - `range`: \<xsd_type\> OR \<class_name\> OR `/Namespace/ClassName`
  - `sinceVersion`, `deprecated`, `deprecatedVersion`, `isReplacedBy` *(Optional)*

#### Property example

```markdown
---
SPDX-License-Identifier: Community-Spec-1.0
---

# sensor

## Summary

Describes a sensor used for collecting the data.

## Description

Describes a sensor that was used for collecting the data
and its calibration value as a key-value pair.

## Metadata

- name: sensor
- nature: ObjectProperty
- range: /Core/DictionaryEntry
```

### Vocabularies

The name of a vocabulary shall be in `UpperCamelCase` format.

Allowed headings:

- Summary
- Description
- Metadata
  - `name`: \<vocabulary_name\>
  - `sinceVersion`, `deprecated`, `deprecatedVersion`, `isReplacedBy`,
    `example` *(Optional)*
- Entries *(see formats below)*

#### Simple entry format

For general enumerations where entries are plain named values:

```markdown
## Entries

- entryName: A plain description of this entry.
```

Entry formatting:

- Entry names shall be in `lowerCamelCase` format.
- Each entry shall be written on a single line.
- Entries should be listed alphabetically whenever possible.

#### Structured entry format

For relationship-type vocabularies where entries carry semantic constraints,
a structured format may be used:

```markdown
## Entries

- entryName:
  - description: A description of this entry.
  - from: SourceClass
  - to:
    - TargetClass
    - AnotherTargetClass
  - relationshipClass: ConstraintRelationship
  - sinceVersion: 2.0
  - deprecated: true
  - deprecatedVersion: 2.1
  - isReplacedBy: /Core/replacementEntry
```

Structured entry fields:

| Field | Type | Default | Description |
| - | - | - | - |
| `description` | string | `""` | Human-readable description. |
| `from` | class name or list | configurable | Source class(es) for this relationship type. |
| `to` | class name or list | configurable | Target class(es) for this relationship type. |
| `relationshipClass` | class name | configurable | Relationship OWL class for this entry. |
| `sinceVersion` | string | -- | Version when this entry was introduced. |
| `deprecated` | `true` | -- | Marks this entry as deprecated. |
| `deprecatedVersion` | string | -- | Version when deprecation was announced. |
| `isReplacedBy` | string | -- | Recommended replacement. |
| `example` | URI or inline string | -- | Usage example. |

The defaults for `from`, `to`, and `relationshipClass` apply across all
relationship-type vocabularies in the model. They may be overridden in
`specmd.yml` (at the model root):

| `specmd.yml` key | Default | Description |
| - | - | - |
| `default-from` | `Element` | Default source class when `from` is omitted. |
| `default-to` | `Element` | Default target class when `to` is omitted. |
| `default-relationship-class` | `Relationship` | Default OWL class when `relationshipClass` is omitted. |

Example `specmd.yml` fragment:

```yaml
default-from: Element
default-to: Element
default-relationship-class: Relationship
```

**`from` and `to` syntax:**

Single class -- write the class name inline:

```markdown
  - from: Agent
```

Multiple classes -- use a YAML block list:

```markdown
  - from:
    - Vulnerability
    - Action
    - DefinedProcess
```

Do not use a comma-separated string for multiple values.
An inline YAML list (`[A, B]`) is also accepted but not recommended
because it conflicts with the qualifier syntax (see below).

**Class name qualifiers:**

A class name in `from` or `to` may carry a qualifier block that constrains
which instances of that class are valid:

```text
ClassName[propName=value]
```

Multiple allowed values for one property are separated by `,`;
multiple properties are separated by `;`:

| Example | Meaning |
| - | - |
| `Relationship[relationshipType=invokedBy]` | `relationshipType` = `invokedBy` |
| `Relationship[relationshipType=a,b,c]` | `relationshipType` ∈ {a, b, c} |
| `Relationship[t=a,b;scope=build]` | `t` ∈ {a, b} and `scope` = `build` |

Qualified names are most useful as block list items, where they read cleanly:

```markdown
  - to:
    - Relationship[relationshipType=invokedBy]
```

SpecMD warns if the base class name or any qualifier property name is not
found in the model.

A mix of simple and structured entries within the same vocabulary is allowed.

#### Vocabulary example (simple)

```markdown
---
SPDX-License-Identifier: Community-Spec-1.0
---

# RpsType

## Summary

Specifies the hand shapes used in Rock-Paper-Scissors.

## Description

RpsType specifies the type of a hand shape.

## Metadata

- name: RpsType

## Entries

- paper: A flat, open hand.
- rock: A closed fist.
- scissors: Two fingers extended, forming a V shape.
```

#### Vocabulary example (structured, relationship type)

```markdown
---
SPDX-License-Identifier: Community-Spec-1.0
---

# RelationshipType

## Summary

A type of relationship between two elements.

## Description

RelationshipType is a vocabulary of directed relationships between software elements.

## Metadata

- name: RelationshipType

## Entries

- affects:
  - description: The from Vulnerability, Action or DefinedProcess affects each to Element.
  - from:
    - Vulnerability
    - Action
    - DefinedProcess
  - to: Element
  - relationshipClass: Relationship
- hasEvidence:
  - description: The subject element is supported by the object as evidence.
  - from: Element
  - to: Artifact
- packagedBy:
  - description: The subject is packaged by the object.
  - from: Artifact
  - to: Agent
- delegatedTo:
  - description: The from Agent delegates an action to the Agent of the to Relationship.
  - from: Agent
  - to:
    - Relationship[relationshipType=invokedBy]
  - relationshipClass: LifecycleScopedRelationship
```

## Model configuration (specmd.yml)

An optional `specmd.yml` file at the model root controls parsing and
generation behaviour. All keys are optional.

```yaml
# specmd.yml -- model configuration

# SPDX license identifier for generated output documents.
# Falls back to the license of the first namespace file if omitted.
license: CC0-1.0

# Ontology base URI (trailing slash added automatically if absent).
# All namespace IRIs must start with this prefix.
# If omitted, SpecMD attempts to derive it from a 'Core' namespace IRI
# (SPDX 3 convention). Non-SPDX models should set this explicitly.
base-uri: https://example.org/rdf/terms/

# Explicit namespace ordering for generated output.
# Namespaces not listed are excluded unless include-unlisted-namespaces is true.
namespace-order:
  - Core
  - Security

# Include namespaces not listed in namespace-order (default: false).
include-unlisted-namespaces: false

# Defaults for relationship-type vocabulary entries (see Vocabularies section).
default-from: Element
default-to: Element
default-relationship-class: Relationship

# PlantUML diagram settings.
plantuml:
  title: My Model
  scale: 4000*4000

# RDF output filenames (without extension).
rdf:
  filename: my-model
  context-filename: my-model-context

# OWL ontology metadata written into the generated RDF.
ontology:
  preferred-namespace-prefix: myns
  label: My Model Ontology
  title: My Model Ontology
  abstract: This ontology defines terms for my model.
  creator: My Organisation
  license: https://creativecommons.org/publicdomain/zero/1.0/
  references: https://example.org/my-model/
  copyright: Copyright (C) My Organisation
```

| Top-level key | Type | Default | Description |
| - | - | - | - |
| `license` | string | *(from namespace file)* | SPDX license for generated output. |
| `base-uri` | string (URI) | *(derived from model)* | Ontology base URI. Recommended for non-SPDX models. |
| `namespace-order` | list | *(alphabetical)* | Ordered namespace list; unlisted are excluded. |
| `include-unlisted-namespaces` | bool | `false` | Include namespaces absent from `namespace-order`. |
| `default-from` | string or list | `Element` | Default `from` class for vocab entries. |
| `default-to` | string or list | `Element` | Default `to` class for vocab entries. |
| `default-relationship-class` | string | `Relationship` | Default OWL class for vocab entries. |
| `plantuml` | mapping | -- | PlantUML diagram settings (see below). |
| `rdf` | mapping | -- | RDF output filename settings (see below). |
| `ontology` | mapping | -- | OWL ontology metadata (see below). |

**`plantuml` keys:**

| Key | Default | Description |
| - | - | - |
| `title` | `SPDXv3 model` | Diagram title. |
| `scale` | `4000*4000` | Diagram canvas size. |

**`rdf` keys:**

| Key | Default | Description |
| - | - | - |
| `filename` | `spdx-model` | Output filename (without extension). |
| `context-filename` | `spdx-context` | JSON-LD context filename (without extension). |

**`ontology` keys:**

| Key | Default | Description |
| - | - | - |
| `preferred-namespace-prefix` | `spdx` | `vann:preferredNamespacePrefix` value. |
| `label` | *(SPDX label)* | `rdfs:label` for the ontology. |
| `title` | *(SPDX title)* | `dcterms:title`. |
| `abstract` | *(SPDX abstract)* | `dcterms:abstract`. |
| `creator` | `SPDX Project` | `dcterms:creator`. |
| `license` | *(SPDX license URI)* | `dcterms:license` (URI). |
| `references` | *(SPDX references URI)* | `dcterms:references` (URI). |
| `copyright` | *(SPDX copyright)* | `omg_ann:copyright`. |

## Verbal forms for expressions of provisions

When a specification document uses normative language, verbal forms should be
chosen consistently to signal the level of requirement. A common convention,
used by ISO/IEC standards and IETF RFCs, is:

| Verbal forms          | Type of provision                                                                   |
| --------------------- | ----------------------------------------------------------------------------------- |
| shall / shall not     | Requirement                                                                         |
| should / should not   | Recommendation                                                                      |
| may                   | Permission (do not use "can", "might", "possible", or "impossible" in this context) |
| can / cannot          | Possibility and capability                                                          |
| must                  | External constraint                                                                 |

Equivalent phrases or expressions may be used in certain cases,
provided they maintain the exact meaning and level of normativity established
by these verbal forms.

> **SPDX 3 model:** The SPDX 3 specification follows *ISO/IEC Directives,
> Part 2 -- Principles and rules for the structure and drafting of ISO and
> IEC documents*. Use the verbal forms in the table above exactly as defined
> there.

## Writing style

To ensure clear and consistent documentation generation, follow these
recommendations when writing paragraph text and incorporating links.

- **Avoid overly long paragraphs.**

    Breaking up text into smaller paragraphs, using bullet points, or creating
    numbered lists can significantly improve readability and comprehension.

- **Maintain a consistent style.**

  - Use a uniform writing style, particularly when presenting similar
    information.
  - Use parallel sentence structures for related entries.

  Here's an example of a **consistent** writing style:

  ```markdown
  ## Entries

  - crl: Certificate Revocation List, or CRL, is a list of ...
  - ocsp: Online Certificate Status Protocol, or OCSP, is a common ...
  - tls: Transport Layer Security, or TLS, is a widely ...
  ```

- **Avoid bare URLs.**

    Always provide a descriptive label for each link.

    Recommended:

    ```markdown
    [Example Project](https://example.org/)
    ```

    The `iri` field in the Metadata section of an Individual is an exception
    where a bare URL is appropriate:

    ```markdown
    ## Metadata

    - name: SpdxOrganization
    - type: Organization
    - iri: https://spdx.org/
    ```

- **Code highlighting.**

    When using code blocks, specify the appropriate language code
    (e.g., `json`, `yaml`, `text`) to enable syntax highlighting.

## Translation

Model summaries, descriptions, and vocabulary entry descriptions can be
translated into other languages. Translations are added to the same file as
the source content, using H2 headings with a BCP 47 language tag:

```markdown
## Summary @ja

日本語の要約。

## Entries @ja

- entryName: 日本語の説明。
```

Only `Summary`, `Description`, and `Entries` sections can be translated.
`Metadata` and `Properties` sections cannot be translated.

Translated `Entries` sections shall use the simple `- name: description`
format regardless of whether the base `Entries` section uses structured format.
Entry names shall not be translated.

Please see [translation.md](./translation.md) for full details.

## Migrating from the old format

The `specmd migrate` command converts a model directory from the old format
(bare `SPDX-License-Identifier:` line, Title-Case metadata keys such as
`SubclassOf`/`Nature`/`Range`/`IRI`, `Instantiability: Abstract/Concrete`,
`type:` lines in Properties) to the new format described in this document.
Metadata key `SubclassOf` is renamed to `subClassOf` to match `rdfs:subClassOf`.

```shell
specmd migrate <input-directory> --output <output-directory>
```

The inverse operation (new → old) is performed by `specmd export`:

```shell
specmd export <input-directory> --output <output-directory>
```

Key differences between old and new format:

| Element | Old format | New format |
| - | - | - |
| License header | `SPDX-License-Identifier: X` (bare line) | YAML frontmatter `--- ... ---` block |
| Class parent | `- SubclassOf: ClassName` | `- subClassOf: ClassName` |
| Abstractness | `- Instantiability: Abstract` | `- abstract: true` |
| Concreteness | `- Instantiability: Concrete` | *(omit; false is the default)* |
| Property nature | `- Nature: ObjectProperty` | `- nature: ObjectProperty` |
| Property range | `- Range: ClassName` | `- range: ClassName` |
| Individual IRI | `- IRI: https://...` | `- iri: https://...` |
| Datatype parent | `- SubclassOf: xsd:string` | `- subClassOf: xsd:string` |
| Property in class | `- propName` (plain, then `- type: ...`) | `- propName:` (colon; no `type:` line) |
| Format pattern | `- pattern: regex` | `- pattern: \`regex\`` (backtick-wrapped) |
| Deprecation notice | `**DEPRECATED in X.**` in Description | `- deprecated: true` + `- deprecatedVersion: X` in Metadata |
| Vocab `from`/`to` (single) | `- from: ClassName` | `- from: ClassName` |
| Vocab `from`/`to` (multiple) | `- from: A, B, C` | YAML block list |

## Checking if everything is ok

To check if your additions or edits are correctly formatted, use the
following commands.

Install SpecMD:

```shell
pip install specmd
```

Validate only (no output generated):

```shell
specmd validate <MODEL_MARKDOWN_DIR>
```

Generate RDF to inspect outputs:

```shell
specmd generate <MODEL_MARKDOWN_DIR> --formats rdf --rdf-dir <OUTPUT_RDF_DIR>
```

Generate all outputs at once:

```shell
specmd generate <MODEL_MARKDOWN_DIR> --output <OUTPUT_DIR>
```

All options:

```shell
specmd --help
specmd generate --help
```
