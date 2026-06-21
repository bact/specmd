---
SPDX-License-Identifier: CC0-1.0
---

# ExternalIdentifierType

## Summary

The kind of an external identifier.

## Description

ExternalIdentifierType enumerates identifier schemes, each with a format pattern.

## Metadata

- name: ExternalIdentifierType

## Entries

- cve:
  - description: A CVE identifier.
  - pattern: `^CVE-[0-9]{4}-[0-9]{4,}$`
- email:
  - description: An email address.
  - pattern: `^[^@]+@[^@]+$`
