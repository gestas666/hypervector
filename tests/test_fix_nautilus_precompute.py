"""Precomputed signals replace per-bar window rebuilds without changing decisions."""

from __future__ import annotations

import functools
import json
import time
from pathlib import Path

import pandas as pd
import pytest

import hypervector.nautilus.runner as runner_mod
from hypervector.nautilus.actor import _bar_ohlcv_record, _bars_to_ohlcv_df
from hypervector.nautilus.bars import dataframe_to_bars, synthetic_btc_perp_instrument
from hypervector.nautilus.errors import Phase2TechnicalFailure
from hypervector.nautilus.runner import run_phase2_backtest
from nautilus_fix_support import (
    FIXTEST_LOOKAHEAD,
    capture_engine,
    register_fix_strategies,
    synth_ohlcv,
    write_export,
)


@pytest.fixture(autouse=True)
def _strategies() -> None:
    register_fix_strategies()


def _fills(captured: dict) -> list[tuple]:
    return [
        (o["side"], o["type"], o["status"], o["ts_init"], o["quantity"], o["avg_px"])
        for o in captured["orders"]
    ]


def _short_window(monkeypatch: pytest.MonkeyPatch, max_lookback: int) -> None:
    """Shrink the actor window so a short replay exercises window sliding."""
    monkeypatch.setattr(
        runner_mod,
        "config_from_loadout",
        functools.partial(runner_mod.config_from_loadout, max_lookback=max_lookback),
    )


@pytest.mark.parametrize(
    ("strategy", "exit_mode", "params"),
    [
        ("test_sma_cross_long", "fixed_rr", {"fast": 5, "slow": 20}),
        ("test_sma_cross_long", "trail", {"fast": 10, "slow": 30}),
        ("test_sma_cross_short", "atr", {}),
    ],
)
def test_precomputed_matches_windowed_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    strategy: str,
    exit_mode: str,
    params: dict,
) -> None:
    _short_window(monkeypatch, 300)
    export_dir = write_export(
        tmp_path, strategy=strategy, exit_mode=exit_mode, params=params
    )
    df = synth_ohlcv(900, seed=3)
    runs = {}
    for mode in ("windowed", "precomputed"):
        captured = capture_engine(monkeypatch)
        result = run_phase2_backtest(
            export_dir=export_dir,
            data_root=tmp_path / mode,
            ohlcv=df,
            signal_mode=mode,
        )
        runs[mode] = (
            result,
            _fills(captured),
            json.loads(result.report_path.read_text()),
        )
    (w_res, w_fills, w_sum), (p_res, p_fills, p_sum) = (
        runs["windowed"],
        runs["precomputed"],
    )
    assert w_fills == p_fills
    assert w_res.orders_count == p_res.orders_count
    assert w_res.trade_count == p_res.trade_count
    assert w_res.pnl == p_res.pnl
    assert w_sum["signal_mode_used"] == "windowed"
    assert w_sum["signal_semantics"] == "rolling_window_live_parity"
    assert p_sum["signal_mode_used"] == "precomputed"
    assert p_sum["signal_semantics"] == "full_frame_research_parity"
    assert p_sum["causal_probe"]["mismatches"] == 0
    assert p_sum["causal_probe"]["sampled"] > 10


def test_auto_mode_uses_precomputed_for_causal_builders(tmp_path: Path) -> None:
    result = run_phase2_backtest(
        export_dir=write_export(tmp_path),
        data_root=tmp_path / "data",
        ohlcv=synth_ohlcv(300),
    )
    summary = json.loads(result.report_path.read_text())
    assert summary["signal_mode"] == "auto"
    assert summary["signal_mode_used"] == "precomputed"
    assert result.signal_mode == "precomputed"


def test_lookahead_builder_falls_back_to_windowed_in_auto(tmp_path: Path) -> None:
    export_dir = write_export(tmp_path, strategy=FIXTEST_LOOKAHEAD)
    result = run_phase2_backtest(
        export_dir=export_dir, data_root=tmp_path / "data", ohlcv=synth_ohlcv(300)
    )
    summary = json.loads(result.report_path.read_text())
    assert summary["signal_mode_used"] == "windowed"
    assert summary["signal_fallback_reason"] == "causal_probe_mismatch"
    assert summary["causal_probe"]["mismatches"] > 0


def test_lookahead_builder_fails_when_precompute_is_required(tmp_path: Path) -> None:
    export_dir = write_export(tmp_path, strategy=FIXTEST_LOOKAHEAD)
    with pytest.raises(Phase2TechnicalFailure, match="disagree with the windowed"):
        run_phase2_backtest(
            export_dir=export_dir,
            data_root=tmp_path / "data",
            ohlcv=synth_ohlcv(300),
            signal_mode="precomputed",
        )


def test_invalid_signal_mode_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="signal_mode"):
        run_phase2_backtest(
            export_dir=write_export(tmp_path),
            data_root=tmp_path / "data",
            ohlcv=synth_ohlcv(50),
            signal_mode="fast",  # type: ignore[arg-type]
        )


def test_long_replay_runs_within_budget(tmp_path: Path) -> None:
    """6,000 x 15m bars (62 days): the per-bar rebuild path took minutes."""
    export_dir = write_export(
        tmp_path,
        strategy="test_sma_cross_long",
        exit_mode="trail",
        params={"bbwp_lookback": 50, "bbwp_threshold": 50.0},
    )
    df = synth_ohlcv(6_000, seed=5)
    started = time.perf_counter()
    result = run_phase2_backtest(
        export_dir=export_dir, data_root=tmp_path / "data", ohlcv=df
    )
    elapsed = time.perf_counter() - started
    assert result.signal_mode == "precomputed"
    assert json.loads(result.report_path.read_text())["bars"] == 6_000
    assert elapsed < 60.0, f"6,000-bar replay took {elapsed:.1f}s"


def test_column_built_window_frame_is_identical_to_dict_frame() -> None:
    df = synth_ohlcv(50)
    bars = dataframe_to_bars(
        df,
        "BTC-PERP.HYPERLIQUID-15-MINUTE-LAST-EXTERNAL",
        synthetic_btc_perp_instrument(),
    )
    records = [_bar_ohlcv_record(b, label_offset_ns=900_000_000_000) for b in bars]
    legacy = (
        pd.DataFrame(records)
        .set_index("timestamp")
        .loc[:, ["open", "high", "low", "close", "volume"]]
        .astype(float)
    )
    pd.testing.assert_frame_equal(_bars_to_ohlcv_df(records), legacy, check_exact=True)
