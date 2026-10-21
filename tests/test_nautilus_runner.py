"""Phase 2 historical backtest runner — offline (fixture OHLCV, no network)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.data.sources import fixture_ohlcv
from hypervector.export.phase2 import export_candidate
from hypervector.nautilus.load_export import StrategyLoadout
from hypervector.nautilus.runner import (
    Phase2Result,
    _default_leverage,
    run_phase2_backtest,
)
from hypervector.strategies import register_all_strategies


@pytest.fixture(scope="module", autouse=True)
def _register_strategies() -> None:
    register_all_strategies()


def _write_strict_export(
    root: Path,
    *,
    strategy: str = "test_sma_cross_long",
    params: dict | None = None,
) -> Path:
    """Strict Phase 1.5 export for Phase 2 readiness (same pattern as actor tests)."""
    base_params = {
        "strategy": strategy,
        "exit_mode": "fixed_rr",
    }
    if strategy == "test_sma_cross_long":
        base_params.update({"fast": 5, "slow": 20})
    if params:
        base_params.update(params)
    return export_candidate(
        root / "exports",
        run_id="run01",
        meta={
            "symbol": "BTC",
            "timeframe": "1m",
            "track": "uptrend",
            "lookback_days": 30,
            "init_cash": 10_000.0,
            "tp_sl_mode": "fixed_rr",
            "exits": {
                "mode": "fixed_rr",
                "sl_pct": 0.01,
                "rr": 2.0,
                "atr_length": 14,
                "sl_atr_mult": 1.5,
                "trail_atr_mult": 2.0,
            },
            "costs": {
                "taker_fee": 0.00035,
                "slippage_bps": 2.0,
                "funding_rate_8h": 0.0001,
                "minutes_per_funding": 480,
            },
            "risk": {
                "risk_pct_min": 0.01,
                "risk_pct_max": 0.05,
                "default_conviction": 0.5,
                "max_size_frac": 1.0,
            },
            "data_provenance": {"sources": {"fixture": 200}},
        },
        params=base_params,
        metrics={
            "net_pnl": 100.0,
            "total_return_pct": 1.0,
            "sharpe": 0.5,
            "trade_count": 5,
        },
        candidate_id="runner_test",
        strict=True,
    )


def test_run_phase2_backtest_writes_summary_offline(tmp_path: Path) -> None:
    """Engine run with injected fixture OHLCV; never hits network/cache."""
    export_dir = _write_strict_export(tmp_path)
    data_root = tmp_path / "data"
    # ≤500 bars; MA cross fires on wave fixture → non-trivial order path
    ohlcv = fixture_ohlcv(n_bars=300, drift=5.0, wave_period=40)

    result = run_phase2_backtest(
        export_dir=export_dir,
        data_root=data_root,
        ohlcv=ohlcv,
        conviction=0.5,
        max_bars=300,
    )

    assert isinstance(result, Phase2Result)
    assert Path(result.export_dir) == export_dir.resolve()
    assert result.report_path.is_file()
    assert result.report_path.name == "summary.json"
    assert "nautilus" in result.report_path.parts
    assert "backtest" in result.report_path.parts
    assert result.orders_count >= 1
    assert isinstance(result.pnl, float)
    assert isinstance(result.loadout_summary, dict)
    assert result.loadout_summary.get("strategy_name") == "test_sma_cross_long"

    summary = json.loads(result.report_path.read_text())
    assert summary["orders_count"] == result.orders_count
    assert summary["pnl"] == pytest.approx(result.pnl)
    assert summary["execution_mode"] == "phase2_historical"
    assert "loadout" in summary
    assert summary["bars"] <= 300


def test_run_phase2_backtest_creates_data_layout(tmp_path: Path) -> None:
    export_dir = _write_strict_export(tmp_path)
    data_root = tmp_path / "data"
    ohlcv = fixture_ohlcv(n_bars=50, drift=2.0, wave_period=20)

    run_phase2_backtest(
        export_dir=export_dir,
        data_root=data_root,
        ohlcv=ohlcv,
        max_bars=50,
    )

    assert (data_root / "nautilus" / "backtest").is_dir()
    assert (data_root / "cache").is_dir()
    assert (data_root / "exports").is_dir()


def test_sim_leverage_is_the_declared_leverage_else_1x() -> None:
    base = {
        "role": None,
        "params": {},
        "meta": {},
        "costs": None,
        "risk": None,
        "exit_mode": None,
        "exits": None,
        "export_dir": Path("/tmp"),
    }
    declared = StrategyLoadout(strategy_name="test_managed_short", **base)
    ordinary = StrategyLoadout(strategy_name="test_sma_cross_long", **base)

    assert _default_leverage(declared) == 10
    assert _default_leverage(ordinary) == 1


def test_run_phase2_backtest_respects_max_bars(tmp_path: Path) -> None:
    export_dir = _write_strict_export(tmp_path)
    data_root = tmp_path / "data"
    ohlcv = fixture_ohlcv(n_bars=200, drift=5.0, wave_period=40)

    result = run_phase2_backtest(
        export_dir=export_dir,
        data_root=data_root,
        ohlcv=ohlcv,
        max_bars=80,
    )

    summary = json.loads(result.report_path.read_text())
    assert summary["bars"] == 80


def test_strategy_managed_exits_run_without_brackets(tmp_path: Path) -> None:
    export_dir = _write_strict_export(
        tmp_path,
        strategy="test_managed_long",
    )
    result = run_phase2_backtest(
        export_dir=export_dir,
        data_root=tmp_path / "data",
        ohlcv=fixture_ohlcv(n_bars=80, drift=2.0, wave_period=20),
        max_bars=80,
    )

    summary = json.loads(result.report_path.read_text())
    assert summary["data_fidelity"] == "ohlcv_bar"
    assert summary["venue_model"] == "phase2_bar_only"
    assert summary["event_venue_model_gaps"] == ["native_liquidation"]
    assert summary["bracket_same_bar_tp_fills"] is None
    assert summary["margin"]["sim_leverage"] == 10.0
