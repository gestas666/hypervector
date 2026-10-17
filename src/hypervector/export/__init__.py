"""Strategy export bundles.

Exports resolve lazily (PEP 562) so importing ``hypervector.export.schema`` for
read-only inspection never loads pandas through the bundle writer.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "EXPORT_SCHEMA_VERSION": "hypervector.export.schema",
    "ExportSchemaError": "hypervector.export.schema",
    "validate_export_dir": "hypervector.export.schema",
    "export_candidate": "hypervector.export.phase2",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_EXPORTS})
