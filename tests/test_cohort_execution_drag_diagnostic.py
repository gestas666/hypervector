"""Tests for report-only execution drag diagnostics."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_execution_drag_diagnostic import (
    build_execution_drag_diagnostic,
)


def test_diagnostic_reports_route_drag_without_execution_authority() -> None:
    """Fees and funding must remain attributable to the exact route."""
    report = build_execution_drag_diagnostic(
        [
            _trade(1.0, fees=0.1, funding=-0.01),
            _trade(-0.5, fees=0.1, funding=-0.01),
        ]
    )

    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
        "performance_gate": False,
    }
    total = report["performance"]["total"]
    assert total["execution_cash_drag_usd"] == pytest.approx(0.22)
    assert total[
        "execution_cash_drag_as_pct_of_positive_gross_market_pnl"
    ] == pytest.approx(0.22 / 1.11 * 100.0)
    route = report["performance"]["by_provider_symbol"]["alpha|BTC"]
    assert route["closed_trades"] == 2
    assert route["net_pnl_usd"] == pytest.approx(0.5)


def _trade(net: float, *, fees: float, funding: float) -> dict[str, object]:
    return {
        "strategy_id": "alpha",
        "symbol": "BTC",
        "side": "long",
        "net_pnl_usd": net,
        "entry_margin_used_usd": 10.0,
        "net_return_on_margin_pct": net * 10.0,
        "fees_usd": fees,
        "funding_usd": funding,
    }
