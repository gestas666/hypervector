"""Unified-account contract tests for the read-only SOL venue boundary."""

from __future__ import annotations

import pytest

from hypervector.live.hyperliquid_perp_parsing import (
    parse_account_mode_for_symbol,
)
from hypervector.live.hyperliquid_sol_account import parse_account_for_mode
from hypervector.live.hyperliquid_sol_reader import SolHyperliquidReader


class UnifiedInfo:
    """Return the balance split observed from a unified Hyperliquid account."""

    def meta(self, dex: str = "") -> object:
        """Return frozen SOL venue precision."""
        return {"universe": [{"name": "SOL", "szDecimals": 2, "maxLeverage": 20}]}

    def user_fees(self, address: str) -> object:
        """Return the observed base account fee tier."""
        return {
            "userAddRate": "0.00015",
            "userCrossRate": "0.00045",
            "activeReferralDiscount": "0",
        }

    def all_mids(self, dex: str = "") -> object:
        """Return a deterministic SOL midpoint."""
        return {"SOL": "73.66"}

    def query_user_abstraction_state(self, address: str) -> object:
        """Report that the configured account uses unified collateral."""
        return "unifiedAccount"

    def spot_user_state(self, address: str) -> object:
        """Return the unified USDC source of truth."""
        return {
            "balances": [
                {
                    "coin": "USDC",
                    "token": 0,
                    "hold": "0.0",
                    "total": "153.61038949",
                    "entryNtl": "0.0",
                }
            ]
        }

    def user_state(self, address: str, dex: str = "") -> object:
        """Return the non-authoritative zero perp summary and no exposure."""
        return {
            "assetPositions": [],
            "marginSummary": {
                "accountValue": "0.0",
                "totalMarginUsed": "0.0",
                "totalNtlPos": "0.0",
            },
            "withdrawable": "0.0",
        }


def _open_unified_states() -> tuple[dict[str, object], dict[str, object]]:
    position = {
        "coin": "BTC",
        "szi": "-0.00039",
        "entryPx": "62915.0",
        "liquidationPx": "74539.8594491928",
        "marginUsed": "10.262939",
        "positionValue": "24.54141",
        "unrealizedPnl": "0.39236",
        "leverage": {"type": "isolated", "value": 5},
    }
    perp_state: dict[str, object] = {
        "assetPositions": [{"position": position}],
        "marginSummary": {
            "accountValue": "10.262939",
            "totalMarginUsed": "10.262939",
            "totalNtlPos": "24.54141",
        },
        "withdrawable": "0",
    }
    spot_state: dict[str, object] = {
        "balances": [
            {
                "coin": "USDC",
                "token": 0,
                "hold": "10.262939",
                "total": "503.54133149",
                "entryNtl": "0",
            }
        ]
    }
    return perp_state, spot_state


def test_unified_account_uses_spot_clearinghouse_usdc_as_equity() -> None:
    """A unified account must not be misreported as an empty perp account."""
    reader = SolHyperliquidReader(
        info=UnifiedInfo(),  # type: ignore[arg-type]
        account_address="0x1111111111111111111111111111111111111111",
    )

    account = reader.account_snapshot()

    assert account.account_value_usd == pytest.approx(153.61038949)
    assert account.withdrawable_usd == pytest.approx(153.61038949)
    assert account.position.size_signed == 0.0
    assert account.balance_source == "spot_clearinghouse_state"


def test_sol_unified_equity_does_not_add_position_pnl_twice() -> None:
    """The unified USDC total already includes open-position economics."""
    perp_state, spot_state = _open_unified_states()

    account = parse_account_for_mode(
        mode="unifiedAccount",
        perp_state=perp_state,
        spot_state=spot_state,
    )

    assert account.account_value_usd == pytest.approx(503.54133149)


def test_sol_unified_available_balance_does_not_subtract_margin_twice() -> None:
    """The unified USDC hold already reserves isolated position margin."""
    perp_state, spot_state = _open_unified_states()

    account = parse_account_for_mode(
        mode="unifiedAccount",
        perp_state=perp_state,
        spot_state=spot_state,
    )

    assert account.withdrawable_usd == pytest.approx(493.27839249)


def test_symbol_parser_uses_the_same_unified_balance_contract() -> None:
    """Every symbol adapter must project identical unified account totals."""
    perp_state, spot_state = _open_unified_states()

    account = parse_account_mode_for_symbol(
        mode="unifiedAccount",
        perp_state=perp_state,
        spot_state=spot_state,
        symbol="BTC",
    )

    assert account.account_value_usd == pytest.approx(503.54133149)
    assert account.withdrawable_usd == pytest.approx(493.27839249)


def test_legacy_parsers_identify_the_perp_clearinghouse_source() -> None:
    """Standard accounts must distinguish their authoritative balance model."""
    perp_state, _ = _open_unified_states()

    accounts = (
        parse_account_for_mode(
            mode="disabled",
            perp_state=perp_state,
            spot_state=None,
        ),
        parse_account_mode_for_symbol(
            mode="disabled",
            perp_state=perp_state,
            spot_state=None,
            symbol="BTC",
        ),
    )

    assert all(
        account.balance_source == "perp_clearinghouse_state" for account in accounts
    )


def test_preflight_reports_the_validated_account_abstraction_mode() -> None:
    """Operators must see which balance model supplied live sizing equity."""
    reader = SolHyperliquidReader(
        info=UnifiedInfo(),  # type: ignore[arg-type]
        account_address="0x1111111111111111111111111111111111111111",
    )

    preflight = reader.preflight(expected_max_leverage=20)

    assert preflight.account_abstraction_mode == "unifiedAccount"
