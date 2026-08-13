"""Tests for freezing the report-only HYPE L2 Ridge observer bundle."""

from __future__ import annotations

import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import numpy as np
import pandas as pd
import pytest

from hypervector.research.hype_entry_l2_features import HYPE_ENTRY_L2_FEATURES

SCRIPT = Path(__file__).parents[1] / "scripts" / "hype_l2_ridge_bundle.py"


def _load_module() -> ModuleType:
    spec = spec_from_file_location("hype_l2_ridge_bundle_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_run_freezes_hash_linked_bundle_without_execution_authority(
    tmp_path: Path,
) -> None:
    module = _load_module()
    paths = _source_files(tmp_path)
    args = module.build_parser().parse_args(
        [
            "--features",
            str(paths["features"]),
            "--development-report",
            str(paths["report"]),
            "--model-plan",
            str(paths["model_plan"]),
            "--materialization-summary",
            str(paths["materialization"]),
            "--bundle-plan-out",
            str(tmp_path / "bundle_plan.json"),
            "--out",
            str(tmp_path / "bundle.json"),
        ]
    )

    result = module.run(args)

    payload = json.loads((tmp_path / "bundle.json").read_text())
    plan = json.loads((tmp_path / "bundle_plan.json").read_text())
    assert payload["contract"]["execution_authority"] == "none"
    assert payload["training"]["rows"] == 40
    assert plan["contract"]["automatic_promotion"] is False
    assert result["bundle"]["sha256"]


def test_run_rejects_an_unsupported_development_candidate(tmp_path: Path) -> None:
    module = _load_module()
    paths = _source_files(tmp_path)
    report = json.loads(paths["report"].read_text())
    report["candidates"]["l2_ridge_return"]["development_supported"] = False
    paths["report"].write_text(json.dumps(report), encoding="utf-8")
    args = module.build_parser().parse_args(
        [
            "--features",
            str(paths["features"]),
            "--development-report",
            str(paths["report"]),
            "--model-plan",
            str(paths["model_plan"]),
            "--materialization-summary",
            str(paths["materialization"]),
            "--bundle-plan-out",
            str(tmp_path / "bundle_plan.json"),
            "--out",
            str(tmp_path / "bundle.json"),
        ]
    )

    with pytest.raises(ValueError, match="not development-supported"):
        module.run(args)


def _source_files(tmp_path: Path) -> dict[str, Path]:
    index = np.arange(40, dtype=float)
    frame = pd.DataFrame(
        {
            **{
                name: np.cos(index / (position + 2.0))
                for position, name in enumerate(HYPE_ENTRY_L2_FEATURES)
            },
            "gross_return_bps": index - 20.0,
            "signal_time_utc": pd.date_range(
                "2026-01-01", periods=40, freq="5min", tz="UTC"
            ),
        }
    )
    paths = {
        "features": tmp_path / "features.parquet",
        "report": tmp_path / "report.json",
        "model_plan": tmp_path / "model_plan.json",
        "materialization": tmp_path / "materialization.json",
    }
    frame.to_parquet(paths["features"], index=False)
    paths["report"].write_text(
        json.dumps(
            {
                "mode": "hype_entry_l2_return_model_development_v1",
                "contract": {
                    "execution_authority": "none",
                    "report_only": True,
                    "runtime_strategy_changed": False,
                    "automatic_promotion": False,
                },
                "forward_candidate": {"candidate": "l2_ridge_return"},
                "candidates": {"l2_ridge_return": {"development_supported": True}},
            }
        ),
        encoding="utf-8",
    )
    paths["model_plan"].write_text(
        json.dumps(
            {
                "mode": "hype_entry_l2_model_predeclared_plan_v3",
                "overrides": {"implementation_parity": {"sampling_interval_ms": 1000}},
            }
        ),
        encoding="utf-8",
    )
    paths["materialization"].write_text(
        json.dumps(
            {
                "mode": "hype_entry_l2_features_development_v1",
                "contract": {"execution_authority": "none"},
                "sampling": {"interval_ms": 1000},
            }
        ),
        encoding="utf-8",
    )
    return paths
