"""Decision/report tests for the frozen BTC sweep-relaxation replay."""

from __future__ import annotations

from dataclasses import replace

import pytest

from hypervector.research.btc_sweep_primary_relaxation_experiment import (
    BtcSweepHistoricalCell,
    build_historical_experiment_report,
    evaluate_frozen_acceptance,
    no_action_summary,
    summarize_replay_report,
)
from hypervector.research.btc_sweep_primary_relaxation_replay import (
    BtcSweepPrimaryRelaxationReplay,
)
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioReport,
    SharedPortfolioTrade,
)


def test_summary_discloses_repeatability_frequency_and_exit_path() -> None:
    """Every predeclared diagnostic must derive from the actual trade stream."""
    trades = (
        _trade(10.0, "target"),
        _trade(5.0, "target", ambiguous=True),
        _trade(-3.0, "stop"),
    )
    report = _report(trades)
    summary = summarize_replay_report(report, signal_count=4, partition_days=7.0)
    assert summary["signal_episodes"] == 4
    assert summary["completed_trades"] == 3
    assert summary["trades_per_week"] == pytest.approx(3.0)
    assert summary["largest_winner_usd"] == 10.0
    assert summary["net_pnl_excluding_largest_winner_usd"] == 2.0
    assert summary["same_bar_ambiguities"] == 1
    assert summary["exit_reasons"] == {"stop": 1, "target": 2}


def test_no_action_is_an_explicit_zero_economic_baseline() -> None:
    """The absence of a route must not be represented as missing data."""
    summary = no_action_summary(91.0)
    assert summary["arm"] == "no_action"
    assert summary["net_pnl_usd"] == 0.0
    assert summary["completed_trades"] == 0
    assert summary["trades_per_week"] == 0.0


def test_frozen_acceptance_passes_only_when_every_registered_gate_passes() -> None:
    """Both validation partitions and both cost scenarios must be repeatable."""
    rows = _passing_rows()
    decision = evaluate_frozen_acceptance(rows)
    assert decision["accepted_for_next_validation_stage"] is True
    assert decision["live_promotion_authorized"] is False
    assert decision["failed_checks"] == []


def test_largest_winner_dependency_rejects_otherwise_positive_candidate() -> None:
    """A positive aggregate cannot override a registered repeatability failure."""
    rows = _passing_rows()
    selected = next(
        row
        for row in rows
        if row["partition"] == "pseudo_holdout"
        and row["scenario"] == "stress"
        and row["arm"] == "candidate"
    )
    selected["net_pnl_excluding_largest_winner_usd"] = -0.01
    decision = evaluate_frozen_acceptance(rows)
    assert decision["accepted_for_next_validation_stage"] is False
    assert (
        "pseudo_holdout_stress_candidate_positive_ex_largest"
        in decision["failed_checks"]
    )


def test_historical_report_contains_every_baseline_delta_and_trade_sidecar() -> None:
    """The immutable payload must account for each partition, cost, and arm."""
    control = _report((_trade(-3.0, "stop"),))
    candidate = _report(
        (_trade(10.0, "target"), _trade(5.0, "target"), _trade(-3.0, "stop"))
    )
    cells = tuple(
        BtcSweepHistoricalCell(
            partition=partition,
            scenario=scenario,
            partition_days=91.0,
            replay=BtcSweepPrimaryRelaxationReplay(
                control=control,
                candidate=candidate,
                control_signal_count=1,
                candidate_signal_count=4,
                slippage_bps_per_taker_side=2.0 if scenario == "nominal" else 5.0,
            ),
        )
        for partition in ("development", "validation", "pseudo_holdout")
        for scenario in ("nominal", "stress")
    )
    result = build_historical_experiment_report(cells)
    assert len(result.report["summary_rows"]) == 18
    assert len(result.report["comparisons"]) == 6
    comparison = result.report["comparisons"][0]
    assert comparison["control_minus_no_action_usd"] == -3.0
    assert comparison["candidate_minus_control_usd"] == 15.0
    assert len(result.trade_rows) == 24
    assert result.report["authority"]["execution_authority"] == "none"
    assert result.report["acceptance"]["live_promotion_authorized"] is False


def _passing_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for partition in ("validation", "pseudo_holdout"):
        for scenario in ("nominal", "stress"):
            rows.append(_acceptance_row(partition, scenario, "control", net=1.0))
            rows.append(_acceptance_row(partition, scenario, "candidate", net=12.0))
    return rows


def _acceptance_row(
    partition: str,
    scenario: str,
    arm: str,
    *,
    net: float,
) -> dict[str, object]:
    return {
        "partition": partition,
        "scenario": scenario,
        "arm": arm,
        "completed_trades": 6,
        "net_pnl_usd": net,
        "profit_factor": 1.5,
        "net_pnl_excluding_largest_winner_usd": net - 1.0,
        "maximum_drawdown_pct": -2.0,
        "liquidations": 0,
    }


def _report(trades: tuple[SharedPortfolioTrade, ...]) -> SharedPortfolioReport:
    profits = [trade.net_pnl_usd for trade in trades if trade.net_pnl_usd > 0.0]
    losses = [-trade.net_pnl_usd for trade in trades if trade.net_pnl_usd <= 0.0]
    net = sum(trade.net_pnl_usd for trade in trades)
    return SharedPortfolioReport(
        initial_equity=5_000.0,
        final_equity=5_000.0 + net,
        net_pnl_usd=net,
        return_pct=net / 50.0,
        maximum_drawdown_pct=-1.0,
        completed_trades=len(trades),
        wins=len(profits),
        losses=len(losses),
        gross_profit_usd=sum(profits),
        gross_loss_usd=sum(losses),
        profit_factor=sum(profits) / sum(losses),
        liquidations=0,
        total_fees_usd=3.0,
        funding_cashflow_usd=0.5,
        conflicting_entry_signals=0,
        maximum_concurrent_positions=1,
        forced_end_exits=0,
        barrier_invalidated_entries=0,
        insolvent=False,
        monthly_net_pnl_usd={"2025-01": net},
        limitations=(),
        trades=trades,
    )


def _trade(
    net: float,
    reason: str,
    *,
    ambiguous: bool = False,
) -> SharedPortfolioTrade:
    base = SharedPortfolioTrade(
        signal_name="candidate",
        direction="long",
        signal_time_utc="2025-01-01T00:00:00+00:00",
        entry_time_utc="2025-01-01T00:01:00+00:00",
        exit_time_utc="2025-01-01T01:00:00+00:00",
        signal_position=0,
        entry_position=1,
        exit_position=60,
        entry_price=100.0,
        exit_price=100.0,
        target_price=100.6,
        stop_price=99.4,
        liquidation_price=91.0,
        quantity=1.0,
        margin_usd=500.0,
        notional_usd=5_000.0,
        leverage=10.0,
        gross_pnl_usd=net,
        fees_usd=0.0,
        funding_cashflow_usd=0.0,
        net_pnl_usd=net,
        equity_before_usd=5_000.0,
        equity_after_usd=5_000.0 + net,
        exit_reason="target",
        same_bar_ambiguous=ambiguous,
    )
    return replace(base, exit_reason=reason)
