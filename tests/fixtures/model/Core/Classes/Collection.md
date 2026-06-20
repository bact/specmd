---
SPDX-License-Identifier: CC0-1.0
---

# Collection

## Summary

A grouping of elements with optional roots.

## Description

Collection gathers a set of elements and may designate one or more as roots.

## Metadata

- name: Collection
- subClassOf: Element

## Properties

- element:
  - minCount: 0
- rootElement:
  - minCount: 0
- customIdToLicense:
  - minCount: 0
- score:
  - minCount: 0
  - maxCount: 1
- supportLevel:
  - minCount: 0
  - maxCount: 1

## Constraints

- if element min 1 then rootElement min 1
- element not type Agent
- rootElement not type Agent
- score in 0..10
- supportLevel = noSupport
