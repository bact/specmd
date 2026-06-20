---
SPDX-License-Identifier: CC0-1.0
---

# ExternalIdentifier

## Summary

A typed identifier referencing something outside the SPDX document.

## Description

ExternalIdentifier pairs an identifier string with the scheme that defines its
format.

## Metadata

- name: ExternalIdentifier
- subClassOf: Element

## Properties

- externalIdentifierType:
  - minCount: 1
  - maxCount: 1
- identifier:
  - minCount: 1
  - maxCount: 1

## Constraints

- identifier matches externalIdentifierType
