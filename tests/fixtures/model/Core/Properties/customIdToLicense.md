---
SPDX-License-Identifier: CC0-1.0
---

# customIdToLicense

## Summary

Maps a custom identifier to a license element.

## Description

Associates a reference string with the element that defines the license.

## Metadata

- name: customIdToLicense
- nature: ObjectProperty
- range: ElementMap

## Constraints

- /Core/elementValue type /Core/Tool, ElementMap
- key matches `^(LicenseRef-|AdditionRef-)` flags i
