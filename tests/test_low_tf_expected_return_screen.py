"""Tests for serialized expected-return screening under realistic friction."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.low_tf_expected_return_screen import (
    ExpectedReturnScreenConfig,
    screen_low_tf_expected_returns,
)


def _pair(
    signal: str,
    *,
    long_prediction: float,
    short_prediction: float,
    long_gross_bps: float,
    short_gross_bps: float,
    minutes_held: int = 10,
) -> list[dict[str, object]]:
    signal_at = pd.Timestamp(signal, tz="UTC")
    outcome_at = signal_at + pd.Timedelta(minutes=minutes_held)
    values = (
        ("long", long_prediction, long_gross_bps),
        ("short", short_prediction, short_gross_bps),
    )
    return [
        {
            "signal_ts_ms": int(signal_at.timestamp() * 1_000),
            "outcome_ts_ms": int(outcome_at.timestamp() * 1_000),
            "side": side,
            "candidate": "ridge_return",
            "predicted_gross_return_bps": prediction,
            "gross_return_bps": gross,
            "status": "target" if gross > 0.0 else "stop",
            "ambiguous": False,
        }
        for side, prediction, gross in values
    ]


def test_expected_return_screen_applies_nominal_and_stress_costs() -> None:
    """Each cost surface must hurdle and debit the same round-trip friction."""
    rows = _pair(
        "2026-01-01 00:00",
        long_prediction=30.0,
        short_prediction=2.0,
        long_gross_bps=25.0,
        short_gross_bps=-18.0,
    )
    config = ExpectedReturnScreenConfig(
        candidates=("ridge_return",),
        round_trip_costs_bps=(13.0, 20.0),
    )

    report = screen_low_tf_expected_returns(pd.DataFrame(rows), config)

    assert [trial.trade_count for trial in report.trials] == [1, 1]
    assert [trial.net_pnl_bps for trial in report.trials] == pytest.approx([12.0, 5.0])
    assert [trial.total_cost_bps for trial in report.trials] == pytest.approx(
        [13.0, 20.0]
    )


def test_expected_return_screen_serializes_and_hurdles_signals() -> None:
    """Below-hurdle and occupied signals must not become overlapping trades."""
    rows = _pair(
        "2026-01-01 00:00",
        long_prediction=18.0,
        short_prediction=1.0,
        long_gross_bps=25.0,
        short_gross_bps=-18.0,
        minutes_held=15,
    )
    rows += _pair(
        "2026-01-01 00:05",
        long_prediction=1.0,
        short_prediction=22.0,
        long_gross_bps=-18.0,
        short_gross_bps=25.0,
    )
    rows += _pair(
        "2026-01-01 00:15",
        long_prediction=8.0,
        short_prediction=7.0,
        long_gross_bps=25.0,
        short_gross_bps=-18.0,
    )
    config = ExpectedReturnScreenConfig(
        candidates=("ridge_return",),
        round_trip_costs_bps=(13.0,),
    )

    trial = screen_low_tf_expected_returns(pd.DataFrame(rows), config).trials[0]

    assert [trade.side for trade in trial.trades] == ["long"]
    assert trial.expired_occupied_signals == 1
    assert trial.below_hurdle_signals == 1


def test_expected_return_screen_rejects_ties_and_denies_authority() -> None:
    """Equal forecasts are no-trade and the report can never place orders."""
    rows = _pair(
        "2026-01-01 00:00",
        long_prediction=20.0,
        short_prediction=20.0,
        long_gross_bps=25.0,
        short_gross_bps=25.0,
    )
    config = ExpectedReturnScreenConfig(
        candidates=("ridge_return",),
        round_trip_costs_bps=(13.0,),
    )

    report = screen_low_tf_expected_returns(pd.DataFrame(rows), config)

    assert report.trials[0].trade_count == 0
    assert report.trials[0].prediction_ties == 1
    assert report.report_only is True
    assert report.execution_authority == "none"
    assert report.place_attempted is False
