"""Tests for the frozen IBIT creation long economic replay."""

from __future__ import annotations

import pandas as pd
import pytest

from btc_ibit_creation_fixtures import ibit_creation_history, ibit_market
from hypervector.research.btc_ibit_creation_replay import (
    evaluate_btc_ibit_creation_long,
)


_BASE_SIGNAL = pd.Timestamp("2026-08-03T12:00:00Z")
_BASE_ENTRY = _BASE_SIGNAL + pd.Timedelta(minutes=1)


def test_replay_enters_next_bar_with_frozen_60_60_24h_economics() -> None:
    """Issuer availability is a close-known pulse filled at the next open."""
    bars = ibit_market(80)
    bars.loc[_BASE_ENTRY, "high"] = 101.0

    result = evaluate_btc_ibit_creation_long(bars, ibit_creation_history(), 2.0)

    assert result.candidate_signal_count == 1
    assert result.candidate_signal_times_utc == (_BASE_SIGNAL.isoformat(),)
    assert result.candidate_report.completed_trades == 1
    trade = result.candidate_report.trades[0]
    assert trade.signal_time_utc == _BASE_SIGNAL.isoformat()
    assert trade.entry_time_utc == _BASE_ENTRY.isoformat()
    assert trade.margin_usd == pytest.approx(500.0)
    assert trade.notional_usd == pytest.approx(5_000.0)
    assert trade.leverage == pytest.approx(10.0)
    assert trade.target_price == pytest.approx(trade.entry_price * 1.006)
    assert trade.stop_price == pytest.approx(trade.entry_price * 0.994)
    assert trade.exit_reason == "target"
    assert result.execution_authority == "none"


def test_replay_reports_all_four_active_arms() -> None:
    """Candidate, causal controls, and unchanged V58 sweep must all run."""
    result = evaluate_btc_ibit_creation_long(
        ibit_market(80), ibit_creation_history(), 2.0
    )

    assert result.candidate_report is not None
    assert result.single_creation_control_report is not None
    assert result.redemption_placebo_report is not None
    assert result.v58_sweep_control_report is not None
    assert result.candidate_signal_count == 1
    assert result.single_creation_signal_count == 1
    assert result.redemption_placebo_signal_count == 0
    assert result.v58_sweep_signal_count == 0


def test_stress_slippage_is_adverse_without_changing_signals() -> None:
    """Execution stress must not select or suppress issuer observations."""
    bars = ibit_market(90)

    nominal = evaluate_btc_ibit_creation_long(bars, ibit_creation_history(), 2.0)
    stress = evaluate_btc_ibit_creation_long(bars, ibit_creation_history(), 5.0)

    assert nominal.candidate_signal_count == stress.candidate_signal_count == 1
    assert nominal.candidate_report.trades[0].exit_reason == "max_hold"
    assert stress.candidate_report.trades[0].exit_reason == "max_hold"
    assert stress.candidate_report.net_pnl_usd < nominal.candidate_report.net_pnl_usd


def test_publication_delay_moves_ibit_pulse_by_exactly_twenty_four_hours() -> None:
    """The frozen delay sensitivity applies before next-bar execution."""
    bars = ibit_market(110)

    result = evaluate_btc_ibit_creation_long(
        bars,
        ibit_creation_history(),
        2.0,
        publication_delay_minutes=1440,
    )

    delayed = _BASE_SIGNAL + pd.Timedelta(days=1)
    assert result.candidate_signal_times_utc == (delayed.isoformat(),)
    assert (
        result.candidate_report.trades[0].entry_time_utc
        == (delayed + pd.Timedelta(minutes=1)).isoformat()
    )
    assert result.publication_delay_minutes == 1440


def test_entry_window_masks_after_publication_delay() -> None:
    """A base pulse before a partition may enter if delayed into the window."""
    bars = ibit_market(110)
    start = pd.Timestamp("2026-08-04T00:00:00Z")
    end = pd.Timestamp("2026-08-05T00:00:00Z")

    result = evaluate_btc_ibit_creation_long(
        bars,
        ibit_creation_history(),
        2.0,
        publication_delay_minutes=1440,
        entry_start_utc=start,
        entry_end_utc=end,
    )

    assert result.candidate_signal_count == 1
    assert result.candidate_signal_times_utc == ("2026-08-04T12:00:00+00:00",)


def test_publication_delay_crossing_explicit_gap_cancels_entry() -> None:
    """A shifted instruction cannot cross a missing-market boundary."""
    bars = ibit_market(110)
    bars.loc[pd.Timestamp("2026-08-04T00:00:00Z"), "gap_before_bars"] = 1

    result = evaluate_btc_ibit_creation_long(
        bars,
        ibit_creation_history(),
        2.0,
        publication_delay_minutes=1440,
    )

    assert result.candidate_signal_count == 0
    assert result.candidate_report.completed_trades == 0
    assert result.candidate_delay_gap_cancellations == 1


def test_replay_requires_exact_funding_and_frozen_delay() -> None:
    """Missing funding or an unregistered delay is a technical failure."""
    bars = ibit_market(80).drop(columns="funding_rate")

    with pytest.raises(ValueError, match="requires exact funding_rate"):
        evaluate_btc_ibit_creation_long(bars, ibit_creation_history(), 2.0)
    with pytest.raises(ValueError, match="zero or 1440 minutes"):
        evaluate_btc_ibit_creation_long(
            ibit_market(80),
            ibit_creation_history(),
            2.0,
            publication_delay_minutes=1,
        )
