"""Entry ablations for the causal four-Pine strategy stack."""

from __future__ import annotations

import numpy as np
import pandas as pd

_CANDIDATES = (
    ("cs_base", False, None),
    ("cs_trend", True, None),
    ("cs_sentiment_55", False, 55.0),
    ("cs_trend_sentiment_55", True, 55.0),
    ("cs_sentiment_60", False, 60.0),
    ("cs_trend_sentiment_60", True, 60.0),
)
_OUTPUT_COLUMNS = (
    "candidate",
    "symbol",
    "signal_bar_open_at",
    "decision_time_utc",
    "side",
    "cs_selected_factor",
    "cs_trailing_stop",
    "trend_levels_state",
    "sentiment_score",
    "reason",
    "execution_authority",
)
_REQUIRED = {
    "bar_open_at",
    "decision_time_utc",
    "cs_long_onset",
    "cs_short_onset",
    "cs_selected_factor",
    "cs_trailing_stop",
    "trend_levels_state",
    "sentiment_score",
    "execution_authority",
}


def declared_pine_stack_candidates() -> tuple[str, ...]:
    """Return every base and confluence entry ablation identity."""
    return tuple(candidate for candidate, _, _ in _CANDIDATES)


def compose_pine_stack_entries(
    features: pd.DataFrame,
    *,
    symbol: str,
) -> pd.DataFrame:
    """Return CS onset entries while preserving explicit filtered subsets."""
    frame = _validated_features(features)
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol or normalized_symbol != symbol:
        raise ValueError("Pine stack symbol must be non-empty uppercase text")
    records: list[dict[str, object]] = []
    for candidate, require_trend, sentiment in _CANDIDATES:
        for side, direction, onset in (
            ("long", 1, "cs_long_onset"),
            ("short", -1, "cs_short_onset"),
        ):
            mask = frame[onset].astype(bool)
            if require_trend:
                mask &= frame["trend_levels_state"].eq(direction)
            if sentiment is not None:
                mask &= _sentiment_aligned(
                    frame["sentiment_score"], direction, sentiment
                )
            for position in np.flatnonzero(mask.fillna(False).to_numpy()):
                records.append(
                    _entry_record(
                        frame.iloc[position], candidate, normalized_symbol, side
                    )
                )
    return (
        pd.DataFrame(records, columns=list(_OUTPUT_COLUMNS))
        .sort_values(["decision_time_utc", "candidate", "side"])
        .reset_index(drop=True)
    )


def _validated_features(features: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_REQUIRED.difference(features.columns))
    if missing:
        raise ValueError(f"Pine stack entry features missing columns: {missing}")
    times = pd.DatetimeIndex(features["decision_time_utc"])
    if features.empty or times.tz is None:
        raise ValueError("Pine stack entry features require aware decision times")
    if not times.is_monotonic_increasing or times.has_duplicates:
        raise ValueError("Pine stack decision times must be ordered and unique")
    if not features["execution_authority"].eq("none").all():
        raise ValueError(
            "Pine stack research features must have no execution authority"
        )
    return features.copy()


def _sentiment_aligned(
    sentiment: pd.Series,
    direction: int,
    bullish_threshold: float,
) -> pd.Series:
    bearish_threshold = 100.0 - bullish_threshold
    return (
        sentiment.ge(bullish_threshold)
        if direction == 1
        else sentiment.le(bearish_threshold)
    )


def _entry_record(
    row: pd.Series,
    candidate: str,
    symbol: str,
    side: str,
) -> dict[str, object]:
    return {
        "candidate": candidate,
        "symbol": symbol,
        "signal_bar_open_at": pd.Timestamp(row["bar_open_at"]),
        "decision_time_utc": pd.Timestamp(row["decision_time_utc"]),
        "side": side,
        "cs_selected_factor": float(row["cs_selected_factor"]),
        "cs_trailing_stop": float(row["cs_trailing_stop"]),
        "trend_levels_state": int(row["trend_levels_state"]),
        "sentiment_score": float(row["sentiment_score"]),
        "reason": f"{candidate}:{side}:cs_onset",
        "execution_authority": "none",
    }
