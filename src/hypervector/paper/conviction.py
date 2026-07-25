"""Fixed and LightGBM conviction policies for backend execution.

The explicit modes are observe (annotation only), scale (size by probability),
and filter (size and gate by probability). Fixed and observe modes never gate.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

import numpy as np
import pandas as pd

from hypervector.ml.features import FeatureBuilder, FeatureBuildError

logger = logging.getLogger(__name__)

# Default metalabel entry gate: take only when model p ≥ this.
DEFAULT_METALABEL_MIN_P = 0.5
ActiveMetalabelMode = Literal["observe", "scale", "filter"]
MetalabelMode = Literal["off", "observe", "scale", "filter"]

__all__ = [
    "DEFAULT_METALABEL_MIN_P",
    "ConvictionProvider",
    "ConvictionResult",
    "FeatureBuilder",
    "FeatureBuildError",
    "FixedConvictionProvider",
    "MetalabelConvictionProvider",
    "MetalabelMode",
    "resolve_metalabel_mode",
]


@dataclass(frozen=True)
class ConvictionResult:
    """Resolved conviction for one sizing / filter decision."""

    conviction: float
    source: str  # fixed | metalabel_observe | metalabel | metalabel_skip | fallback_*
    metalabel_p: float | None
    metalabel_bundle_id: str | None
    allow_entry: bool = True
    skip_reason: str | None = None


class ConvictionProvider(Protocol):
    @property
    def bundle_id(self) -> str | None: ...

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

    @property
    def bundle_id(self) -> str | None:
        """Return no model identity for fixed conviction."""
        return None

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
    """Resolve a LightGBM probability under an explicit backend policy.

    Parameters
    ----------
    min_p:
        Minimum calibrated probability to allow a new entry when
        ``filter_entries`` is True. Sizing still uses p when allowed.
    filter_entries:
        When True (default), p < min_p blocks enter (not close).
    fail_closed:
        When True with filtering, feature/predict errors block
        entry instead of falling back to fixed full size.
    mode:
        ``observe`` records probability without affecting strategy behavior;
        ``scale`` sizes by probability; ``filter`` also gates below ``min_p``.
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
        mode: ActiveMetalabelMode | None = None,
    ) -> None:
        self._metalabeler = metalabeler
        self._feature_builder = feature_builder
        self._fixed_fallback = float(np.clip(float(fixed_fallback), 0.0, 1.0))
        self._min_p = float(np.clip(float(min_p), 0.0, 1.0))
        resolved_mode: ActiveMetalabelMode = mode or (
            "filter" if filter_entries else "scale"
        )
        if resolved_mode not in ("observe", "scale", "filter"):
            raise ValueError("metalabel mode must be one of: observe, scale, filter")
        self._mode = resolved_mode
        self._filter_entries = resolved_mode == "filter"
        self._fail_closed = bool(fail_closed) and self._filter_entries

    @property
    def bundle_id(self) -> str | None:
        """Return the immutable model directory name used for inference."""
        return _bundle_id(self._metalabeler)

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

        if self._mode == "observe":
            return ConvictionResult(
                conviction=self._fixed_fallback,
                source="metalabel_observe",
                metalabel_p=p,
                metalabel_bundle_id=bundle,
                allow_entry=True,
                skip_reason=None,
            )

        return ConvictionResult(
            conviction=p,
            source="metalabel",
            metalabel_p=p,
            metalabel_bundle_id=bundle,
            allow_entry=True,
            skip_reason=None,
        )


def resolve_metalabel_mode(
    *,
    enabled: bool,
    filter_entries: bool,
    requested: str | None = None,
) -> MetalabelMode:
    """Resolve legacy booleans and an explicit runtime policy into one mode."""
    if requested is None:
        if not enabled:
            return "off"
        return "filter" if filter_entries else "scale"
    normalized = requested.strip().lower()
    if normalized == "off":
        return "off"
    if normalized == "observe":
        return "observe"
    if normalized == "scale":
        return "scale"
    if normalized == "filter":
        return "filter"
    raise ValueError("metalabel mode must be one of: off, observe, scale, filter")


def _bundle_id(metalabeler: Any) -> str | None:
    root = getattr(metalabeler, "root", None)
    if root is None:
        return None
    try:
        return str(Path(root).name)
    except (TypeError, ValueError):
        name = getattr(root, "name", None)
        return str(name) if name is not None else str(root)
