"""Typed state and report contracts for causal maker replay."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Literal

import pandas as pd

Direction = Literal["long", "short"]
FillRule = Literal["touch", "through", "trade-through"]
SameDirectionReentryPolicy = Literal[
    "regime_reset",
    "cooldown_only",
    "target_continuation",
    "target_pullback_transition",
]
OccupiedSignalPolicy = Literal["structural", "ignore"]
_TARGET_REENTRY_POLICIES = frozenset(
    {"target_continuation", "target_pullback_transition"}
)
LifecycleStatus = Literal[
    "pending",
    "expired",
    "canceled",
    "open",
    "target_completed",
    "liquidated",
    "stopped",
    "time_exited",
    "regime_exited",
    "reversed",
]
_BTC_MAX_LEVERAGE = 40.0


def _validate_contract_variant(
    margin_fraction: float, leverage: float, target_margin_pct: float
) -> None:
    if not math.isfinite(margin_fraction) or not 0.0 < margin_fraction <= 1.0:
        raise ValueError("margin fraction must be finite within (0, 1]")
    if not math.isfinite(leverage) or not 0.0 < leverage <= _BTC_MAX_LEVERAGE:
        raise ValueError("leverage must be finite within (0, 40]")
    if not math.isfinite(target_margin_pct) or target_margin_pct <= 0.0:
        raise ValueError("target margin pct must be finite and positive")


def _validate_reentry_config(
    policy: SameDirectionReentryPolicy,
    clearance_bps: float,
) -> None:
    if policy not in {
        "regime_reset",
        "cooldown_only",
        "target_continuation",
        "target_pullback_transition",
    }:
        raise ValueError(
            "same_direction_reentry_policy must be "
            "regime_reset|cooldown_only|target_continuation|"
            "target_pullback_transition"
        )
    if not math.isfinite(clearance_bps) or clearance_bps < 0.0:
        raise ValueError(
            "same_direction_reentry_clearance_bps must be finite and non-negative"
        )


def _validate_stop_config(
    proximity_fraction: float | None,
    margin_pct: float | None,
) -> None:
    if proximity_fraction is not None and (
        not math.isfinite(proximity_fraction) or not 0.0 < proximity_fraction < 1.0
    ):
        raise ValueError(
            "liquidation_proximity_stop_fraction must be finite within (0, 1)"
        )
    if margin_pct is not None and (
        not math.isfinite(margin_pct) or not 0.0 < margin_pct < 100.0
    ):
        raise ValueError("fixed_margin_stop_pct must be finite within (0, 100)")
    if proximity_fraction is not None and margin_pct is not None:
        raise ValueError("only one maker-replay stop model may be configured")


def _validate_target_continuation_limit(
    policy: SameDirectionReentryPolicy,
    limit: int | None,
) -> None:
    if limit is not None and (
        isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0
    ):
        raise ValueError(
            "target_continuation_limit_per_episode must be a positive integer"
        )
    if limit is not None and policy not in _TARGET_REENTRY_POLICIES:
        raise ValueError(
            "target_continuation_limit_per_episode requires a target re-entry policy"
        )


def _validate_target_continuation_maturity(
    policy: SameDirectionReentryPolicy,
    minimum_seconds: float,
) -> None:
    if (
        isinstance(minimum_seconds, bool)
        or not math.isfinite(minimum_seconds)
        or minimum_seconds < 0.0
    ):
        raise ValueError(
            "target_continuation_minimum_episode_seconds must be finite "
            "and non-negative"
        )
    if minimum_seconds > 0.0 and policy not in _TARGET_REENTRY_POLICIES:
        raise ValueError(
            "target_continuation_minimum_episode_seconds requires a target "
            "re-entry policy"
        )


def _validate_event_exit(
    opposite_regime_exit: object,
    opposite_entry_close_reverse: object,
    context_max_age_seconds: float,
) -> None:
    if not isinstance(opposite_regime_exit, bool):
        raise ValueError("opposite_regime_exit must be a boolean")
    if not isinstance(opposite_entry_close_reverse, bool):
        raise ValueError("opposite_entry_close_reverse must be a boolean")
    if not math.isfinite(context_max_age_seconds) or context_max_age_seconds <= 0.0:
        raise ValueError("context_max_age_seconds must be finite and positive")


def _validate_peak_protection(
    activation_margin_pct: float | None,
    lock_ratio: float | None,
    minimum_price_move_fraction: float,
    update_cooldown_seconds: float,
) -> None:
    if (activation_margin_pct is None) != (lock_ratio is None):
        raise ValueError("peak protection activation and lock ratio must be paired")
    if activation_margin_pct is not None and (
        isinstance(activation_margin_pct, bool)
        or not math.isfinite(activation_margin_pct)
        or activation_margin_pct <= 0.0
    ):
        raise ValueError("peak protection activation must be finite and positive")
    if lock_ratio is not None and (
        isinstance(lock_ratio, bool)
        or not math.isfinite(lock_ratio)
        or not 0.0 < lock_ratio <= 1.0
    ):
        raise ValueError("peak protection lock ratio must be within (0, 1]")
    if (
        isinstance(minimum_price_move_fraction, bool)
        or not math.isfinite(minimum_price_move_fraction)
        or minimum_price_move_fraction < 0.0
    ):
        raise ValueError("peak protection minimum price move must be non-negative")
    if (
        isinstance(update_cooldown_seconds, bool)
        or not math.isfinite(update_cooldown_seconds)
        or update_cooldown_seconds < 0.0
    ):
        raise ValueError("peak protection update cooldown must be non-negative")


@dataclass(frozen=True)
class MakerReplayConfig:
    """Explicit maker-replay assumptions that remain reportable and tunable."""

    initial_equity: float = 10_000.0
    margin_fraction: float = 0.70
    leverage: float = 40.0
    target_margin_pct: float = 8.0
    target_price_points: float | None = None
    maker_fee_rate: float = 0.00015
    taker_fee_rate: float = 0.00045
    fill_rule: FillRule = "through"
    tick_size: float = 1.0
    entry_depth_ticks: int = 0
    entry_ttl_seconds: float = 300.0
    reentry_cooldown_seconds: float = 60.0
    liquidation_reentry_cooldown_seconds: float = 0.0
    same_direction_reentry_policy: SameDirectionReentryPolicy = "regime_reset"
    same_direction_reentry_clearance_bps: float = 0.0
    target_continuation_limit_per_episode: int | None = None
    target_continuation_minimum_episode_seconds: float = 0.0
    liquidation_proximity_stop_fraction: float | None = None
    fixed_margin_stop_pct: float | None = None
    maximum_hold_seconds: float | None = None
    opposite_regime_exit: bool = False
    opposite_entry_close_reverse: bool = False
    occupied_signal_policy: OccupiedSignalPolicy = "structural"
    context_max_age_seconds: float = 120.0
    maximum_entry_spread_bps: float | None = None
    peak_protection_activation_margin_pct: float | None = None
    peak_protection_lock_ratio: float | None = None
    peak_protection_minimum_price_move_fraction: float = 0.0005
    peak_protection_update_cooldown_seconds: float = 60.0

    def __post_init__(self) -> None:
        """Reject invalid or ambiguous replay assumptions."""
        if self.initial_equity <= 0.0:
            raise ValueError("initial_equity must be positive")
        _validate_contract_variant(
            self.margin_fraction, self.leverage, self.target_margin_pct
        )
        if self.target_price_points is not None and (
            isinstance(self.target_price_points, bool)
            or not math.isfinite(self.target_price_points)
            or self.target_price_points <= 0.0
        ):
            raise ValueError("target_price_points must be finite and positive")
        for name in ("maker_fee_rate", "taker_fee_rate"):
            value = float(getattr(self, name))
            if not 0.0 <= value < 1.0:
                raise ValueError(f"{name} must be within [0, 1)")
        if self.fill_rule not in ("touch", "through", "trade-through"):
            raise ValueError("fill_rule must be touch|through|trade-through")
        if self.tick_size <= 0.0:
            raise ValueError("tick_size must be positive")
        if (
            isinstance(self.entry_depth_ticks, bool)
            or not isinstance(self.entry_depth_ticks, int)
            or self.entry_depth_ticks < 0
        ):
            raise ValueError("entry_depth_ticks must be a non-negative integer")
        if self.entry_ttl_seconds <= 0.0:
            raise ValueError("entry_ttl_seconds must be positive")
        if self.reentry_cooldown_seconds < 0.0:
            raise ValueError("reentry_cooldown_seconds must be non-negative")
        liquidation_cooldown = self.liquidation_reentry_cooldown_seconds
        if (
            isinstance(liquidation_cooldown, bool)
            or not math.isfinite(liquidation_cooldown)
            or liquidation_cooldown < 0.0
        ):
            raise ValueError(
                "liquidation_reentry_cooldown_seconds must be finite and non-negative"
            )
        _validate_reentry_config(
            self.same_direction_reentry_policy,
            self.same_direction_reentry_clearance_bps,
        )
        _validate_target_continuation_limit(
            self.same_direction_reentry_policy,
            self.target_continuation_limit_per_episode,
        )
        _validate_target_continuation_maturity(
            self.same_direction_reentry_policy,
            self.target_continuation_minimum_episode_seconds,
        )
        _validate_stop_config(
            self.liquidation_proximity_stop_fraction,
            self.fixed_margin_stop_pct,
        )
        if self.maximum_hold_seconds is not None and (
            isinstance(self.maximum_hold_seconds, bool)
            or not math.isfinite(self.maximum_hold_seconds)
            or self.maximum_hold_seconds <= 0.0
        ):
            raise ValueError("maximum_hold_seconds must be finite and positive")
        _validate_event_exit(
            self.opposite_regime_exit,
            self.opposite_entry_close_reverse,
            self.context_max_age_seconds,
        )
        if self.occupied_signal_policy not in {"structural", "ignore"}:
            raise ValueError("occupied_signal_policy must be structural|ignore")
        cap = self.maximum_entry_spread_bps
        if cap is not None and (
            isinstance(cap, bool) or not math.isfinite(cap) or cap <= 0.0
        ):
            raise ValueError("maximum_entry_spread_bps must be finite and positive")
        _validate_peak_protection(
            self.peak_protection_activation_margin_pct,
            self.peak_protection_lock_ratio,
            self.peak_protection_minimum_price_move_fraction,
            self.peak_protection_update_cooldown_seconds,
        )


@dataclass(frozen=True)
class MakerReplayTrade:
    """One completed maker-to-maker trade reconstructed from market evidence."""

    direction: Direction
    signal_time_utc: str
    submitted_time_utc: str
    entry_time_utc: str
    exit_time_utc: str
    entry_price: float
    exit_price: float
    quantity: float
    margin: float
    notional: float
    gross_pnl: float
    fees: float
    net_pnl: float
    entry_wait_seconds: float
    hold_seconds: float
    status: Literal[
        "target_completed",
        "liquidated",
        "stopped",
        "time_exited",
        "regime_exited",
        "reversed",
    ] = "target_completed"
    funding_cashflow: float = 0.0


@dataclass(frozen=True)
class MakerReplayLifecycle:
    """Final observed state of one causally submitted maker entry."""

    lifecycle_id: int
    direction: Direction
    signal_time_utc: str
    submitted_time_utc: str
    entry_time_utc: str | None
    outcome_time_utc: str | None
    status: LifecycleStatus
    entry_price: float | None
    exit_price: float | None
    quantity: float | None
    fees: float | None
    net_pnl: float | None
    stop_price: float | None = None


@dataclass(frozen=True)
class MakerReplayReport:
    """Complete maker replay including unresolved order uncertainty."""

    fill_rule: FillRule
    snapshots: int
    market_trade_prints: int
    submitted_entries: int
    entry_fills: int
    expired_entries: int
    canceled_entries: int
    pending_orders: int
    completed_trades: int
    open_positions: int
    initial_equity: float
    final_equity: float
    submission_times_utc: tuple[str, ...]
    trades: tuple[MakerReplayTrade, ...]
    lifecycles: tuple[MakerReplayLifecycle, ...]
    limitations: tuple[str, ...]
    liquidations: int = 0
    partial_liquidations: int = 0
    maximum_drawdown_pct: float = 0.0
    realized_equity: float | None = None
    liquidation_model: str = "bbo_mark_proxy_partial_liquidation_v1"
    stops: int = 0
    time_exits: int = 0
    regime_exits: int = 0
    close_reversals: int = 0
    authentic_price_updates: int = 0
    missing_mark_events: int = 0
    stale_mark_events: int = 0
    funding_settlements: int = 0
    funding_cashflow: float = 0.0
    funding_paid: float = 0.0
    funding_received: float = 0.0
    missing_oracle_settlements: int = 0
    stale_oracle_settlements: int = 0
    empty_book_evidence_windows: int = 0
    active_book_gap_windows: int = 0
    execution_economics_conclusive: bool = True
    first_book_gap_start_utc: str | None = None
    spread_rejected_entries: int = 0
    peak_protection_arms: int = 0
    peak_protection_updates: int = 0
    peak_protection_exits: int = 0

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe replay report."""
        return asdict(self)


@dataclass
class PendingEntry:
    """Mutable pending maker-entry state carried across evidence chunks."""

    lifecycle_id: int
    direction: Direction
    signal_time: pd.Timestamp
    submitted_time: pd.Timestamp
    limit_price: float
    allocation_multiplier: float = 1.0
    stop_price: float | None = None
    stop_margin_pct: float | None = None
    trade_through_volume: float = 0.0
    maximum_hold_seconds: float | None = None


@dataclass
class OpenPosition:
    """Mutable open position carried until its fixed target is evidenced."""

    lifecycle_id: int
    direction: Direction
    signal_time: pd.Timestamp
    submitted_time: pd.Timestamp
    entry_time: pd.Timestamp
    entry_price: float
    quantity: float
    margin: float
    notional: float
    target_price: float
    exit_trade_through_volume: float = 0.0
    initial_quantity: float = 0.0
    entry_fee: float = 0.0
    liquidation_fees: float = 0.0
    realized_gross_pnl: float = 0.0
    last_partial_liquidation_ms: int | None = None
    stop_price: float | None = None
    funding_cashflow: float = 0.0
    open_fee_basis: float | None = None
    open_funding_basis: float | None = None
    maximum_hold_seconds: float | None = None
    peak_margin_pnl_pct: float = 0.0
    peak_protection_armed: bool = False
    peak_protection_last_update_ms: int | None = None
    venue_max_leverage: float = _BTC_MAX_LEVERAGE


@dataclass
class ReplayState:
    """Complete mutable maker-replay state for one continuous window."""

    equity: float
    pending: PendingEntry | None = None
    position: OpenPosition | None = None
    expired_direction: Direction | None = None
    last_signal: pd.Timestamp | None = None
    submitted: int = 0
    entry_fills: int = 0
    expired: int = 0
    canceled: int = 0
    spread_rejected_entries: int = 0
    submissions: list[str] = field(default_factory=list)
    trades: list[MakerReplayTrade] = field(default_factory=list)
    lifecycles: list[MakerReplayLifecycle] = field(default_factory=list)
    completed_direction: Direction | None = None
    completed_status: (
        Literal[
            "target_completed",
            "liquidated",
            "stopped",
            "time_exited",
            "regime_exited",
            "reversed",
        ]
        | None
    ) = None
    completed_reference_price: float | None = None
    structural_episode_direction: Direction | None = None
    structural_episode_started_at: pd.Timestamp | None = None
    target_completions_in_episode: int = 0
    last_exit_time: pd.Timestamp | None = None
    liquidations: int = 0
    partial_liquidations: int = 0
    stops: int = 0
    time_exits: int = 0
    regime_exits: int = 0
    close_reversals: int = 0
    peak_equity: float = 0.0
    maximum_drawdown_pct: float = 0.0
    last_marked_equity: float | None = None
    authentic_context_enabled: bool = False
    latest_price_ms: int | None = None
    latest_mark_price: float | None = None
    latest_oracle_price: float | None = None
    last_book_ms: int | None = None
    last_bid: float | None = None
    last_ask: float | None = None
    authentic_price_updates: int = 0
    missing_mark_events: int = 0
    stale_mark_events: int = 0
    funding_settlements: int = 0
    funding_cashflow: float = 0.0
    funding_paid: float = 0.0
    funding_received: float = 0.0
    missing_oracle_settlements: int = 0
    stale_oracle_settlements: int = 0
    empty_book_evidence_windows: int = 0
    active_book_gap_windows: int = 0
    execution_economics_conclusive: bool = True
    first_book_gap_start_utc: str | None = None
    peak_protection_arms: int = 0
    peak_protection_updates: int = 0
    peak_protection_exits: int = 0
