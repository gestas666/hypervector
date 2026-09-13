"""Offline unified-account projection with explicit isolated collateral inputs.

This is the account subset consumed by native Hypervector adapters. It does not
infer collateral transfers, charge fees, settle funding or execute liquidations.
Callers must supply qualified collateral and maintenance terms for each position.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Literal, TypedDict

from hypervector.live.perp_venue_identity import parse_perp_venue_identity
from hypervector.research.native_replay_account import (
    REPLAY_DECIMAL_PRECISION,
    ZERO,
    AccountView,
    ReplayPosition,
)
from hypervector.research.native_replay_events import require_amount, require_clock, require_name


class LeverageWire(TypedDict):
    """Native isolated leverage fields consumed by position readers."""

    type: Literal["isolated"]
    value: int
    rawUsd: str


class PositionWire(TypedDict):
    """Exact decimal position fields, serialized only at the SDK boundary."""

    coin: str
    szi: str
    entryPx: str
    positionValue: str
    unrealizedPnl: str
    marginUsed: str
    liquidationPx: str | None
    leverage: LeverageWire


class AssetPositionWire(TypedDict):
    """One native one-way position wrapper."""

    type: Literal["oneWay"]
    position: PositionWire


class MarginSummaryWire(TypedDict):
    """Per-namespace isolated totals, not unified account equity."""

    accountValue: str
    totalNtlPos: str
    totalRawUsd: str
    totalMarginUsed: str


class PerpStateWire(TypedDict):
    """The native clearinghouse subset used by the current account consumers."""

    marginSummary: MarginSummaryWire
    crossMarginSummary: MarginSummaryWire
    crossMaintenanceMarginUsed: str
    withdrawable: str
    time: int
    assetPositions: list[AssetPositionWire]


class SpotBalanceWire(TypedDict):
    """One explicit shared USDC balance and held amount."""

    coin: Literal["USDC"]
    token: Literal[0]
    total: str
    hold: str


class SpotStateWire(TypedDict):
    """Native spot balance projection for a single-collateral USDC replay."""

    balances: list[SpotBalanceWire]


@dataclass(frozen=True)
class MaintenanceTier:
    """One linear maintenance segment, including its exact continuity deduction."""

    lower_notional_usd: Decimal
    rate: Decimal
    deduction_usd: Decimal

    def __post_init__(self) -> None:
        """Validate explicit finite parameters before constructing a schedule."""
        for label in ("lower_notional_usd", "rate", "deduction_usd"):
            require_amount(getattr(self, label), f"maintenance {label}")
        if self.lower_notional_usd < 0 or self.deduction_usd < 0 or not ZERO < self.rate < 1:
            raise ValueError("maintenance terms require nonnegative bounds/deduction and 0 < rate < 1")


@dataclass(frozen=True)
class IsolatedCollateral:
    """Explicit isolated cash after costs/transfers and a complete tier schedule."""

    cash_usd: Decimal
    maintenance_tiers: tuple[MaintenanceTier, ...]

    def __post_init__(self) -> None:
        """Require contiguous, nondecreasing maintenance without inferring terms."""
        require_amount(self.cash_usd, "isolated collateral")
        tiers = self.maintenance_tiers
        if (
            not isinstance(tiers, tuple)
            or not tiers
            or not all(isinstance(t, MaintenanceTier) for t in tiers)
        ):
            raise ValueError("maintenance requires an explicit nonempty tier tuple")
        if tiers[0].lower_notional_usd != 0 or tiers[0].deduction_usd != 0:
            raise ValueError("maintenance schedule must start at zero notional and deduction")
        with localcontext() as context:
            context.prec = REPLAY_DECIMAL_PRECISION
            for prior, current in zip(tiers, tiers[1:]):
                expected = current.lower_notional_usd * (current.rate - prior.rate) + prior.deduction_usd
                if (
                    current.lower_notional_usd <= prior.lower_notional_usd
                    or current.rate < prior.rate
                    or current.deduction_usd != expected
                ):
                    raise ValueError(
                        "maintenance schedule must have increasing bounds and continuous requirements"
                    )


@dataclass(frozen=True)
class UnifiedAccountWire:
    """Fresh adapter-facing objects and explicit positions at maintenance contact."""

    spot_state: SpotStateWire
    perp_states: dict[str, PerpStateWire]
    liquidatable_symbols: tuple[str, ...]


def project_unified_account(
    view: AccountView,
    *,
    symbols: tuple[str, ...],
    marks: Mapping[str, Decimal],
    collateral: Mapping[str, IsolatedCollateral],
    additional_hold_usd: Decimal,
    observed_time_ms: int,
) -> UnifiedAccountWire:
    """Project one economic view without duplicating equity across perp namespaces."""
    _validate_inputs(view, symbols, marks, collateral, additional_hold_usd, observed_time_ms)
    groups: dict[str, list[PositionWire]] = {
        parse_perp_venue_identity(symbol).perp_dex: [] for symbol in symbols
    }
    liquidatable: list[str] = []
    with localcontext() as context:
        context.prec = REPLAY_DECIMAL_PRECISION
        hold = additional_hold_usd
        unrealized = notional = ZERO
        for symbol in symbols:
            if symbol not in view.positions:
                continue
            record, contact = _position(view.positions[symbol], marks[symbol], collateral[symbol])
            groups[parse_perp_venue_identity(symbol).perp_dex].append(record)
            hold += Decimal(record["marginUsed"])
            unrealized += Decimal(record["unrealizedPnl"])
            notional += Decimal(record["positionValue"])
            if contact:
                liquidatable.append(symbol)
        if (
            unrealized != view.unrealized_pnl_usd
            or notional != view.gross_notional_usd
            or view.equity_usd != view.cash_usd + unrealized
        ):
            raise ValueError("explicit marks or totals disagree with the economic view")
        states = {dex: _perp_state(positions, observed_time_ms) for dex, positions in groups.items()}
    spot: SpotStateWire = {
        "balances": [{"coin": "USDC", "token": 0, "total": str(view.equity_usd), "hold": str(hold)}]
    }
    return UnifiedAccountWire(spot, states, tuple(liquidatable))


def _validate_inputs(
    view: AccountView,
    symbols: tuple[str, ...],
    marks: Mapping[str, Decimal],
    collateral: Mapping[str, IsolatedCollateral],
    additional_hold_usd: Decimal,
    observed_time_ms: int,
) -> None:
    if not isinstance(symbols, tuple) or not symbols or len(set(symbols)) != len(symbols):
        raise ValueError("configured symbols must be a nonempty unique tuple")
    for symbol in symbols:
        require_name(symbol, "configured symbol")
    if not set(view.positions).issubset(symbols):
        raise ValueError("economic positions exceed configured symbols")
    if set(marks) != set(view.positions):
        raise ValueError("explicit marks must cover exactly the open positions")
    if set(collateral) != set(view.positions):
        raise ValueError("explicit collateral must cover exactly the open positions")
    for symbol, mark in marks.items():
        require_amount(mark, f"{symbol} mark", positive=True)
        if symbol not in view.mark_prices or mark != view.mark_prices[symbol]:
            raise ValueError(f"{symbol} explicit price differs from its retained mark in the economic view")
        if not isinstance(collateral[symbol], IsolatedCollateral):
            raise ValueError("explicit collateral requires IsolatedCollateral terms")
    require_amount(additional_hold_usd, "additional hold")
    if additional_hold_usd < 0:
        raise ValueError("additional hold must be nonnegative")
    require_clock(observed_time_ms, "wire observation time")
    if view.stamp is not None and observed_time_ms < view.stamp.observed_time_ms:
        raise ValueError("wire observation cannot precede the economic view")


def _position(
    position: ReplayPosition,
    mark: Decimal,
    collateral: IsolatedCollateral,
) -> tuple[PositionWire, bool]:
    quantity = position.quantity_signed
    if position.leverage != position.leverage.to_integral_value():
        raise ValueError("native isolated leverage must be an integer")
    sign = Decimal(1) if quantity > 0 else Decimal(-1)
    notional = abs(quantity) * mark
    unrealized = quantity * mark - sign * position.entry_notional_usd
    margin = collateral.cash_usd + unrealized
    tier = next(t for t in reversed(collateral.maintenance_tiers) if notional >= t.lower_notional_usd)
    maintenance = notional * tier.rate - tier.deduction_usd
    raw_usd = collateral.cash_usd - sign * position.entry_notional_usd
    liquidation = _liquidation_price(quantity, raw_usd, collateral.maintenance_tiers)
    return {
        "coin": position.symbol,
        "szi": str(quantity),
        "entryPx": str(position.entry_price),
        "positionValue": str(notional),
        "unrealizedPnl": str(unrealized),
        "marginUsed": str(margin),
        "liquidationPx": str(liquidation) if liquidation is not None else None,
        "leverage": {"type": "isolated", "value": int(position.leverage), "rawUsd": str(raw_usd)},
    }, margin <= maintenance


def _liquidation_price(
    quantity_signed: Decimal,
    raw_usd: Decimal,
    tiers: tuple[MaintenanceTier, ...],
) -> Decimal | None:
    for index, tier in enumerate(tiers):
        price = -(raw_usd + tier.deduction_usd) / (quantity_signed - abs(quantity_signed) * tier.rate)
        notional = abs(quantity_signed) * price
        upper = tiers[index + 1].lower_notional_usd if index + 1 < len(tiers) else None
        if price > 0 and notional >= tier.lower_notional_usd and (upper is None or notional < upper):
            return price
    return None


def _perp_state(positions: list[PositionWire], observed_time_ms: int) -> PerpStateWire:
    margin = sum((Decimal(p["marginUsed"]) for p in positions), ZERO)
    notional = sum((Decimal(p["positionValue"]) for p in positions), ZERO)
    raw = sum((Decimal(p["leverage"]["rawUsd"]) for p in positions), ZERO)
    return {
        "marginSummary": {
            "accountValue": str(margin),
            "totalNtlPos": str(notional),
            "totalRawUsd": str(raw),
            "totalMarginUsed": str(margin),
        },
        "crossMarginSummary": {
            "accountValue": "0",
            "totalNtlPos": "0",
            "totalRawUsd": "0",
            "totalMarginUsed": "0",
        },
        "crossMaintenanceMarginUsed": "0",
        "withdrawable": "0",
        "time": observed_time_ms,
        "assetPositions": [{"type": "oneWay", "position": p} for p in positions],
    }
