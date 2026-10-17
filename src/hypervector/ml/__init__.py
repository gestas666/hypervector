"""Optional ML inference (no training).

Primary surface: :class:`~hypervector.ml.metalabel.Metalabeler` — a reusable
metalabel process parameterized by bundle root (any asset/interval version).
Exports resolve lazily so status and help never import pandas or numpy.
"""

from importlib import import_module

_EXPORTS = {
    "ENV_ROOT": ("hypervector.ml.metalabel", "ENV_ROOT"),
    "ENV_ROOT_LEGACY": ("hypervector.ml.metalabel", "ENV_ROOT_LEGACY"),
    "MetalabelError": ("hypervector.ml.metalabel", "MetalabelError"),
    "Metalabeler": ("hypervector.ml.metalabel", "Metalabeler"),
    "probe_metalabel": ("hypervector.ml.metalabel", "probe_metalabel"),
    "resolve_metalabel_root": ("hypervector.ml.metalabel", "resolve_metalabel_root"),
    "FEATURE_NAMES": ("hypervector.ml.feature_matrix", "FEATURE_NAMES"),
    "build_feature_matrix": ("hypervector.ml.feature_matrix", "build_feature_matrix"),
    "run_walk_forward_metalabel": (
        "hypervector.ml.walk_forward",
        "run_walk_forward_metalabel",
    ),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> object:
    """Resolve public services without importing unrelated numerical stacks."""
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module, attribute = _EXPORTS[name]
    value = getattr(import_module(module), attribute)
    globals()[name] = value
    return value
