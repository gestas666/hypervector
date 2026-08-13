"""Economic reporting tests for the five-minute sweep challenger."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.liquidity_sweep_reporting import (
    summarize_liquidity_sweep_outcomes,
)


def test_summary_reports_sampled_mtm_and_largest_winner_sensitivity() -> None:
    """Decision output includes path risk, not only closed-trade arithmetic."""
    outcomes = pd.DataFrame(
        {
            "arm": ["arm", "arm"],
            "symbol": ["BTC", "BTC"],
            "side": ["long", "long"],
            "context_15m": ["RANGE", "RANGE"],
            "outcome_time_utc": pd.to_datetime(
                ["2026-01-01 01:00Z", "2026-01-01 02:00Z"]
            ),
            "accepted": [True, True],
            "status": ["target", "stop"],
            "net_return_bps_nominal": [30.0, -10.0],
            "net_return_bps_stress": [23.0, -17.0],
            "sampled_mtm_peak_bps": [35.0, 2.0],
            "sampled_mtm_trough_bps": [-5.0, -12.0],
            "sampled_mtm_maximum_drawdown_bps": [5.0, 14.0],
            "maximum_adverse_excursion_bps": [5.0, 12.0],
            "maximum_favorable_excursion_bps": [35.0, 2.0],
            "hold_minutes": [30.0, 15.0],
        }
    )

    summary = summarize_liquidity_sweep_outcomes(outcomes)
    row = summary.loc[summary["scope"].eq("arm") & summary["cost"].eq("nominal")].iloc[
        0
    ]

    assert row["net_bps"] == 20.0
    assert row["net_ex_largest_winner_bps"] == -10.0
    assert row["sampled_mtm_maximum_drawdown_bps"] == pytest.approx(17.0)
    assert row["mean_mae_bps"] == pytest.approx(8.5)
    assert row["mean_hold_minutes"] == pytest.approx(22.5)
