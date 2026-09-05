"""Frozen first-observed candle inputs for HIP-3 lifecycle replays."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from hypervector.live.hip3_shadow_candle_storage import append_candles_once
from hypervector.live.hip3_shadow_candle_contracts import (
    hip3_shadow_candle_contract,
)
from hypervector.research.hip3_shadow_frozen_candles import (
    FrozenHip3CandleFetcher,
    configured_frozen_candle_fetcher,
)


def test_fetcher_returns_source_bound_signal_and_profit_lock_prefixes(
    tmp_path: Path,
) -> None:
    """Replay candles must be the observer's first-observed immutable rows."""
    signal = tmp_path / "signal.jsonl"
    locks = tmp_path / "locks.jsonl"
    _append(signal, "15m", _ms("2026-08-18T00:15:03Z"))
    _append(locks, "1m", _ms("2026-08-18T00:01:03Z"))
    fetcher = FrozenHip3CandleFetcher("xyz:SP500", signal, locks)

    signal_frame = fetcher("xyz:SP500", "15m", 1.0, end_ms=_ms("2026-08-19"))
    lock_frame = fetcher("xyz:SP500", "1m", 1.0, end_ms=_ms("2026-08-19"))

    assert signal_frame.iloc[0]["source"] == "hl"
    assert lock_frame.iloc[0]["source"] == "hl"
    assert signal_frame.iloc[0]["observation_source"].endswith("_15m")
    assert lock_frame.iloc[0]["observation_source"].endswith("_1m")
    assert len(signal_frame.iloc[0]["source_prefix_sha256"]) == 64
    assert len(lock_frame.iloc[0]["source_prefix_sha256"]) == 64


def test_fetcher_rejects_missing_profit_lock_prefix(tmp_path: Path) -> None:
    """A mutable REST fallback cannot silently stand in for exit evidence."""
    signal = tmp_path / "signal.jsonl"
    _append(signal, "15m", _ms("2026-08-18T00:15:03Z"))

    with pytest.raises(FileNotFoundError, match="profit-lock candle ledger"):
        FrozenHip3CandleFetcher("xyz:SP500", signal, tmp_path / "missing.jsonl")


def test_non_live_route_freezes_signal_prefix_without_profit_lock(
    tmp_path: Path,
) -> None:
    """A no-lock route may freeze 15m signals without inventing 1m evidence."""
    signal = tmp_path / "signal.jsonl"
    output = tmp_path / "report.json"
    _append_for_symbol(signal, "xyz:MU", "15m", _ms("2026-08-18T00:15:03Z"))

    fetcher = configured_frozen_candle_fetcher(
        "xyz:MU",
        signal,
        None,
        output,
        lambda *_args, **_kwargs: pd.DataFrame(),
        required=False,
    )

    frame = fetcher("xyz:MU", "15m", 1.0, end_ms=_ms("2026-08-19"))
    assert frame.iloc[0]["source_prefix_path"] == str(signal.resolve())
    with pytest.raises(ValueError, match="timeframe is unsupported"):
        fetcher("xyz:MU", "1m", 1.0, end_ms=_ms("2026-08-19"))


def _append(path: Path, timeframe: str, observed_at_ms: int) -> None:
    _append_for_symbol(path, "xyz:SP500", timeframe, observed_at_ms)


def _append_for_symbol(
    path: Path, symbol: str, timeframe: str, observed_at_ms: int
) -> None:
    minutes = 15 if timeframe == "15m" else 1
    interval = pd.Timedelta(minutes=minutes)
    close = pd.Timestamp(observed_at_ms, unit="ms", tz="UTC").floor(f"{minutes}min")
    frame = pd.DataFrame(
        {
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [7.0],
        },
        index=pd.DatetimeIndex([close - interval]),
    )
    append_candles_once(
        path,
        frame,
        contract=hip3_shadow_candle_contract(symbol, timeframe),
        observed_at_ms=observed_at_ms,
        prior_boundary_ms=0,
    )


def _ms(value: str) -> int:
    return int(pd.Timestamp(value).timestamp() * 1_000)
