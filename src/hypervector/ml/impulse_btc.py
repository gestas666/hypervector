"""Deprecated aliases — use :mod:`hypervector.ml.metalabel` instead.

Kept so older imports and docs snippets keep working for one cycle.
"""

from __future__ import annotations

import warnings

from hypervector.ml.metalabel import (
    ENV_ROOT_LEGACY as ENV_ROOT,
    MetalabelError as ImpulseBundleError,
    Metalabeler as ImpulseBtcFacade,
    resolve_metalabel_root as resolve_impulse_btc_root,
)

warnings.warn(
    "hypervector.ml.impulse_btc is deprecated; use hypervector.ml.metalabel "
    "(Metalabeler, MetalabelError, HYPERVECTOR_METALABEL_ROOT)",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "ENV_ROOT",
    "ImpulseBtcFacade",
    "ImpulseBundleError",
    "resolve_impulse_btc_root",
]
