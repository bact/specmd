# SPDX-License-Identifier: Apache-2.0

"""specmd -- parse a specification written in Markdown and generate RDF ontology, MkDocs pages, and diagrams."""

__version__ = "0.1.0"

from .parse.model import Model, PropertyNature

__all__ = ["Model", "PropertyNature", "__version__"]
