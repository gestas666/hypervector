"""Phase 2 Nautilus stub — offline load export + config, no network."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.export.phase2 import export_candidate
from hypervector.export.schema import ExportSchemaError
from hypervector.nautilus import (
    build_phase2_stub_config,
    load_strategy_loadout,
)
from hypervector.nautilus.config_stub import phase2_check_report


def _write_phase15_export(root: Path) -> Path:
    return export_candidate(
        root / "exports",
        run_id="stub01",
        meta={
            "symbol": "BTC",
            "timeframe": "1m",
            "track": "downtrend",
            "lookback_days": 30,
            "init_cash": 10_000.0,
            "tp_sl_mode": "atr",
            "exits": {
                "mode": "atr",
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
            },
            "data_provenance": {"sources": {"fixture": 200}},
        },
        params={
            "strategy": "crown_stack_short",
            "bbwp_lookback": 252,
            "bbwp_threshold": 20.0,
            "exit_mode": "atr",
        },
        metrics={
            "net_pnl": -100.0,
            "total_return_pct": -1.0,
            "sharpe": -0.5,
            "trade_count": 10,
        },
        candidate_id="stub_crown",
    )


def test_load_strategy_loadout_from_fixture_export(tmp_path: Path):
    export_dir = _write_phase15_export(tmp_path)
    loadout = load_strategy_loadout(export_dir, strict=True)
    assert loadout.strategy_name == "crown_stack_short"
    assert loadout.role == "downtrend"
    assert loadout.symbol == "BTC"
    assert loadout.timeframe == "1m"
    assert loadout.init_cash == 10_000.0
    assert loadout.exit_mode == "atr"
    assert loadout.exits is not None
    assert loadout.exits["sl_atr_mult"] == 1.5
    assert loadout.costs is not None
    assert loadout.costs["taker_fee"] == 0.00035
    assert loadout.risk is not None
    assert loadout.risk["risk_pct_min"] == 0.01
    assert "bbwp_lookback" in loadout.params
    assert "strategy" not in loadout.params  # identity stripped
    summary = loadout.summary()
    assert summary["has_costs"] is True
    assert "signals are not loadout inputs" in summary["note"]


def test_load_strategy_loadout_rejects_incomplete(tmp_path: Path):
    export_dir = export_candidate(
        tmp_path / "exports",
        run_id="bare",
        meta={"symbol": "BTC", "timeframe": "1m"},
        params={"strategy": "x"},
        metrics={"net_pnl": 0},
        candidate_id="bare",
    )
    with pytest.raises(ExportSchemaError):
        load_strategy_loadout(export_dir, strict=True)


def test_build_phase2_stub_config_offline(tmp_path: Path):
    export_dir = _write_phase15_export(tmp_path)
    data_root = tmp_path / "data"
    stub = build_phase2_stub_config(export_dir, data_root=data_root, strict=True)
    assert stub.execution_mode == "phase2_historical"
    assert stub.paper_live_implemented is False
    assert stub.catalog_path == (data_root / "nautilus" / "backtest").resolve()
    assert stub.log_path == (data_root / "logs" / "nautilus").resolve()
    d = stub.to_dict()
    assert d["loadout"]["strategy_name"] == "crown_stack_short"
    assert d["venue"] == "HYPERLIQUID"
    assert any("paper/live not implemented" in n for n in d["notes"])


def test_phase2_check_report_probes_nautilus(tmp_path: Path):
    export_dir = _write_phase15_export(tmp_path)
    report = phase2_check_report(
        export_dir,
        data_root=tmp_path / "data",
        strict=True,
        probe_nautilus=True,
    )
    assert report["ok"] is True
    assert report["paper_live"]["implemented"] is False
    assert report["paper_live"]["paper_dry_run"]["implemented"] is True
    assert report["paper_live"]["paper_dry_run"]["command"] == "paper-run"
    assert report["paper_live"]["live_submit"]["implemented"] is False
    probe = report["nautilus_probe"]
    assert probe.get("engine_started") is False
    assert probe.get("venue") == "HYPERLIQUID" or "error" in probe
