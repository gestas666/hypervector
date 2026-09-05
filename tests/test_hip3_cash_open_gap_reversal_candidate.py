"""Candidate tests for exact HIP-3 cash-open gap reversal."""

from __future__ import annotations

from dataclasses import replace

import pytest

from hypervector.research.hip3_cash_open_gap_reversal_candidate import (
    evaluate_hip3_cash_open_gap_reversal_development,
    hip3_cash_open_gap_reversal_portfolio_config,
)
from hypervector.research.hip3_cash_open_gap_reversal_signals import (
    Hip3CashOpenGapReversalConfig,
)
from hip3_cash_open_gap_reversal_fixtures import archive_bars, execution


def test_portfolio_contract_matches_frozen_growth_sizing_and_exit_ceiling() -> None:
    """Map the 80-bps stop and 25 bars into the exact $5K contract."""
    nominal = hip3_cash_open_gap_reversal_portfolio_config(
        execution("xyz:SPCX"), Hip3CashOpenGapReversalConfig(), stress=False
    )
    stress = hip3_cash_open_gap_reversal_portfolio_config(
        execution("xyz:SPCX"), Hip3CashOpenGapReversalConfig(), stress=True
    )
    assert nominal.initial_equity == 5000.0
    assert nominal.margin_fraction == 0.1
    assert nominal.leverage == 10.0
    assert nominal.max_hold_bars == 25
    assert nominal.max_hold_seconds == 22_500
    assert nominal.maximum_stop_distance_bps == 80.0
    assert nominal.open_bid_column == "entry_bid"
    assert nominal.risk_low_column == "risk_low"
    assert stress.entry_slippage_bps == 2.0


def test_mu_transfer_requires_its_exact_preregistered_notional() -> None:
    """Permit only the frozen two-thousand-dollar MU transfer contract."""
    mu_execution = replace(execution("xyz:MU"), notional_usd=2000.0)

    portfolio = hip3_cash_open_gap_reversal_portfolio_config(
        mu_execution, Hip3CashOpenGapReversalConfig(), stress=True
    )

    assert portfolio.symbol == "xyz:MU"
    assert portfolio.margin_fraction == 0.04
    with pytest.raises(ValueError, match="frozen notional"):
        hip3_cash_open_gap_reversal_portfolio_config(
            execution("xyz:MU"), Hip3CashOpenGapReversalConfig(), stress=False
        )


def test_development_replay_is_both_side_and_future_invariant() -> None:
    """Consume only development and preserve validation/holdout sealing."""
    bars, windows = archive_bars()
    result = evaluate_hip3_cash_open_gap_reversal_development(
        bars, execution(), windows=windows
    )
    changed = bars.copy()
    later = changed.index >= windows.development_end_utc
    changed.loc[
        later, ["signal_open", "signal_high", "signal_low", "signal_close"]
    ] *= 2.0
    comparison = evaluate_hip3_cash_open_gap_reversal_development(
        changed, execution(), windows=windows
    )
    directions = {trade.direction for trade in result.development.nominal.trades}
    assert result.development == comparison.development
    assert result.folds == comparison.folds
    assert directions == {"long", "short"}
    assert result.proposed_provider_id.endswith("bidirectional_15m_research_v1")
    assert result.out_of_sample_economics == "WITHHELD_NOT_EVALUATED"
    assert result.execution_authority == "none"
