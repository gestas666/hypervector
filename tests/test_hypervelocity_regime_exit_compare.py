"""Contracts for the opposite-5m-regime exit comparison."""

from __future__ import annotations

from dataclasses import asdict, replace
import importlib
import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from hypervector.research.maker_replay_models import (
    MakerReplayLifecycle,
    MakerReplayReport,
    MakerReplayTrade,
)

_MODULE = "hypervector.research.hypervelocity_regime_exit_compare"


def _comparison_module() -> object:
    return importlib.import_module(_MODULE)


def _script_module() -> ModuleType:
    path = Path("scripts/hypervelocity_regime_exit_compare.py")
    spec = importlib.util.spec_from_file_location("regime_exit_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load regime-exit script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _trade(status: str) -> MakerReplayTrade:
    return MakerReplayTrade(
        "long",
        "2026-01-01T00:00:00+00:00",
        "2026-01-01T00:00:01+00:00",
        "2026-01-01T00:00:02+00:00",
        "2026-01-01T00:10:00+00:00",
        100.0,
        99.5 if status == "regime_exited" else 100.2,
        28.0,
        70.0,
        2_800.0,
        -14.0 if status == "regime_exited" else 5.6,
        0.84,
        -14.84 if status == "regime_exited" else 4.76,
        1.0,
        598.0,
        status,
    )


def _lifecycle(status: str) -> MakerReplayLifecycle:
    return MakerReplayLifecycle(
        0,
        "long",
        "2026-01-01T00:00:00+00:00",
        "2026-01-01T00:00:01+00:00",
        "2026-01-01T00:00:02+00:00",
        "2026-01-01T00:10:00+00:00",
        status,
        100.0,
        99.5 if status == "regime_exited" else 100.2,
        28.0,
        0.84,
        -14.84 if status == "regime_exited" else 4.76,
    )


def _report(status: str) -> MakerReplayReport:
    trade = _trade(status)
    return MakerReplayReport(
        "trade-through",
        10,
        20,
        1,
        1,
        0,
        0,
        0,
        1,
        0,
        10_000.0,
        9_985.16 if status == "regime_exited" else 10_004.76,
        (trade.submitted_time_utc,),
        (trade,),
        (_lifecycle(status),),
        (),
        regime_exits=int(status == "regime_exited"),
    )


def test_candidate_grid_is_exact_and_differs_only_by_exit_flag() -> None:
    module = _comparison_module()

    configs = module.opposite_regime_exit_candidate_configs()

    assert list(configs) == ["tp_only_control", "opposite_5m_structural_exit"]
    control, candidate = configs.values()
    differences = {
        name
        for name, value in asdict(control).items()
        if value != asdict(candidate)[name]
    }
    assert differences == {"opposite_regime_exit"}
    assert control.opposite_regime_exit is False
    assert candidate.opposite_regime_exit is True
    assert control.initial_equity == 10_000.0
    assert control.fill_rule == "trade-through"
    assert control.entry_ttl_seconds == 300.0
    assert control.reentry_cooldown_seconds == 300.0


def test_summary_counts_regime_exit_substitution_and_30_day_slices() -> None:
    module = _comparison_module()
    reports = {
        "tp_only_control": _report("target_completed"),
        "opposite_5m_structural_exit": _report("regime_exited"),
    }

    summary = module.summarize_opposite_regime_exit(
        reports,
        module.opposite_regime_exit_candidate_configs(),
        start=pd.Timestamp("2026-01-01T00:00:00Z"),
        end=pd.Timestamp("2026-02-01T00:00:00Z"),
    )

    candidate = summary["candidates"]["opposite_5m_structural_exit"]
    assert candidate["opposite_regime_exit"] is True
    assert candidate["status_counts"] == {"regime_exited": 1}
    assert len(candidate["segments"]) == 2
    assert candidate["versus_control"]["status_transitions"] == {
        "target_completed->regime_exited": 1
    }


def test_source_compatibility_uses_causal_5m_structure_and_reports_range() -> None:
    module = _comparison_module()
    positions = pd.DataFrame(
        {
            "open_time_utc": ["2026-01-01T00:00:30Z"],
            "close_time_utc": ["2026-01-01T00:04:30Z"],
            "side": ["long"],
            "entry_price": [100.0],
            "status": ["closed"],
        }
    )
    index = pd.date_range("2026-01-01", periods=5, freq="1min", tz="UTC")
    decisions = pd.DataFrame(
        {
            "structural_direction": ["long", None, "short", "short", "short"],
            "state_5m": [
                "TREND_UP",
                "RANGE",
                "TREND_DOWN",
                "TREND_DOWN",
                "TREND_DOWN",
            ],
        },
        index=index,
    )

    result = module.source_regime_exit_compatibility(positions, decisions)

    assert result["logical_positions"] == 1
    assert result["opposite_structure_while_open"] == 1
    assert result["range_observed_while_open"] == 1
    row = result["positions"][0]
    assert row["first_opposite_available_utc"] == "2026-01-01T00:03:00+00:00"
    assert row["candidate_minus_creator_close_seconds"] == -90.0


def test_script_contract_is_observe_only_and_output_is_immutable(
    tmp_path: Path,
) -> None:
    module = _script_module()
    args = module._parser().parse_args(
        [
            "--bars",
            "bars.parquet",
            "--positions",
            "positions.csv",
            "--supplemental-positions",
            "supplemental.csv",
            "--config",
            "configs/hypervelocity_faithful.toml",
            "--start",
            "2026-04-28T00:00:00Z",
            "--end",
            "2026-07-27T00:00:00Z",
            "--price-context",
            "prices.parquet",
            "--funding-context",
            "funding.parquet",
            "--out",
            str(tmp_path / "report.json"),
        ]
    )

    assert module._experiment_contract(args)["report_only"] is True
    assert module._experiment_contract(args)["runtime_strategy_changed"] is False
    assert module._metalabel_policy(args.config) == {
        "mode": "observe",
        "may_filter": False,
        "may_scale": False,
    }
    module._write_immutable_report(args.out, {"ok": True})
    with pytest.raises(FileExistsError, match="output exists"):
        module._write_immutable_report(args.out, {"ok": False})


def test_regime_exit_status_is_retained_by_generic_lifecycle_summary() -> None:
    module = _comparison_module()
    report = _report("regime_exited")
    alternate = replace(report, final_equity=9_900.0)

    summary = module.summarize_opposite_regime_exit(
        {"tp_only_control": report, "opposite_5m_structural_exit": alternate},
        module.opposite_regime_exit_candidate_configs(),
        start=pd.Timestamp("2026-01-01T00:00:00Z"),
        end=pd.Timestamp("2026-01-02T00:00:00Z"),
    )

    assert summary["candidates"]["tp_only_control"]["status_counts"] == {
        "regime_exited": 1
    }
