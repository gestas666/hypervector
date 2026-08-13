"""Account-abstraction-aware parsing for Hyperliquid SOL execution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.live.hyperliquid_protocol import SolAccountSnapshot
from hypervector.live.hyperliquid_sol_parsing import (
    HyperliquidAdapterError,
    mapping,
    nonnegative_number,
    parse_account,
    sequence,
    text,
    validate_address,
)

_LEGACY_MODES = frozenset({"disabled", "dexAbstraction"})
_UNIFIED_MODE = "unifiedAccount"


def require_api_agent_parent(value: object, *, account_address: str) -> None:
    """Require a signer role that delegates from the configured funded account."""
    response = mapping(value, "signing wallet role")
    if response.get("role") != "agent":
        raise HyperliquidAdapterError(
            "signing key must belong to an authorized API agent"
        )
    data = mapping(response.get("data"), "API agent role data")
    parent = validate_address(text(data.get("user"), "API agent parent"))
    expected = validate_address(account_address)
    if parent.lower() != expected.lower():
        raise HyperliquidAdapterError(
            "API agent parent does not match the configured funded wallet"
        )


def parse_account_mode(value: object) -> str:
    """Validate an account-abstraction state returned by the Info API."""
    mode = text(value, "account abstraction state")
    if mode == "portfolioMargin":
        raise HyperliquidAdapterError(
            "portfolio-margin accounts are unsupported by the SOL canary"
        )
    if mode == "default":
        raise HyperliquidAdapterError(
            "default account abstraction is ambiguous; select unified or standard"
        )
    if mode != _UNIFIED_MODE and mode not in _LEGACY_MODES:
        raise HyperliquidAdapterError(f"unsupported account abstraction state: {mode}")
    return mode


def parse_account_for_mode(
    *,
    mode: str,
    perp_state: object,
    spot_state: object | None,
) -> SolAccountSnapshot:
    """Parse legacy or unified account equity without mixing balance models."""
    if mode != _UNIFIED_MODE:
        return parse_account(perp_state)
    if spot_state is None:
        raise HyperliquidAdapterError(
            "unified account requires spot clearinghouse state"
        )
    return _parse_unified_account(perp_state=perp_state, spot_state=spot_state)


def _parse_unified_account(
    *,
    perp_state: object,
    spot_state: object,
) -> SolAccountSnapshot:
    legacy = parse_account(perp_state)
    positions = _position_records(perp_state)
    usdc_total, usdc_hold = _usdc_balance(spot_state)
    margin_used = sum(_position_number(item, "marginUsed") for item in positions)
    notional = sum(_position_number(item, "positionValue") for item in positions)
    return SolAccountSnapshot(
        account_value_usd=usdc_total,
        withdrawable_usd=max(0.0, usdc_total - usdc_hold),
        total_margin_used_usd=margin_used,
        total_notional_position_usd=notional,
        position=legacy.position,
        balance_source="spot_clearinghouse_state",
    )


def _position_records(perp_state: object) -> tuple[Mapping[str, object], ...]:
    state = mapping(perp_state, "clearinghouse state")
    records: list[Mapping[str, object]] = []
    for raw in sequence(state.get("assetPositions"), "asset positions"):
        wrapper = mapping(raw, "asset position")
        records.append(mapping(wrapper.get("position"), "position"))
    return tuple(records)


def _position_number(position: Mapping[str, object], field: str) -> float:
    return nonnegative_number(position.get(field), field)


def _usdc_balance(spot_state: object) -> tuple[float, float]:
    state = mapping(spot_state, "spot clearinghouse state")
    balances = sequence(state.get("balances"), "spot balances")
    matches = [
        item for item in _balance_records(balances) if item.get("coin") == "USDC"
    ]
    if len(matches) != 1:
        raise HyperliquidAdapterError(
            "unified spot state must contain exactly one USDC balance"
        )
    balance = matches[0]
    total = nonnegative_number(balance.get("total"), "USDC total")
    hold = nonnegative_number(balance.get("hold"), "USDC hold")
    if hold > total:
        raise HyperliquidAdapterError("USDC hold exceeds unified USDC total")
    return total, hold


def _balance_records(values: Sequence[object]) -> tuple[Mapping[str, object], ...]:
    return tuple(mapping(value, "spot balance") for value in values)
