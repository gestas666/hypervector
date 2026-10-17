"""Research history cache carries and reports its real window.

Regressions:
- the cache key ``SYM_tf_Nd`` was served unconditionally, so a 90d file that
  ended months ago (or a 30d file holding 3.6 days) was returned as "the last N
  days" with no warning and no window in the provenance;
- a strict HL-only load overwrote the shared (backfilled) key;
- gap statistics assumed one-minute bars, so every 15m/1h bar was a "gap".
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from hypervector.data.cache import ParquetCache
from hypervector.data.pipeline import cache_key, load_research_history
from hypervector.data.provenance import summarize_provenance
from hypervector.data.sources import fixture_ohlcv

_NOW = pd.Timestamp("2026-10-17T00:00:00Z")


def _bars(end: pd.Timestamp, days: float, *, freq: str = "1min", source: str = "hl") -> pd.DataFrame:
    step = pd.Timedelta(freq)
    n = int(pd.Timedelta(days=days) / step) + 1
    start = end - step * (n - 1)
    return fixture_ohlcv(n_bars=n, start=str(start.tz_localize(None)), freq=freq, source=source)


def _count_calls(monkeypatch: pytest.MonkeyPatch, *, hl: pd.DataFrame, binance: pd.DataFrame | None = None) -> dict[str, int]:
    calls = {"hl": 0, "binance": 0, "bybit": 0}

    def fetch(name: str, frame: pd.DataFrame | None):
        def _f(*_a: Any) -> pd.DataFrame | None:
            calls[name] += 1
            return frame

        return _f

    monkeypatch.setattr("hypervector.data.pipeline.live_hl_fetcher", fetch("hl", hl))
    monkeypatch.setattr("hypervector.data.pipeline.live_binance_fetcher", fetch("binance", binance))
    monkeypatch.setattr("hypervector.data.pipeline.live_bybit_fetcher", fetch("bybit", None))
    return calls


# --- provenance: timeframe-aware gaps and an explicit window -----------------


@pytest.mark.parametrize("freq,tf", [("15min", "15m"), ("1h", "1h"), ("5min", "5m")])
def test_contiguous_higher_timeframe_has_no_gaps(freq: str, tf: str) -> None:
    df = _bars(_NOW, 30, freq=freq)

    for summary in (summarize_provenance(df, timeframe=tf), summarize_provenance(df)):
        assert summary["gaps"] == {"count": 0, "max_gap_bars": 0}
        assert summary["bar_seconds"] == int(pd.Timedelta(freq).total_seconds())


def test_higher_timeframe_hole_is_measured_in_that_timeframe() -> None:
    df = _bars(_NOW, 10, freq="15min")
    holed = pd.concat([df.iloc[:100], df.iloc[104:]], ignore_index=True)  # 4 bars missing

    summary = summarize_provenance(holed, timeframe="15m")

    assert summary["gaps"] == {"count": 1, "max_gap_bars": 5}


def test_one_minute_gap_stats_are_unchanged() -> None:
    left = fixture_ohlcv(n_bars=10, start="2024-01-01 00:00:00", source="hl")
    right = fixture_ohlcv(n_bars=10, start="2024-01-01 00:15:00", source="hl")
    gapped = pd.concat([left, right], ignore_index=True)

    assert summarize_provenance(gapped)["gaps"] == {"count": 1, "max_gap_bars": 6}
    assert summarize_provenance(gapped, timeframe="1m")["gaps"] == {"count": 1, "max_gap_bars": 6}


def test_summary_reports_window_as_json_safe_strings() -> None:
    df = _bars(_NOW, 1)

    summary = summarize_provenance(df, timeframe="1m")

    assert summary["start"] == "2026-10-16T00:00:00+00:00"
    assert summary["end"] == "2026-10-17T00:00:00+00:00"
    assert summary["timeframe"] == "1m"
    json.dumps(summary)


# --- cache freshness and coverage ------------------------------------------


def test_stale_cache_is_refreshed_when_network_is_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _bars(pd.Timestamp("2026-07-26T23:59:00Z"), 2)
    ParquetCache(tmp_path / "cache").save(cache_key("BTC", "1m", 2), old)
    fresh = _bars(_NOW, 2)
    calls = _count_calls(monkeypatch, hl=fresh, binance=fresh.assign(source="binance"))

    frame, prov = load_research_history(tmp_path, lookback_days=2, now=_NOW)

    assert calls["hl"] == 1
    assert frame["timestamp"].max() == _NOW
    assert prov["refreshed"] is True
    assert "stale" in prov["refresh_reason"]
    assert prov["end"] == _NOW.isoformat()
    assert prov["stale"] is False


def test_stale_cache_offline_is_served_with_explicit_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    end = pd.Timestamp("2026-07-26T23:59:00Z")
    ParquetCache(tmp_path / "cache").save(cache_key("BTC", "1m", 2), _bars(end, 2))
    _count_calls(monkeypatch, hl=None)  # type: ignore[arg-type]

    with caplog.at_level(logging.WARNING, logger="hypervector.data.pipeline"):
        frame, prov = load_research_history(
            tmp_path, lookback_days=2, allow_network=False, now=_NOW
        )

    assert frame["timestamp"].max() == end
    assert prov["cache_hit"] is True
    assert prov["stale"] is True
    assert prov["age_seconds"] == pytest.approx((_NOW - end).total_seconds())
    assert prov["warnings"]
    assert any("2026-07-26" in r.getMessage() for r in caplog.records)
    json.dumps(prov)


def test_partial_legacy_cache_is_refreshed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A "30d" key holding 3.6 days (the strict-clobber residue) is not served as 30d."""
    ParquetCache(tmp_path / "cache").save(cache_key("BTC", "1m", 30), _bars(_NOW, 3.6))
    full = _bars(_NOW, 30)
    calls = _count_calls(monkeypatch, hl=full.tail(5000), binance=full.assign(source="binance"))

    frame, prov = load_research_history(tmp_path, lookback_days=30, now=_NOW)

    assert calls["hl"] == 1
    assert "partial" in prov["refresh_reason"]
    assert prov["coverage_ratio"] >= 0.95
    assert len(frame) == len(full)


def test_pinned_cache_is_served_untouched_but_flagged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    end = pd.Timestamp("2026-07-26T23:59:00Z")
    ParquetCache(tmp_path / "cache").save(cache_key("BTC", "1m", 2), _bars(end, 2))
    calls = _count_calls(monkeypatch, hl=None)  # type: ignore[arg-type]

    frame, prov = load_research_history(tmp_path, lookback_days=2, max_cache_age=None, now=_NOW)

    assert calls == {"hl": 0, "binance": 0, "bybit": 0}
    assert frame["timestamp"].max() == end
    assert prov["stale"] is True
    assert prov["refreshed"] is False


@pytest.mark.parametrize("bad", [3600, 1.5, True, pd.Timedelta(0)])
def test_max_cache_age_must_be_a_positive_timedelta(tmp_path: Path, bad: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        load_research_history(tmp_path, lookback_days=1, max_cache_age=bad, now=_NOW)


def test_fresh_full_cache_is_a_pure_cache_hit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ParquetCache(tmp_path / "cache").save(cache_key("BTC", "1m", 1), _bars(_NOW - pd.Timedelta(hours=2), 1))
    calls = _count_calls(monkeypatch, hl=None)  # type: ignore[arg-type]

    _frame, prov = load_research_history(tmp_path, lookback_days=1, now=_NOW)

    assert calls["hl"] == 0
    assert prov["cache_hit"] is True
    assert prov["stale"] is False and prov["partial"] is False
    assert prov["cache_key"] == "BTC_1m_1d"
    assert prov["cache_path"].endswith("BTC_1m_1d.parquet")
    assert prov["expected_bars"] == 1440


def test_recently_fetched_partial_history_is_not_refetched_every_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HL-only history is partial by venue retention; one fetch per max age."""
    tail = _bars(_NOW, 3)
    calls = _count_calls(monkeypatch, hl=tail)

    load_research_history(tmp_path, lookback_days=30, strict_hl_only=True, now=_NOW)
    later = _NOW + pd.Timedelta(hours=1)
    _frame, prov = load_research_history(
        tmp_path, lookback_days=30, strict_hl_only=True, now=later
    )

    assert calls["hl"] == 1
    assert prov["cache_hit"] is True
    assert prov["partial"] is True
    assert prov["fetched_at"] == _NOW.isoformat()


def test_refresh_preserves_an_unmanaged_cache_file_byte_for_byte(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = ParquetCache(tmp_path / "cache")
    legacy_path = cache.save(cache_key("BTC", "1m", 2), _bars(pd.Timestamp("2026-07-26T23:59:00Z"), 2))
    legacy_bytes = legacy_path.read_bytes()
    fresh = _bars(_NOW, 2)
    _count_calls(monkeypatch, hl=fresh, binance=fresh.assign(source="binance"))

    _frame, prov = load_research_history(tmp_path, lookback_days=2, now=_NOW)

    preserved = Path(prov["preserved_previous"])
    assert preserved.read_bytes() == legacy_bytes
    assert preserved.name.startswith("BTC_1m_2d__preserved_20260724T2359Z_20260726T2359Z")


# --- strict HL-only isolation ----------------------------------------------


def test_strict_refresh_never_overwrites_the_default_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    full = _bars(_NOW, 30)
    hl_tail = full.tail(5000)
    _count_calls(monkeypatch, hl=hl_tail, binance=full.assign(source="binance"))

    default_frame, _ = load_research_history(tmp_path, lookback_days=30, now=_NOW)
    default_path = ParquetCache(tmp_path / "cache").path_for(cache_key("BTC", "1m", 30))
    default_bytes = default_path.read_bytes()

    strict_frame, strict_prov = load_research_history(
        tmp_path, lookback_days=30, strict_hl_only=True, force_refresh=True, now=_NOW
    )
    again, again_prov = load_research_history(tmp_path, lookback_days=30, now=_NOW)

    assert default_path.read_bytes() == default_bytes
    assert len(strict_frame) == 5000
    assert strict_prov["cache_key"] == "BTC_1m_30d_hlonly"
    assert len(again) == len(default_frame)
    assert again_prov["cache_key"] == "BTC_1m_30d"


def test_default_load_never_reads_the_strict_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ParquetCache(tmp_path / "cache").save(
        cache_key("BTC", "1m", 1, strict_hl_only=True), _bars(_NOW, 1)
    )
    _count_calls(monkeypatch, hl=None)  # type: ignore[arg-type]

    with pytest.raises(FileNotFoundError, match="offline"):
        load_research_history(tmp_path, lookback_days=1, allow_network=False, now=_NOW)


def test_load_reports_gaps_in_its_own_timeframe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fifteen = _bars(_NOW, 60, freq="15min")
    _count_calls(monkeypatch, hl=fifteen, binance=fifteen.assign(source="binance"))

    _frame, prov = load_research_history(tmp_path, timeframe="15m", lookback_days=60, now=_NOW)

    assert prov["gaps"] == {"count": 0, "max_gap_bars": 0}
    assert prov["timeframe"] == "15m"
    assert prov["expected_bars"] == 60 * 96


def test_concurrent_refresh_that_already_moved_the_legacy_file_is_tolerated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hypervector.data.pipeline as pipeline

    cache = ParquetCache(tmp_path / "cache")
    cache.save(cache_key("BTC", "1m", 2), _bars(pd.Timestamp("2026-07-26T23:59:00Z"), 2))
    fresh = _bars(_NOW, 2)
    _count_calls(monkeypatch, hl=fresh, binance=fresh.assign(source="binance"))
    real_replace = pipeline.os.replace
    raced_once: list[bool] = []

    def raced(src: Any, dst: Any) -> None:
        if raced_once or "__preserved_" not in str(dst):
            return real_replace(src, dst)  # the cache's own atomic write
        # Another process renamed the legacy file between our check and rename.
        raced_once.append(True)
        real_replace(src, Path(str(dst) + ".other"))
        raise FileNotFoundError(src)

    monkeypatch.setattr(pipeline.os, "replace", raced)
    frame, prov = load_research_history(tmp_path, lookback_days=2, now=_NOW)
    monkeypatch.undo()

    assert frame["timestamp"].max() == _NOW
    assert prov["preserved_previous"] is None
    assert cache.load_metadata(cache_key("BTC", "1m", 2))["origin"] == "research_history"
