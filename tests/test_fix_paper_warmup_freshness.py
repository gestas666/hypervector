"""Warm-up must never run live decisions on a stale or gapped cached history."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from paper_fix_fixtures import hl_bars, write_strict_export

from hypervector.nautilus.actor import DEFAULT_MAX_LOOKBACK
from hypervector.paper.runner import start_paper_daemon
from hypervector.paper.session import PaperSession

NOW = pd.Timestamp("2026-10-17T12:00:30Z")


class _TailFetcher:
    """Deterministic HL tail: contiguous 1m bars ending with the forming candle."""

    def __init__(self, *, fail: bool = False, close: float = 200.0) -> None:
        self.calls: list[float] = []
        self.fail = fail
        self.close = close

    def __call__(self, symbol: str, timeframe: str, lookback_days: float, **_kw):
        assert symbol == "BTC" and timeframe == "1m"
        self.calls.append(float(lookback_days))
        if self.fail:
            raise ConnectionError("public candle endpoint unavailable")
        start = (NOW - pd.Timedelta(days=lookback_days)).ceil("min")
        count = int((NOW.floor("min") - start) / pd.Timedelta(minutes=1)) + 1
        return hl_bars(start.isoformat(), count, close=self.close)


def _spy_warm_up(monkeypatch: pytest.MonkeyPatch) -> list[pd.DataFrame]:
    seen: list[pd.DataFrame] = []
    original = PaperSession.warm_up

    def spy(self: PaperSession, frame: pd.DataFrame, **kwargs: object) -> int:
        seen.append(frame.copy())
        return original(self, frame, **kwargs)

    monkeypatch.setattr(PaperSession, "warm_up", spy)
    return seen


def _run(tmp_path: Path, monkeypatch, cache: pd.DataFrame, fetcher: _TailFetcher):
    export = write_strict_export(tmp_path)
    monkeypatch.setattr(
        "hypervector.paper.runner.load_research_history",
        lambda *_a, **_k: (cache.copy(), {"sources": {"hl": len(cache)}}),
    )
    return start_paper_daemon(
        export_dir=export,
        data_root=tmp_path / "data",
        poll_fn=lambda **_kwargs: cache.iloc[0:0].copy(),
        warm_tail_fn=fetcher,
        max_live_bars=0,
        poll_interval_secs=0.0,
        sleep_fn=lambda _s: None,
        install_signal_handlers=False,
        enable_funding_refresh=False,
        enforce_live_boundary=True,
        execution_mode="paper",
        now_fn=lambda: NOW,
    )


def test_stale_cache_is_replaced_by_fresh_tail_without_splicing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 78-day-old cache must not be spliced in front of today's bars."""
    stale = hl_bars("2026-07-28T00:00:00Z", 3000, close=100.0)
    fetcher = _TailFetcher()
    seen = _spy_warm_up(monkeypatch)

    result = _run(tmp_path, monkeypatch, stale, fetcher)

    assert len(fetcher.calls) == 1
    # Only the bounded indicator window is requested, not the 30-day lookback.
    assert fetcher.calls[0] * 1440 == pytest.approx(DEFAULT_MAX_LOOKBACK + 1, abs=1)
    warm = seen[-1]
    stamps = pd.to_datetime(warm["timestamp"], utc=True)
    assert stamps.min() > stale["timestamp"].max()
    assert stamps.diff().dropna().eq(pd.Timedelta(minutes=1)).all()
    # Causal boundary: the forming 12:00 candle is withheld.
    assert stamps.max() == pd.Timestamp("2026-10-17T11:59:00Z")
    assert len(warm) >= DEFAULT_MAX_LOOKBACK
    assert result.warmup_provenance["mode"] == "tail_replaced_stale_cache"
    assert result.warmup_provenance["cache_last_open"] == "2026-07-30T01:59:00+00:00"


def test_recent_cache_is_topped_up_and_partial_last_bar_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cache a few minutes old keeps its history; HL wins on the overlap."""
    cache = hl_bars("2026-10-17T10:00:00Z", 115, close=100.0)  # ends 11:54
    cache.loc[cache.index[-1], "close"] = 1.0  # partial candle at save time
    fetcher = _TailFetcher(close=200.0)
    seen = _spy_warm_up(monkeypatch)

    result = _run(tmp_path, monkeypatch, cache, fetcher)

    assert len(fetcher.calls) == 1
    assert fetcher.calls[0] * 1440 < 10.0  # only the missing tail
    warm = seen[-1].set_index(pd.to_datetime(seen[-1]["timestamp"], utc=True))
    assert warm.index.min() == pd.Timestamp("2026-10-17T10:00:00Z")
    assert warm.index.max() == pd.Timestamp("2026-10-17T11:59:00Z")
    assert warm.index.to_series().diff().dropna().eq(pd.Timedelta(minutes=1)).all()
    assert warm.loc[pd.Timestamp("2026-10-17T11:52:00Z"), "close"] == 100.0
    assert warm.loc[pd.Timestamp("2026-10-17T11:54:00Z"), "close"] == 200.0
    assert result.warmup_provenance["mode"] == "tail_merged"


def test_cache_whose_last_bar_is_still_forming_needs_no_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = hl_bars("2026-10-17T10:00:00Z", 121, close=100.0)  # ends 12:00 (forming)
    fetcher = _TailFetcher()

    result = _run(tmp_path, monkeypatch, cache, fetcher)

    assert fetcher.calls == []
    assert result.warm_bars == 120
    assert result.warmup_provenance["mode"] == "cache_fresh"


def test_failed_tail_refresh_is_a_technical_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stale = hl_bars("2026-07-28T00:00:00Z", 3000, close=100.0)

    with pytest.raises(RuntimeError, match="warm-up history stale"):
        _run(tmp_path, monkeypatch, stale, _TailFetcher(fail=True))
