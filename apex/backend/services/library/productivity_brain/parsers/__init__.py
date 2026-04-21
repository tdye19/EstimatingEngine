"""Format-specific PB parsers. Each module owns one input layout.

New-for-DATA-1.1: multi_project_rates for files that preserve per-project
columns (e.g., CityGate Flint/Bancroft/Hanover/Highland). The legacy
averaged-rates parser in `..parser.py` is intentionally left untouched.
"""

from apex.backend.services.library.productivity_brain.parsers.multi_project_rates import (
    MultiProjectRatesParser,
    ParsedLineItem,
    ParsedProject,
    ParseResult,
)

__all__ = [
    "MultiProjectRatesParser",
    "ParsedProject",
    "ParsedLineItem",
    "ParseResult",
]
