"""Accounting and missing-data boundaries for the economic reset report."""

import pandas as pd
import pytest

from strategy_economic_reset import funding_months, validate_performance


def test_accounting_reconciles_across_strategy_identities() -> None:
    """Recorded funding receipts increase net PnL, unlike fees."""
    row = dict(closed_trades=2, gross_market_pnl_usd=-10.0,
               fees_usd=2.0, funding_usd=1.0, net_pnl_usd=-11.0)
    validate_performance({"total": row, "by_strategy": {"test": row}})


@pytest.mark.parametrize("field,value", [("net_pnl_usd", 1.0),
                                         ("fees_usd", float("nan")),
                                         ("closed_trades", True)])
def test_bad_accounting_is_rejected(field: str, value: object) -> None:
    """Malformed or inconsistent economic evidence cannot become success."""
    row = dict(closed_trades=2, gross_market_pnl_usd=-10.0,
               fees_usd=2.0, funding_usd=1.0, net_pnl_usd=-11.0)
    total = {**row, field: value}
    with pytest.raises(ValueError):
        validate_performance({"total": total, "by_strategy": {"test": row}})


def test_complete_month_has_capital_normalized_receipts() -> None:
    """A receipt screen includes all hours and declares its cost assumption."""
    stamps = pd.date_range("2026-02-01", "2026-03-01", inclusive="left",
                           freq="h", tz="UTC")
    frame = pd.DataFrame({"ts": stamps, "fundingRate": 0.00001})
    result = funding_months(frame, notional_fraction=0.5)
    assert result[0]["complete"] is True
    assert result[0]["funding_receipt_on_capital_pct"] == pytest.approx(0.336)
    assert result[0]["after_30bps_allowance_pct"] == pytest.approx(0.186)


def test_missing_hour_is_disclosed_without_a_return() -> None:
    """Incomplete months are retained as missing evidence, never zero-filled."""
    stamps = pd.date_range("2026-02-01", periods=671, freq="h", tz="UTC")
    result = funding_months(pd.DataFrame({"ts": stamps, "fundingRate": 0.0}),
                            notional_fraction=0.5)
    assert result[0]["complete"] is False
    assert "funding_receipt_on_capital_pct" not in result[0]


def test_duplicate_funding_timestamp_is_rejected() -> None:
    """Duplicated settlement rows cannot inflate carry receipts."""
    frame = pd.DataFrame({"ts": ["2026-02-01T00:00Z"] * 2,
                          "fundingRate": [0.01, 0.01]})
    with pytest.raises(ValueError, match="duplicate"):
        funding_months(frame, notional_fraction=0.5)
