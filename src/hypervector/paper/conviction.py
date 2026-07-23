"""Conviction providers for paper sizing: fixed or metalabel scale-only.

Policy (Phase 4a): when metalabel is enabled, conviction = clip(p, 0, 1)
with **no skip floor**. Any feature/predict failure → fixed fallback and
``source=fallback_fixed``. Metalabel is default **off** at the session layer.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pandas as pd

from hypervector.ml.features import FeatureBuilder, FeatureBuildError

logger = logging.getLogger(__name__)

__all__ = [
    "ConvictionProvider",
    "ConvictionResult",
    "FeatureBuilder",
    "FeatureBuildError",
    "FixedConvictionProvider",
    "MetalabelConvictionProvider",
]


@dataclass(frozen=True)
class ConvictionResult:
    """Resolved conviction for one sizing decision."""

    conviction: float
    source: str  # fixed | metalabel | fallback_fixed
    metalabel_p: float | None
    metalabel_bundle_id: str | None


class ConvictionProvider(Protocol):
    def resolve(
        self,
        *,
        features: Mapping[str, float] | None = None,
        bars: pd.DataFrame | None = None,
    ) -> ConvictionResult: ...


class FixedConvictionProvider:
    """Always returns the configured fixed conviction (Phase 3 default path)."""

    def __init__(self, conviction: float) -> None:
        self._conviction = float(np.clip(float(conviction), 0.0, 1.0))

    def resolve(
        self,
        *,
        features: Mapping[str, float] | None = None,
        bars: pd.DataFrame | None = None,
    ) -> ConvictionResult:
        del features, bars  # unused — fixed path ignores live features
        return ConvictionResult(
            conviction=self._conviction,
            source="fixed",
            metalabel_p=None,
            metalabel_bundle_id=None,
        )


class MetalabelConvictionProvider:
    """Map Metalabeler p → conviction (scale only); fall back on any error.

    No skip floor: low p shrinks size via existing risk helpers, never gates entry.
    """

    def __init__(
        self,
        metalabeler: Any,
        feature_builder: FeatureBuilder,
        *,
        fixed_fallback: float,
    ) -> None:
        self._metalabeler = metalabeler
        self._feature_builder = feature_builder
        self._fixed_fallback = float(np.clip(float(fixed_fallback), 0.0, 1.0))

    def resolve(
        self,
        *,
        features: Mapping[str, float] | None = None,
        bars: pd.DataFrame | None = None,
    ) -> ConvictionResult:
        try:
            feature_names = list(self._metalabeler.feature_names)
            built = self._feature_builder.build(
                feature_names=feature_names,
                bars=bars,
                features=features,
            )
            p = float(self._metalabeler.predict_probability(built))
            p = float(np.clip(p, 0.0, 1.0))
            return ConvictionResult(
                conviction=p,
                source="metalabel",
                metalabel_p=p,
                metalabel_bundle_id=_bundle_id(self._metalabeler),
            )
        except Exception as exc:  # noqa: BLE001 — any metalabel/feature failure → fallback
            logger.warning(
                "metalabel conviction failed; using fixed_fallback=%s: %s",
                self._fixed_fallback,
                exc,
                exc_info=True,
            )
            return ConvictionResult(
                conviction=self._fixed_fallback,
                source="fallback_fixed",
                metalabel_p=None,
                metalabel_bundle_id=None,
            )


def _bundle_id(metalabeler: Any) -> str | None:
    root = getattr(metalabeler, "root", None)
    if root is None:
        return None
    try:
        return str(Path(root).name)
    except (TypeError, ValueError):
        name = getattr(root, "name", None)
        return str(name) if name is not None else str(root)
