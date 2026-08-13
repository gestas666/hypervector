"""Contracts for strict-source opposite-entry close/reverse comparison."""

from __future__ import annotations

from dataclasses import asdict
import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd

from hypervector.research.hypervelocity_close_reverse_compare import (
    aggregate_close_reverse_blocks,
    close_reverse_candidate_configs,
    summarize_close_reverse_grid,
)
from hypervector.research.maker_replay_models import (
    MakerReplayLifecycle,
    MakerReplayReport,
    MakerReplayTrade,
)


def _trade(status: str, net_pnl: float) -> MakerReplayTrade:
    return MakerReplayTrade(
        "long",
        "2026-01-01T00:00:00+00:00",
        "2026-01-01T00:00:01+00:00",
        "2026-01-01T00:00:02+00:00",
        "2026-01-01T00:10:00+00:00",
        100.0,
        99.5,
        28.0,
        70.0,
        2_800.0,
        net_pnl + 0.84,
        0.84,
        net_pnl,
        1.0,
        598.0,
        status,
    )


def _lifecycle(status: str, net_pnl: float) -> MakerReplayLifecycle:
    return MakerReplayLifecycle(
        0,
        "long",
        "2026-01-01T00:00:00+00:00",
        "2026-01-01T00:00:01+00:00",
        "2026-01-01T00:00:02+00:00",
        "2026-01-01T00:10:00+00:00",
        status,
        100.0,
        99.5,
        28.0,
        0.84,
        net_pnl,
    )


def _report(status: str, final_equity: float) -> MakerReplayReport:
    net_pnl = final_equity - 10_000.0
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
        final_equity,
        ("2026-01-01T00:00:01+00:00",),
        (_trade(status, net_pnl),),
        (_lifecycle(status, net_pnl),),
        (),
        liquidations=int(status == "liquidated"),
        close_reversals=int(status == "reversed"),
    )


def _comparison(control_equity: float, candidate_equity: float) -> dict[str, object]:
    reports = {
        "tp_only_strict_source_control": _report("liquidated", control_equity),
        "opposite_entry_close_reverse": _report("reversed", candidate_equity),
    }
    return summarize_close_reverse_grid(
        reports,
        close_reverse_candidate_configs(),
        start=pd.Timestamp("2026-01-01T00:00:00Z"),
        end=pd.Timestamp("2026-01-02T00:00:00Z"),
    )


def _script_module() -> ModuleType:
    path = Path("scripts/hypervelocity_close_reverse_compare.py")
    spec = importlib.util.spec_from_file_location("close_reverse_compare", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load close/reverse script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_candidate_grid_is_exact_and_differs_only_by_close_reverse_flag() -> None:
    configs = close_reverse_candidate_configs()

    assert list(configs) == [
        "tp_only_strict_source_control",
        "opposite_entry_close_reverse",
    ]
    control, candidate = configs.values()
    differences = {
        name
        for name, value in asdict(control).items()
        if value != asdict(candidate)[name]
    }
    assert differences == {"opposite_entry_close_reverse"}
    assert control.opposite_entry_close_reverse is False
    assert candidate.opposite_entry_close_reverse is True
    assert control.reentry_cooldown_seconds == 60.0
    assert control.fill_rule == "trade-through"
    assert control.fixed_margin_stop_pct is None
    assert control.maximum_hold_seconds is None


def test_summary_retains_reversed_status_and_liquidation_substitution() -> None:
    comparison = _comparison(5_000.0, 9_500.0)

    candidate = comparison["candidates"]["opposite_entry_close_reverse"]
    assert candidate["opposite_entry_close_reverse"] is True
    assert candidate["status_counts"] == {"reversed": 1}
    assert candidate["replay"]["close_reversals"] == 1
    assert candidate["versus_control"]["status_transitions"] == {
        "liquidated->reversed": 1
    }


def test_aggregate_uses_reset_block_net_pnl_without_stitching_gaps() -> None:
    aggregate = aggregate_close_reverse_blocks(
        [_comparison(5_000.0, 12_000.0), _comparison(8_000.0, 9_000.0)]
    )

    control = aggregate["candidates"]["tp_only_strict_source_control"]
    candidate = aggregate["candidates"]["opposite_entry_close_reverse"]
    assert aggregate["block_count"] == 2
    assert aggregate["portfolio_paths_stitched_across_gaps"] is False
    assert control["total_net_pnl"] == -7_000.0
    assert candidate["total_net_pnl"] == 1_000.0
    assert candidate["positive_blocks"] == 1
    assert candidate["liquidations"] == 0
    assert candidate["close_reversals"] == 2
    assert candidate["aggregate_development_profitable"] is True


def test_script_parser_requires_explicit_windows_and_observe_only_contract() -> None:
    module = _script_module()
    args = module._parser().parse_args(
        [
            "--bars",
            "bars.parquet",
            "--config",
            "config.toml",
            "--strict-labels",
            "strict.parquet",
            "--strict-metadata",
            "strict.json",
            "--price-context",
            "prices.parquet",
            "--funding-context",
            "funding.parquet",
            "--database",
            "market.duckdb",
            "--creator-evidence",
            "creator.json",
            "--window",
            "2025-08-01T00:00:00Z",
            "2025-09-01T00:00:00Z",
            "--window",
            "2025-10-01T00:00:00Z",
            "2025-11-01T00:00:00Z",
            "--out",
            "report.json",
        ]
    )

    contract = module._experiment_contract(args)
    assert len(args.window) == 2
    assert contract["report_only"] is True
    assert contract["runtime_strategy_changed"] is False
    assert contract["model_authority"] == "observe_only"
    assert contract["portfolio_paths_stitched_across_gaps"] is False
