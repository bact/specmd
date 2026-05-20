# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Smoke tests for main.py (backward-compatibility entry point).

Verifies that main.py:
  1. Migrates old-format Markdown to the new specmd format.
  2. Passes the *converted* files (not the originals) to the generate step.
  3. Produces mkdocs output without parse errors.

Old-format fixture: tests/fixtures/model-old-format/
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests.conftest import FIXTURE_MODEL_OLD_FORMAT

MAIN_PY = Path(__file__).parent.parent / "main.py"


class TestMainPy:
    def test_migrate_and_generate_mkdocs(self, tmp_path: Path) -> None:
        """main.py migrates old format and generates mkdocs output without errors."""
        mkdocs_out = tmp_path / "mkdocs"

        result = subprocess.run(  # noqa: S603
            [
                sys.executable,
                str(MAIN_PY),
                str(FIXTURE_MODEL_OLD_FORMAT),
                "-m",
                "-M",
                str(mkdocs_out),
            ],
            capture_output=True,
            text=True,
            check=False,  # returncode checked explicitly below
        )

        assert result.returncode == 0, f"main.py exited {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"

        error_lines = [ln for ln in result.stderr.splitlines() if "ERROR:" in ln]
        assert not error_lines, "Unexpected ERROR lines:\n" + "\n".join(error_lines)

        assert mkdocs_out.exists(), "mkdocs output directory not created"
        assert list(mkdocs_out.rglob("*.md")), "No Markdown files generated"

    def test_old_format_not_read_by_generate(self, tmp_path: Path) -> None:
        """Generate step reads migrated files, not the original old-format input.

        If main.py fed the original input to generate, the YAML frontmatter
        check would fail (old files have bare SPDX line, no --- block) and
        the parser would log 'missing YAML frontmatter' errors.
        """
        mkdocs_out = tmp_path / "mkdocs"

        result = subprocess.run(  # noqa: S603
            [
                sys.executable,
                str(MAIN_PY),
                str(FIXTURE_MODEL_OLD_FORMAT),
                "-m",
                "-M",
                str(mkdocs_out),
            ],
            capture_output=True,
            text=True,
            check=False,  # returncode checked explicitly below
        )

        assert "missing YAML frontmatter" not in result.stderr, (
            f"Generate step appears to be reading un-migrated (old-format) files.\nstderr:\n{result.stderr}"
        )
