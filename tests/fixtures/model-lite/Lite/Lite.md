---
SPDX-License-Identifier: CC0-1.0
---

# Lite

## Summary

The Lite profile: a minimal set of conformance requirements.

## Description

The Lite namespace defines the Lite profile conformance requirements.

## Metadata

- name: Lite
- id: https://example.org/rdf/terms/Lite

## Profile conformance

- forEach: /Software/Package
  in: /Core/element
  exists: /Core/Relationship
  count: 1
  linkedBy: /Core/from
  where:
    - /Core/relationshipType is hasConcludedLicense
    - /Core/to type /Core/AnyLicenseInfo

- forEach: /Software/Package
  in: /Core/element
  exists: /Core/Relationship
  count: 1
  linkedBy: /Core/from
  where:
    - /Core/relationshipType is hasDeclaredLicense
    - /Core/to type /Core/AnyLicenseInfo

- forEach: /Software/Package
  in: /Core/element
  where:
    - /Software/copyrightText min 1
    - /Software/packageVersion min 1
    - /Core/suppliedBy min 1
    - if /Software/downloadLocation max 0 then /Software/packageUrl min 1

- forEach: /Core/Agent
  in: /Core/element
  where:
    - /Core/name min 1

- appliesTo: /Core/SpdxDocument
  where:
    - /Core/element min 1
    - /Core/rootElement min 1

- appliesTo: /Software/Sbom
  where:
    - /Core/element min 1
    - /Core/rootElement min 1
