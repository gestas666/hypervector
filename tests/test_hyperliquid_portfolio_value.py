"""Exact portfolio-value tests for the read-only Hyperliquid account observer."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hypervector.live.hyperliquid_portfolio_value import (
    HyperliquidPortfolioValueError,
    HyperliquidPortfolioValueReader,
)


class PortfolioInfo:
    """Return one unified USDC balance, one AAPL spot asset, and one vault."""

    def spot_user_state(self, address: str) -> object:
        """Return exact token-indexed balances for the configured account."""
        del address
        return {
            "balances": [
                {"coin": "USDC", "token": 0, "total": "504.10851149", "hold": "4.88"},
                {"coin": "AAPL", "token": 413, "total": "0.00972", "hold": "0"},
            ]
        }

    def spot_meta(self) -> object:
        """Map the exact AAPL token index to its USDC market."""
        return {
            "tokens": [
                {"name": "USDC", "index": 0},
                {"name": "AAPL", "index": 413},
            ],
            "universe": [
                {"name": "@268", "tokens": [413, 0], "index": 268},
            ],
        }

    def all_mids(self, dex: str = "") -> object:
        """Return the current AAPL/USDC midpoint."""
        del dex
        return {"@268": "304.505"}

    def user_vault_equities(self, address: str) -> object:
        """Return one separately reported vault balance."""
        del address
        return [{"vaultAddress": "0x1", "equity": "1.25"}]


def test_reader_separates_portfolio_value_from_execution_collateral() -> None:
    """Non-USDC spot and vault value must not be mislabeled as USDC collateral."""
    observed_at = datetime(2026, 8, 4, 9, 0, tzinfo=UTC)
    reader = HyperliquidPortfolioValueReader(
        info=PortfolioInfo(),
        account_address="0x1111111111111111111111111111111111111111",
        now_fn=lambda: observed_at,
    )

    snapshot = reader.snapshot()

    assert snapshot.execution_collateral_value_usd == pytest.approx(504.10851149)
    assert snapshot.non_usdc_spot_value_usd == pytest.approx(2.9597886)
    assert snapshot.vault_equity_usd == pytest.approx(1.25)
    assert snapshot.portfolio_value_usd == pytest.approx(508.31830009)
    assert snapshot.observed_at_utc == "2026-08-04T09:00:00+00:00"
    assert snapshot.valuation_source == "spot_midpoints_plus_vault_equity"
    assert snapshot.as_payload()["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "execution_collateral_unchanged": True,
    }


def test_reader_rejects_positive_spot_balance_without_usdc_market() -> None:
    """A partial valuation must fail explicitly instead of looking authoritative."""
    info = PortfolioInfo()
    original = info.spot_meta
    info.spot_meta = lambda: {**original(), "universe": []}  # type: ignore[method-assign]
    reader = HyperliquidPortfolioValueReader(
        info=info,
        account_address="0x1111111111111111111111111111111111111111",
    )

    with pytest.raises(
        HyperliquidPortfolioValueError,
        match="positive AAPL balance has no direct USDC market",
    ):
        reader.snapshot()


def test_reader_rejects_duplicate_usdc_balance() -> None:
    """Ambiguous collateral truth must not be silently summed or selected."""
    info = PortfolioInfo()
    original = info.spot_user_state

    def duplicated(address: str) -> object:
        state = original(address)
        assert isinstance(state, dict)
        return {"balances": [*state["balances"], state["balances"][0]]}

    info.spot_user_state = duplicated  # type: ignore[method-assign]
    reader = HyperliquidPortfolioValueReader(
        info=info,
        account_address="0x1111111111111111111111111111111111111111",
    )

    with pytest.raises(
        HyperliquidPortfolioValueError,
        match="duplicate token index",
    ):
        reader.snapshot()
