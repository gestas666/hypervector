"""Performance-review regressions (final pass).

- ``pipeline run``'s tune stage reloaded history with the default 24 h cache
  age, so ``--no-network`` re-downloaded (and rewrote) the window the data
  stage had just pinned.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from hypervector.cli import main
from hypervector.data.cache import ParquetCache
from hypervector.data.pipeline import cache_key
from hypervector.data.sources import fixture_ohlcv


def _forbid_network(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def refuse(name: str):
        def _fetch(*_args: Any, **_kwargs: Any) -> pd.DataFrame:
            calls.append(name)
            raise RuntimeError(f"NETWORK FORBIDDEN: {name}")

        return _fetch

    for name in ("hl", "binance", "bybit"):
        monkeypatch.setattr(
            f"hypervector.data.pipeline.live_{name}_fetcher", refuse(name)
        )
    return calls


# --- pipeline run: the tune stage serves the pinned window -----------------------


def test_pipeline_tune_stage_never_refreshes_the_pinned_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = tmp_path / "data"
    lookback = 30
    end = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=10)).floor("h")
    n_bars = lookback * 24
    start = end - pd.Timedelta(hours=n_bars - 1)
    legacy = fixture_ohlcv(
        n_bars=n_bars,
        start=str(start.tz_localize(None)),
        freq="1h",
        drift=5.0,
        wave_period=48,
        source="hl",
    )
    cache = ParquetCache(data / "cache")
    path = cache.save(cache_key("BTC", "1h", lookback), legacy)  # unmanaged, stale
    before = path.read_bytes()
    calls = _forbid_network(monkeypatch)

    code = main(
        [
            "--data-root",
            str(data),
            "pipeline",
            "run",
            "--strategy",
            "test_sma_cross_long",
            "--timeframe",
            "1h",
            "--lookback-days",
            str(lookback),
            "--n-trials",
            "4",
            "--no-network",
            "--no-nautilus",
        ]
    )
    manifest = json.loads(capsys.readouterr().out)

    stages = {stage["stage"]: stage for stage in manifest["stages"]}
    assert calls == []
    assert stages["search"]["status"] == "ok", stages["search"]
    assert code == 0
    assert path.read_bytes() == before
    assert sorted(p.name for p in (data / "cache").glob("*.parquet")) == [path.name]
    search_argv = stages["search"]["argv"]
    assert "--pin-cache" in search_argv and "--refresh" not in search_argv

    meta = json.loads((Path(manifest["export_dir"]) / "meta.json").read_text())
    provenance = meta["data_provenance"]
    assert provenance["refreshed"] is False and provenance["cache_hit"] is True
    assert provenance["start"] == manifest["window"]["start"]
    assert provenance["end"] == manifest["window"]["end"]


# --- compute_trial_metrics: no per-trial re-parse of datetime timestamps -----------


def _reference_bar_times_ns(column: pd.Series) -> Any:
    import numpy as np

    times = pd.DatetimeIndex(pd.to_datetime(column, utc=True))
    times = times.tz_convert("UTC").tz_localize(None)
    return np.asarray(times.as_unit("ns").asi8, dtype=np.int64)


@pytest.mark.parametrize(
    "kind", ["utc_ms", "naive_ns", "new_york", "iso_strings", "utc_object"]
)
def test_bar_times_match_the_parsed_reference_for_every_column_kind(kind: str) -> None:
    import numpy as np

    from hypervector.sweep.metrics import _bar_times_ns

    base = pd.date_range("2026-03-07", periods=600, freq="5min", tz="UTC")
    column = {
        "utc_ms": pd.Series(base.as_unit("ms")),
        "naive_ns": pd.Series(base.tz_localize(None)),
        "new_york": pd.Series(base.tz_convert("America/New_York")),  # spans a DST switch
        "iso_strings": pd.Series(base.strftime("%Y-%m-%dT%H:%M:%S%z")),
        "utc_object": pd.Series(list(base), dtype=object),
    }[kind]
    work = pd.DataFrame({"timestamp": column, "close": 1.0})  # RangeIndex

    got = _bar_times_ns(work.index, work)

    assert got is not None and got.dtype == np.int64
    np.testing.assert_array_equal(got, _reference_bar_times_ns(column))
    np.testing.assert_array_equal(got, base.tz_localize(None).as_unit("ns").asi8)


def test_datetime_timestamp_column_is_not_reparsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hypervector.sweep import metrics

    work = pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-01-01", periods=50, freq="1min", tz="UTC"
            ).as_unit("ms"),
            "close": 1.0,
        }
    )
    parsed: list[object] = []
    original = pd.to_datetime

    def spy(*args: Any, **kwargs: Any) -> Any:
        parsed.append(args[0] if args else None)
        return original(*args, **kwargs)

    monkeypatch.setattr(metrics.pd, "to_datetime", spy)

    assert metrics._bar_times_ns(work.index, work) is not None
    assert parsed == []


def test_numeric_or_missing_timestamps_still_refuse() -> None:
    from hypervector.sweep.metrics import _bar_times_ns

    numeric = pd.DataFrame({"timestamp": [1, 2, 3]})
    holed = pd.DataFrame(
        {"timestamp": pd.Series([pd.Timestamp("2026-01-01", tz="UTC"), pd.NaT])}
    )
    assert _bar_times_ns(numeric.index, numeric) is None
    assert _bar_times_ns(holed.index, holed) is None


# --- paper report: one Counter per field, not one per counted value ----------------


def test_paper_summary_builds_one_counter_per_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from collections import Counter

    from hypervector.paper import report

    built: list[int] = []

    class CountingCounter(Counter):  # type: ignore[type-arg]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            built.append(1)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(report, "Counter", CountingCounter)
    summary = report._PaperSummary(last_n=5)
    for i in range(500):
        summary.count("action", "buy" if i % 2 else "sell")
        summary.count("network", None)

    assert len(built) == 2
    assert summary.totals("action") == {"buy": 250, "sell": 250}
    assert summary.totals("network") == {"": 500}
    assert summary.totals("never_counted") == {}
    assert "never_counted" not in summary.counts


# --- stale-cache refresh: top up the missing tail, not the whole lookback ----------

_NOW = pd.Timestamp("2026-10-17T00:00:00Z")
_STEP = pd.Timedelta("5min")
_HL_RETENTION = 5000


class _Venues:
    """Deterministic venues over one true 5m series; records every request."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        start = _NOW - pd.Timedelta(days=60)
        n = int((_NOW - start) / _STEP) + 1
        self.truth = fixture_ohlcv(
            n_bars=n, start=str(start.tz_localize(None)), freq="5min", drift=0.5
        )
        self.now = _NOW
        self.calls: list[tuple[str, int]] = []
        self.unavailable: set[str] = set()
        self.hl_retention = _HL_RETENTION
        for name in ("hl", "binance", "bybit"):
            monkeypatch.setattr(
                f"hypervector.data.pipeline.live_{name}_fetcher", self._fetcher(name)
            )

    def _fetcher(self, name: str):
        from hypervector.data.backfill import BackfillUnavailable

        def fetch(symbol: str, timeframe: str, lookback_days: int) -> pd.DataFrame:
            self.calls.append((name, lookback_days))
            if name in self.unavailable:
                raise BackfillUnavailable(f"{name} lists no {symbol}")
            ts = self.truth["timestamp"]
            lower = self.now - pd.Timedelta(days=lookback_days)
            frame = self.truth.loc[(ts >= lower) & (ts <= self.now)]
            if name == "hl":
                frame = frame.tail(self.hl_retention)
            return frame.assign(source=name).reset_index(drop=True)

        return fetch


def _seed_managed_cache(root: Path, venues: _Venues, *, fetched: pd.Timestamp) -> None:
    from hypervector.data.pipeline import load_research_history

    venues.now = fetched
    load_research_history(root, timeframe="5m", lookback_days=30, now=fetched)
    venues.now = _NOW
    venues.calls.clear()


def test_stale_managed_cache_is_topped_up_not_redownloaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hypervector.data.pipeline import load_research_history

    venues = _Venues(monkeypatch)
    _seed_managed_cache(tmp_path / "a", venues, fetched=_NOW - pd.Timedelta(hours=25))

    frame, prov = load_research_history(
        tmp_path / "a", timeframe="5m", lookback_days=30, now=_NOW
    )

    # HL is one request either way; the CEX backfill covers only the gap.
    assert venues.calls == [("hl", 30), ("binance", 2)]
    assert prov["refreshed"] is True and prov["cache_hit"] is False
    assert prov["refresh_reason"] == "stale (top-up)"
    assert prov["stale"] is False and prov["partial"] is False
    assert prov["end"] == _NOW.isoformat()
    assert prov["fetched_at"] == _NOW.isoformat()
    assert prov["preserved_previous"] is None
    assert "top_up" in prov["backfill"] and prov["backfill"]["bybit"].startswith("skipped")

    # Same window and prices as a whole refetch, with no seam hole.
    full, _ = load_research_history(
        tmp_path / "b", timeframe="5m", lookback_days=30, force_refresh=True, now=_NOW
    )
    cols = ["timestamp", "open", "high", "low", "close", "volume"]
    pd.testing.assert_frame_equal(frame[cols], full[cols])
    assert frame["timestamp"].diff().dropna().eq(_STEP).all()
    # Cached HL bars that aged out of HL retention are kept, not replaced.
    assert frame["source"].eq("hl").sum() > full["source"].eq("hl").sum()

    venues.calls.clear()
    _again, again_prov = load_research_history(
        tmp_path / "a", timeframe="5m", lookback_days=30, now=_NOW
    )
    assert venues.calls == [] and again_prov["cache_hit"] is True


def test_top_up_that_cannot_reach_the_cached_window_refetches_it_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hypervector.data.pipeline import load_research_history

    venues = _Venues(monkeypatch)
    _seed_managed_cache(tmp_path, venues, fetched=_NOW - pd.Timedelta(days=3))
    venues.hl_retention = 100  # HL now starts after the cached last bar
    venues.unavailable = {"binance", "bybit"}

    _frame, prov = load_research_history(
        tmp_path, timeframe="5m", lookback_days=30, now=_NOW
    )

    assert venues.calls == [
        ("hl", 30),
        ("binance", 4),
        ("bybit", 4),
        ("hl", 30),
        ("binance", 30),
        ("bybit", 30),
    ]
    assert prov["refresh_reason"] == "stale"
    assert "top_up" not in prov["backfill"]


@pytest.mark.parametrize("variant", ["unmanaged", "strict"])
def test_unmanaged_or_strict_stale_cache_keeps_the_full_refetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variant: str
) -> None:
    from hypervector.data.pipeline import load_research_history

    venues = _Venues(monkeypatch)
    strict = variant == "strict"
    if strict:
        venues.now = _NOW - pd.Timedelta(hours=25)
        load_research_history(
            tmp_path, timeframe="5m", lookback_days=10, strict_hl_only=True, now=venues.now
        )
        venues.now = _NOW
        venues.calls.clear()
    else:
        ts = venues.truth["timestamp"]
        old = venues.truth.loc[
            (ts > _NOW - pd.Timedelta(days=32)) & (ts <= _NOW - pd.Timedelta(days=2))
        ].assign(source="hl")
        ParquetCache(tmp_path / "cache").save(cache_key("BTC", "5m", 30), old)

    lookback = 10 if strict else 30
    _frame, prov = load_research_history(
        tmp_path, timeframe="5m", lookback_days=lookback, strict_hl_only=strict, now=_NOW
    )

    assert venues.calls[0] == ("hl", lookback)
    assert all(days == lookback for _name, days in venues.calls)
    assert prov["refresh_reason"] == "stale"
    if not strict:
        assert prov["preserved_previous"] is not None


def test_top_up_backfill_failure_stays_loud_and_keeps_hl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hypervector.data.pipeline import load_research_history

    venues = _Venues(monkeypatch)
    _seed_managed_cache(tmp_path, venues, fetched=_NOW - pd.Timedelta(hours=25))
    before = (tmp_path / "cache" / "BTC_5m_30d.parquet").read_bytes()

    def outage(*_args: Any) -> pd.DataFrame:
        raise RuntimeError("binance outage")

    monkeypatch.setattr("hypervector.data.pipeline.live_binance_fetcher", outage)

    with pytest.raises(RuntimeError, match="binance outage"):
        load_research_history(tmp_path, timeframe="5m", lookback_days=30, now=_NOW)

    assert (tmp_path / "cache" / "BTC_5m_30d.parquet").read_bytes() == before
    assert (tmp_path / "cache" / "BTC_5m_30d_hlonly.parquet").is_file()
