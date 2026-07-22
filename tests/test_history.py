"""Cache-first history merge + provenance (SRS_HV1_DATA_*, SRS_HV1_CACHE)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from hypervector.data.cache import ParquetCache
from hypervector.data.history import load_or_fetch_history, merge_history
from hypervector.data.provenance import OHLCV_COLUMNS, summarize_provenance
from hypervector.data.sources import fixture_ohlcv, split_source_frames


def test_merge_hl_wins_on_overlap():
    frames = split_source_frames(hl_bars=60, binance_extra=30)
    merged = merge_history(frames["hl"], [("binance", frames["binance"])])
    assert list(merged.columns) == OHLCV_COLUMNS
    # Shared timestamps must be HL
    hl_ts = set(pd.to_datetime(frames["hl"]["timestamp"], utc=True))
    overlap = merged[merged["timestamp"].isin(hl_ts)]
    assert (overlap["source"] == "hl").all()
    # Prefix-only binance rows present
    binance_only = merged[merged["source"] == "binance"]
    assert len(binance_only) == 30
    # HL prices preserved on overlap (distinct +100 in fixture)
    sample_ts = frames["hl"]["timestamp"].iloc[0]
    row = merged.loc[merged["timestamp"] == sample_ts].iloc[0]
    expected = frames["hl"].loc[frames["hl"]["timestamp"] == sample_ts, "close"].iloc[0]
    assert row["close"] == pytest.approx(expected)


def test_provenance_summary_has_fractions_and_sources():
    frames = split_source_frames(hl_bars=60, binance_extra=30)
    merged = merge_history(frames["hl"], [("binance", frames["binance"])])
    summary = summarize_provenance(merged)
    assert summary["bar_count"] == 90
    assert "hl" in summary["sources"]
    assert "binance" in summary["sources"]
    assert summary["sources"]["hl"] == 60
    assert summary["sources"]["binance"] == 30
    assert abs(summary["fractions"]["hl"] - 60 / 90) < 1e-9
    assert abs(summary["fractions"]["binance"] - 30 / 90) < 1e-9
    assert "gaps" in summary


def test_cache_first_does_not_call_fetcher(tmp_path: Path):
    cache = ParquetCache(tmp_path / "cache")
    key = "BTC_1m_90d"
    df = fixture_ohlcv(n_bars=50, source="hl")
    cache.save(key, df)

    def boom(*_a, **_k):
        raise AssertionError("fetcher must not be called on cache hit")

    loaded, prov = load_or_fetch_history(
        cache,
        key,
        hl_fetcher=boom,
        backfill_fetchers=[("binance", boom)],
    )
    assert len(loaded) == 50
    assert prov["bar_count"] == 50
    assert (loaded["source"] == "hl").all()


def test_load_or_fetch_writes_cache_and_merges(tmp_path: Path):
    cache = ParquetCache(tmp_path / "cache")
    key = "BTC_1m_30d"
    frames = split_source_frames(hl_bars=40, binance_extra=20)

    def hl_f(*_a, **_k):
        return frames["hl"]

    def bn_f(*_a, **_k):
        return frames["binance"]

    df, prov = load_or_fetch_history(
        cache,
        key,
        symbol="BTC",
        timeframe="1m",
        lookback_days=30,
        hl_fetcher=hl_f,
        backfill_fetchers=[("binance", bn_f)],
    )
    assert cache.exists(key)
    assert len(df) == 60
    assert prov["sources"]["hl"] == 40
    # Second load is cache-first
    df2, _ = load_or_fetch_history(
        cache,
        key,
        hl_fetcher=lambda *_: (_ for _ in ()).throw(RuntimeError("no")),
    )
    pd.testing.assert_frame_equal(df.reset_index(drop=True), df2.reset_index(drop=True))


def test_parquet_roundtrip_preserves_source(tmp_path: Path):
    cache = ParquetCache(tmp_path)
    df = fixture_ohlcv(n_bars=10, source="bybit")
    cache.save("x", df)
    loaded = cache.load("x")
    assert loaded is not None
    assert (loaded["source"] == "bybit").all()


def test_provenance_gapped_bars_reports_gaps_without_error():
    """Intentional multi-minute hole must populate gaps (not AttributeError)."""
    left = fixture_ohlcv(n_bars=10, start="2024-01-01 00:00:00", source="hl")
    # Skip 5 minutes → gap of 6 expected-bar steps between last left and first right
    right = fixture_ohlcv(n_bars=10, start="2024-01-01 00:15:00", source="hl")
    gapped = pd.concat([left, right], ignore_index=True)
    summary = summarize_provenance(gapped)
    assert summary["bar_count"] == 20
    assert summary["gaps"]["count"] >= 1
    # 15 minutes between 00:09 and 00:15 → 15 bar-minutes
    assert summary["gaps"]["max_gap_bars"] >= 5
    assert isinstance(summary["gaps"]["max_gap_bars"], int)


def test_merge_bybit_prefix_and_provenance_via_load_or_fetch(tmp_path: Path):
    """Bybit-only prefix + HL/binance; gapped merge still summarizes safely."""
    frames = split_source_frames(hl_bars=40, binance_extra=20, bybit_extra=15)
    assert "bybit" in frames
    # Punch a hole in HL so provenance gap path runs after merge
    hl = frames["hl"].copy()
    hl = pd.concat([hl.iloc[:10], hl.iloc[20:]], ignore_index=True)

    cache = ParquetCache(tmp_path / "cache")
    key = "BTC_1m_gapped_multi"

    def hl_f(*_a, **_k):
        return hl

    def bn_f(*_a, **_k):
        return frames["binance"]

    def bb_f(*_a, **_k):
        return frames["bybit"]

    df, prov = load_or_fetch_history(
        cache,
        key,
        symbol="BTC",
        timeframe="1m",
        lookback_days=30,
        hl_fetcher=hl_f,
        backfill_fetchers=[("binance", bn_f), ("bybit", bb_f)],
    )
    assert "bybit" in prov["sources"]
    assert prov["sources"]["bybit"] == 15
    assert "hl" in prov["sources"]
    assert "binance" in prov["sources"]
    # HL hole is partially filled by binance on overlap timestamps; remaining
    # timeline discontinuity still yields a gap count without crashing.
    assert "gaps" in prov
    assert isinstance(prov["gaps"]["count"], int)
    assert isinstance(prov["gaps"]["max_gap_bars"], int)
    # Bybit bars appear only where no later source claimed them
    assert (df.loc[df["source"] == "bybit"].shape[0]) == 15
