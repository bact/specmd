# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Backward-compatibility entry point mimicking the original spec-parser CLI.

This file is provided for a smooth transition. It:
  1. Prints a notice encouraging users to switch to the native ``specmd`` command.
  2. Accepts the original spec-parser command-line arguments.
  3. Runs ``specmd migrate`` to convert old-format Markdown to specmd format in a temp directory.
  4. Runs ``specmd generate`` on the migrated input.
  5. Cleans up the temporary directory on exit.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

# Allow running without installation: add src/ to sys.path when the package
# is not already importable (e.g. in CI that clones the repo but skips pip install).
try:
    import specmd  # noqa: F401
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).parent / "src"))

from specmd.__main__ import main as specmd_main

_NOTICE = """\
\033[33m[specmd compat] Running in compatibility mode via main.py.
[specmd compat] Consider switching to the native `specmd` command for full features.\033[0m
"""


def _parse_legacy_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the original spec-parser argument style."""
    p = argparse.ArgumentParser(
        prog="main.py",
        description="[Compatibility mode] Parse a spec-parser model directory. Use the native `specmd` command for new projects.",
    )
    p.add_argument("input_dir", type=Path, help="Path to the input 'model' directory.")
    p.add_argument("-V", "--version", action="version", version="%(prog)s (specmd compat)")
    p.add_argument("-d", "--debug", action="store_true", help="Print debug information.")
    p.add_argument("-v", "--verbose", action="store_true", help="Print verbose information.")
    p.add_argument("-f", "--force", action="store_true", help="Force overwrite of existing output directories.")
    p.add_argument("-n", "--no-output", action="store_true", help="Validate input only; generate no output.")
    p.add_argument("-o", "--output", type=Path, default=None, metavar="OUTPUT", help="Single output directory for all output types.")
    p.add_argument("-j", "--generate-jsondump", action="store_true")
    p.add_argument("-J", "--output-jsondump", type=Path, default=None, metavar="DIR")
    p.add_argument("-m", "--generate-mkdocs", action="store_true")
    p.add_argument("-M", "--output-mkdocs", type=Path, default=None, metavar="DIR")
    p.add_argument("-p", "--generate-plantuml", action="store_true")
    p.add_argument("-P", "--output-plantuml", type=Path, default=None, metavar="DIR")
    p.add_argument("-r", "--generate-rdf", action="store_true")
    p.add_argument("-R", "--output-rdf", type=Path, default=None, metavar="DIR")
    p.add_argument("-t", "--generate-tex", action="store_true")
    p.add_argument("-T", "--output-tex", type=Path, default=None, metavar="DIR")
    p.add_argument("-w", "--generate-webpages", action="store_true")
    p.add_argument("-W", "--output-webpages", type=Path, default=None, metavar="DIR")
    p.add_argument("-x", "--generate-singlefile", action="store_true")
    p.add_argument("-X", "--output-singlefile", type=Path, default=None, metavar="DIR")
    return p.parse_args(argv)


def _build_generate_argv(args: argparse.Namespace, migrated_input: Path) -> list[str]:
    """Translate legacy args into ``specmd generate`` argv."""
    argv = ["generate", str(migrated_input)]
    if args.debug:
        argv.append("--debug")
    elif args.verbose:
        argv.append("--verbose")
    if args.force:
        argv.append("--force")
    if args.output:
        argv += ["--output", str(args.output)]

    _format_map = ["jsondump", "mkdocs", "plantuml", "rdf", "tex", "webpages", "singlefile"]
    requested = [g for g in _format_map if getattr(args, "generate_" + g, False)]
    if requested:
        argv += ["--formats", ",".join(requested)]
    for g in _format_map:
        val = getattr(args, "output_" + g, None)
        if val is not None:
            argv += [f"--{g}-dir", str(val)]
    return argv


def _build_validate_argv(args: argparse.Namespace, migrated_input: Path) -> list[str]:
    """Translate legacy -n/--no-output into ``specmd validate`` argv."""
    argv = ["validate", str(migrated_input)]
    if args.debug:
        argv.append("--debug")
    elif args.verbose:
        argv.append("--verbose")
    return argv


def main() -> None:
    if "--quiet" not in sys.argv and "-q" not in sys.argv:
        print(_NOTICE, file=sys.stderr)

    args = _parse_legacy_args()

    tmpdir = Path(tempfile.mkdtemp(prefix="specmd_compat_"))
    try:
        # Step 1: migrate old format → new format into tmpdir.
        sys.argv = ["specmd", "migrate", str(args.input_dir), "--output", str(tmpdir)]
        if args.force:
            sys.argv.append("--force")
        specmd_main()

        # Step 2: generate or validate from the migrated input.
        if args.no_output:
            sys.argv = ["specmd", *_build_validate_argv(args, tmpdir)]
        else:
            sys.argv = ["specmd", *_build_generate_argv(args, tmpdir)]
        specmd_main()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
