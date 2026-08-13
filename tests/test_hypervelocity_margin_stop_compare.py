"""Creator-calibrated fixed-margin stop comparison contracts."""

from __future__ import annotations

import importlib
import importlib.util
from dataclasses import replace

import pandas as pd
import pytest

from hypervector.research.maker_replay_models import (
    MakerReplayConfig,
    MakerReplayLifecycle,
    MakerReplayReport,
    MakerReplayTrade,
)

_MODULE = "hypervector.research.hypervelocity_margin_stop_compare"


def _comparison_module() -> object:
    assert importlib.util.find_spec(_MODULE) is not None
    return importlib.import_module(_MODULE)


def _trade(day: int, status: str, net_pnl: float) -> MakerReplayTrade:
    signal = pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(days=day)
    return MakerReplayTrade(
        direction="long",
        signal_time_utc=signal.isoformat(),
        submitted_time_utc=signal.isoformat(),
        entry_time_utc=(signal + pd.Timedelta(seconds=1)).isoformat(),
        exit_time_utc=(signal + pd.Timedelta(minutes=1)).isoformat(),
        entry_price=100.0,
        exit_price=100.2,
        quantity=28.0,
        margin=70.0,
        notional=2_800.0,
        gross_pnl=5.6,
        fees=0.84,
        net_pnl=net_pnl,
        entry_wait_seconds=1.0,
        hold_seconds=59.0,
        status=status,
    )


def _lifecycle(identifier: int, day: int, status: str) -> MakerReplayLifecycle:
    signal = pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(days=day)
    outcome = None if status in {"pending", "open"} else signal.isoformat()
    return MakerReplayLifecycle(
        lifecycle_id=identifier,
        direction="long",
        signal_time_utc=signal.isoformat(),
        submitted_time_utc=signal.isoformat(),
        entry_time_utc=signal.isoformat() if status != "pending" else None,
        outcome_time_utc=outcome,
        status=status,
        entry_price=100.0 if status != "pending" else None,
        exit_price=100.2
        if status in {"target_completed", "stopped", "liquidated"}
        else None,
        quantity=28.0 if status != "pending" else None,
        fees=0.84 if status in {"target_completed", "stopped", "liquidated"} else None,
        net_pnl=1.0
        if status in {"target_completed", "stopped", "liquidated"}
        else None,
    )


def _report() -> MakerReplayReport:
    trades = (
        _trade(1, "target_completed", 4.76),
        _trade(31, "stopped", -8.68),
        _trade(61, "liquidated", -35.0),
    )
    lifecycles = (
        _lifecycle(0, 1, "target_completed"),
        _lifecycle(1, 31, "stopped"),
        _lifecycle(2, 61, "liquidated"),
        _lifecycle(3, 62, "expired"),
    )
    return MakerReplayReport(
        fill_rule="trade-through",
        snapshots=10,
        market_trade_prints=20,
        submitted_entries=4,
        entry_fills=3,
        expired_entries=1,
        canceled_entries=0,
        pending_orders=0,
        completed_trades=3,
        open_positions=0,
        initial_equity=100.0,
        final_equity=61.08,
        submission_times_utc=tuple(row.submitted_time_utc for row in lifecycles),
        trades=trades,
        lifecycles=lifecycles,
        limitations=(),
        liquidations=1,
        stops=1,
        maximum_drawdown_pct=-40.0,
        realized_equity=61.08,
    )


def test_candidate_grid_is_exact_and_predeclared() -> None:
    module = _comparison_module()

    configs = module.margin_stop_candidate_configs(initial_equity=10_000.0)

    assert list(configs) == [
        "no_stop_control",
        "stop_6pct_margin",
        "stop_10pct_margin",
        "stop_14pct_margin",
        "stop_18pct_margin",
    ]
    assert [config.fixed_margin_stop_pct for config in configs.values()] == [
        None,
        6.0,
        10.0,
        14.0,
        18.0,
    ]
    assert all(config.initial_equity == 10_000.0 for config in configs.values())
    assert all(config.fill_rule == "trade-through" for config in configs.values())


def test_tight_stop_candidate_grid_is_exact_and_predeclared() -> None:
    module = _comparison_module()

    configs = module.tight_margin_stop_candidate_configs(initial_equity=10_000.0)

    assert list(configs) == [
        "no_stop_control",
        "stop_2pct_margin",
        "stop_3pct_margin",
        "stop_4pct_margin",
    ]
    assert [config.fixed_margin_stop_pct for config in configs.values()] == [
        None,
        2.0,
        3.0,
        4.0,
    ]
    assert all(config.initial_equity == 10_000.0 for config in configs.values())
    assert all(config.fill_rule == "trade-through" for config in configs.values())
    assert all(
        config.same_direction_reentry_policy == "regime_reset"
        for config in configs.values()
    )


def test_wide_stop_candidate_grid_is_exact_and_predeclared() -> None:
    module = _comparison_module()

    configs = module.wide_margin_stop_candidate_configs(initial_equity=10_000.0)

    assert list(configs) == [
        "no_stop_control",
        "stop_25pct_margin",
        "stop_35pct_margin",
        "stop_45pct_margin",
    ]
    assert [config.fixed_margin_stop_pct for config in configs.values()] == [
        None,
        25.0,
        35.0,
        45.0,
    ]
    assert all(config.initial_equity == 10_000.0 for config in configs.values())
    assert all(config.fill_rule == "trade-through" for config in configs.values())


def test_bounded_target_ladder_replay_grid_is_exact() -> None:
    module = _comparison_module()

    configs = module.bounded_target_ladder_candidate_configs(10_000.0)

    assert list(configs) == [
        "regime_reset_60s",
        "target_ladder_cap2",
        "target_ladder_cap3",
        "target_ladder_cap6",
    ]
    assert [config.same_direction_reentry_policy for config in configs.values()] == [
        "regime_reset",
        "target_continuation",
        "target_continuation",
        "target_continuation",
    ]
    assert [
        config.target_continuation_limit_per_episode for config in configs.values()
    ] == [None, 2, 3, 6]
    assert all(
        config.same_direction_reentry_clearance_bps == 0.0
        for config in configs.values()
    )


def test_mature_target_continuation_replay_grid_is_exact() -> None:
    module = _comparison_module()

    configs = module.mature_target_continuation_candidate_configs(10_000.0)

    assert list(configs) == [
        "regime_reset_60s",
        "target_ladder_cap2",
        "mature_target_ladder_cap2",
    ]
    assert [
        config.target_continuation_minimum_episode_seconds
        for config in configs.values()
    ] == [0.0, 0.0, 1_800.0]


def test_candidate_summary_reports_reentry_assumptions() -> None:
    module = _comparison_module()
    config = MakerReplayConfig(
        initial_equity=100.0,
        same_direction_reentry_policy="target_continuation",
        target_continuation_limit_per_episode=2,
    )

    payload = module.summarize_margin_stop_grid(
        {"target_ladder_cap2": _report()},
        {"target_ladder_cap2": config},
        start=pd.Timestamp("2026-01-01T00:00:00Z"),
        end=pd.Timestamp("2026-04-01T00:00:00Z"),
    )

    candidate = payload["candidates"]["target_ladder_cap2"]
    assert candidate["same_direction_reentry_policy"] == "target_continuation"
    assert candidate["same_direction_reentry_clearance_bps"] == 0.0
    assert candidate["target_continuation_limit_per_episode"] == 2
    assert candidate["target_continuation_minimum_episode_seconds"] == 0.0


def test_break_even_stop_includes_maker_and_taker_fees() -> None:
    module = _comparison_module()

    result = module.break_even_gross_margin_stop_pct(
        win_rate=0.70,
        target_margin_pct=8.0,
        leverage=40.0,
        maker_fee_rate=0.00015,
        taker_fee_rate=0.00045,
    )

    assert result == pytest.approx(13.4666666667)


def test_summary_retains_statuses_and_chronological_slices() -> None:
    module = _comparison_module()
    config = MakerReplayConfig(
        initial_equity=100.0,
        fill_rule="trade-through",
        fixed_margin_stop_pct=10.0,
    )

    payload = module.summarize_margin_stop_grid(
        {"stop_10pct_margin": _report()},
        {"stop_10pct_margin": config},
        start=pd.Timestamp("2026-01-01T00:00:00Z"),
        end=pd.Timestamp("2026-04-01T00:00:00Z"),
        segment_days=30,
    )

    candidate = payload["candidates"]["stop_10pct_margin"]
    assert candidate["status_counts"] == {
        "target_completed": 1,
        "stopped": 1,
        "liquidated": 1,
        "expired": 1,
    }
    assert candidate["resolved_target_rate_pct"] == pytest.approx(100.0 / 3.0)
    assert candidate["average_net_pnl_by_status"]["target_completed"] == 4.76
    assert candidate["average_net_pnl_by_status"]["stopped"] == -8.68
    assert candidate["average_net_pnl_by_status"]["liquidated"] == -35.0
    assert [segment["resolved_trades"] for segment in candidate["segments"]] == [
        1,
        1,
        1,
    ]
    assert candidate["segments"][2]["expired_entries"] == 1
    assert candidate["segments"][0]["closed_trade_growth_multiple"] > 1.0
    assert candidate["segments"][1]["closed_trade_growth_multiple"] < 1.0


def test_summary_reports_maximum_hold_and_time_exits() -> None:
    module = _comparison_module()
    base = _report()
    trades = tuple(
        replace(trade, status="time_exited") if trade.status == "stopped" else trade
        for trade in base.trades
    )
    lifecycles = tuple(
        replace(row, status="time_exited") if row.status == "stopped" else row
        for row in base.lifecycles
    )
    report = replace(
        base,
        trades=trades,
        lifecycles=lifecycles,
        stops=0,
        time_exits=1,
    )
    config = MakerReplayConfig(
        initial_equity=100.0,
        fill_rule="trade-through",
        maximum_hold_seconds=21_600.0,
    )

    payload = module.summarize_margin_stop_grid(
        {"max_hold_6h": report},
        {"max_hold_6h": config},
        start=pd.Timestamp("2026-01-01T00:00:00Z"),
        end=pd.Timestamp("2026-04-01T00:00:00Z"),
    )

    candidate = payload["candidates"]["max_hold_6h"]
    assert candidate["maximum_hold_seconds"] == 21_600.0
    assert candidate["status_counts"]["time_exited"] == 1
    assert candidate["average_net_pnl_by_status"]["time_exited"] == -8.68


def test_summary_reports_lifecycle_substitutions_against_control() -> None:
    module = _comparison_module()
    control = _report()
    candidate_lifecycles = (
        replace(control.lifecycles[0], status="time_exited"),
        control.lifecycles[1],
        _lifecycle(4, 70, "target_completed"),
    )
    candidate = replace(control, lifecycles=candidate_lifecycles)
    configs = {
        "no_timeout_control": MakerReplayConfig(initial_equity=100.0),
        "max_hold_6h": MakerReplayConfig(
            initial_equity=100.0,
            maximum_hold_seconds=21_600.0,
        ),
    }

    payload = module.summarize_margin_stop_grid(
        {"no_timeout_control": control, "max_hold_6h": candidate},
        configs,
        start=pd.Timestamp("2026-01-01T00:00:00Z"),
        end=pd.Timestamp("2026-04-01T00:00:00Z"),
    )

    assert payload["control_candidate"] == "no_timeout_control"
    overlap = payload["candidates"]["max_hold_6h"]["versus_control"]
    assert overlap == {
        "shared_resolved_lifecycles": 2,
        "control_only_resolved_lifecycles": 1,
        "candidate_only_resolved_lifecycles": 1,
        "status_transitions": {
            "stopped->stopped": 1,
            "target_completed->time_exited": 1,
        },
    }
