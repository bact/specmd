---
SPDX-License-Identifier: CC0-1.0
---

# Core

## Summary

Core namespace for testing.

## Description

The Core namespace contains fundamental classes and properties used for testing.

## Metadata

- name: Core
- id: https://example.org/rdf/terms/Core

## Profile conformance

- forEach: /Core/SoftwareArtifact
  in: element
  exists: /Core/Relationship
  count: 1
  linkedBy: from
  where:
    - relationshipType is hasConcludedLicense
    - to type /Core/AnyLicenseInfo

- forEach: /Core/SoftwareArtifact
  in: element
  where:
    - name min 1

- appliesTo: /Core/ElementCollection
  where:
    - element min 1
    - rootElement min 1
