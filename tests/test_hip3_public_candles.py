"""Unsigned HIP-3 public candle source tests."""

from __future__ import annotations

from importlib import import_module

import pandas as pd
from pytest import raises


def test_public_source_fetches_the_explicit_five_minute_contract(monkeypatch) -> None:
    """A five-minute audit must not silently fetch fifteen-minute candles."""
    module = import_module("hypervector.data.hip3_public_candles")
    calls: list[tuple[str, str, float, int]] = []

    def fetch(symbol: str, interval: str, days: float, *, end_ms: int) -> pd.DataFrame:
        calls.append((symbol, interval, days, end_ms))
        return pd.DataFrame()

    monkeypatch.setattr(module, "fetch_hl_ohlcv_snapshot", fetch)
    module.Hip3PublicCandleSource().completed_candles(
        symbol="xyz:BRENTOIL",
        start_ms=1_800_000_000_000,
        end_ms=1_800_000_300_000,
        observed_at_ms=1_800_000_300_000,
        timeframe_minutes=5,
    )

    assert calls == [("xyz:BRENTOIL", "5m", 0.5, 1_800_000_300_000)]


def test_public_source_rejects_an_unsupported_timeframe() -> None:
    """Unsupported research cadence must fail instead of being substituted."""
    module = import_module("hypervector.data.hip3_public_candles")

    with raises(ValueError, match="timeframe"):
        module.Hip3PublicCandleSource().completed_candles(
            symbol="xyz:BRENTOIL",
            start_ms=1_800_000_000_000,
            end_ms=1_800_000_300_000,
            observed_at_ms=1_800_000_300_000,
            timeframe_minutes=7,
        )
