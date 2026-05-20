# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Entry point for ``python -m specmd`` and the ``specmd`` CLI command."""

import logging
import shutil
import sys

from specmd import generate
from specmd._logging import LogCountingHandler, setup_logging
from specmd._params import RunParams
from specmd.commands.export import export_directory
from specmd.commands.migrate import migrate_directory
from specmd.commands.validate import validate_inplace, validate_yaml_sections
from specmd.parse.model import Model


def main() -> None:
    """Dispatch to the appropriate specmd subcommand."""
    _argv = sys.argv[1:]
    if "--debug" in _argv or "--verbose" in _argv or "-v" in _argv:
        _level = logging.DEBUG
    elif "--quiet" in _argv or "-q" in _argv:
        _level = logging.WARNING
    else:
        _level = logging.INFO
    root_logger, handler = setup_logging(level=_level)
    root_logger.info("SpecMD starts.")

    cfg = RunParams("specmd")
    if handler.has_errors():
        root_logger.error("Errors during parameter processing. Exiting.")
        sys.exit(1)

    if cfg.command == "validate":
        _cmd_validate(cfg, root_logger, handler)
    elif cfg.command == "generate":
        _cmd_generate(cfg, root_logger, handler)
    elif cfg.command == "migrate":
        _cmd_migrate(cfg, root_logger, handler)
    elif cfg.command == "export":
        _cmd_export(cfg, root_logger, handler)


def _cmd_validate(cfg: RunParams, root_logger: logging.Logger, handler: LogCountingHandler) -> None:
    if cfg.input_path.is_file():
        _cmd_validate_file(cfg, root_logger)
    else:
        _cmd_validate_directory(cfg, root_logger, handler)


def _cmd_validate_file(cfg: RunParams, root_logger: logging.Logger) -> None:
    """Validate a single .md file: raw YAML section check only."""
    errors = validate_yaml_sections(cfg.input_path)
    for section_name, msg in errors:
        root_logger.warning("  [%s]: %s", section_name, msg)

    issues = len(errors)
    root_logger.info(
        "Validation complete: 1 file checked, %d section issue(s) found.",
        issues,
    )
    if issues and cfg.strict:
        root_logger.error("Raw YAML issues found. Exiting (--strict).")
        sys.exit(1)


def _cmd_validate_directory(cfg: RunParams, root_logger: logging.Logger, handler: LogCountingHandler) -> None:
    """Validate a model directory: raw YAML check then full semantic load."""
    # Step 1: raw YAML syntax check (independent of the parser's safety net).
    valid_files, invalid_files = validate_inplace(cfg.input_path)
    total_files = valid_files + invalid_files

    if invalid_files:
        root_logger.warning(
            "Raw YAML check: %d of %d file(s) have sections with unquoted YAML-unsafe "
            "characters. Run 'specmd migrate' to fix them automatically.",
            invalid_files,
            total_files,
        )

    if invalid_files and cfg.strict:
        root_logger.error("Raw YAML issues found. Exiting (--strict).")
        root_logger.info(
            "Validation complete: %d file(s) checked, %d file(s) with issues.",
            total_files,
            invalid_files,
        )
        sys.exit(1)

    # Step 2: full semantic validation via model loading.
    try:
        Model(cfg.input_path)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        root_logger.exception("Unexpected error loading the model: %s", exc)  # noqa: TRY401

    if _exit_on_errors(handler, root_logger, "Errors loading the model."):
        return

    root_logger.info(
        "Validation complete: %d file(s) checked, %d file(s) with issues.",
        total_files,
        invalid_files,
    )
    root_logger.info("Model at '%s' is valid.", cfg.input_path)


def _cmd_generate(cfg: RunParams, root_logger: logging.Logger, handler: LogCountingHandler) -> None:
    cfg.create_output_dirs()
    if _exit_on_errors(handler, root_logger, "Errors creating output directories."):
        return

    m = Model(cfg.input_path)
    if _exit_on_errors(handler, root_logger, "Errors loading the model."):
        return

    generate.run(m, cfg)
    _exit_on_errors(handler, root_logger, "Errors during generation.")


def _cmd_migrate(cfg: RunParams, root_logger: logging.Logger, handler: LogCountingHandler) -> None:  # noqa: ARG001
    if cfg.output_path.exists() and not cfg.force:
        root_logger.error("Output directory '%s' already exists (use -f/--force to overwrite).", cfg.output_path)
        sys.exit(1)
    if cfg.force and cfg.output_path.exists():
        shutil.rmtree(cfg.output_path)

    root_logger.info("Migrating '%s' → '%s'.", cfg.input_path, cfg.output_path)
    changed, skipped = migrate_directory(cfg.input_path, cfg.output_path)
    root_logger.info("Migration complete: %d migrated, %d already up-to-date.", changed, skipped)


def _cmd_export(cfg: RunParams, root_logger: logging.Logger, handler: LogCountingHandler) -> None:  # noqa: ARG001
    if cfg.output_path.exists() and not cfg.force:
        root_logger.error("Output directory '%s' already exists (use -f/--force to overwrite).", cfg.output_path)
        sys.exit(1)
    if cfg.force and cfg.output_path.exists():
        shutil.rmtree(cfg.output_path)

    root_logger.info("Exporting '%s' → '%s' (format: %s).", cfg.input_path, cfg.output_path, cfg.export_format)
    changed, skipped = export_directory(cfg.input_path, cfg.output_path, cfg.export_format)
    root_logger.info("Export complete: %d exported, %d unchanged.", changed, skipped)


def _exit_on_errors(handler: LogCountingHandler, root_logger: logging.Logger, msg: str) -> bool:
    if handler.has_errors():
        root_logger.error("%s Exiting.", msg)
        errors = handler.error_messages()
        sys.stderr.write(f"\nTotal errors: {len(errors)}\n")
        for i, err in enumerate(errors, 1):
            sys.stderr.write(f"  {i}: {err}\n")
        sys.exit(1)
    return False


if __name__ == "__main__":
    main()
