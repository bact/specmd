SPDX-License-Identifier: Community-Spec-1.0

# seeAlso

## Summary

See also reference.

## Description

References a related resource.
This property intentionally has only a type declaration in the class properties
section (no minCount/maxCount), so after migration it becomes an empty property.
This exercises the BaseLoader empty-string handling in the parser.

## Metadata

- name: seeAlso
- Nature: ObjectProperty
- Range: xsd:anyURI
