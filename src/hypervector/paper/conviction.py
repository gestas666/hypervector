"""Conviction providers: fixed or metalabel (scale + optional entry filter).

When metalabel is enabled with ``filter_entries=True`` (default):
  - conviction = clip(p, 0, 1) for sizing when entry allowed
  - if p < min_p → ``allow_entry=False`` (strategy signal filtered out)
  - feature/predict failure → fail-closed skip when filtering (not full size)

Fixed path never filters.
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

# Default metalabel entry gate: take only when model p ≥ this.
DEFAULT_METALABEL_MIN_P = 0.5

__all__ = [
    "DEFAULT_METALABEL_MIN_P",
    "ConvictionProvider",
    "ConvictionResult",
    "FeatureBuilder",
    "FeatureBuildError",
    "FixedConvictionProvider",
    "MetalabelConvictionProvider",
]


@dataclass(frozen=True)
class ConvictionResult:
    """Resolved conviction for one sizing / filter decision."""

    conviction: float
    source: str  # fixed | metalabel | metalabel_skip | fallback_fixed | fallback_skip
    metalabel_p: float | None
    metalabel_bundle_id: str | None
    allow_entry: bool = True
    skip_reason: str | None = None


class ConvictionProvider(Protocol):
    def resolve(
        self,
        *,
        features: Mapping[str, float] | None = None,
        bars: pd.DataFrame | None = None,
    ) -> ConvictionResult: ...


class FixedConvictionProvider:
    """Always returns the configured fixed conviction (no filter)."""

    def __init__(self, conviction: float) -> None:
        self._conviction = float(np.clip(float(conviction), 0.0, 1.0))

    def resolve(
        self,
        *,
        features: Mapping[str, float] | None = None,
        bars: pd.DataFrame | None = None,
    ) -> ConvictionResult:
        del features, bars
        return ConvictionResult(
            conviction=self._conviction,
            source="fixed",
            metalabel_p=None,
            metalabel_bundle_id=None,
            allow_entry=True,
            skip_reason=None,
        )


class MetalabelConvictionProvider:
    """LightGBM metalabel: scale conviction by p, optionally filter entries.

    Parameters
    ----------
    min_p:
        Minimum calibrated probability to allow a new entry when
        ``filter_entries`` is True. Sizing still uses p when allowed.
    filter_entries:
        When True (default), p < min_p blocks enter (not close).
    fail_closed:
        When True (default with filtering), feature/predict errors block
        entry instead of falling back to fixed full size.
    """

    def __init__(
        self,
        metalabeler: Any,
        feature_builder: FeatureBuilder,
        *,
        fixed_fallback: float,
        min_p: float = DEFAULT_METALABEL_MIN_P,
        filter_entries: bool = True,
        fail_closed: bool = True,
    ) -> None:
        self._metalabeler = metalabeler
        self._feature_builder = feature_builder
        self._fixed_fallback = float(np.clip(float(fixed_fallback), 0.0, 1.0))
        self._min_p = float(np.clip(float(min_p), 0.0, 1.0))
        self._filter_entries = bool(filter_entries)
        self._fail_closed = bool(fail_closed)

    def resolve(
        self,
        *,
        features: Mapping[str, float] | None = None,
        bars: pd.DataFrame | None = None,
    ) -> ConvictionResult:
        bundle = _bundle_id(self._metalabeler)
        try:
            feature_names = list(self._metalabeler.feature_names)
            built = self._feature_builder.build(
                feature_names=feature_names,
                bars=bars,
                features=features,
            )
            p = float(self._metalabeler.predict_probability(built))
            p = float(np.clip(p, 0.0, 1.0))
        except Exception as exc:  # noqa: BLE001
            if self._filter_entries and self._fail_closed:
                logger.warning(
                    "metalabel failed (fail-closed filter): %s",
                    exc,
                    exc_info=True,
                )
                return ConvictionResult(
                    conviction=0.0,
                    source="fallback_skip",
                    metalabel_p=None,
                    metalabel_bundle_id=bundle,
                    allow_entry=False,
                    skip_reason=f"metalabel_error:{type(exc).__name__}",
                )
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
                metalabel_bundle_id=bundle,
                allow_entry=True,
                skip_reason=None,
            )

        if self._filter_entries and p < self._min_p:
            return ConvictionResult(
                conviction=0.0,
                source="metalabel_skip",
                metalabel_p=p,
                metalabel_bundle_id=bundle,
                allow_entry=False,
                skip_reason=f"p_below_min:{p:.4f}<{self._min_p:.4f}",
            )

        return ConvictionResult(
            conviction=p,
            source="metalabel",
            metalabel_p=p,
            metalabel_bundle_id=bundle,
            allow_entry=True,
            skip_reason=None,
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
