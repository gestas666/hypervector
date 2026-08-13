"""Comparison contract for the preregistered HIP-3 early-adverse exit."""

from __future__ import annotations

from dataclasses import replace

import pytest

from hypervector.research.hip3_deployed_lifecycle import (
    Hip3DeployedLifecycleCell,
    Hip3DeployedLifecycleSpec,
)
from hypervector.research.hip3_early_adverse_exit import (
    Hip3ExitPolicyArm,
    build_exit_policy_comparison,
)
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioReport,
    SharedPortfolioTrade,
)


def _trade(net: float, reason: str, direction: str) -> SharedPortfolioTrade:
    return SharedPortfolioTrade(
        signal_name=f"{direction}_entry",
        direction=direction,
        signal_time_utc="2026-01-01T00:00:00+00:00",
        entry_time_utc="2026-01-01T00:15:00+00:00",
        exit_time_utc="2026-01-01T00:30:00+00:00",
        signal_position=0,
        entry_position=1,
        exit_position=2,
        entry_price=100.0,
        exit_price=100.0,
        target_price=None,
        stop_price=99.2,
        liquidation_price=80.0,
        quantity=1.0,
        margin_usd=20.0,
        notional_usd=100.0,
        leverage=5.0,
        gross_pnl_usd=net + 0.1,
        fees_usd=0.1,
        funding_cashflow_usd=0.0,
        net_pnl_usd=net,
        equity_before_usd=500.0,
        equity_after_usd=500.0 + net,
        exit_reason=reason,
        same_bar_ambiguous=False,
    )


def _report(*trades: SharedPortfolioTrade, drawdown: float) -> SharedPortfolioReport:
    pnl = [trade.net_pnl_usd for trade in trades]
    gross_profit = sum(max(value, 0.0) for value in pnl)
    gross_loss = -sum(min(value, 0.0) for value in pnl)
    net = sum(pnl)
    return SharedPortfolioReport(
        initial_equity=500.0,
        final_equity=500.0 + net,
        net_pnl_usd=net,
        return_pct=net / 5.0,
        maximum_drawdown_pct=drawdown,
        completed_trades=len(trades),
        wins=sum(value > 0.0 for value in pnl),
        losses=sum(value < 0.0 for value in pnl),
        gross_profit_usd=gross_profit,
        gross_loss_usd=gross_loss,
        profit_factor=gross_profit / gross_loss if gross_loss else None,
        liquidations=0,
        total_fees_usd=sum(trade.fees_usd for trade in trades),
        funding_cashflow_usd=0.0,
        conflicting_entry_signals=0,
        maximum_concurrent_positions=1,
        forced_end_exits=0,
        barrier_invalidated_entries=0,
        insolvent=False,
        monthly_net_pnl_usd={"2026-01": net},
        limitations=(),
        trades=trades,
    )


def _arm(policy: str, validation: SharedPortfolioReport) -> Hip3ExitPolicyArm:
    baseline = _report(_trade(0.5, "max_hold", "long"), drawdown=-0.1)
    cells = tuple(
        Hip3DeployedLifecycleCell("xyz:SNDK", phase, friction, report, 0, 0)
        for phase, report in (("development", baseline), ("validation", validation))
        for friction in ("nominal", "stress")
    )
    return Hip3ExitPolicyArm(
        Hip3DeployedLifecycleSpec(signal_exit_policy=policy),
        cells,
    )


def test_comparison_reports_repeatability_sides_and_delta_from_ignore() -> None:
    ignored = _report(
        _trade(2.0, "max_hold", "long"),
        _trade(-1.0, "stop", "short"),
        drawdown=-0.4,
    )
    honored = _report(
        _trade(0.2, "signal", "long"),
        _trade(-1.2, "signal", "short"),
        drawdown=-0.6,
    )
    early = _report(
        _trade(1.5, "max_hold", "long"),
        _trade(-0.2, "signal", "short"),
        drawdown=-0.2,
    )

    result = build_exit_policy_comparison(
        {
            "ignore": _arm("ignore", ignored),
            "honor": _arm("honor", honored),
            "early_adverse": _arm("early_adverse", early),
        }
    )

    row = result["results"]["validation"]["nominal"]["early_adverse"]
    assert row["aggregate"]["net_pnl_usd"] == pytest.approx(1.3)
    assert row["aggregate"]["net_pnl_ex_largest_winner_usd"] == pytest.approx(-0.2)
    assert row["aggregate"]["signal_exits"] == 1
    assert row["by_direction"]["long"]["completed_trades"] == 1
    assert row["by_direction"]["short"]["net_pnl_usd"] == -0.2
    delta = result["deltas_vs_ignore"]["validation"]["nominal"]
    assert delta["early_adverse"]["net_pnl_usd"] == pytest.approx(0.3)
    assert result["policy_contracts"]["early_adverse"]["max_age_bars"] == 8


def test_comparison_rejects_policy_identity_or_cell_coverage_drift() -> None:
    report = _report(_trade(0.5, "max_hold", "long"), drawdown=-0.1)
    arms = {
        "ignore": _arm("ignore", report),
        "honor": _arm("honor", report),
        "early_adverse": _arm("early_adverse", report),
    }
    arms["honor"] = replace(
        arms["honor"],
        cells=arms["honor"].cells[:-1],
    )

    with pytest.raises(ValueError, match="identical cell coverage"):
        build_exit_policy_comparison(arms)

    arms["honor"] = _arm("ignore", report)
    with pytest.raises(ValueError, match="policy identity"):
        build_exit_policy_comparison(arms)
