"""Causality tests for the frozen four-crypto bull-participation state."""

from __future__ import annotations

import pandas as pd

from hypervector.research.crypto_bull_participation_models import (
    CryptoBullParticipationConfig,
)
from hypervector.research.crypto_bull_participation_signals import (
    build_crypto_bull_decisions,
)


def test_breadth_entry_uses_only_completed_hours_and_emits_onsets() -> None:
    """A new broad trend may enter only at the next hourly boundary."""
    config = CryptoBullParticipationConfig(
        symbols=("BTC", "ETH", "SOL", "HYPE"),
        fast_ema_hours=2,
        slow_ema_hours=3,
        minimum_ema_hours=3,
        entry_breadth=3,
        exit_breadth=2,
    )
    closes = {
        "BTC": [100, 101, 102, 103, 104, 105, 90, 110],
        "ETH": [100, 101, 102, 103, 104, 105, 90, 110],
        "SOL": [100, 101, 102, 103, 104, 105, 90, 110],
        "HYPE": [100, 100, 100, 100, 100, 100, 100, 100],
    }

    decisions = build_crypto_bull_decisions(
        {symbol: _hourly(values) for symbol, values in closes.items()}, config
    )

    first = decisions["BTC"].index[decisions["BTC"]["entry_onset"]][0]
    assert first == pd.Timestamp("2026-01-01T03:00:00Z")
    assert decisions["BTC"].loc[first, "breadth"] == 3
    assert decisions["HYPE"].loc[first, "entry_eligible"] == 0
    assert decisions["BTC"]["entry_onset"].sum() == 2
    assert decisions["BTC"].loc["2026-01-01T07:00:00Z", "exit_signal"]
    assert decisions["BTC"].loc["2026-01-01T08:00:00Z", "entry_onset"]


def test_decision_builder_rejects_misaligned_hourly_sources() -> None:
    """Cross-asset breadth cannot be built from different decision clocks."""
    config = CryptoBullParticipationConfig(
        symbols=("BTC", "ETH"),
        fast_ema_hours=2,
        slow_ema_hours=3,
        minimum_ema_hours=3,
        entry_breadth=2,
        exit_breadth=1,
        maximum_positions=2,
        maximum_total_margin_fraction=0.2,
    )
    btc = _hourly([100, 101, 102, 103])
    eth = _hourly([100, 101, 102, 103]).iloc[1:]

    try:
        build_crypto_bull_decisions({"BTC": btc, "ETH": eth}, config)
    except ValueError as exc:
        assert "aligned hourly indexes" in str(exc)
    else:
        raise AssertionError("misaligned sources must fail")


def _hourly(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(closes), freq="h", tz="UTC")
    values = pd.Series(closes, index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": values,
            "high": values + 1.0,
            "low": values - 1.0,
            "close": values,
        }
    )
