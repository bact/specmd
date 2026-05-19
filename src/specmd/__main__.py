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
    root_logger.info("specmd starts.")

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
    Model(cfg.input_path)
    if _exit_on_errors(handler, root_logger, "Errors loading the model."):
        return
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
