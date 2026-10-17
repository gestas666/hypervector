"""Exact startup evidence and unchanged offline poller behavior."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest

from cohort_startup_candle_support import OBSERVED, OBSERVED_MS, candle_frame
from test_multi_asset_intent_poller import _CanonicalCollector, _Collector

from hypervector.live.multi_asset_intent_poller import ConfiguredMultiAssetIntentPoller
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_market_bars import MultiAssetIntentPollerError


def test_poller_captures_full_initial_frames_once_without_changing_results() -> None:
    """Observe actual retained inputs before collectors with no extra requests."""
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/multi_asset_bidirectional_canary.toml", mode="observe"
    )
    frame = candle_frame()
    requests: list[tuple[str, float, int | None]] = []
    collectors = {p.strategy_id: _Collector(p.strategy_id, emit=False) for p in config.providers}

    def fetch(symbol: str, timeframe: str, days: float, *, end_ms: int | None = None) -> pd.DataFrame:
        """Return fixed evidence while recording every transport request."""
        assert timeframe == "1m"
        requests.append((symbol, days, end_ms))
        return frame.copy(deep=True)

    captured: list[dict[str, pd.DataFrame]] = []

    def observe(frames: dict[str, pd.DataFrame], activation_ms: int, cutoff_ms: int) -> None:
        """Require capture before any provider has consumed its input."""
        assert not any(c.bar_counts for c in collectors.values())
        assert activation_ms == OBSERVED_MS - 60_000
        assert cutoff_ms == OBSERVED_MS
        captured.append({symbol: value.copy(deep=True) for symbol, value in frames.items()})

    poller = ConfiguredMultiAssetIntentPoller(
        config=config, fetch_bars=fetch, collectors=collectors,
        canonical_regime_collector=_CanonicalCollector(),
    )
    assert hasattr(poller, "bind_startup_input_observer"), "full startup input observer is missing"
    poller.bind_startup_input_observer(observe)
    poller.activate(OBSERVED_MS - 60_000)
    first = poller.poll(OBSERVED)
    second = poller.poll(OBSERVED + timedelta(seconds=1))
    assert len(captured) == 1
    assert tuple(captured[0]) == config.symbols
    for symbol in config.symbols:
        pd.testing.assert_frame_equal(captured[0][symbol], frame, check_exact=True)
        assert len(first.market_bars[symbol]) == 360
        assert first.market_bars[symbol][-1].timestamp_ms < OBSERVED_MS
    assert len(requests) == 2 * len(config.symbols)
    baseline = ConfiguredMultiAssetIntentPoller(
        config=config, fetch_bars=fetch,
        collectors={p.strategy_id: _Collector(p.strategy_id, emit=False) for p in config.providers},
        canonical_regime_collector=_CanonicalCollector(),
    )
    baseline.activate(OBSERVED_MS - 60_000)
    assert baseline.poll(OBSERVED) == first
    assert baseline.poll(OBSERVED + timedelta(seconds=1)) == second
    assert requests[: 2 * len(config.symbols)] == requests[2 * len(config.symbols):]


def test_archive_preserves_exact_frames_and_hourly_indicator_seeds(tmp_path: Path) -> None:
    """Persisted evidence reproduces initialization beyond the chart tail."""
    from hypervector.live.cohort_startup_candles import (
        StartupCandleContext, load_startup_candles, write_startup_candles,
    )
    from hypervector.live.multi_asset_market_bars import resample_one_minute_bars
    from hypervector.research.hourly_band_reentry import build_hourly_band_reentry_signals

    context = StartupCandleContext(
        "fixture", "a" * 64, "b" * 64, "run-1", ("BTC", "xyz:SPCX"),
        OBSERVED_MS - 60_000, OBSERVED_MS, 14.0,
    )
    frames = {symbol: candle_frame() for symbol in context.symbols}
    receipt = write_startup_candles(tmp_path, context, frames)
    loaded = load_startup_candles(receipt.manifest_path, receipt.manifest_sha256, context)
    assert receipt.rows == 10_002
    for symbol, original in frames.items():
        restored = loaded[symbol]
        pd.testing.assert_frame_equal(original, restored, check_exact=True)
        before = build_hourly_band_reentry_signals(resample_one_minute_bars(original, minutes=15).set_index("timestamp"))
        after = build_hourly_band_reentry_signals(resample_one_minute_bars(restored, minutes=15).set_index("timestamp"))
        pd.testing.assert_frame_equal(before, after, check_exact=True)
        assert after.atr.notna().sum() > 20


def test_observer_binding_is_fixed_before_activation() -> None:
    """A later cycle cannot be mislabeled as the original startup input."""
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/multi_asset_bidirectional_canary.toml", mode="observe"
    )
    poller = ConfiguredMultiAssetIntentPoller(
        config=config, fetch_bars=lambda *args, **kwargs: candle_frame(),
        collectors={p.strategy_id: _Collector(p.strategy_id, emit=False) for p in config.providers},
        canonical_regime_collector=_CanonicalCollector(),
    )

    def observer(*_args: object) -> None:
        return None

    poller.bind_startup_input_observer(observer)
    with pytest.raises(MultiAssetIntentPollerError, match="observer"):
        poller.bind_startup_input_observer(observer)
    poller.activate(OBSERVED_MS)
    with pytest.raises(MultiAssetIntentPollerError, match="observer"):
        poller.bind_startup_input_observer(observer)
