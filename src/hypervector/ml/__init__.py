"""Optional ML inference (no training).

Primary surface: :class:`~hypervector.ml.metalabel.Metalabeler` — a reusable
metalabel process parameterized by bundle root (any asset/interval version).
"""

from hypervector.ml.metalabel import (
    ENV_ROOT,
    ENV_ROOT_LEGACY,
    MetalabelError,
    Metalabeler,
    probe_metalabel,
    resolve_metalabel_root,
)
from hypervector.ml.feature_matrix import FEATURE_NAMES, build_feature_matrix
from hypervector.ml.walk_forward import run_walk_forward_metalabel

__all__ = [
    "ENV_ROOT",
    "ENV_ROOT_LEGACY",
    "FEATURE_NAMES",
    "MetalabelError",
    "Metalabeler",
    "build_feature_matrix",
    "probe_metalabel",
    "resolve_metalabel_root",
    "run_walk_forward_metalabel",
]
