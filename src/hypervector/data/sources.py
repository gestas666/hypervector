"""Shared OHLCV helpers for unit tests of pure ranking/regime logic.

Market history for research is live via ``data.hl`` / ``data.backfill`` /
``data.pipeline``. The series builders here exist only so strategy/regime unit
tests can assert signal math without a network call — they are not a product
history path and are not used by the CLI.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import numpy as np
import pandas as pd

from hypervector.data.provenance import normalize_ohlcv

Fetcher = Callable[[str, str, int], pd.DataFrame]


class HistorySource(Protocol):
    name: str

    def fetch(
        self, symbol: str, timeframe: str, lookback_days: int
    ) -> pd.DataFrame: ...


def fixture_ohlcv(
    n_bars: int = 100,
    start: str = "2024-01-01",
    freq: str = "1min",
    base_price: float = 40_000.0,
    drift: float = 0.0,
    source: str = "fixture",
    *,
    wave_amp: float | None = None,
    wave_period: int = 40,
) -> pd.DataFrame:
    """Synthetic 1m OHLCV for offline tests (no network).

    Linear ``drift`` plus an optional sine wave (default on when |drift| > 0)
    so MA-cross strategies actually fire entries/exits.
    """
    idx = pd.date_range(start=start, periods=n_bars, freq=freq, tz="UTC")
    t = pd.Series(range(n_bars), dtype=float)
    if wave_amp is None:
        # Enough amplitude relative to MA windows to create crosses
        wave_amp = max(abs(drift) * 8.0, 50.0) if drift != 0.0 else 100.0
    wave = wave_amp * np.sin(2.0 * np.pi * t / max(wave_period, 2))
    close = base_price + drift * t + wave
    open_ = close.shift(1).fillna(base_price)
    high = pd.concat([open_, close], axis=1).max(axis=1) + 1.0
    low = pd.concat([open_, close], axis=1).min(axis=1) - 1.0
    volume = pd.Series(1.0, index=close.index)
    df = pd.DataFrame(
        {
            "timestamp": idx,
            "open": open_.values,
            "high": high.values,
            "low": low.values,
            "close": close.values,
            "volume": volume.values,
            "source": source,
        }
    )
    return normalize_ohlcv(df, source=source)


def split_source_frames(
    hl_bars: int = 60,
    binance_extra: int = 30,
    bybit_extra: int = 0,
) -> dict[str, pd.DataFrame]:
    """Build overlapping multi-source frames for merge/provenance tests.

    Timeline: binance-only prefix → shared HL+binance middle → HL-only tail.
    """
    total = hl_bars + binance_extra
    full = fixture_ohlcv(n_bars=total, source="binance", drift=10.0)
    # HL covers the last hl_bars of the timeline (overlap with binance)
    hl_start = binance_extra
    hl = full.iloc[hl_start:].copy()
    hl["source"] = "hl"
    # Distinct HL prices on overlap so merge preference is observable
    hl["close"] = hl["close"] + 100.0
    hl["open"] = hl["open"] + 100.0
    hl["high"] = hl["high"] + 100.0
    hl["low"] = hl["low"] + 100.0
    frames: dict[str, pd.DataFrame] = {
        "hl": normalize_ohlcv(hl, source="hl"),
        "binance": normalize_ohlcv(full, source="binance"),
    }
    if bybit_extra > 0:
        bybit = fixture_ohlcv(
            n_bars=bybit_extra,
            start="2023-12-01",
            source="bybit",
            drift=5.0,
        )
        frames["bybit"] = bybit
    return frames
