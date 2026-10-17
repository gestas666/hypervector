"""Regression: export validation reports diagnostics once and never leaves partial bundles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.export.phase2 import export_candidate
from hypervector.export.schema import (
    REQUIRED_METRIC_KEYS,
    ExportSchemaError,
    validate_export_dir,
)


def _meta(**extra: object) -> dict:
    base = {
        "symbol": "BTC",
        "timeframe": "1m",
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
        "costs": {"taker_fee": 0.00045, "slippage_bps": 2.0},
        "risk": {"risk_pct_min": 0.01, "risk_pct_max": 0.05},
        "apply_costs": True,
    }
    base.update(extra)
    return base


_METRICS = {key: 0.0 for key in REQUIRED_METRIC_KEYS}


def _write(root: Path, meta: dict, metrics: dict) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    full = {"schema_version": "1", "run_id": "r1", "package_version": "0", **meta}
    (root / "meta.json").write_text(json.dumps(full), encoding="utf-8")
    (root / "params.json").write_text(json.dumps({"strategy": "ma_cross_long"}), encoding="utf-8")
    (root / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    return root


def test_required_metric_keys_mirror_the_sweep_contract() -> None:
    from hypervector.sweep.metrics import REQUIRED_METRIC_KEYS as SWEEP_KEYS

    assert REQUIRED_METRIC_KEYS == SWEEP_KEYS


def test_strict_validation_reports_each_cost_error_once(tmp_path: Path) -> None:
    meta = _meta(costs={"taker_fee": 0.00045})
    bundle = _write(tmp_path / "b", meta, _METRICS)

    with pytest.raises(ExportSchemaError) as caught:
        validate_export_dir(bundle, strict=True)

    assert caught.value.errors.count("meta.costs.slippage_bps missing") == 1


def test_diagnostic_bundle_is_flagged_but_still_loadable(tmp_path: Path) -> None:
    bundle = _write(tmp_path / "diag", _meta(apply_costs=False), {})

    report = validate_export_dir(bundle, strict=True)

    assert report["ok"] is True
    assert report["apply_costs"] is False
    assert report["missing_metric_keys"] == list(REQUIRED_METRIC_KEYS)
    assert any("apply_costs=false" in w for w in report["warnings"])
    assert any("metrics missing" in w for w in report["warnings"])


def test_costed_complete_bundle_has_no_warnings(tmp_path: Path) -> None:
    report = validate_export_dir(_write(tmp_path / "ok", _meta(), _METRICS), strict=True)
    assert report["warnings"] == []
    assert report["missing_metric_keys"] == []


def test_opt_in_requirements_reject_diagnostic_bundles(tmp_path: Path) -> None:
    bundle = _write(tmp_path / "diag", _meta(apply_costs=False), {})

    with pytest.raises(ExportSchemaError, match="apply_costs"):
        validate_export_dir(bundle, require_costed=True)
    with pytest.raises(ExportSchemaError, match="metrics.net_pnl missing"):
        validate_export_dir(bundle, require_metrics=True)


def test_failed_strict_export_leaves_no_partial_bundle(tmp_path: Path) -> None:
    with pytest.raises(ExportSchemaError) as caught:
        export_candidate(
            tmp_path / "exports",
            "run1",
            meta={"symbol": "BTC", "timeframe": "1m"},
            params={"strategy": "ma_cross_long"},
            metrics=_METRICS,
            candidate_id="cand",
            strict=True,
        )

    assert caught.value.path == tmp_path / "exports" / "cand"
    assert not (tmp_path / "exports" / "cand").exists()
    leftovers = list((tmp_path / "exports").iterdir()) if (tmp_path / "exports").exists() else []
    assert leftovers == []


def test_failed_reexport_keeps_the_previous_valid_bundle(tmp_path: Path) -> None:
    out = export_candidate(
        tmp_path / "exports",
        "run1",
        meta=_meta(),
        params={"strategy": "ma_cross_long"},
        metrics={**_METRICS, "net_pnl": 12.5},
        candidate_id="cand",
        strict=True,
    )
    before = {p.name: p.read_bytes() for p in out.iterdir()}

    with pytest.raises(ExportSchemaError):
        export_candidate(
            tmp_path / "exports",
            "run2",
            meta={"symbol": "BTC", "timeframe": "1m"},
            params={"strategy": "ma_cross_long"},
            metrics=_METRICS,
            candidate_id="cand",
            strict=True,
        )

    assert {p.name: p.read_bytes() for p in out.iterdir()} == before
    assert sorted(p.name for p in (tmp_path / "exports").iterdir()) == ["cand"]


def test_successful_reexport_replaces_bundle_files(tmp_path: Path) -> None:
    kwargs = dict(params={"strategy": "ma_cross_long"}, candidate_id="cand", strict=True)
    export_candidate(tmp_path / "exports", "run1", meta=_meta(), metrics={**_METRICS, "net_pnl": 1.0}, **kwargs)
    out = export_candidate(tmp_path / "exports", "run2", meta=_meta(), metrics={**_METRICS, "net_pnl": 2.0}, **kwargs)

    assert json.loads((out / "metrics.json").read_text())["net_pnl"] == 2.0
    assert json.loads((out / "meta.json").read_text())["run_id"] == "run2"
    assert sorted(p.name for p in (tmp_path / "exports").iterdir()) == ["cand"]
