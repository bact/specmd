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
- id: <https://example.org/rdf/terms/Lite>

## Profile conformance

- forEach: /Software/Package
  in: element
  exists: /Core/Relationship
  count: 1
  linkedBy: from
  where:
  - relationshipType is hasConcludedLicense
  - to type /Core/AnyLicenseInfo

- forEach: /Software/Package
  in: element
  exists: /Core/Relationship
  count: 1
  linkedBy: from
  where:
  - relationshipType is hasDeclaredLicense
  - to type /Core/AnyLicenseInfo

- forEach: /Software/Package
  in: element
  where:
  - copyrightText min 1
  - packageVersion min 1
  - suppliedBy min 1
  - if downloadLocation max 0 then packageUrl min 1

- forEach: /Core/Agent
  in: element
  where:
  - name min 1

- appliesTo: /Core/SpdxDocument
  where:
  - element min 1
  - rootElement min 1

- appliesTo: /Software/Sbom
  where:
  - element min 1
  - rootElement min 1
