"""Point-in-time feature rows for metalabel inference (no training).

PIT rule: last closed bar only. Mapping path is the preferred test surface;
OHLCV column passthrough is a thin adapter for names already present as columns.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd


class FeatureBuildError(RuntimeError):
    """Feature row incomplete or unbuildable from provided inputs."""


class FeatureBuilder:
    """Build a single feature dict matching a metalabel bundle schema.

    Priority:
      1. Complete ``features`` mapping (all ``feature_names`` present) → use it.
      2. Else if ``bars`` provided → take last row columns matching names;
         any missing name → :class:`FeatureBuildError`.
      3. Else → :class:`FeatureBuildError`.
    """

    def build(
        self,
        *,
        feature_names: list[str],
        bars: pd.DataFrame | None = None,
        features: Mapping[str, Any] | None = None,
    ) -> dict[str, float]:
        names = list(feature_names)
        if not names:
            raise FeatureBuildError("feature_names is empty")

        if features is not None:
            missing = [n for n in names if n not in features]
            if not missing:
                return {n: float(features[n]) for n in names}
            # Incomplete mapping: fall through to bars if available.

        if bars is not None:
            if not isinstance(bars, pd.DataFrame) or bars.empty:
                raise FeatureBuildError("bars DataFrame is empty or invalid")
            cols = set(bars.columns)
            missing_cols = [n for n in names if n not in cols]
            if missing_cols:
                raise FeatureBuildError(
                    f"missing feature columns on last closed bar: {missing_cols}"
                )
            row = bars.iloc[-1]
            return {n: float(row[n]) for n in names}

        if features is not None:
            missing = [n for n in names if n not in features]
            raise FeatureBuildError(f"missing features for metalabel: {missing}")

        raise FeatureBuildError(
            "no features mapping or bars provided for FeatureBuilder.build"
        )
