# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Output generators: one module per supported format, plus the top-level dispatcher."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from specmd._params import RunParams
    from specmd.parse.model import Model


def run(model: Model, cfg: RunParams) -> None:
    """Invoke each enabled generator in turn, passing *cfg* for output paths."""
    if cfg.generate_jsondump:
        from .jsondump import gen_jsondump

        gen_jsondump(model, cfg.output_jsondump_path, cfg)
    if cfg.generate_mkdocs:
        from .mkdocs import gen_mkdocs

        gen_mkdocs(model, cfg.output_mkdocs_path, cfg)
    if cfg.generate_plantuml:
        from .plantuml import gen_plantuml

        gen_plantuml(model, cfg.output_plantuml_path, cfg)
    if cfg.generate_rdf:
        from .rdf import gen_rdf

        gen_rdf(model, cfg.output_rdf_path, cfg)
    if cfg.generate_tex:
        from .tex import gen_tex

        gen_tex(model, cfg.output_tex_path, cfg)
    if cfg.generate_webpages:
        from .webpages import gen_webpages

        gen_webpages(model, cfg.output_webpages_path, cfg)
    if cfg.generate_singlefile:
        from .singlefile import gen_singlefile

        gen_singlefile(model, cfg.output_singlefile_path, cfg)
