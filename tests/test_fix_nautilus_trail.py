"""Trail exit mode: one intrabar trailing stop per position (VectorBT parity).

Research trail mode is ONE VectorBT trailing ``sl_stop``: the distance is fixed
at entry (``trail_atr_mult x ATR / close``, ``sl_pct`` during ATR warm-up), the
anchor starts at the entry close and ratchets with later bar highs (long) /
lows (short), each bar is evaluated intrabar against the level carried in
from the previous bars (gap -> open, touch -> level, stop-market), and every
entry starts a fresh stop. The Nautilus actor rests a reduce-only STOP_MARKET
at the tick-grid level and moves it after every bar; a level that ratchets
through the close exits at the next bar's opening instant.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from hypervector.nautilus.runner import run_phase2_backtest
from hypervector.nautilus.trail import (
    TRAIL_EXIT_MODEL,
    grid_stop_price,
    level_through_close,
    trail_fill_price,
    trail_ratchet,
    trail_start,
    trail_step,
)
from hypervector.sweep.costs import ZERO_COST
from hypervector.sweep.exits import ExitConfig, stop_distance_frac
from nautilus_fix_support import (
    FIXTEST_ENTER_AT,
    FIXTEST_ENTER_EACH,
    capture_engine,
    register_fix_strategies,
    synth_ohlcv,
    write_export,
)

_ENTRY_TS = "2026-01-01T05:00:00+00:00"  # bar 20, after ATR warm-up
_INTERVAL_NS = 15 * 60 * 1_000_000_000
_TICK = 0.1  # BTC price increment in the venue spec


@pytest.fixture(autouse=True)
def _strategies() -> None:
    register_fix_strategies()


# -- pure trail math ---------------------------------------------------------


def test_stop_is_anchored_at_the_entry_close_with_the_entry_distance() -> None:
    st = trail_start("long", entry_close=100.0, sl_frac=0.05)
    assert st.anchor == 100.0
    assert st.stop_level == pytest.approx(95.0)
    short = trail_start("short", entry_close=100.0, sl_frac=0.05)
    assert short.stop_level == pytest.approx(105.0)
    with pytest.raises(ValueError):
        trail_start("flat", entry_close=100.0, sl_frac=0.05)


def test_long_bar_is_evaluated_before_it_ratchets_the_stop() -> None:
    st = trail_start("long", entry_close=100.0, sl_frac=0.05)  # level 95
    # High 110 would lift the level to 104.5, but this bar is judged at 95.
    st, fill = trail_step(st, open=101.0, high=110.0, low=100.0)
    assert fill is None
    assert st.anchor == 110.0 and st.stop_level == pytest.approx(104.5)
    # A lower high never loosens the stop.
    st, fill = trail_step(st, open=108.0, high=109.0, low=105.0)
    assert fill is None and st.anchor == 110.0
    st, fill = trail_step(st, open=106.0, high=107.0, low=104.0)
    assert fill == pytest.approx(104.5)  # touched intrabar: fills at the level


def test_long_fill_is_the_open_on_a_gap_and_the_level_on_a_touch() -> None:
    st = trail_start("long", entry_close=100.0, sl_frac=0.05)  # level 95
    assert trail_fill_price(st, open=94.0, high=96.0, low=93.0) == 94.0  # gap
    assert trail_fill_price(st, open=99.0, high=99.5, low=94.5) == pytest.approx(95.0)
    assert trail_fill_price(st, open=99.0, high=99.5, low=95.5) is None


def test_short_trail_mirrors_long() -> None:
    st = trail_start("short", entry_close=100.0, sl_frac=0.05)  # level 105
    st, fill = trail_step(st, open=99.0, high=100.0, low=90.0)
    assert fill is None and st.stop_level == pytest.approx(94.5)
    assert trail_ratchet(st, high=80.0, low=91.0).anchor == 90.0  # never loosens
    assert trail_fill_price(st, open=95.0, high=96.0, low=94.0) == 95.0  # gap
    st, fill = trail_step(st, open=93.0, high=94.6, low=92.0)
    assert fill == pytest.approx(94.5)


def test_level_through_close_flags_a_stop_that_cannot_rest() -> None:
    st = trail_ratchet(
        trail_start("long", entry_close=100.0, sl_frac=0.05), high=110.0, low=99.0
    )
    assert level_through_close(st, 104.0)  # level 104.5 is above the close
    assert not level_through_close(st, 105.0)
    short = trail_ratchet(
        trail_start("short", entry_close=100.0, sl_frac=0.05), high=101.0, low=90.0
    )
    assert level_through_close(short, 95.0)  # level 94.5 is below the close
    assert not level_through_close(short, 94.0)


def test_grid_trigger_is_touched_exactly_when_the_level_is() -> None:
    kw = {"increment": 0.1, "precision": 1}
    assert grid_stop_price(60096.6667, direction="long", **kw) == 60096.6
    assert grid_stop_price(59896.6667, direction="short", **kw) == 59896.7
    assert grid_stop_price(60000.0, direction="long", **kw) == 60000.0  # on grid
    assert grid_stop_price(60000.0, direction="short", **kw) == 60000.0
    assert grid_stop_price(0.04, direction="long", **kw) is None  # unreachable
    assert grid_stop_price(-5.0, direction="long", **kw) is None
    rng = np.random.default_rng(3)
    for level in rng.uniform(1_000.0, 90_000.0, 500):
        lo = grid_stop_price(level, direction="long", **kw)
        hi = grid_stop_price(level, direction="short", **kw)
        assert lo <= level < round(lo + 0.1, 1)
        assert round(hi - 0.1, 1) < level <= hi


@pytest.mark.parametrize("direction", ["long", "short"])
@pytest.mark.parametrize("seed", [3, 11, 29])
def test_pure_trail_reproduces_the_vectorbt_stop_path(
    direction: str, seed: int
) -> None:
    """trail_start/trail_step == compute_trial_metrics trail mode (bar and price)."""
    df = synth_ohlcv(300, seed=seed, vol=0.006)
    entry_row = 20
    cfg = ExitConfig(mode="trail", atr_length=14, trail_atr_mult=1.5, sl_pct=0.01)
    records = _vectorbt_records(df, direction, [entry_row], cfg)
    assert len(records) == 1 and records[0]["closed"]

    st = trail_start(
        direction,
        entry_close=float(df["close"].iloc[entry_row]),
        sl_frac=float(stop_distance_frac(df, cfg).iloc[entry_row]),
    )
    exit_row, fill = None, None
    for i in range(entry_row + 1, len(df)):
        st, fill = trail_step(
            st,
            open=float(df["open"].iloc[i]),
            high=float(df["high"].iloc[i]),
            low=float(df["low"].iloc[i]),
        )
        if fill is not None:
            exit_row = i
            break
    assert exit_row == records[0]["exit_row"]
    assert fill == pytest.approx(records[0]["exit_price"], rel=1e-12)


# -- VectorBT reference ------------------------------------------------------


def _vectorbt_records(
    df: pd.DataFrame,
    direction: str,
    entry_rows: list[int],
    cfg: ExitConfig,
) -> list[dict]:
    """Trades of the research portfolio (compute_trial_metrics, trail mode).

    1x notional keeps the isolated-liquidation barrier out of reach, so the
    trailing stop alone closes positions.
    """
    import vectorbt as vbt

    from hypervector.sweep.metrics import compute_trial_metrics

    captured: dict = {}
    original = vbt.Portfolio.from_signals

    def _spy(*args, **kwargs):
        captured["pf"] = original(*args, **kwargs)
        return captured["pf"]

    vbt.Portfolio.from_signals = _spy
    try:
        frame = df.set_index("timestamp")[["open", "high", "low", "close", "volume"]]
        entries = pd.Series(False, index=frame.index)
        entries.iloc[entry_rows] = True
        compute_trial_metrics(
            frame["close"],
            entries,
            pd.Series(False, index=frame.index),
            direction=direction,
            df=frame,
            exit_cfg=cfg,
            cost=ZERO_COST,
            apply_costs=False,
            fixed_notional_fraction=1.0,
        )
    finally:
        vbt.Portfolio.from_signals = original
    rows = captured["pf"].trades.records_readable
    out = []
    for _, r in rows.iterrows():
        closed = str(r["Status"]) == "Closed"
        exit_ts = pd.Timestamp(r["Exit Timestamp"]) if closed else None
        out.append(
            {
                "entry_ts": pd.Timestamp(r["Entry Timestamp"]),
                "closed": closed,
                "exit_ts": exit_ts,
                "exit_row": int(df.index[df["timestamp"] == exit_ts][0])
                if closed
                else None,
                "exit_price": float(r["Avg Exit Price"]) if closed else None,
            }
        )
    return out


def _cfg(trail_atr_mult: float = 2.0) -> ExitConfig:
    # Same exit fields write_export puts in the bundle.
    return ExitConfig(
        mode="trail", atr_length=14, trail_atr_mult=trail_atr_mult, sl_pct=0.01
    )


def _fill_bar(ts_ns: int) -> pd.Timestamp:
    """Research label of the bar whose (open, close] contains a fill time."""
    close_ns = -(-int(ts_ns) // _INTERVAL_NS) * _INTERVAL_NS
    return pd.Timestamp(close_ns - _INTERVAL_NS, unit="ns", tz="UTC")


def _by_fill_time(captured: dict) -> list[dict]:
    return sorted(captured["fills"], key=lambda o: o["ts_last"])


def _assert_exit_matches(exit_fill: dict, record: dict, direction: str) -> None:
    """Same exit bar; price equal (gap/open) or within one tick on the safe side."""
    assert record["closed"]
    assert _fill_bar(exit_fill["ts_last"]) == record["exit_ts"]
    px, ref = exit_fill["avg_px"], record["exit_price"]
    assert abs(px - ref) < _TICK + 1e-9
    if direction == "long":
        assert px <= ref + 1e-9  # trigger is the grid price at/below the level
    else:
        assert px >= ref - 1e-9


# -- engine: random-walk parity ----------------------------------------------


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

    assert summary["trail_exits"] == 1
    assert summary["trail_exit_model"] == TRAIL_EXIT_MODEL
    assert result.trade_count == 1
    assert result.open_positions_at_end == 0
    fills = _by_fill_time(captured)
    assert len(fills) == 2
    entry_fill, exit_fill = fills
    entry_row = int(df.index[df["timestamp"] == pd.Timestamp(_ENTRY_TS)][0])
    assert entry_fill["avg_px"] == pytest.approx(float(df["close"].iloc[entry_row]))

    (record,) = _vectorbt_records(df, direction, [entry_row], _cfg())
    _assert_exit_matches(exit_fill, record, direction)
    # The exit is the resting reduce-only stop, filled intrabar at its trigger.
    assert exit_fill["type"] == "STOP_MARKET" and exit_fill["reduce_only"]
    assert exit_fill["avg_px"] == pytest.approx(exit_fill["trigger_price"])


@pytest.mark.parametrize("direction", ["long", "short"])
def test_trail_entry_during_atr_warmup_matches_vectorbt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, direction: str
) -> None:
    """Entry at bar 11 (ATR not finite yet): the sl_pct distance, as in research."""
    df = synth_ohlcv(500, seed=109, vol=0.006)
    entry_row = 11
    assert stop_distance_frac(df, _cfg(1.0)).iloc[entry_row] == pytest.approx(0.01)
    export_dir = write_export(
        tmp_path,
        strategy=FIXTEST_ENTER_AT,
        params={
            "entry_ts": df["timestamp"].iloc[entry_row].isoformat(),
            "direction": direction,
        },
        exit_mode="trail",
        exits={"trail_atr_mult": 1.0},
    )
    captured = capture_engine(monkeypatch)
    run_phase2_backtest(export_dir=export_dir, data_root=tmp_path / "data", ohlcv=df)
    fills = _by_fill_time(captured)
    assert len(fills) == 2
    (record,) = _vectorbt_records(df, direction, [entry_row], _cfg(1.0))
    _assert_exit_matches(fills[1], record, direction)


# Exit path each seeded case takes: the resting stop, or the next-open market
# exit after the level ratcheted through the close.
_TIGHT_EXIT_TYPE = {
    (2, "long"): "STOP_MARKET",
    (2, "short"): "STOP_MARKET",
    (5, "long"): "STOP_MARKET",
    (5, "short"): "MARKET",
    (17, "long"): "MARKET",
    (17, "short"): "STOP_MARKET",
    (23, "long"): "MARKET",
    (23, "short"): "STOP_MARKET",
}


@pytest.mark.parametrize(("seed", "direction"), sorted(_TIGHT_EXIT_TYPE))
def test_tight_trail_matches_vectorbt_across_seeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, seed: int, direction: str
) -> None:
    """A 0.5 x ATR trail exercises both exit paths (resting stop, next-open)."""
    df = synth_ohlcv(200, seed=seed, vol=0.004)
    export_dir = write_export(
        tmp_path,
        strategy=FIXTEST_ENTER_AT,
        params={"entry_ts": _ENTRY_TS, "direction": direction},
        exit_mode="trail",
        exits={"trail_atr_mult": 0.5},
    )
    captured = capture_engine(monkeypatch)
    run_phase2_backtest(export_dir=export_dir, data_root=tmp_path / "data", ohlcv=df)
    fills = _by_fill_time(captured)
    assert len(fills) == 2
    (record,) = _vectorbt_records(df, direction, [20], _cfg(0.5))
    exit_fill = fills[1]
    _assert_exit_matches(exit_fill, record, direction)
    assert exit_fill["type"] == _TIGHT_EXIT_TYPE[(seed, direction)]
    if exit_fill["type"] == "MARKET":
        # Opening instant of VectorBT's exit bar, at that bar's open.
        assert exit_fill["ts_last"] == record["exit_ts"].value + 1
        assert exit_fill["avg_px"] == pytest.approx(record["exit_price"])
    else:
        assert exit_fill["avg_px"] == pytest.approx(exit_fill["trigger_price"])


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
    assert summary["trail_exits"] == 0


# -- engine: hand-built bars (each exit path, both directions) ---------------

_BASE = 60_000.0
_ENTRY_ROW = 30  # last of 31 flat bars: TR = ATR = 200, distance 400 / 60000
# (open, high, low, close) after the entry bar, written for a long position;
# the short scenario mirrors prices around the base.
_PATHS = {
    # bar 31 lifts the anchor to 60500 (level 60096.67); bar 32 trades through it.
    "touch": [(60000, 60500, 59950, 60400), (60400, 60450, 60000, 60100)],
    # bar 32 opens below the resting level: stop-market fills at the open.
    "gap": [(60000, 60500, 59950, 60400), (60050, 60080, 59990, 60010)],
    # bar 31 sets a new high and closes below the ratcheted level (60394.67):
    # VectorBT fills at bar 32's open, the actor exits at that instant.
    "through_close": [(60000, 60800, 59950, 60100), (60100, 60200, 60000, 60150)],
}


def _scenario_frame(path: list[tuple], direction: str, tail: int = 4) -> pd.DataFrame:
    rows = [(_BASE, _BASE + 100, _BASE - 100, _BASE)] * (_ENTRY_ROW + 1)
    rows += [tuple(float(x) for x in r) for r in path]
    last = rows[-1][3]
    rows += [(last, last + 100, last - 100, last)] * tail
    o, h, lo, c = (np.asarray(col, dtype=float) for col in zip(*rows))
    if direction == "short":
        o, h, lo, c = 2 * _BASE - o, 2 * _BASE - lo, 2 * _BASE - h, 2 * _BASE - c
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-01-01", periods=len(rows), freq="15min", tz="UTC"
            ),
            "open": o,
            "high": h,
            "low": lo,
            "close": c,
            "volume": 50.0,
        }
    )


def _run_scenario(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    df: pd.DataFrame,
    direction: str,
    entry_rows: list[int],
) -> tuple[dict, dict, object]:
    export_dir = write_export(
        tmp_path,
        strategy=FIXTEST_ENTER_EACH,
        params={
            "entry_ts": ",".join(
                df["timestamp"].iloc[r].isoformat() for r in entry_rows
            ),
            "direction": direction,
        },
        exit_mode="trail",
    )
    captured = capture_engine(monkeypatch)
    result = run_phase2_backtest(
        export_dir=export_dir, data_root=tmp_path / "data", ohlcv=df
    )
    return captured, json.loads(result.report_path.read_text()), result


def _trigger_path(
    df: pd.DataFrame, direction: str, entry_row: int, last_row: int
) -> list[float]:
    """Grid triggers the pure model rests after the entry bar and each later bar."""
    st = trail_start(
        direction,
        entry_close=float(df["close"].iloc[entry_row]),
        sl_frac=float(stop_distance_frac(df, _cfg()).iloc[entry_row]),
    )
    path = [
        grid_stop_price(
            st.stop_level, increment=_TICK, precision=1, direction=direction
        )
    ]
    for i in range(entry_row + 1, last_row + 1):
        st = trail_ratchet(
            st, high=float(df["high"].iloc[i]), low=float(df["low"].iloc[i])
        )
        path.append(
            grid_stop_price(
                st.stop_level, increment=_TICK, precision=1, direction=direction
            )
        )
    return path


@pytest.mark.parametrize("direction", ["long", "short"])
@pytest.mark.parametrize("scenario", sorted(_PATHS))
def test_each_trail_exit_path_matches_vectorbt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scenario: str, direction: str
) -> None:
    df = _scenario_frame(_PATHS[scenario], direction)
    captured, summary, result = _run_scenario(
        tmp_path, monkeypatch, df, direction, [_ENTRY_ROW]
    )
    (record,) = _vectorbt_records(df, direction, [_ENTRY_ROW], _cfg())
    assert record["exit_row"] == _ENTRY_ROW + 2
    fills = _by_fill_time(captured)
    assert len(fills) == 2
    exit_fill = fills[1]
    _assert_exit_matches(exit_fill, record, direction)
    assert summary["trail_exits"] == 1 and result.open_positions_at_end == 0

    stop_orders = [o for o in captured["orders"] if o["type"] == "STOP_MARKET"]
    assert len(stop_orders) == 1 and stop_orders[0]["reduce_only"]
    exit_row = record["exit_row"]
    if scenario == "touch":
        # Intrabar touch: the resting stop fills at its (moved) grid trigger.
        triggers = _trigger_path(df, direction, _ENTRY_ROW, exit_row - 1)
        assert triggers[0] != triggers[-1]  # the stop was moved by bar 31's extreme
        assert exit_fill["type"] == "STOP_MARKET"
        assert exit_fill["avg_px"] == pytest.approx(triggers[-1])
        assert stop_orders[0]["trigger_price"] == pytest.approx(triggers[-1])
    elif scenario == "gap":
        # Bar opens through the resting stop: filled at the open, like VectorBT.
        assert exit_fill["type"] == "STOP_MARKET"
        assert exit_fill["avg_px"] == pytest.approx(float(df["open"].iloc[exit_row]))
        assert exit_fill["avg_px"] == pytest.approx(record["exit_price"])
    else:
        # Level ratcheted through the close: market exit at the next bar's
        # opening instant, at the price VectorBT fills (that bar's open).
        assert exit_fill["type"] == "MARKET" and exit_fill["reduce_only"]
        assert exit_fill["ts_last"] == (record["exit_ts"].value + 1)
        assert exit_fill["avg_px"] == pytest.approx(float(df["open"].iloc[exit_row]))
        assert exit_fill["avg_px"] == pytest.approx(record["exit_price"])
        assert stop_orders[0]["status"] == "CANCELED"  # never left resting


@pytest.mark.parametrize("direction", ["long", "short"])
def test_stop_bar_ignores_signals_and_reentry_gets_a_fresh_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, direction: str
) -> None:
    """Entry signals on the stop bar are skipped (VectorBT); the next entry's
    stop is anchored at its own close with its own entry-bar distance."""
    df = _scenario_frame(_PATHS["touch"], direction, tail=6)
    stop_row = _ENTRY_ROW + 2
    entries = [_ENTRY_ROW, stop_row, stop_row + 1]
    captured, summary, result = _run_scenario(
        tmp_path, monkeypatch, df, direction, entries
    )

    records = _vectorbt_records(df, direction, entries, _cfg())
    assert [r["entry_ts"] for r in records] == [
        df["timestamp"].iloc[_ENTRY_ROW],
        df["timestamp"].iloc[stop_row + 1],
    ]
    assert records[0]["exit_row"] == stop_row and not records[1]["closed"]

    fills = _by_fill_time(captured)
    assert len(fills) == 3  # entry, stop exit, re-entry (still open)
    _assert_exit_matches(fills[1], records[0], direction)
    reentry = fills[2]
    assert _fill_bar(reentry["ts_last"]) == df["timestamp"].iloc[stop_row + 1]
    assert reentry["avg_px"] == pytest.approx(float(df["close"].iloc[stop_row + 1]))
    assert summary["trail_exits"] == 1
    assert result.trade_count == 2 and result.open_positions_at_end == 1

    # The second stop rests at the re-entry's own level (fresh anchor and
    # distance), not at the first trade's ratcheted level.
    open_stops = [
        o
        for o in captured["orders"]
        if o["type"] == "STOP_MARKET" and o["filled_qty"] == 0
    ]
    assert len(open_stops) == 1
    expected = _trigger_path(df, direction, stop_row + 1, len(df) - 1)[-1]
    assert open_stops[0]["trigger_price"] == pytest.approx(expected)
    sl_frac = float(stop_distance_frac(df, _cfg()).iloc[stop_row + 1])
    assert sl_frac != pytest.approx(
        float(stop_distance_frac(df, _cfg()).iloc[_ENTRY_ROW])
    )
    assert not math.isclose(expected, fills[1]["avg_px"])
