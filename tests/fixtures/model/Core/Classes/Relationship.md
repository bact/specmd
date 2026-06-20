---
SPDX-License-Identifier: CC0-1.0
---

# Relationship

## Summary

A directed relationship between elements.

## Description

Relationship connects a source element to one or more target elements with a typed link.

## Metadata

- name: Relationship
- subClassOf: Element

## Properties

- relationshipType:
  - minCount: 1
  - maxCount: 1
- from:
  - minCount: 1
  - maxCount: 1
- to:
  - minCount: 0
