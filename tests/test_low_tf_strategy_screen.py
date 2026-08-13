"""Tests for the friction-aware low-timeframe strategy screen."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.low_tf_strategy_screen import (
    LowTimeframeScreenConfig,
    LowTimeframeScreenReport,
    screen_low_tf_strategies,
)


def _row(
    signal: str,
    *,
    long_probability: float,
    short_probability: float,
    long_gross_bps: float,
    short_gross_bps: float,
    minutes_held: int = 10,
    long_status: str = "target",
    short_status: str = "stop",
    ambiguous: bool = False,
) -> list[dict[str, object]]:
    signal_at = pd.Timestamp(signal, tz="UTC")
    outcome_at = signal_at + pd.Timedelta(minutes=minutes_held)
    values = (
        ("long", long_probability, long_gross_bps, long_status),
        ("short", short_probability, short_gross_bps, short_status),
    )
    return [
        {
            "signal_ts_ms": int(signal_at.timestamp() * 1_000),
            "outcome_ts_ms": int(outcome_at.timestamp() * 1_000),
            "side": side,
            "candidate": "logistic_l2",
            "prediction": probability,
            "status": status,
            "gross_return_bps": gross,
            "ambiguous": ambiguous,
        }
        for side, probability, gross, status in values
    ]


def _screen(rows: list[dict[str, object]]) -> LowTimeframeScreenReport:
    config = LowTimeframeScreenConfig(
        thresholds=(0.60,),
        candidates=("logistic_l2",),
    )
    return screen_low_tf_strategies(pd.DataFrame(rows), config)


def test_screen_serializes_positions_and_expires_occupied_signals() -> None:
    """A second qualifying signal must expire while the first trade is open."""
    rows = _row(
        "2026-01-01 00:00",
        long_probability=0.80,
        short_probability=0.20,
        long_gross_bps=25.0,
        short_gross_bps=-18.0,
        minutes_held=15,
    )
    rows += _row(
        "2026-01-01 00:05",
        long_probability=0.10,
        short_probability=0.90,
        long_gross_bps=-18.0,
        short_gross_bps=25.0,
    )
    rows += _row(
        "2026-01-01 00:15",
        long_probability=0.10,
        short_probability=0.90,
        long_gross_bps=-18.0,
        short_gross_bps=25.0,
    )

    trial = _screen(rows).trials[0]

    assert [trade.side for trade in trial.trades] == ["long", "short"]
    assert trial.expired_occupied_signals == 1


def test_screen_rejects_probability_ties_as_no_trade() -> None:
    """Equal side probabilities must not receive arbitrary direction."""
    report = _screen(
        _row(
            "2026-01-01 00:00",
            long_probability=0.75,
            short_probability=0.75,
            long_gross_bps=25.0,
            short_gross_bps=25.0,
        )
    )

    assert report.trials[0].trade_count == 0
    assert report.trials[0].probability_ties == 1


def test_screen_subtracts_frozen_maker_and_taker_fees() -> None:
    """Every completed unit-notional trial pays six basis points."""
    report = _screen(
        _row(
            "2026-01-01 00:00",
            long_probability=0.80,
            short_probability=0.20,
            long_gross_bps=25.0,
            short_gross_bps=-18.0,
        )
    )

    trial = report.trials[0]
    assert trial.trades[0].fee_bps == pytest.approx(6.0)
    assert trial.trades[0].net_return_bps == pytest.approx(19.0)
    assert trial.total_fee_bps == pytest.approx(6.0)


def test_screen_attributes_timeout_ambiguity_and_monthly_results() -> None:
    """Non-target outcomes and exit months must remain visible in results."""
    rows = _row(
        "2026-01-31 23:55",
        long_probability=0.90,
        short_probability=0.10,
        long_gross_bps=4.0,
        short_gross_bps=-4.0,
        minutes_held=10,
        long_status="timeout",
    )
    rows += _row(
        "2026-02-01 00:10",
        long_probability=0.90,
        short_probability=0.10,
        long_gross_bps=-18.0,
        short_gross_bps=-18.0,
        long_status="ambiguous_stop_first",
        ambiguous=True,
    )

    trial = _screen(rows).trials[0]

    assert trial.timeout_trades == 1
    assert trial.ambiguous_trades == 1
    assert trial.monthly_net_bps == {"2026-02": pytest.approx(-26.0)}


def test_screen_reports_profit_factor_and_drawdown_from_net_returns() -> None:
    """PF and drawdown must use the same post-fee serialized trade stream."""
    rows = _row(
        "2026-01-01 00:00",
        long_probability=0.80,
        short_probability=0.20,
        long_gross_bps=25.0,
        short_gross_bps=-18.0,
    )
    rows += _row(
        "2026-01-01 00:10",
        long_probability=0.80,
        short_probability=0.20,
        long_gross_bps=-18.0,
        short_gross_bps=25.0,
    )

    trial = _screen(rows).trials[0]

    assert trial.profit_factor == pytest.approx(19.0 / 24.0)
    assert trial.net_pnl_bps == pytest.approx(-5.0)
    assert trial.max_drawdown_bps == pytest.approx(24.0)


def test_screen_uses_none_profit_factor_when_there_are_no_losses() -> None:
    """An all-win sample must not fabricate an infinite numeric PF."""
    report = _screen(
        _row(
            "2026-01-01 00:00",
            long_probability=0.80,
            short_probability=0.20,
            long_gross_bps=25.0,
            short_gross_bps=-18.0,
        )
    )

    assert report.trials[0].profit_factor is None


def test_screen_contract_has_no_execution_authority() -> None:
    """Research screening must explicitly deny any order placement path."""
    report = _screen(
        _row(
            "2026-01-01 00:00",
            long_probability=0.50,
            short_probability=0.40,
            long_gross_bps=25.0,
            short_gross_bps=-18.0,
        )
    )

    assert report.report_only is True
    assert report.execution_authority == "none"
    assert report.place_attempted is False


def test_screen_rejects_duplicate_side_rows() -> None:
    """Duplicate candidate signal sides must fail instead of double counting."""
    rows = _row(
        "2026-01-01 00:00",
        long_probability=0.80,
        short_probability=0.20,
        long_gross_bps=25.0,
        short_gross_bps=-18.0,
    )
    rows.append(rows[0].copy())

    with pytest.raises(ValueError, match="exactly one long and short"):
        _screen(rows)
