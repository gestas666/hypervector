"""Validated economic events with separate decision, venue and receipt clocks."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


def require_name(value: str, label: str) -> None:
    """Require an explicit nonblank identity without silently stripping it."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a nonblank, unpadded string")


def require_clock(value: int, label: str) -> None:
    """Refuse booleans, fractions and negative clock or sequence values."""
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")


def require_amount(value: Decimal, label: str, *, positive: bool = False) -> None:
    """Accept only explicit finite Decimal amounts, optionally above zero."""
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{label} must be a finite Decimal")
    if positive and value <= 0:
        raise ValueError(f"{label} must be positive")


@dataclass(frozen=True, order=True)
class Stamp:
    """An observation millisecond and explicit order within that millisecond."""

    observed_time_ms: int
    sequence: int

    def __post_init__(self) -> None:
        """Validate both components before this key can order economic events."""
        require_clock(self.observed_time_ms, "observation time")
        require_clock(self.sequence, "observation sequence")


@dataclass(frozen=True)
class FillEvent:
    """An exact executed quantity; fee sign preserves both charges and rebates."""

    fill_id: str
    order_id: str
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    fee_usd: Decimal
    leverage: Decimal
    decision_time_ms: int
    dispatch_time_ms: int
    fill_time_ms: int
    stamp: Stamp
    reduce_only: bool

    def __post_init__(self) -> None:
        """Reject malformed economics or a noncausal decision-to-receipt chain."""
        for value, label in ((self.fill_id, "fill ID"), (self.order_id, "order ID"), (self.symbol, "symbol")):
            require_name(value, label)
        if self.side not in ("buy", "sell") or type(self.reduce_only) is not bool:
            raise ValueError("fill requires buy/sell and an explicit reduce_only bool")
        for label in ("quantity", "price", "leverage"):
            require_amount(getattr(self, label), label, positive=True)
        require_amount(self.fee_usd, "fee")
        clocks = (self.decision_time_ms, self.dispatch_time_ms, self.fill_time_ms)
        for value in clocks:
            require_clock(value, "fill clock")
        if not isinstance(self.stamp, Stamp):
            raise ValueError("fill requires an observation Stamp")
        if not clocks[0] <= clocks[1] <= clocks[2] <= self.stamp.observed_time_ms:
            raise ValueError("fill clocks must follow decision <= dispatch <= fill <= observed")


@dataclass(frozen=True)
class FundingEvent:
    """An explicit signed cash settlement, including late observed funding."""

    event_id: str
    symbol: str
    amount_usd: Decimal
    effective_time_ms: int
    stamp: Stamp

    def __post_init__(self) -> None:
        """Require a causal settlement identity without requiring open exposure."""
        require_name(self.event_id, "funding ID")
        require_name(self.symbol, "funding symbol")
        require_amount(self.amount_usd, "funding")
        require_clock(self.effective_time_ms, "funding effective time")
        if not isinstance(self.stamp, Stamp):
            raise ValueError("funding requires an observation Stamp")
        if self.effective_time_ms > self.stamp.observed_time_ms:
            raise ValueError("funding effective time must not exceed observation")
