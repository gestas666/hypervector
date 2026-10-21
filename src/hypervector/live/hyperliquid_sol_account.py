"""Account-abstraction and API-agent checks for Hyperliquid execution."""

from __future__ import annotations

from hypervector.live.hyperliquid_sol_parsing import (
    HyperliquidAdapterError,
    mapping,
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
            "portfolio-margin accounts are unsupported by the cohort engine"
        )
    if mode == "default":
        raise HyperliquidAdapterError(
            "default account abstraction is ambiguous; select unified or standard"
        )
    if mode != _UNIFIED_MODE and mode not in _LEGACY_MODES:
        raise HyperliquidAdapterError(f"unsupported account abstraction state: {mode}")
    return mode
