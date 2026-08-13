"""Causal multi-timeframe regime annotations for Hulk Smash."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hypervector.research.hulk_smash_regime import (
    annotate_hulk_signal_regimes,
    build_hulk_regime_frame,
)


def _bars(rows: int) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=rows, freq="30min", tz="UTC")
    close = 100.0 + np.linspace(0.0, 30.0, rows) + np.sin(np.arange(rows) / 9.0)
    return pd.DataFrame(
        {
            "open": close - 0.05,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "volume": 10.0 + np.cos(np.arange(rows) / 7.0),
        },
        index=index,
    )


def test_hulk_regime_frame_exposes_30m_2h_and_6h_context() -> None:
    """Execution, structural, and context states remain separately visible."""
    bars = _bars(3_100)

    frame = build_hulk_regime_frame(bars)

    assert frame.index.equals(bars.index)
    assert {
        "regime_30m",
        "regime_2h_primary",
        "regime_6h_context",
        "regime_2h_available_at",
        "regime_6h_available_at",
    }.issubset(frame.columns)
    decision_times = frame.index.to_series() + pd.Timedelta(minutes=30)
    for column in ("regime_2h_available_at", "regime_6h_available_at"):
        available = frame[column].dropna()
        assert available.le(decision_times.reindex(available.index)).all()


def test_hulk_regime_history_is_append_invariant() -> None:
    """Later bars cannot alter regime annotations available to earlier entries."""
    bars = _bars(3_200)

    prefix = build_hulk_regime_frame(bars.iloc[:3_000])
    full = build_hulk_regime_frame(bars)

    pd.testing.assert_frame_equal(prefix, full.loc[prefix.index])


def test_signal_regime_annotation_is_read_only_and_directional() -> None:
    """Regime agreement is telemetry and cannot mutate Hulk eligibility."""
    bars = _bars(3_100)
    regimes = build_hulk_regime_frame(bars)
    timestamp = bars.index[-1]
    signals = pd.DataFrame(
        {
            "signal_time_utc": [timestamp, timestamp],
            "side": ["long", "short"],
            "eligible": [True, False],
        }
    )
    original = signals.copy(deep=True)

    annotated = annotate_hulk_signal_regimes(signals, regimes)

    assert annotated[original.columns.tolist()].equals(original)
    alignments = set(annotated["regime_primary_alignment"])
    assert alignments.issubset({"aligned", "opposed", "non_directional"})
    assert annotated["regime_execution_authority"].eq("none").all()


def test_gap_starts_fresh_regime_warmup_instead_of_bridging_history() -> None:
    """Disconnected venue blocks may not share rolling regime state."""
    bars = _bars(400)
    shifted = bars.iloc[200:].copy()
    shifted.index = shifted.index + pd.Timedelta(days=2)
    gapped = pd.concat([bars.iloc[:200], shifted])

    frame = build_hulk_regime_frame(gapped)

    second_start = shifted.index[0]
    assert frame.loc[second_start, "regime_30m"] == "UNKNOWN"
    assert pd.isna(frame.loc[second_start, "regime_2h_available_at"])
