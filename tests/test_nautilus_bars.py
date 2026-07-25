"""Research OHLCV → Nautilus Bar list (offline; no network, no engine.run)."""

from __future__ import annotations

from pathlib import Path

import pytest
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.instruments import CryptoPerpetual

from hypervector.data.sources import fixture_ohlcv
from hypervector.nautilus.bars import (
    bar_type_from_loadout,
    dataframe_to_bars,
    synthetic_btc_perp_instrument,
)
from hypervector.nautilus.load_export import StrategyLoadout


def _loadout(**overrides) -> StrategyLoadout:
    base = dict(
        strategy_name="test_strategy",
        role=None,
        params={},
        meta={},
        costs=None,
        risk=None,
        exit_mode=None,
        exits=None,
        export_dir=Path("/tmp"),
        symbol="BTC",
        timeframe="1m",
    )
    base.update(overrides)
    return StrategyLoadout(**base)


def test_synthetic_btc_perp_instrument_is_crypto_perp_on_hyperliquid():
    inst = synthetic_btc_perp_instrument()
    assert isinstance(inst, CryptoPerpetual)
    assert str(inst.id) == "BTC-PERP.HYPERLIQUID"
    assert str(inst.id.venue) == "HYPERLIQUID"
    assert float(inst.margin_init) == pytest.approx(0.025)


def test_synthetic_btc_perp_instrument_sim_venue():
    inst = synthetic_btc_perp_instrument(venue="SIM")
    assert str(inst.id) == "BTC-PERP.SIM"


def test_bar_type_from_loadout_defaults_to_btc_1m_external():
    loadout = _loadout()
    bt = bar_type_from_loadout(loadout)
    assert bt == "BTC-PERP.HYPERLIQUID-1-MINUTE-LAST-EXTERNAL"
    # Round-trip through Nautilus parser
    assert str(BarType.from_str(bt)) == bt


def test_bar_type_from_loadout_maps_timeframes():
    assert "5-MINUTE" in bar_type_from_loadout(_loadout(timeframe="5m"))
    assert "1-HOUR" in bar_type_from_loadout(_loadout(timeframe="1h"))


def test_dataframe_to_bars_from_fixture_ohlcv_no_network():
    n = 50
    df = fixture_ohlcv(n_bars=n, drift=2.0, wave_period=20)
    instrument = synthetic_btc_perp_instrument()
    bar_type = f"{instrument.id}-1-MINUTE-LAST-EXTERNAL"

    bars = dataframe_to_bars(df, bar_type, instrument)

    assert len(bars) == n
    assert all(isinstance(b, Bar) for b in bars)
    assert str(bars[0].bar_type) == bar_type
    # First fixture close is base_price with zero drift offset at t=0
    assert float(bars[0].close) == pytest.approx(
        float(df["close"].iloc[0]), rel=0, abs=0.1
    )
    # Timestamps advance (ns)
    assert bars[1].ts_event > bars[0].ts_event


def test_dataframe_to_bars_accepts_bar_type_object():
    df = fixture_ohlcv(n_bars=5)
    instrument = synthetic_btc_perp_instrument()
    bar_type = BarType.from_str(f"{instrument.id}-1-MINUTE-LAST-EXTERNAL")
    bars = dataframe_to_bars(df, bar_type, instrument)
    assert len(bars) == 5


def test_dataframe_to_bars_preserves_fractional_volume():
    df = fixture_ohlcv(n_bars=3)
    df = df.copy()
    df["volume"] = [1.234, 0.5, 2.0]
    instrument = synthetic_btc_perp_instrument()
    bar_type = f"{instrument.id}-1-MINUTE-LAST-EXTERNAL"
    bars = dataframe_to_bars(df, bar_type, instrument)
    assert float(bars[0].volume) == pytest.approx(1.234, abs=1e-3)
    assert float(bars[1].volume) == pytest.approx(0.5, abs=1e-3)
