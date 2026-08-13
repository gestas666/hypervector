"""Equity-risk sizing and structural bracket calculations for Hulk."""

from __future__ import annotations

from dataclasses import dataclass
import math

from hypervector.live.hulk_smash_live_config import HulkSmashLiveConfig


@dataclass(frozen=True)
class HulkProtectionPlan:
    """One bounded short position size, stop, and target calculation."""

    entry_price: float
    raw_stop_anchor: float
    stop_bps: float
    stop_price: float
    target_price: float
    target_r_multiple: float
    account_equity_usd: float
    configured_risk_usd: float
    requested_notional_usd: float
    actual_stop_risk_usd: float
    notional_basis: str

    def as_payload(self) -> dict[str, object]:
        """Return a JSON-safe pre-order risk decision."""
        return {
            "entry_price": self.entry_price,
            "raw_stop_anchor": self.raw_stop_anchor,
            "stop_bps": self.stop_bps,
            "trigger_price": self.stop_price,
            "target_price": self.target_price,
            "target_r_multiple": self.target_r_multiple,
            "account_equity_usd": self.account_equity_usd,
            "configured_risk_usd": self.configured_risk_usd,
            "requested_notional_usd": self.requested_notional_usd,
            "actual_stop_risk_usd": self.actual_stop_risk_usd,
            "notional_basis": self.notional_basis,
        }


def build_hulk_protection_plan(
    *,
    entry_price: float,
    stop_anchor: float,
    account_equity_usd: float,
    config: HulkSmashLiveConfig,
    position_notional_usd: float | None = None,
) -> HulkProtectionPlan:
    """Size one short from equity risk and a clamped structural stop."""
    entry = _positive(entry_price, "entry_price")
    anchor = _positive(stop_anchor, "stop_anchor")
    equity = _positive(account_equity_usd, "account_equity_usd")
    raw_stop_bps = (anchor / entry - 1.0) * 10_000.0
    stop_bps = min(config.maximum_stop_bps, max(config.minimum_stop_bps, raw_stop_bps))
    stop_fraction = stop_bps / 10_000.0
    configured_risk = equity * config.risk_fraction
    risk_sized_notional = configured_risk / stop_fraction
    if position_notional_usd is None:
        notional = min(
            risk_sized_notional,
            config.max_notional_usd,
            equity * config.leverage,
        )
        basis = "pretrade_risk_sizing"
    else:
        notional = _positive(position_notional_usd, "position_notional_usd")
        basis = "venue_position"
    stop_price = entry * (1.0 + stop_fraction)
    target_price = entry * (1.0 - config.target_r_multiple * stop_fraction)
    if target_price <= 0.0:
        raise ValueError("Hulk target price must remain positive")
    actual_stop_risk = notional * stop_fraction
    portfolio_risk_cap = equity * config.maximum_portfolio_risk_fraction
    if actual_stop_risk > portfolio_risk_cap + 1e-12:
        raise ValueError("Hulk position exceeds configured portfolio risk cap")
    return HulkProtectionPlan(
        entry_price=entry,
        raw_stop_anchor=anchor,
        stop_bps=stop_bps,
        stop_price=stop_price,
        target_price=target_price,
        target_r_multiple=config.target_r_multiple,
        account_equity_usd=equity,
        configured_risk_usd=configured_risk,
        requested_notional_usd=notional,
        actual_stop_risk_usd=actual_stop_risk,
        notional_basis=basis,
    )


def _positive(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{label} must be positive and finite")
    return number
