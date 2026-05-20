# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Integration test: specmd and spec-parser produce shacl2code-compatible RDF.

Flow
----
1. Load the ``model-old-format`` fixture with upstream spec-parser → serialize to Turtle.
2. Migrate the same fixture to SpecMD format → load with specmd → serialize to Turtle.
3. Feed both Turtle files to shacl2code ``jsonschema`` generator.
4. Assert the two JSON schemas are identical.

Both ``spec_parser`` and ``shacl2code`` must be importable; the test is
skipped automatically when either is missing.
"""

from __future__ import annotations

import json
import subprocess
import sys  # used by _jsonschema_from_graph for sys.executable
import tempfile
from pathlib import Path

import pytest
from rdflib import Graph

FIXTURE_OLD_FORMAT = Path(__file__).parent / "fixtures" / "model-old-format"

# ---------------------------------------------------------------------------
# Skip guards
# ---------------------------------------------------------------------------

# Both spec_parser and shacl2code are optional dependencies.
# Add spec-parser's directory to PYTHONPATH before running tests if needed.
pytest.importorskip("spec_parser", reason="spec_parser not on PYTHONPATH")
pytest.importorskip("shacl2code", reason="shacl2code not installed")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rdf_via_spec_parser(model_path: Path) -> Graph:
    """Load old-format model with upstream spec_parser and return the rdflib Graph."""
    from spec_parser.model import Model as SpModel  # type: ignore[import-not-found]  # pylint: disable=import-error
    from spec_parser.rdf import gen_rdf_ontology as sp_gen  # type: ignore[import-not-found]  # pylint: disable=import-error

    m = SpModel(model_path)
    return sp_gen(m)


def _rdf_via_specmd_migrate(model_path: Path, tmp: Path) -> Graph:
    """Migrate old-format model then load with specmd; return the rdflib Graph."""
    from specmd.commands.migrate import migrate_directory
    from specmd.generate.rdf import gen_rdf_ontology as sm_gen
    from specmd.parse.model import Model as SmModel

    migrated = tmp / "migrated"
    migrate_directory(model_path, migrated)
    m = SmModel(migrated)
    return sm_gen(m)


def _jsonschema_from_graph(g: Graph, tmp: Path, name: str) -> dict:
    """Serialize *g* to Turtle, run shacl2code jsonschema, return parsed JSON."""
    ttl = tmp / f"{name}.ttl"
    schema = tmp / f"{name}.json"
    g.serialize(str(ttl), format="ttl")
    result = subprocess.run(  # noqa: S603 — argv is fully controlled, no user input
        [sys.executable, "-m", "shacl2code", "generate", "-i", str(ttl), "jsonschema", "-o", str(schema)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"shacl2code failed for {name}:\n{result.stderr}"
    return json.loads(schema.read_text())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestShacl2codeCompatibility:
    def test_jsonschema_identical(self) -> None:
        """specmd (via migrate) and spec-parser produce identical shacl2code JSON schema."""
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            sp_graph = _rdf_via_spec_parser(FIXTURE_OLD_FORMAT)
            sm_graph = _rdf_via_specmd_migrate(FIXTURE_OLD_FORMAT, tmp)
            sp_schema = _jsonschema_from_graph(sp_graph, tmp, "spec-parser")
            sm_schema = _jsonschema_from_graph(sm_graph, tmp, "specmd")

        # Strip the auto-generated comment (contains tool name/version).
        for schema in (sp_schema, sm_schema):
            schema.pop("$comment", None)

        assert sp_schema == sm_schema, (
            "shacl2code JSON schema differs between spec-parser and specmd output.\n"
            "This indicates a SHACL shape incompatibility in specmd's RDF generation."
        )
