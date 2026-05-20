---
SPDX-License-Identifier: CC0-1.0
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
