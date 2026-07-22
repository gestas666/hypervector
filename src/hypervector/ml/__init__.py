"""Optional ML inference (no training).

Primary surface: :class:`~hypervector.ml.metalabel.Metalabeler` — a reusable
metalabel process parameterized by bundle root (any asset/interval version).
"""

from hypervector.ml.metalabel import (
    ENV_ROOT,
    ENV_ROOT_LEGACY,
    MetalabelError,
    Metalabeler,
    resolve_metalabel_root,
)

__all__ = [
    "ENV_ROOT",
    "ENV_ROOT_LEGACY",
    "MetalabelError",
    "Metalabeler",
    "resolve_metalabel_root",
]
