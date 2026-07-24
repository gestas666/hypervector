"""Point-in-time feature rows for metalabel inference (no training).

PIT rule: last closed bar only. Prefer an explicit ``features`` mapping;
else OHLCV bars → compute the metalabel feature matrix (same schema as train).
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
      2. Else if ``bars`` has those columns on the last row → passthrough.
      3. Else if ``bars`` has OHLCV → compute via :func:`build_feature_matrix`.
      4. Else → :class:`FeatureBuildError`.
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
            if not missing_cols:
                row = bars.iloc[-1]
                return {n: float(row[n]) for n in names}

            # Compute metalabel features from OHLCV when columns are raw bars only.
            ohlc = {"open", "high", "low", "close"}
            if ohlc.issubset(cols):
                try:
                    from hypervector.ml.feature_matrix import build_feature_matrix

                    # Need warm-up history; require a minimum bar count.
                    if len(bars) < 30:
                        raise FeatureBuildError(
                            f"need ≥30 bars to compute metalabel features, got {len(bars)}"
                        )
                    matrix = build_feature_matrix(bars)
                    row = matrix.iloc[-1]
                    missing_after = [n for n in names if n not in row.index]
                    if missing_after:
                        raise FeatureBuildError(
                            f"computed features missing names: {missing_after}"
                        )
                    return {n: float(row[n]) for n in names}
                except FeatureBuildError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    raise FeatureBuildError(
                        f"failed to compute metalabel features from OHLCV: {exc}"
                    ) from exc

            raise FeatureBuildError(
                f"missing feature columns on last closed bar: {missing_cols}"
            )

        if features is not None:
            missing = [n for n in names if n not in features]
            raise FeatureBuildError(f"missing features for metalabel: {missing}")

        raise FeatureBuildError(
            "no features mapping or bars provided for FeatureBuilder.build"
        )
