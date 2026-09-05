"""Report-contract tests for the crypto bull-participation experiment."""

from __future__ import annotations

from hypervector.research.crypto_bull_participation_experiment import (
    CryptoBullExperimentCell,
    build_crypto_bull_experiment_report,
)
from hypervector.research.crypto_bull_participation_models import (
    CryptoBullPortfolioReport,
    CryptoBullTrade,
)


def test_experiment_publishes_every_losing_or_sparse_registered_cell() -> None:
    """Performance never aborts a technically valid frozen trial."""
    cells = [
        CryptoBullExperimentCell(partition, scenario, _empty(), _empty())
        for partition in ("development", "validation", "pseudo_holdout")
        for scenario in ("nominal", "stress")
    ]

    result = build_crypto_bull_experiment_report(cells)

    assert result.report["authority"]["execution_authority"] == "none"
    assert len(result.report["summary_rows"]) == 18
    assert result.report["acceptance"]["historical_support"] is False
    assert (
        "validation_nominal_net_not_positive"
        in result.report["acceptance"]["failed_checks"]
    )
    assert result.trade_rows == ()


def test_experiment_reports_adjacent_entry_cadence() -> None:
    """Multiple entries produce N-1 interarrival intervals without failure."""
    report = _report_with_two_trades()
    cells = [
        CryptoBullExperimentCell(partition, scenario, report, _empty())
        for partition in ("development", "validation", "pseudo_holdout")
        for scenario in ("nominal", "stress")
    ]

    result = build_crypto_bull_experiment_report(cells)

    first = result.report["summary_rows"][0]
    assert first["entry_cadence"] == {
        "entry_count": 2,
        "median_interarrival_hours": 24.0,
    }


def _empty() -> CryptoBullPortfolioReport:
    return CryptoBullPortfolioReport(
        initial_equity_usd=5_000.0,
        final_equity_usd=5_000.0,
        net_pnl_usd=0.0,
        maximum_drawdown_pct=0.0,
        maximum_concurrent_positions=0,
        maximum_margin_fraction=0.0,
        simultaneous_stop_wave_loss_usd=0.0,
        turnover_usd=0.0,
        exposure_minutes=0,
        available_minutes=1,
        trades=(),
    )


def _report_with_two_trades() -> CryptoBullPortfolioReport:
    trades = (_trade("2026-01-01T00:00:00+00:00"), _trade("2026-01-02T00:00:00+00:00"))
    return CryptoBullPortfolioReport(
        initial_equity_usd=5_000.0,
        final_equity_usd=5_002.0,
        net_pnl_usd=2.0,
        maximum_drawdown_pct=-1.0,
        maximum_concurrent_positions=1,
        maximum_margin_fraction=0.1,
        simultaneous_stop_wave_loss_usd=0.0,
        turnover_usd=400.0,
        exposure_minutes=120,
        available_minutes=2_880,
        trades=trades,
    )


def _trade(entry_time: str) -> CryptoBullTrade:
    return CryptoBullTrade(
        symbol="BTC",
        entry_time_utc=entry_time,
        exit_time_utc=entry_time,
        entry_price=100.0,
        exit_price=101.0,
        quantity=1.0,
        margin_usd=50.0,
        notional_usd=100.0,
        gross_pnl_usd=1.0,
        fees_usd=0.0,
        funding_cashflow_usd=0.0,
        slippage_cost_usd=0.0,
        net_pnl_usd=1.0,
        holding_minutes=60,
        exit_reason="trend_deterioration",
        initial_stop_price=97.0,
        final_stop_price=97.0,
        highest_completed_hour_price=101.0,
        equity_before_usd=5_000.0,
        equity_after_usd=5_001.0,
    )
