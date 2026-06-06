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
  - excludeType: Agent
  - minCount: 0
- rootElement:
  - excludeType: Agent
  - minCount: 0

## Constraints

- if element min 1 then rootElement min 1
