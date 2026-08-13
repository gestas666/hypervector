"""Economic reporting tests for one-minute order-flow impulse outcomes."""

from __future__ import annotations

import pandas as pd

from hypervector.research.orderflow_impulse_reporting import (
    summarize_orderflow_outcomes,
)


def test_summary_reports_concentration_drawdown_and_direction() -> None:
    """Every arm and side must retain after-cost concentration diagnostics."""
    rows = pd.DataFrame(
        {
            "arm": ["continuation_all"] * 4,
            "symbol": ["BTC"] * 4,
            "side": ["long", "long", "short", "short"],
            "outcome_time_utc": pd.date_range(
                "2026-01-01", periods=4, freq="1h", tz="UTC"
            ),
            "accepted": [True, True, True, False],
            "status": ["target", "stop", "target", "target"],
            "net_return_bps_nominal": [30.0, -20.0, 10.0, 100.0],
            "net_return_bps_stress": [23.0, -27.0, 3.0, 93.0],
        }
    )

    summary = summarize_orderflow_outcomes(rows)
    aggregate = summary.loc[
        summary["scope"].eq("arm")
        & summary["arm"].eq("continuation_all")
        & summary["cost"].eq("nominal")
    ].iloc[0]

    assert aggregate["trades"] == 3
    assert aggregate["net_bps"] == 20.0
    assert aggregate["net_ex_largest_winner_bps"] == -10.0
    assert aggregate["profit_factor"] == 2.0
    assert aggregate["maximum_drawdown_bps"] == 20.0
