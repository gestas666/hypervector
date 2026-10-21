"""Export schema validation — missing files, invalid meta, round-trip write."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.export.phase2 import export_candidate
from hypervector.export.schema import (
    EXPORT_SCHEMA_VERSION,
    ExportSchemaError,
    validate_export_dir,
)


def _phase15_meta(**extra) -> dict:
    base = {
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
        "data_provenance": {"sources": {"fixture": 100}},
    }
    base.update(extra)
    return base


def test_validate_missing_directory(tmp_path: Path):
    with pytest.raises(ExportSchemaError) as ei:
        validate_export_dir(tmp_path / "nope")
    assert "not a directory" in str(ei.value)


def test_validate_missing_files(tmp_path: Path):
    d = tmp_path / "empty"
    d.mkdir()
    with pytest.raises(ExportSchemaError) as ei:
        validate_export_dir(d)
    err = str(ei.value)
    assert "meta.json" in err
    assert "params.json" in err
    assert "metrics.json" in err


def test_validate_invalid_meta_missing_fields(tmp_path: Path):
    d = tmp_path / "partial"
    d.mkdir()
    (d / "meta.json").write_text(json.dumps({"symbol": "BTC"}), encoding="utf-8")
    (d / "params.json").write_text(json.dumps({"strategy": "x"}), encoding="utf-8")
    (d / "metrics.json").write_text(json.dumps({"net_pnl": 0.0}), encoding="utf-8")
    with pytest.raises(ExportSchemaError) as ei:
        validate_export_dir(d)
    msg = str(ei.value)
    assert "schema_version" in msg
    assert "run_id" in msg


def test_validate_invalid_tp_sl_mode(tmp_path: Path):
    out = export_candidate(
        tmp_path / "exports",
        run_id="badmode",
        meta=_phase15_meta(tp_sl_mode="yolo"),
        params={"strategy": "test_sma_cross_short"},
        metrics={"net_pnl": 0.0},
        candidate_id="badmode",
        validate=False,
    )
    with pytest.raises(ExportSchemaError) as ei:
        validate_export_dir(out)
    assert "tp_sl_mode" in str(ei.value)


def test_validate_strict_requires_phase15_fields(tmp_path: Path):
    out = export_candidate(
        tmp_path / "exports",
        run_id="min",
        meta={"symbol": "BTC", "timeframe": "1m"},
        params={"strategy": "test_sma_cross_long"},
        metrics={"net_pnl": 1.0},
        candidate_id="min",
    )
    # non-strict: basic fields only
    report = validate_export_dir(out, strict=False)
    assert report["ok"] is True
    assert report["strategy"] == "test_sma_cross_long"

    with pytest.raises(ExportSchemaError) as ei:
        validate_export_dir(out, strict=True)
    msg = str(ei.value)
    assert "init_cash" in msg
    assert "costs" in msg
    assert "risk" in msg
    assert "tp_sl_mode" in msg
    assert "exits" in msg


def test_export_write_round_trip_validates(tmp_path: Path):
    out = export_candidate(
        tmp_path / "exports",
        run_id="rt01",
        meta=_phase15_meta(),
        params={
            "strategy": "test_sma_cross_short",
            "bbwp_lookback": 252,
            "bbwp_threshold": 20.0,
        },
        metrics={
            "net_pnl": -10.0,
            "total_return_pct": -0.1,
            "sharpe": -1.0,
            "trade_count": 3,
        },
        candidate_id="rt01",
    )
    report = validate_export_dir(out, strict=True)
    assert report["ok"] is True
    assert report["schema_version"] == EXPORT_SCHEMA_VERSION
    assert report["strategy"] == "test_sma_cross_short"
    assert report["run_id"] == "rt01"
    assert report["has_costs"] is True
    assert report["has_risk"] is True
    assert report["tp_sl_mode"] == "atr"
    assert "net_pnl" in report["metric_keys"]

    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["schema_version"] == EXPORT_SCHEMA_VERSION
    assert meta["strategy"] == "test_sma_cross_short"


def test_validate_bad_costs_shape(tmp_path: Path):
    out = export_candidate(
        tmp_path / "exports",
        run_id="bc",
        meta=_phase15_meta(costs={"oops": True}),
        params={"strategy": "x"},
        metrics={"net_pnl": 0},
        candidate_id="bc",
        validate=False,
    )
    with pytest.raises(ExportSchemaError) as ei:
        validate_export_dir(out, strict=True)
    assert "taker_fee" in str(ei.value)
