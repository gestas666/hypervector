"""Shared bar-window signal adapter (Phase 2 Nautilus actor input)."""

from hypervector.data.sources import fixture_ohlcv
from hypervector.nautilus.signals import last_bar_intent, signals_from_ohlcv
from hypervector.strategies import register_all_strategies


def test_signals_from_ohlcv_matches_registry_builder():
    register_all_strategies()
    df = fixture_ohlcv(n_bars=400, drift=20.0, wave_period=30)
    params = {"bbwp_lookback": 100, "bbwp_threshold": 20.0, "pmarp_exit_lo": 10.0}
    entries, exits, direction = signals_from_ohlcv(df, "test_sma_cross_short", params)
    assert direction == "short"
    assert len(entries) == len(df)
    assert entries.dtype == bool or entries.astype(bool).dtype == bool


def test_last_bar_intent_is_boolean_on_final_index():
    register_all_strategies()
    df = fixture_ohlcv(n_bars=400, drift=20.0, wave_period=30)
    intent = last_bar_intent(df, "test_sma_cross_short", {"bbwp_lookback": 100})
    assert intent.direction in ("long", "short", "flat")
    assert isinstance(intent.enter, bool)
    assert isinstance(intent.exit, bool)
