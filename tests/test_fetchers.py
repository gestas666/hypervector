"""Live exchange fetchers: parsers on real samples + network smoke."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from hypervector.data.backfill import (
    bars_from_binance_klines,
    bars_from_bybit_list,
    fetch_binance_ohlcv,
    fetch_bybit_ohlcv,
)
from hypervector.data.hl import (
    bars_from_hl_payload,
    fetch_hl_funding_history,
    fetch_hl_ohlcv,
    funding_from_hl_payload,
)
from hypervector.data.history import merge_history
from hypervector.data.cache import ParquetCache
from hypervector.data.pipeline import cache_key, load_research_history
from hypervector.data.provenance import summarize_provenance

FIX = Path(__file__).parent / "fixtures"


def test_parse_hl_real_sample():
    raw = json.loads((FIX / "hl_candle_sample.json").read_text())
    assert len(raw) >= 1
    df = bars_from_hl_payload(raw)
    assert len(df) == len(raw)
    assert (df["source"] == "hl").all()
    assert df["close"].notna().all()
    assert df["timestamp"].is_monotonic_increasing


def test_parse_hl_funding_history_normalizes_utc_hours() -> None:
    """Public funding rows become typed UTC settlement observations."""
    raw = [
        {
            "coin": "BTC",
            "fundingRate": "0.0000125",
            "premium": "0.0002",
            "time": 1_784_995_200_030,
        }
    ]

    frame = funding_from_hl_payload(raw)

    assert frame.to_dict("records") == [
        {
            "timestamp": pd.Timestamp("2026-07-25T16:00:00Z"),
            "funding_rate": 0.0000125,
            "source": "hl_funding_history",
        }
    ]


def test_fetch_hl_funding_history_uses_public_info_request() -> None:
    """Historical funding transport sends the documented time-bounded body."""
    response = Mock()
    response.json.return_value = []
    session = Mock()
    session.post.return_value = response

    frame = fetch_hl_funding_history(
        "BTC-PERP",
        start_time=pd.Timestamp("2026-07-25T12:00:00Z"),
        end_time=pd.Timestamp("2026-07-25T14:00:00Z"),
        session=session,
    )

    session.post.assert_called_once_with(
        "https://api.hyperliquid.xyz/info",
        json={
            "type": "fundingHistory",
            "coin": "BTC",
            "startTime": 1_784_980_800_000,
            "endTime": 1_784_988_000_000,
        },
        timeout=30,
    )
    response.raise_for_status.assert_called_once_with()
    assert frame.empty


def test_parse_binance_real_sample():
    raw = json.loads((FIX / "binance_klines_sample.json").read_text())
    df = bars_from_binance_klines(raw)
    assert len(df) == len(raw)
    assert (df["source"] == "binance").all()


def test_parse_bybit_real_sample():
    body = json.loads((FIX / "bybit_kline_sample.json").read_text())
    raw = body["result"]["list"]
    df = bars_from_bybit_list(raw)
    assert len(df) == len(raw)
    assert (df["source"] == "bybit").all()


def test_merge_live_shaped_frames_hl_wins():
    hl = bars_from_hl_payload(json.loads((FIX / "hl_candle_sample.json").read_text()))
    bn = bars_from_binance_klines(
        json.loads((FIX / "binance_klines_sample.json").read_text())
    )
    # Force one overlapping timestamp to prove HL preference
    if len(hl) and len(bn):
        bn = bn.copy()
        bn.loc[bn.index[0], "timestamp"] = hl["timestamp"].iloc[0]
        bn.loc[bn.index[0], "close"] = 1.0  # poison; must not survive
    merged = merge_history(hl, [("binance", bn)])
    if len(hl):
        row = merged.loc[merged["timestamp"] == hl["timestamp"].iloc[0]].iloc[0]
        assert row["source"] == "hl"
        assert row["close"] != 1.0


def test_strict_hl_load_refreshes_incompatible_mixed_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Venue-strict execution cannot reuse a research cache with other venues."""
    hl = bars_from_hl_payload(json.loads((FIX / "hl_candle_sample.json").read_text()))
    mixed = hl.copy()
    mixed.loc[mixed.index[0], "source"] = "binance"
    cache = ParquetCache(tmp_path / "cache")
    cache.save(cache_key("BTC", "1m", 1), mixed)
    calls = {"hl": 0}

    def fresh_hl(symbol: str, timeframe: str, lookback_days: int) -> pd.DataFrame:
        del symbol, timeframe, lookback_days
        calls["hl"] += 1
        return hl

    monkeypatch.setattr("hypervector.data.pipeline.live_hl_fetcher", fresh_hl)

    frame, _provenance = load_research_history(
        tmp_path,
        symbol="BTC",
        timeframe="1m",
        lookback_days=1,
        strict_hl_only=True,
    )

    assert calls["hl"] == 1
    assert frame["source"].eq("hl").all()


@pytest.mark.network
def test_live_hl_short_window():
    df = fetch_hl_ohlcv("BTC", "1m", lookback_days=1)
    # HL may return only partial day; non-empty expected on healthy network
    assert len(df) > 0
    assert (df["source"] == "hl").all()
    assert df["close"].iloc[-1] > 0


@pytest.mark.network
def test_live_binance_short_window():
    df = fetch_binance_ohlcv("BTC", "1m", lookback_days=1)
    assert len(df) > 500  # ~1d of 1m
    assert (df["source"] == "binance").all()


@pytest.mark.network
def test_live_bybit_short_window():
    df = fetch_bybit_ohlcv("BTC", "1m", lookback_days=1)
    assert len(df) > 500
    assert (df["source"] == "bybit").all()


@pytest.mark.network
def test_live_pipeline_hl_then_backfill(tmp_path: Path):
    """End-to-end: real venues, cache, provenance fractions."""
    df, prov = load_research_history(
        tmp_path,
        symbol="BTC",
        timeframe="1m",
        lookback_days=30,
        force_refresh=True,
    )
    assert len(df) > 10_000  # 30d floor roughly if backfill works
    assert prov["bar_count"] == len(df)
    # Recent identity is HL when HL returns bars
    sources = set(prov["sources"])
    assert "binance" in sources or "bybit" in sources
    # HL present if venue returned retention window
    if "hl" in sources:
        # not all must be HL, but source column is real venue labels only
        assert set(df["source"].unique()).issubset({"hl", "binance", "bybit"})
    summary = summarize_provenance(df)
    assert abs(sum(summary["fractions"].values()) - 1.0) < 1e-9
