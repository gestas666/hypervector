"""Typed exact-decimal models for BTC liquidation covariate replay."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

AggressorSide = Literal["buy", "sell"]
CandidateBranch = Literal["continuation_long", "exhaustion_reclaim_long"]
BurstArm = Literal["5s_p95", "5s_p99", "15s_p95", "15s_p99"]
EntryStatus = Literal["eligible", "signal_blocked", "technical_excluded"]
OutcomeStatus = Literal["resolved", "technical_excluded"]
_REQUIRED_DEPTH_LEVELS = 20


@dataclass(frozen=True)
class PublicTrade:
    """One exchange-timestamped public trade."""

    ts_exchange_ms: int
    trade_id: int
    aggressor_side: AggressorSide
    price: Decimal
    size: Decimal

    def __post_init__(self) -> None:
        """Reject malformed public-trade observations."""
        _nonnegative_integer(self.ts_exchange_ms, "trade timestamp")
        _nonnegative_integer(self.trade_id, "trade identity")
        if self.aggressor_side not in ("buy", "sell"):
            raise ValueError("aggressor_side must be buy or sell")
        _positive_decimal(self.price, "trade price")
        _positive_decimal(self.size, "trade size")

    @property
    def notional(self) -> Decimal:
        """Return exact public-trade quote notional."""
        return self.price * self.size


@dataclass(frozen=True)
class VisibleLevel:
    """One exact-decimal visible order-book level."""

    price: Decimal
    size: Decimal

    def __post_init__(self) -> None:
        """Reject malformed visible depth."""
        _positive_decimal(self.price, "level price")
        _positive_decimal(self.size, "level size")


@dataclass(frozen=True)
class BookSnapshot:
    """One exchange-timestamped visible BTC order book."""

    ts_exchange_ms: int
    bids: tuple[VisibleLevel, ...]
    asks: tuple[VisibleLevel, ...]

    def __post_init__(self) -> None:
        """Require ordered, uncrossed, nonempty visible depth."""
        _nonnegative_integer(self.ts_exchange_ms, "book timestamp")
        if not self.bids or not self.asks:
            raise ValueError("book must contain bids and asks")
        _ordered(self.bids, ascending=False, label="bids")
        _ordered(self.asks, ascending=True, label="asks")
        if self.bids[0].price >= self.asks[0].price:
            raise ValueError("book must be uncrossed")

    @property
    def complete(self) -> bool:
        """Return whether both sides retain the frozen 20 visible levels."""
        return (
            len(self.bids) == _REQUIRED_DEPTH_LEVELS
            and len(self.asks) == _REQUIRED_DEPTH_LEVELS
        )

    @property
    def midpoint(self) -> Decimal:
        """Return the exact best-bid/best-ask midpoint."""
        return (self.bids[0].price + self.asks[0].price) / Decimal("2")


@dataclass(frozen=True)
class ReplayEpisode:
    """Treatment identity and fields available before outcome replay."""

    episode_id: str
    partition: str
    branch: CandidateBranch
    end_ms: int
    volume_weighted_price: Decimal
    eligible_arms: tuple[BurstArm, ...]

    def __post_init__(self) -> None:
        """Reject treatment identities that violate the frozen schema."""
        if not self.episode_id or not self.partition:
            raise ValueError("episode identity and partition must be nonempty")
        if self.branch not in ("continuation_long", "exhaustion_reclaim_long"):
            raise ValueError("episode branch is unsupported")
        _nonnegative_integer(self.end_ms, "episode end")
        _positive_decimal(self.volume_weighted_price, "episode VWAP")
        if not self.eligible_arms or len(set(self.eligible_arms)) != len(
            self.eligible_arms
        ):
            raise ValueError("eligible arms must be nonempty and unique")


@dataclass(frozen=True)
class DepthExecution:
    """Exact-decimal finite visible-depth execution result."""

    requested_quantity: Decimal
    filled_quantity: Decimal
    quote_notional: Decimal
    vwap: Decimal
    best_price: Decimal
    worst_price: Decimal
    impact_bps: Decimal
    levels_consumed: int
    complete: bool


@dataclass(frozen=True)
class EntryAssessment:
    """Causal entry-gate and visible-depth result for one episode."""

    episode: ReplayEpisode
    status: EntryStatus
    blockers: tuple[str, ...]
    decision_time_ms: int
    flow_imbalance: Decimal | None
    decision_book_time_ms: int | None
    decision_midpoint: Decimal | None
    entry_fill: DepthExecution | None


@dataclass(frozen=True)
class HorizonReplay:
    """One fixed-horizon exit result before official funding cashflows."""

    horizon_ms: int
    target_time_ms: int
    status: OutcomeStatus
    reason: str | None
    exit_book_time_ms: int | None
    exit_fill: DepthExecution | None
    gross_pnl_usd: Decimal | None
    fee_usd: Decimal | None
    nominal_net_pnl_before_funding_usd: Decimal | None
    stressed_net_pnl_before_funding_usd: Decimal | None


@dataclass(frozen=True)
class FundingSettlement:
    """One exact official venue funding settlement."""

    event_time_ms: int
    funding_rate: Decimal

    def __post_init__(self) -> None:
        """Reject malformed settlement timestamps or rates."""
        _nonnegative_integer(self.event_time_ms, "funding settlement timestamp")
        if not self.funding_rate.is_finite():
            raise ValueError("funding rate must be finite")


@dataclass(frozen=True)
class FundingCashflow:
    """Exact long-side funding cashflow over one execution interval."""

    entry_time_ms: int
    exit_time_ms: int
    entry_notional_usd: Decimal
    settlement_count: int
    total_funding_rate: Decimal
    cashflow_usd: Decimal


@dataclass(frozen=True)
class FundingAdjustedHorizon:
    """One horizon replay with exact official long funding applied."""

    replay: HorizonReplay
    funding: FundingCashflow | None
    nominal_net_pnl_usd: Decimal | None
    stressed_net_pnl_usd: Decimal | None


@dataclass(frozen=True)
class BookTimingCoverage:
    """Outcome-blind availability of entry and fixed-horizon book timestamps."""

    episode_id: str
    decision_time_ms: int
    entry_book_time_ms: int | None
    entry_delay_ms: int | None
    horizon_book_times_ms: tuple[tuple[int, int | None], ...]
    technical_complete: bool


@dataclass(frozen=True)
class PurgeCandidate:
    """One eligible entry identity for exact-group overlap suppression."""

    episode_id: str
    partition: str
    branch: CandidateBranch
    arm: BurstArm
    decision_time_ms: int
    entry_time_ms: int

    def __post_init__(self) -> None:
        """Reject malformed overlap-purge identities."""
        if not self.episode_id or not self.partition:
            raise ValueError("purge identity and partition must be nonempty")
        _nonnegative_integer(self.decision_time_ms, "decision timestamp")
        _nonnegative_integer(self.entry_time_ms, "entry timestamp")
        if self.entry_time_ms < self.decision_time_ms:
            raise ValueError("entry timestamp cannot predate decision")


@dataclass(frozen=True)
class OverlapPurge:
    """Retained and suppressed position-equivalent entry identities."""

    retained: tuple[PurgeCandidate, ...]
    suppressed: tuple[PurgeCandidate, ...]


def _ordered(
    levels: tuple[VisibleLevel, ...],
    *,
    ascending: bool,
    label: str,
) -> None:
    prices = tuple(row.price for row in levels)
    invalid = (
        any(left >= right for left, right in zip(prices, prices[1:]))
        if ascending
        else any(left <= right for left, right in zip(prices, prices[1:]))
    )
    if invalid:
        raise ValueError(f"book {label} prices are not strictly ordered")


def _positive_decimal(value: Decimal, label: str) -> None:
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{label} must be finite and positive")


def _nonnegative_integer(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
