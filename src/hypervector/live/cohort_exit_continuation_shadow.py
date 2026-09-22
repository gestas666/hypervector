"""Prospective continuation forecasts with explicitly no execution authority."""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

from hypervector.live.multi_asset_market_bars import CohortMarketBar, resample_one_minute_bars
from hypervector.research.v91_exit_continuation import FEATURE_NAMES, continuation_features

MODEL_PATH = Path(__file__).resolve().parents[3] / "configs/models/v91_exit_continuation_ridge_v1.json"
MODEL_ID = "v91_exit_continuation_ridge_v1"


def continuation_shadow(
    symbol: str, side: str, bars: tuple[CohortMarketBar, ...], observed_ms: int,
) -> dict[str, object]:
    """Report a causal signed 30-minute forecast, or its precise unavailability."""
    base: dict[str, object] = {"execution_authority": "none", "model_id": MODEL_ID,
                              "horizon_minutes": 30, "outcome": "unavailable"}
    try:
        document, digest = _load_models(MODEL_PATH)
        models = document.get("models")
        if not isinstance(models, Mapping) or symbol not in models:
            raise ValueError("model symbol coverage missing")
        scoped = [bar for bar in bars if bar.symbol == symbol and bar.timestamp_ms + 60_000 <= observed_ms]
        if not scoped:
            raise ValueError("no completed minute features")
        frame = pd.DataFrame([{"timestamp": pd.Timestamp(bar.timestamp_ms, unit="ms", tz="UTC"),
                               "open": bar.open, "high": bar.high, "low": bar.low,
                               "close": bar.close, "volume": bar.volume} for bar in scoped])
        frame = resample_one_minute_bars(frame, minutes=15).set_index("timestamp")
        if frame.empty or observed_ms - int((frame.index[-1] + pd.Timedelta(minutes=15)).timestamp() * 1_000) > 900_000:
            raise ValueError("completed forecast candle is stale")
        features = continuation_features(frame).iloc[-1]
        prediction = score_bundle(models[symbol], features, observed_ms)
    except (OSError, ValueError) as exc:
        return {**base, "reason": str(exc), "error_type": type(exc).__name__}
    return {**base, "outcome": "observed", "model_sha256": digest,
            "feature_decision_ms": int((frame.index[-1] + pd.Timedelta(minutes=15)).timestamp() * 1_000),
            "incremental_hold_bps": prediction * (1 if side == "long" else -1)}


def score_bundle(bundle: object, features: pd.Series, observed_ms: int) -> float:
    """Score only exact finite features strictly after the training labels ended."""
    if not isinstance(bundle, Mapping) or bundle.get("features") != list(FEATURE_NAMES):
        raise ValueError("continuation bundle feature identity invalid")
    training_end = pd.Timestamp(bundle.get("training_end"))
    if pd.isna(training_end) or training_end.tzinfo is None or int(training_end.timestamp() * 1_000) >= observed_ms:
        raise ValueError("continuation model is not prior to the decision")
    vectors = [bundle.get(key) for key in ("means", "scales", "coefficients")]
    if any(not isinstance(values, list) or len(values) != len(FEATURE_NAMES) for values in vectors):
        raise ValueError("continuation parameter dimensions invalid")
    means, scales, coefficients = vectors
    numbers = [*features.loc[list(FEATURE_NAMES)], *means, *scales, *coefficients, bundle.get("intercept")]
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in numbers):
        raise ValueError("continuation parameters/features must be finite")
    if any(scale <= 0 for scale in scales):
        raise ValueError("continuation scales must be positive")
    return float(bundle["intercept"]) + sum((features[name] - mean) / scale * coefficient
        for name, mean, scale, coefficient in zip(FEATURE_NAMES, means, scales, coefficients, strict=True))


@lru_cache(maxsize=1)
def _load_models(path: Path) -> tuple[Mapping[str, object], str]:
    encoded = path.read_bytes()
    value = json.loads(encoded)
    if not isinstance(value, Mapping) or value.get("model_id") != MODEL_ID or value.get("execution_authority") != "none":
        raise ValueError("continuation artifact identity or authority invalid")
    return value, hashlib.sha256(encoded).hexdigest()
