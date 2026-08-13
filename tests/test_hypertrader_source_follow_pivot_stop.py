"""Contracts for the report-only source-follow confirmed-pivot stop screen."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_source_follow_pivot_stop.py")
    spec = importlib.util.spec_from_file_location("source_follow_pivot_stop", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load pivot-stop script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_follow_pivot_stop_command_exists() -> None:
    assert Path("scripts/hypervelocity_source_follow_pivot_stop.py").is_file()


def test_parser_requires_frozen_artifact_candles_and_output() -> None:
    module = _load_script()

    args = module._parser().parse_args(
        [
            "--source-artifact",
            "leader.json",
            "--candles",
            "development.parquet",
            "--candles",
            "fresh.parquet",
            "--out",
            "screen.json",
        ]
    )

    assert args.source_artifact == Path("leader.json")
    assert args.candles == [Path("development.parquet"), Path("fresh.parquet")]
    assert args.pivot_left_bars == 2
    assert args.pivot_right_bars == 2
    assert args.pivot_buffer_bps == 0.0


def test_contract_is_report_only_and_changes_no_entry_policy() -> None:
    module = _load_script()

    contract = module._experiment_contract()

    assert contract == {
        "candidate": "source_follow_confirmed_pivot_stop",
        "report_only": True,
        "runtime_strategy_changed": False,
        "model_authority": "observe",
        "entry_policy_changed": False,
        "stop_kind": "confirmed_strict_pivot",
        "pivot_left_bars": 2,
        "pivot_right_bars": 2,
        "pivot_buffer_bps": 0.0,
        "stateful_replay_performed": False,
    }


def test_source_payload_rejects_nonleader_or_runtime_artifact() -> None:
    module = _load_script()

    with pytest.raises(ValueError, match="source-follow-only"):
        module._validate_source_payload(
            {
                "candidate_family": "source-fade-only",
                "report_only": True,
                "runtime_strategy_changed": False,
                "stop_policy": "none",
            }
        )
    with pytest.raises(ValueError, match="report-only"):
        module._validate_source_payload(
            {
                "candidate_family": "source-follow-only",
                "report_only": False,
                "runtime_strategy_changed": False,
                "stop_policy": "none",
            }
        )


def test_source_payload_accepts_all_day_range_challenger() -> None:
    module = _load_script()

    module._validate_source_payload(
        {
            "candidate_family": "source-follow-all-day",
            "report_only": True,
            "runtime_strategy_changed": False,
            "stop_policy": "none",
            "fill_rule": "trade-through",
            "entry_ttl_seconds": 60.0,
            "initial_equity": 10_000.0,
            "allocation_fraction": 0.70,
            "leverage": 40.0,
            "gross_margin_target_pct": 8.0,
            "maximum_signal_range_bps": 40.0,
        }
    )


def test_qualification_requires_better_development_and_preserved_fresh_target() -> None:
    module = _load_script()
    improved = {
        "original_net_pnl_usd": 100.0,
        "counterfactual_net_pnl_usd": 120.0,
        "target_stop_regret": 0,
        "filled_lifecycles": 30,
    }
    fresh = {
        "original_net_pnl_usd": 10.0,
        "counterfactual_net_pnl_usd": 10.0,
        "target_stop_regret": 0,
        "filled_lifecycles": 1,
    }

    assert module._qualification(improved, fresh)["qualified"] is True
    assert (
        module._qualification({**improved, "counterfactual_net_pnl_usd": 99.0}, fresh)[
            "qualified"
        ]
        is False
    )
    assert (
        module._qualification(improved, {**fresh, "target_stop_regret": 1})["qualified"]
        is False
    )


def test_main_writes_immutable_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    output = tmp_path / "screen.json"
    monkeypatch.setattr(
        module,
        "_report",
        lambda _args: {"report_only": True, "qualified": False},
        raising=False,
    )
    argv = [
        "--source-artifact",
        "leader.json",
        "--candles",
        "bars.parquet",
        "--out",
        str(output),
    ]

    assert module.main(argv) == 0
    assert output.is_file()
    assert module.main(argv) == 1
