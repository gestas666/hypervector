"""Bars are stamped at bar close; fills are timestamped when their price exists."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from hypervector.nautilus.actor import HypervectorStrategy, config_from_loadout
from hypervector.nautilus.bars import (
    bar_open_label_ns,
    dataframe_to_bars,
    synthetic_btc_perp_instrument,
)
from hypervector.nautilus.load_export import load_strategy_loadout
from hypervector.nautilus.precompute import ohlcv_frame_from_bars
from hypervector.nautilus.runner import run_phase2_backtest
from nautilus_fix_support import (
    FIXTEST_ENTER_AT,
    capture_engine,
    register_fix_strategies,
    synth_ohlcv,
    write_export,
)

_BAR_TYPE = "BTC-PERP.HYPERLIQUID-15-MINUTE-LAST-EXTERNAL"
_INTERVAL = pd.Timedelta(minutes=15)


@pytest.fixture(autouse=True)
def _strategies() -> None:
    register_fix_strategies()


def test_bars_are_stamped_at_close_by_default() -> None:
    df = synth_ohlcv(5)
    bars = dataframe_to_bars(df, _BAR_TYPE, synthetic_btc_perp_instrument())
    for bar, label in zip(bars, df["timestamp"], strict=True):
        close_ns = (label + _INTERVAL).value
        assert bar.ts_event == close_ns
        assert bar.ts_init == close_ns
        assert bar_open_label_ns(bar) == label.value


def test_open_stamping_still_available() -> None:
    df = synth_ohlcv(3)
    bars = dataframe_to_bars(
        df, _BAR_TYPE, synthetic_btc_perp_instrument(), timestamp_at="open"
    )
    assert [b.ts_event for b in bars] == [ts.value for ts in df["timestamp"]]


def test_actor_and_precompute_rebuild_research_labels(tmp_path: Path) -> None:
    df = synth_ohlcv(10)
    bars = dataframe_to_bars(df, _BAR_TYPE, synthetic_btc_perp_instrument())
    loadout = load_strategy_loadout(write_export(tmp_path), strict=True)
    strategy = HypervectorStrategy(config_from_loadout(loadout, bar_type=_BAR_TYPE))
    for bar in bars:
        strategy._append_bar(bar)
    labels = [r["timestamp"] for r in strategy._bar_buffer]
    assert labels == list(df["timestamp"])
    frame = ohlcv_frame_from_bars(bars, label_offset_ns=_INTERVAL.value)
    assert list(frame.index) == list(df["timestamp"])


def test_entry_fill_is_stamped_at_the_close_of_its_bar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry_label = pd.Timestamp("2026-01-01T05:00:00+00:00")
    export_dir = write_export(
        tmp_path,
        strategy=FIXTEST_ENTER_AT,
        params={"entry_ts": entry_label.isoformat(), "direction": "long"},
        exit_mode="trail",
        exits={"trail_atr_mult": 50.0},
    )
    df = synth_ohlcv(40)
    captured = capture_engine(monkeypatch)
    run_phase2_backtest(export_dir=export_dir, data_root=tmp_path / "data", ohlcv=df)
    entry = captured["fills"][0]
    row = int(df.index[df["timestamp"] == entry_label][0])
    # Fills at the close of the 05:00 bar, which only exists at 05:15.
    assert entry["avg_px"] == pytest.approx(float(df["close"].iloc[row]))
    assert entry["ts_last"] == (entry_label + _INTERVAL).value
