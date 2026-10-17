"""Trail exit mode protects positions with a trailing stop (VectorBT trail parity)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import pytest

from hypervector.nautilus.runner import run_phase2_backtest
from hypervector.nautilus.trail import trail_start, trail_step
from nautilus_fix_support import (
    FIXTEST_ENTER_AT,
    capture_engine,
    register_fix_strategies,
    synth_ohlcv,
    write_export,
)

_ENTRY_TS = "2026-01-01T05:00:00+00:00"  # bar 20, after ATR warm-up
_INTERVAL_NS = 15 * 60 * 1_000_000_000


@pytest.fixture(autouse=True)
def _strategies() -> None:
    register_fix_strategies()


# -- pure trail math ---------------------------------------------------------


def test_long_trail_ratchets_with_high_and_hits_on_close() -> None:
    st = trail_start(
        "long", high=101.0, low=99.0, close=100.0, trail_dist=2.0, sl_frac=0.5
    )
    assert st.atr_stop == pytest.approx(99.0)
    st, hit = trail_step(st, high=105.0, low=102.0, close=104.0, trail_dist=2.0)
    assert not hit
    assert st.atr_stop == pytest.approx(103.0)  # 105 - 2
    # Wider ATR never loosens the stop.
    st, hit = trail_step(st, high=104.5, low=103.5, close=103.6, trail_dist=5.0)
    assert not hit
    assert st.atr_stop == pytest.approx(103.0)
    st, hit = trail_step(st, high=103.5, low=102.0, close=102.9, trail_dist=2.0)
    assert hit  # close < 103


def test_short_trail_mirrors_long() -> None:
    st = trail_start(
        "short", high=101.0, low=99.0, close=100.0, trail_dist=2.0, sl_frac=0.5
    )
    assert st.atr_stop == pytest.approx(101.0)
    st, hit = trail_step(st, high=98.0, low=95.0, close=96.0, trail_dist=2.0)
    assert not hit and st.atr_stop == pytest.approx(97.0)
    st, hit = trail_step(st, high=97.5, low=96.5, close=97.2, trail_dist=2.0)
    assert hit  # close > 97


def test_percent_trail_follows_best_close() -> None:
    # VectorBT sl_stop + sl_trail: stop = best close * (1 - sl_frac), hit on close <= stop.
    st = trail_start(
        "long", high=100.0, low=100.0, close=100.0, trail_dist=math.nan, sl_frac=0.02
    )
    st, hit = trail_step(st, high=110.0, low=110.0, close=110.0, trail_dist=math.nan)
    assert not hit and st.peak_close == 110.0
    st, hit = trail_step(st, high=107.9, low=107.7, close=107.8, trail_dist=math.nan)
    assert hit  # 107.8 <= 110 * 0.98


# -- engine ------------------------------------------------------------------


def _vectorbt_exit_label(
    df: pd.DataFrame, direction: str, monkeypatch: pytest.MonkeyPatch
) -> pd.Timestamp:
    """Exit bar of the research portfolio (compute_trial_metrics, trail mode)."""
    import vectorbt as vbt

    from hypervector.sweep.costs import ZERO_COST
    from hypervector.sweep.exits import ExitConfig
    from hypervector.sweep.metrics import compute_trial_metrics

    captured = {}
    original = vbt.Portfolio.from_signals

    def _spy(*args, **kwargs):
        captured["pf"] = original(*args, **kwargs)
        return captured["pf"]

    monkeypatch.setattr(vbt.Portfolio, "from_signals", _spy)
    frame = df.set_index("timestamp")[["open", "high", "low", "close", "volume"]]
    entries = pd.Series(frame.index == pd.Timestamp(_ENTRY_TS), index=frame.index)
    exits = pd.Series(False, index=frame.index)
    compute_trial_metrics(
        frame["close"],
        entries,
        exits,
        direction=direction,
        df=frame,
        exit_cfg=ExitConfig(
            mode="trail", atr_length=14, trail_atr_mult=2.0, sl_pct=0.01
        ),
        cost=ZERO_COST,
        apply_costs=False,
    )
    records = captured["pf"].trades.records_readable
    assert len(records) == 1
    assert str(records.iloc[0]["Status"]) == "Closed"
    return pd.Timestamp(records.iloc[0]["Exit Timestamp"])


@pytest.mark.parametrize("direction", ["long", "short"])
@pytest.mark.parametrize("signal_mode", ["windowed", "precomputed"])
def test_trail_mode_closes_position_on_vectorbt_exit_bar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    direction: str,
    signal_mode: str,
) -> None:
    df = synth_ohlcv(400, seed=11)
    export_dir = write_export(
        tmp_path,
        strategy=FIXTEST_ENTER_AT,
        params={"entry_ts": _ENTRY_TS, "direction": direction},
        exit_mode="trail",
    )
    captured = capture_engine(monkeypatch)
    result = run_phase2_backtest(
        export_dir=export_dir,
        data_root=tmp_path / "data",
        ohlcv=df,
        signal_mode=signal_mode,
    )
    summary = json.loads(result.report_path.read_text())

    # Before the fix: one bare market entry, no stop, position open at the end.
    assert summary["trail_exits"] == 1
    assert (
        summary["trail_exit_model"] == "close_evaluated_trailing_stop_vectorbt_parity"
    )
    assert result.trade_count == 1
    assert result.open_positions_at_end == 0
    fills = captured["fills"]
    assert len(fills) == 2
    exit_fill = fills[1]
    exit_label = pd.Timestamp(exit_fill["ts_last"] - _INTERVAL_NS, unit="ns", tz="UTC")

    expected = _vectorbt_exit_label(df, direction, monkeypatch)
    assert exit_label == expected
    row = df.index[df["timestamp"] == expected][0]
    assert exit_fill["avg_px"] == pytest.approx(float(df["close"].iloc[row]))


def test_trail_disabled_for_strategy_managed_exits(tmp_path: Path) -> None:
    export_dir = write_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
        exit_mode="trail",
        timeframe="1m",
    )
    from hypervector.data.sources import fixture_ohlcv

    result = run_phase2_backtest(
        export_dir=export_dir,
        data_root=tmp_path / "data",
        ohlcv=fixture_ohlcv(n_bars=80, drift=2.0, wave_period=20),
    )
    summary = json.loads(result.report_path.read_text())
    assert summary["trail_exit_model"] is None
