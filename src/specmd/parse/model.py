# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""In-memory model of the parsed spec: namespaces, classes, properties, vocabularies, datatypes, individuals, and inheritance."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from copy import deepcopy
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar

import yaml

from .markdown import ContentSection, NestedListSection, SingleListSection, SpecFile, VocabDefaults, VocabularySection, _split_class_list

logger = logging.getLogger(__name__)


_RE_QUALIFIED_CLASS = re.compile(r"^([^\[]+)(?:\[([^\]]*)\])?$")


def _parse_qualified_class(item: str) -> tuple[str, dict[str, list[str]]]:
    """Parse ``ClassName[prop1=v1,v2;prop2=v3]`` into ``(base_name, qualifiers)``.

    Qualifier syntax inside ``[...]``:
    - Props are separated by ``;``.
    - Multiple values for one prop are separated by ``,``.
    - Example: ``Relationship[relationshipType=a,b,c;scope=build]``
      → ``("Relationship", {"relationshipType": ["a", "b", "c"], "scope": ["build"]})``

    Returns ``(item.strip(), {})`` if the format is not recognised or has no
    qualifier block.
    """
    m = _RE_QUALIFIED_CLASS.match(item.strip())
    if not m:
        return item.strip(), {}
    base = m.group(1).strip()
    qualifier_str = m.group(2) or ""
    qualifiers: dict[str, list[str]] = {}
    for prop_expr in qualifier_str.split(";"):
        expr = prop_expr.strip()
        if not expr:
            continue
        if "=" in expr:
            key, _, vals_str = expr.partition("=")
            qualifiers[key.strip()] = [v.strip() for v in vals_str.split(",") if v.strip()]
        else:
            qualifiers[expr] = []
    return base, qualifiers


def _parse_class_list_config(val: object, default: list[str]) -> list[str]:
    """Parse a ``default-from`` / ``default-to`` config value into a ``list[str]``.

    Accepts a YAML list (``["Agent", "Tool"]``), a comma-separated string
    (``"Agent, Tool"``), or ``None`` (returns *default*).
    """
    if val is None:
        return list(default)
    if isinstance(val, list):
        return [str(v).strip() for v in val if str(v).strip()]
    if isinstance(val, str):
        return _split_class_list(val)
    return list(default)


class PropertyNature(StrEnum):
    """Allowed values for the ``Nature`` metadata field on properties."""

    OBJECT_PROPERTY = "ObjectProperty"
    DATA_PROPERTY = "DataProperty"


class Model:
    """Top-level container for an entire parsed spec: all namespaces and their contents."""

    def __init__(self, inpath: Path | None = None) -> None:
        self.name: str | None = None
        self.namespaces: list[Namespace] = []
        self.classes: dict[str, Class] = {}
        self.properties: dict[str, Property] = {}
        self.vocabularies: dict[str, Vocabulary] = {}
        self.individuals: dict[str, Individual] = {}
        self.datatypes: dict[str, Datatype] = {}
        self.types: dict[str, Class | Vocabulary | Datatype] = {}
        self.class_hierarchy: dict[str, list[str]] = {}
        self.toplevel_classes: list[str] = []
        self.base_uri: str = ""
        self.config: dict[str, Any] = {}

        if inpath is not None:
            self.load(inpath)

    def load(self, inpath: Path) -> None:
        """Scan *inpath* for namespace directories and populate all model collections."""
        config_path = inpath / "specmd.yml"
        if config_path.is_file():
            self.config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            logger.info("Loaded configuration from %s", config_path)
        else:
            self.config = {}

        for d in [d for d in inpath.iterdir() if d.is_dir() and d.name[0].isupper()]:
            nsp = inpath / d.name / f"{d.name}.md"
            if not nsp.is_file():
                logger.error("Missing top-level namespace file: %s", nsp)
                continue

            ns = Namespace(nsp)
            self.namespaces.append(ns)

            n: Class | Property | Vocabulary | Individual | Datatype
            dp = inpath / d.name / "Classes"
            if dp.is_dir():
                for f in [f for f in dp.iterdir() if f.is_file() and f.name[0].isupper() and f.name.endswith(".md")]:
                    n = Class(f, ns)
                    k = n.fqname
                    self.classes[k] = n
                    ns.classes[k] = n

            dp = inpath / d.name / "Properties"
            if dp.is_dir():
                for f in [f for f in dp.iterdir() if f.is_file() and f.name[0].islower() and f.name.endswith(".md")]:
                    n = Property(f, ns)
                    k = n.fqname
                    self.properties[k] = n
                    ns.properties[k] = n

            dp = inpath / d.name / "Vocabularies"
            if dp.is_dir():
                default_rel_class: str = self.config.get("default-relationship-class", "Relationship")
                default_from: list[str] = _parse_class_list_config(self.config.get("default-from"), ["Element"])
                default_to: list[str] = _parse_class_list_config(self.config.get("default-to"), ["Element"])
                for f in [f for f in dp.iterdir() if f.is_file() and f.name[0].isupper() and f.name.endswith(".md")]:
                    n = Vocabulary(
                        f,
                        ns,
                        defaults=VocabDefaults(
                            default_from=default_from,
                            default_to=default_to,
                            default_relationship_class=default_rel_class,
                        ),
                    )
                    k = n.fqname
                    self.vocabularies[k] = n
                    ns.vocabularies[k] = n

            dp = inpath / d.name / "Individuals"
            if dp.is_dir():
                for f in [f for f in dp.iterdir() if f.is_file() and f.name[0].isupper() and f.name.endswith(".md")]:
                    n = Individual(f, ns)
                    k = n.fqname
                    self.individuals[k] = n
                    ns.individuals[k] = n

            dp = inpath / d.name / "Datatypes"
            if dp.is_dir():
                for f in [f for f in dp.iterdir() if f.is_file() and f.name[0].isupper() and f.name.endswith(".md")]:
                    n = Datatype(f, ns)
                    k = n.fqname
                    self.datatypes[k] = n
                    ns.datatypes[k] = n

        logger.info(
            "Loaded %d namespaces, %d classes, %d properties, %d vocabularies, %d individuals, %d datatypes",
            len(self.namespaces),
            len(self.classes),
            len(self.properties),
            len(self.vocabularies),
            len(self.individuals),
            len(self.datatypes),
        )
        self._process_after_load()

    def _process_after_load(self) -> None:
        self.types = {**self.classes, **self.vocabularies, **self.datatypes}
        logger.info("Total %d types", len(self.types))

        self.base_uri = self._derive_base_uri()
        self.validate_vocab_entries()

        for c in self.classes.values():
            for p in c.properties:
                pname = p if p.startswith("/") else f"/{c.ns.name}/{p}"
                self.properties[pname].used_in.append(c.fqname)

        inheritances: list[tuple[str, str]] = []
        for c in self.classes.values():
            parent = c.fqsupercname
            if parent:
                inheritances.append((c.fqname, parent))
                if parent in self.classes:
                    self.classes[parent].direct_subclasses.append(c.fqname)

        tree: dict[str, list[str]] = defaultdict(list)
        children: set[str] = set()
        nodes: set[str] = set()
        for child, parent in inheritances:
            tree[parent].append(child)
            children.add(child)
            nodes.add(parent)
            nodes.add(child)
        self.class_hierarchy = dict(tree)
        self.toplevel_classes = list(nodes - children)

        # Topological sort so that parent classes are processed before children.
        visited: dict[str, bool] = {c.fqname: False for c in self.classes.values()}
        stack: list[str] = []

        def _tsort(cn: str) -> None:
            visited[cn] = True
            for chd, par in inheritances:
                if chd == cn and not visited[par]:
                    _tsort(par)
            stack.append(cn)

        for c in self.classes.values():
            if not visited[c.fqname]:
                _tsort(c.fqname)

        for cn in stack:
            c = self.classes[cn]
            pcn = c.fqsupercname
            while pcn:
                c.inheritance_stack.append(pcn)
                pcn = self.classes[pcn].fqsupercname

        for cn in stack:
            c = self.classes[cn]
            c.all_properties = {}
            for p, pkv in c.properties.items():
                shortname = p.rpartition("/")[-1]
                fullname = p if p.startswith("/") else f"/{c.ns.name}/{p}"
                prop = self.properties[fullname]
                prop_range = prop.metadata["range"]
                fulltype = prop_range if prop_range.startswith(("/", "xsd:")) else f"/{prop.ns.name}/{prop_range}"
                c.all_properties[shortname] = deepcopy(pkv)
                c.all_properties[shortname]["fullname"] = fullname
                c.all_properties[shortname]["fulltype"] = fulltype

            if c.inheritance_stack:
                parent_cn = c.inheritance_stack[0]
                c.all_properties.update(deepcopy(self.classes[parent_cn].all_properties))

            for p, pkv in c.ext_prop_restrs.items():
                (_, pns, _, shortname) = p.split("/")
                assert c.all_properties[shortname]["fullname"] == f"/{pns}/{shortname}"
                for k, v in pkv.items():
                    if c.all_properties[shortname][k] == v:
                        logger.warning(
                            "In class %s property %s has same %s as the parent class",
                            c.fqname,
                            p,
                            k,
                        )
                    c.all_properties[shortname][k] = v

    def validate_vocab_entries(self) -> None:
        """Warn about unknown class or property names in vocabulary ``from``/``to``/``relationshipClass``."""
        short_type_names: set[str] = {fqn.rpartition("/")[2] for fqn in self.types}
        short_class_names: set[str] = {fqn.rpartition("/")[2] for fqn in self.classes}
        short_prop_names: set[str] = {fqn.rpartition("/")[2] for fqn in self.properties}

        def _check_class(name: str, loc: str, field: str) -> None:
            base, qualifiers = _parse_qualified_class(name)
            if base not in short_type_names and base not in self.types:
                logger.warning("%s: %s: unknown class %r", loc, field, base)
            for prop in qualifiers:
                if prop not in short_prop_names and prop not in self.properties:
                    logger.warning("%s: %s: qualifier uses unknown property %r in %r", loc, field, prop, name)

        for vocab in self.vocabularies.values():
            for entry_name, entry in vocab.entries.items():
                loc = f"{vocab.fqname}/{entry_name}"
                for field in ("from", "to"):
                    items = entry.get(field)
                    if isinstance(items, list):
                        for item in items:
                            _check_class(str(item), loc, field)
                rel_class = entry.get("relationshipClass")
                if rel_class and isinstance(rel_class, str):
                    base, _ = _parse_qualified_class(rel_class)
                    if base not in short_class_names and base not in self.classes:
                        logger.warning("%s: relationshipClass: unknown class %r", loc, base)

    def _derive_base_uri(self) -> str:
        """Derive the ontology base URI from the Core namespace IRI, if present."""
        for ns in self.namespaces:
            iri = ns.metadata.get("id", "")
            if iri.endswith("/Core/"):
                return iri[: -len("Core/")]
            if iri.endswith("/Core"):
                prefix = iri[: -len("Core")]
                return prefix if prefix.endswith("/") else prefix + "/"
        # Fall back: use the longest common prefix of all namespace IRIs.
        iris = [ns.metadata.get("id", "") for ns in self.namespaces if ns.metadata.get("id")]
        if not iris:
            return ""
        common = iris[0]
        for iri in iris[1:]:
            while not iri.startswith(common):
                common = common[: common.rfind("/", 0, -1) + 1]
        logger.warning("No Core namespace found; derived base URI: %s", common)
        return common

    def namespace_order(self) -> list[str]:
        """Return the ordered list of namespace names to generate.

        If ``specmd.yml`` defines ``namespace-order``, that explicit list governs.
        Namespaces listed in config but absent from the model are warned and skipped.
        Namespaces present in the model but absent from the list are excluded by
        default (treat omission as deliberate intent) with a warning.
        Set ``include-unlisted-namespaces: true`` to append them alphabetically instead.

        If no config file exists, or ``namespace-order`` is not set, all namespaces
        are returned in alphabetical order.
        """
        explicit: list[str] | None = self.config.get("namespace-order")
        known = {ns.name for ns in self.namespaces}

        if explicit is None:
            return sorted(known)

        for name in explicit:
            if name not in known:
                logger.warning("specmd.yml namespace-order: %r not found in model -- skipping", name)

        ordered = [n for n in explicit if n in known]

        unlisted = known - set(ordered)
        if unlisted:
            if self.config.get("include-unlisted-namespaces", False):
                ordered += sorted(unlisted)
            else:
                logger.warning(
                    "Namespaces excluded from generation (not listed in namespace-order): %s",
                    ", ".join(sorted(unlisted)),
                )

        return ordered

    @property
    def spdx_license(self) -> str:
        """SPDX license identifier for generated output documents.

        Resolution order:
        1. ``license`` key in ``specmd.yml``
        2. ``SPDX-License-Identifier`` from the first namespace source file
        3. Empty string (no identifier added)
        """
        cfg_license: str | None = self.config.get("license")
        if cfg_license:
            return cfg_license
        for ns in self.namespaces:
            if ns.license:
                return ns.license
        return ""


class Namespace:
    """A single namespace directory (e.g. ``Core``), holding all its model elements."""

    def __init__(self, fname: Path) -> None:
        self.classes: dict[str, Class] = {}
        self.properties: dict[str, Property] = {}
        self.vocabularies: dict[str, Vocabulary] = {}
        self.individuals: dict[str, Individual] = {}
        self.datatypes: dict[str, Datatype] = {}

        sf = SpecFile(fname)
        self.license: str | None = sf.license
        self.name: str = sf.name

        cs = ContentSection(sf.sections["Summary"])
        self.summary: str = cs.content

        cs = ContentSection(sf.sections["Description"])
        self.description: str = cs.content

        ss = SingleListSection(sf.sections["Metadata"])
        self.metadata: dict[str, str] = ss.kv

        if "Profile conformance" in sf.sections:
            cs = ContentSection(sf.sections["Profile conformance"])
            self.conformance: str | None = cs.content
        else:
            self.conformance = None

        assert self.name == self.metadata["name"], f"Namespace name {self.name} does not match metadata {self.metadata['name']}"

        self.iri: str = self.metadata["id"]
        self.translations: dict[str, dict[str, str]] = _load_text_translations(sf)


def _load_text_translations(sf: SpecFile) -> dict[str, dict[str, str]]:
    """Extract per-language Summary/Description translations from *sf*.

    Returns ``{lang: {"summary": str, "description": str}}`` for every
    language tag found in ``sf.translations``.  Only keys that are present
    in the source file are included.
    """
    result: dict[str, dict[str, str]] = {}
    for lang, lang_secs in sf.translations.items():
        t: dict[str, str] = {}
        for sec in ("Summary", "Description"):
            if sec in lang_secs:
                t[sec.lower()] = ContentSection(lang_secs[sec]).content
        if t:
            result[lang] = t
    return result


def _normalize_metadata(kv: dict[str, str], renames: dict[str, str]) -> dict[str, str]:
    """Rename keys case-insensitively according to *renames* (lowercase key → canonical key)."""
    result: dict[str, str] = {}
    for k, v in kv.items():
        result[renames.get(k.lower(), k)] = v
    return result


def _normalize_class_metadata(kv: dict[str, str]) -> dict[str, str]:
    """Normalise old-format metadata keys to canonical new-format keys.

    Accepted legacy forms (case-insensitive):
    - ``SubclassOf`` → ``subClassOf``
    - ``Instantiability: Abstract`` → ``abstract: true``
    - ``Instantiability: Concrete`` → omitted (false is the default)
    """
    result: dict[str, str] = {}
    for k, v in kv.items():
        kl = k.lower()
        if kl == "subclassof":
            result["subClassOf"] = v
        elif kl == "instantiability":
            if v.lower() == "abstract":
                result["abstract"] = "true"
            # Concrete → omit; false is the default
        else:
            result[k] = v
    return result


class Class:
    """A class definition parsed from a ``Classes/<Name>.md`` file."""

    VALID_METADATA: tuple[str, ...] = (
        "abstract",
        "deprecated",
        "deprecatedVersion",
        "example",
        "isReplacedBy",
        "name",
        "sinceVersion",
        "subClassOf",
    )
    VALID_PROP_METADATA: tuple[str, ...] = (
        "maxCount",
        "minCount",
    )

    def __init__(self, fname: Path, ns: Namespace) -> None:
        self.ns: Namespace = ns

        sf = SpecFile(fname)
        self.license: str | None = sf.license
        self.name: str = sf.name
        self.fqname: str = f"/{ns.name}/{sf.name}"

        cs = ContentSection(sf.sections["Summary"], filename=self.fqname, context="summary")
        self.summary: str = cs.content

        cs = ContentSection(sf.sections["Description"], filename=self.fqname, context="description")
        self.description: str = cs.content

        ss = SingleListSection(sf.sections["Metadata"], filename=self.fqname, context="metadata")
        self.metadata: dict[str, str] = _normalize_class_metadata(ss.kv)

        if "Properties" in sf.sections:
            s2 = NestedListSection(sf.sections["Properties"], filename=self.fqname, context="properties")
            self.properties: dict[str, dict[str, str]] = s2.ikv
        else:
            self.properties = {}

        if "External properties restrictions" in sf.sections:
            s2 = NestedListSection(
                sf.sections["External properties restrictions"],
                filename=self.fqname,
                context="external properties restrictions",
            )
            self.ext_prop_restrs: dict[str, dict[str, str]] = s2.ikv
        else:
            self.ext_prop_restrs = {}

        if self.name != self.metadata.get("name", ""):
            logger.error("%s: heading name %r does not match metadata name: %r", fname, self.name, self.metadata.get("name"))
        for p in self.metadata:
            if p not in self.VALID_METADATA:
                logger.error("%s: unknown metadata key %r; expected one of: %s", fname, p, ", ".join(sorted(self.VALID_METADATA)))
        for prop, pkv in self.properties.items():
            for p in pkv:
                if p not in self.VALID_PROP_METADATA:
                    logger.error(
                        "%s: property %r has unknown attribute %r; expected one of: %s",
                        fname,
                        prop,
                        p,
                        ", ".join(sorted(self.VALID_PROP_METADATA)),
                    )

        self.iri: str = f"{self.ns.iri}/{self.name}"
        if self.metadata.get("subClassOf") == "none":
            del self.metadata["subClassOf"]
        for prop in self.properties:
            self.properties[prop]["fqname"] = prop if prop.startswith("/") else f"/{ns.name}/{prop}"
            if "minCount" not in self.properties[prop]:
                self.properties[prop]["minCount"] = "0"
            if "maxCount" not in self.properties[prop]:
                self.properties[prop]["maxCount"] = "*"

        parent = self.metadata.get("subClassOf")
        if parent and not parent.startswith("/"):
            parent = f"/{ns.name}/{parent}"
        self.fqsupercname: str | None = parent

        self.inheritance_stack: list[str] = []
        self.direct_subclasses: list[str] = []
        self.all_properties: dict[str, dict[str, str]] = {}
        self.translations: dict[str, dict[str, str]] = _load_text_translations(sf)


class Property:
    """A property definition parsed from a ``Properties/<name>.md`` file."""

    _METADATA_RENAMES: ClassVar[dict[str, str]] = {"nature": "nature", "range": "range"}

    VALID_METADATA: tuple[str, ...] = (
        "deprecated",
        "deprecatedVersion",
        "example",
        "isReplacedBy",
        "name",
        "nature",
        "range",
        "sinceVersion",
    )
    REQUIRED_METADATA: tuple[str, ...] = ("name", "nature", "range")

    def __init__(self, fname: Path, ns: Namespace) -> None:
        self.ns: Namespace = ns

        sf = SpecFile(fname)
        self.license: str | None = sf.license
        self.name: str = sf.name
        self.fqname: str = f"/{ns.name}/{sf.name}"

        cs = ContentSection(sf.sections["Summary"], filename=self.fqname, context="summary")
        self.summary: str = cs.content

        cs = ContentSection(sf.sections["Description"], filename=self.fqname, context="description")
        self.description: str = cs.content

        ss = SingleListSection(sf.sections["Metadata"], filename=self.fqname, context="metadata")
        self.metadata: dict[str, str] = _normalize_metadata(ss.kv, self._METADATA_RENAMES)

        if self.name != self.metadata.get("name", ""):
            logger.error("%s: heading name %r does not match metadata name: %r", fname, self.name, self.metadata.get("name"))
        for p in self.metadata:
            if p not in self.VALID_METADATA:
                logger.error("%s: unknown metadata key %r; expected one of: %s", fname, p, ", ".join(sorted(self.VALID_METADATA)))
        for p in self.REQUIRED_METADATA:
            if p not in self.metadata:
                logger.error("%s: missing required metadata field %r", fname, p)

        self.iri: str = f"{self.ns.iri}/{self.name}"
        self.used_in: list[str] = []
        self.translations: dict[str, dict[str, str]] = _load_text_translations(sf)


class Vocabulary:
    """A closed enumeration parsed from a ``Vocabularies/<Name>.md`` file."""

    VALID_METADATA: tuple[str, ...] = (
        "deprecated",
        "deprecatedVersion",
        "example",
        "isReplacedBy",
        "name",
        "sinceVersion",
    )

    def __init__(
        self,
        fname: Path,
        ns: Namespace,
        defaults: VocabDefaults | None = None,
    ) -> None:
        self.ns: Namespace = ns

        sf = SpecFile(fname)
        self.license: str | None = sf.license
        self.name: str = sf.name
        self.fqname: str = f"/{ns.name}/{sf.name}"

        cs = ContentSection(sf.sections["Summary"], filename=self.fqname, context="summary")
        self.summary: str = cs.content

        cs = ContentSection(sf.sections["Description"], filename=self.fqname, context="description")
        self.description: str = cs.content

        ss = SingleListSection(sf.sections["Metadata"], filename=self.fqname, context="metadata")
        self.metadata: dict[str, str] = ss.kv

        _d = defaults or VocabDefaults()
        vs = VocabularySection(
            sf.sections["Entries"],
            filename=self.fqname,
            context="entries",
            defaults=_d,
        )
        self.entries: dict[str, dict[str, object]] = vs.entries

        if self.name != self.metadata.get("name", ""):
            logger.error("%s: heading name %r does not match metadata name: %r", fname, self.name, self.metadata.get("name"))
        for p in self.metadata:
            if p not in self.VALID_METADATA:
                logger.error("%s: unknown metadata key %r; expected one of: %s", fname, p, ", ".join(sorted(self.VALID_METADATA)))

        self.iri: str = f"{self.ns.iri}/{self.name}"

        self.is_relationship_vocab: bool = any(
            entry.get("from") != _d.default_from
            or entry.get("to") != _d.default_to
            or entry.get("relationshipClass") != _d.default_relationship_class
            for entry in self.entries.values()
        )

        self.translations: dict[str, dict[str, object]] = {}
        for lang, lang_secs in sf.translations.items():
            t: dict[str, object] = {}
            for sec in ("Summary", "Description"):
                if sec in lang_secs:
                    t[sec.lower()] = ContentSection(lang_secs[sec]).content
            if "Entries" in lang_secs:
                # Translated entries are always simple "- name: translated desc" lists.
                es = SingleListSection(lang_secs["Entries"], filename=self.fqname, context=f"entries @{lang}")
                t["entries"] = es.kv
            if t:
                self.translations[lang] = t


class Individual:
    """A named individual parsed from an ``Individuals/<Name>.md`` file."""

    _METADATA_RENAMES: ClassVar[dict[str, str]] = {"iri": "iri"}

    VALID_METADATA: tuple[str, ...] = (
        "deprecated",
        "deprecatedVersion",
        "example",
        "iri",
        "isReplacedBy",
        "name",
        "sameAs",
        "sinceVersion",
        "type",
    )

    def __init__(self, fname: Path, ns: Namespace) -> None:
        self.ns: Namespace = ns

        sf = SpecFile(fname)
        self.license: str | None = sf.license
        self.name: str = sf.name
        self.fqname: str = f"/{ns.name}/{sf.name}"

        cs = ContentSection(sf.sections["Summary"], filename=self.fqname, context="summary")
        self.summary: str = cs.content

        cs = ContentSection(sf.sections["Description"], filename=self.fqname, context="description")
        self.description: str = cs.content

        ss = SingleListSection(sf.sections["Metadata"], filename=self.fqname, context="metadata")
        self.metadata: dict[str, str] = _normalize_metadata(ss.kv, self._METADATA_RENAMES)

        ss = SingleListSection(sf.sections["Property values"], filename=self.fqname, context="property values")
        self.values: dict[str, str] = ss.kv

        if self.name != self.metadata.get("name", ""):
            logger.error("%s: heading name %r does not match metadata name: %r", fname, self.name, self.metadata.get("name"))
        for p in self.metadata:
            if p not in self.VALID_METADATA:
                logger.error("%s: unknown metadata key %r; expected one of: %s", fname, p, ", ".join(sorted(self.VALID_METADATA)))

        self.iri: str = f"{self.ns.iri}/{self.name}"
        if "iri" not in self.metadata:
            self.metadata["iri"] = self.iri
        self.translations: dict[str, dict[str, str]] = _load_text_translations(sf)


class Datatype:
    """A scalar datatype definition parsed from a ``Datatypes/<Name>.md`` file."""

    _METADATA_RENAMES: ClassVar[dict[str, str]] = {"subclassof": "subClassOf"}

    VALID_METADATA: tuple[str, ...] = (
        "deprecated",
        "deprecatedVersion",
        "example",
        "isReplacedBy",
        "name",
        "sinceVersion",
        "subClassOf",
    )

    def __init__(self, fname: Path, ns: Namespace) -> None:
        self.ns: Namespace = ns

        sf = SpecFile(fname)
        self.license: str | None = sf.license
        self.name: str = sf.name
        self.fqname: str = f"/{ns.name}/{sf.name}"

        cs = ContentSection(sf.sections["Summary"], filename=self.fqname, context="summary")
        self.summary: str = cs.content

        cs = ContentSection(sf.sections["Description"], filename=self.fqname, context="description")
        self.description: str = cs.content

        ss = SingleListSection(sf.sections["Metadata"], filename=self.fqname, context="metadata")
        self.metadata: dict[str, str] = _normalize_metadata(ss.kv, self._METADATA_RENAMES)

        ss = SingleListSection(sf.sections["Format"], filename=self.fqname, context="format")
        self.format: dict[str, str] = ss.kv

        if self.name != self.metadata.get("name", ""):
            logger.error("%s: heading name %r does not match metadata name: %r", fname, self.name, self.metadata.get("name"))
        for p in self.metadata:
            if p not in self.VALID_METADATA:
                logger.error("%s: unknown metadata key %r; expected one of: %s", fname, p, ", ".join(sorted(self.VALID_METADATA)))

        self.iri: str = f"{self.ns.iri}/{self.name}"
        self.translations: dict[str, dict[str, str]] = _load_text_translations(sf)
