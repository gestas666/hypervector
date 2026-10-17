"""Cache-first history merge + provenance (SRS_HV1_DATA_*, SRS_HV1_CACHE)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from hypervector.data.cache import ParquetCache
from hypervector.data.history import merge_history
from hypervector.data.pipeline import cache_key, load_research_history
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


def _patch_fetchers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    hl=None,
    binance=None,
    bybit=None,
) -> dict[str, int]:
    """Route the production pipeline's live fetchers to frames and count calls."""
    calls = {"hl": 0, "binance": 0, "bybit": 0}

    def make(name, frame):
        def fetch(*_a, **_k):
            calls[name] += 1
            if isinstance(frame, Exception):
                raise frame
            return frame

        return fetch

    monkeypatch.setattr("hypervector.data.pipeline.live_hl_fetcher", make("hl", hl))
    monkeypatch.setattr("hypervector.data.pipeline.live_binance_fetcher", make("binance", binance))
    monkeypatch.setattr("hypervector.data.pipeline.live_bybit_fetcher", make("bybit", bybit))
    return calls


def _now_after(frame: pd.DataFrame) -> pd.Timestamp:
    return pd.to_datetime(frame["timestamp"], utc=True).max() + pd.Timedelta(minutes=1)


def test_duplicate_cache_loader_is_gone():
    """Production has one cache-first loader: pipeline.load_research_history."""
    import hypervector.data as data
    import hypervector.data.history as history

    assert not hasattr(history, "load_or_fetch_history")
    assert "load_or_fetch_history" not in data.__all__


def test_cache_first_does_not_call_fetcher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    df = fixture_ohlcv(n_bars=1441, source="hl")  # a full 1-day window
    ParquetCache(tmp_path / "cache").save(cache_key("BTC", "1m", 1), df)
    boom = AssertionError("fetcher must not be called on cache hit")
    calls = _patch_fetchers(monkeypatch, hl=boom, binance=boom, bybit=boom)

    loaded, prov = load_research_history(tmp_path, lookback_days=1, now=_now_after(df))

    assert calls == {"hl": 0, "binance": 0, "bybit": 0}
    assert len(loaded) == 1441
    assert prov["bar_count"] == 1441
    assert prov["cache_hit"] is True
    assert (loaded["source"] == "hl").all()


def test_load_writes_cache_and_second_call_is_cache_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    frames = split_source_frames(hl_bars=40, binance_extra=20)
    now = _now_after(frames["binance"])
    calls = _patch_fetchers(monkeypatch, hl=frames["hl"], binance=frames["binance"])

    df, prov = load_research_history(tmp_path, lookback_days=30, now=now)

    assert ParquetCache(tmp_path / "cache").exists(cache_key("BTC", "1m", 30))
    assert len(df) == 60
    assert prov["sources"]["hl"] == 40
    assert prov["cache_hit"] is False
    # Second load is cache-first (the window was fetched moments ago).
    df2, prov2 = load_research_history(tmp_path, lookback_days=30, now=now)
    assert calls["hl"] == 1
    assert prov2["cache_hit"] is True
    pd.testing.assert_frame_equal(df.reset_index(drop=True), df2.reset_index(drop=True))


def test_low_coverage_fetches_bybit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    frames = split_source_frames(hl_bars=40, binance_extra=20, bybit_extra=15)
    calls = _patch_fetchers(
        monkeypatch, hl=frames["hl"], binance=frames["binance"], bybit=frames["bybit"]
    )

    _df, prov = load_research_history(
        tmp_path, lookback_days=1, now=_now_after(frames["binance"])
    )

    assert calls["bybit"] == 1
    assert prov["sources"]["bybit"] == 15
    assert prov["backfill"]["bybit"].startswith("ok")


def test_full_coverage_skips_bybit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    full = fixture_ohlcv(n_bars=1441, source="binance")
    hl = full.tail(300).assign(source="hl")
    calls = _patch_fetchers(monkeypatch, hl=hl, binance=full, bybit=AssertionError("no"))

    _df, prov = load_research_history(tmp_path, lookback_days=1, now=_now_after(full))

    assert calls["bybit"] == 0
    assert prov["backfill"]["bybit"].startswith("skipped")
    assert prov["coverage_ratio"] >= 0.95


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


def test_merge_bybit_prefix_and_provenance_via_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Bybit-only prefix + HL/binance; gapped merge still summarizes safely."""
    frames = split_source_frames(hl_bars=40, binance_extra=20, bybit_extra=15)
    assert "bybit" in frames
    # Punch a hole in HL so provenance gap path runs after merge
    hl = frames["hl"].copy()
    hl = pd.concat([hl.iloc[:10], hl.iloc[20:]], ignore_index=True)
    _patch_fetchers(monkeypatch, hl=hl, binance=frames["binance"], bybit=frames["bybit"])

    df, prov = load_research_history(
        tmp_path, lookback_days=30, now=_now_after(frames["binance"])
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
