"""Reporting and disposition tests for BTC subminute absorption."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.btc_subminute_absorption_replay import (
    BtcAbsorptionReplayReport,
)
from hypervector.research.btc_subminute_absorption_reporting import (
    evaluate_btc_absorption_support,
    summarize_btc_absorption_replay,
)


_START = pd.Timestamp("2026-02-01T00:00:00Z")


def _signals(count: int) -> pd.DataFrame:
    """Return hourly synthetic candidate signals."""
    return pd.DataFrame(
        {
            "available_at_utc": pd.date_range(_START, periods=count, freq="h"),
            "event_id": [f"event-{index}" for index in range(count)],
        }
    )


def _trades(values: list[float]) -> pd.DataFrame:
    """Return minimal replay economics for reporting."""
    rows = []
    for index, value in enumerate(values):
        rows.append(
            {
                "event_id": f"event-{index}",
                "exit_time_ms": int(
                    (_START + pd.Timedelta(hours=index + 1)).timestamp() * 1000
                ),
                "exit_reason": (
                    "fixed_target" if value > 0.0 else "protective_stop_proxy"
                ),
                "gross_pnl_usd": value + 1.0,
                "fee_usd": 1.0,
                "funding_usd": 0.0,
                "net_pnl_usd": value,
                "net_return_bps": value * 2.0,
            }
        )
    return pd.DataFrame(rows)


def test_summary_reports_after_cost_concentration_and_rejections() -> None:
    """One summary must retain complete economics and attempt failures."""
    report = BtcAbsorptionReplayReport(
        _trades([10.0, -5.0, 2.0]),
        {"entry_visible_depth_incomplete": 2},
        5,
    )

    summary = summarize_btc_absorption_replay(
        _signals(5), report, "validation", "candidate", "nominal"
    )

    assert summary["signal_count"] == 5
    assert summary["completed_trades"] == 3
    assert summary["wins"] == 2
    assert summary["losses"] == 1
    assert summary["net_pnl_usd"] == pytest.approx(7.0)
    assert summary["profit_factor"] == pytest.approx(12.0 / 5.0)
    assert summary["net_pnl_excluding_largest_winner_usd"] == pytest.approx(-3.0)
    assert summary["entry_capacity_rejections"] == 2
    assert summary["events_per_week"] == pytest.approx(168.0)
    assert summary["execution_authority"] == "none"


def test_support_fails_when_preregistered_trade_and_robustness_gates_fail() -> None:
    """Sparse or largest-winner-dependent evidence must reject without tuning."""
    summaries = []
    for partition in ("validation", "pseudo_holdout"):
        for scenario in (
            "nominal_midpoint_stop_proxy",
            "latency_and_slippage_stress",
            "public_trade_stop_proxy",
        ):
            summaries.extend(
                [
                    {
                        "partition": partition,
                        "arm": "sell_flow_absorption_candidate",
                        "scenario": scenario,
                        "completed_trades": 3,
                        "net_pnl_usd": 7.0,
                        "profit_factor": 2.4,
                        "wins": 2,
                        "net_pnl_excluding_largest_winner_usd": -3.0,
                        "net_expectancy_bps": 4.0,
                        "unreconciled_lifecycle_paths": 0,
                    },
                    {
                        "partition": partition,
                        "arm": "extreme_sell_uptrend_control",
                        "scenario": scenario,
                        "completed_trades": 20,
                        "net_pnl_usd": 20.0,
                        "profit_factor": 1.4,
                        "wins": 12,
                        "net_pnl_excluding_largest_winner_usd": 10.0,
                        "net_expectancy_bps": 5.0,
                        "unreconciled_lifecycle_paths": 0,
                    },
                ]
            )

    result = evaluate_btc_absorption_support(summaries, pd.DataFrame())

    assert result["supported"] is False
    assert "candidate_completed_trades_below_13" in result["failed_requirements"]
    assert (
        "candidate_largest_winner_removal_not_positive" in result["failed_requirements"]
    )
    assert "candidate_expectancy_not_above_control" in result["failed_requirements"]
    assert result["disposition"] == "reject_exact_candidate_without_retuning"
