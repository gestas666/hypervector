"""Typed immutable inputs and state for the Hypervelocity event runtime."""

from __future__ import annotations

from dataclasses import dataclass

from hypervector.execution import OrderCommand
from hypervector.strategies.hypervelocity_runtime_values import (
    Direction,
    require_nonempty,
    require_nonnegative,
    require_positive,
    utc_timestamp,
)


@dataclass(frozen=True)
class RuntimeMarketState:
    """Pre-classified backend market input; no regime calculation occurs here."""

    symbol: str
    observed_at: str
    entry_direction: Direction | None
    structural_direction: Direction | None
    entry_quantity: float
    entry_limit_price: float | None
    evidence_fresh: bool
    entry_ttl_seconds: float
    reentry_cooldown_seconds: float
    target_price_fraction: float
    price_tick: float
    maximum_hold_seconds: float | None = None

    def __post_init__(self) -> None:
        require_nonempty(self.symbol, "symbol")
        utc_timestamp(self.observed_at, "observed_at")
        if self.entry_direction not in {None, "long", "short"}:
            raise ValueError("entry_direction must be long|short|None")
        if self.structural_direction not in {None, "long", "short"}:
            raise ValueError("structural_direction must be long|short|None")
        if (
            self.entry_direction is not None
            and self.entry_direction != self.structural_direction
        ):
            raise ValueError("entry_direction must match structural_direction")
        require_positive(self.entry_quantity, "entry_quantity")
        if self.entry_direction is not None:
            require_positive(self.entry_limit_price, "entry_limit_price")
        elif self.entry_limit_price is not None:
            raise ValueError("flat market state cannot carry entry_limit_price")
        require_nonnegative(self.entry_ttl_seconds, "entry_ttl_seconds")
        require_nonnegative(self.reentry_cooldown_seconds, "reentry_cooldown_seconds")
        require_positive(self.target_price_fraction, "target_price_fraction")
        require_positive(self.price_tick, "price_tick")
        if self.maximum_hold_seconds is not None:
            require_positive(self.maximum_hold_seconds, "maximum_hold_seconds")


@dataclass(frozen=True)
class RuntimeOrder:
    """Coordinator-owned state for one submitted venue command."""

    command: OrderCommand
    cumulative_quantity: float = 0.0
    cancel_requested: bool = False

    def __post_init__(self) -> None:
        require_nonnegative(self.cumulative_quantity, "cumulative_quantity")
        if self.cumulative_quantity > self.command.quantity:
            raise ValueError("cumulative quantity exceeds requested quantity")


@dataclass(frozen=True)
class HypervelocityRuntimeState:
    """Immutable state passed between pure coordinator advances."""

    next_order_sequence: int = 1
    pending_entry: RuntimeOrder | None = None
    active_targets: tuple[RuntimeOrder, ...] = ()
    terminal_order_ids: tuple[str, ...] = ()
    position_direction: Direction | None = None
    position_quantity: float = 0.0
    position_average_price: float | None = None
    expired_entry_direction: Direction | None = None
    completed_trade_direction: Direction | None = None
    last_exit_at: str | None = None
    position_opened_at: str | None = None
    maximum_hold_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.next_order_sequence <= 0:
            raise ValueError("next_order_sequence must be positive")
        require_nonnegative(self.position_quantity, "position_quantity")
        if self.position_quantity == 0.0:
            self._validate_flat()
        else:
            if self.position_direction not in {"long", "short"}:
                raise ValueError("open position requires position_direction")
            require_positive(self.position_average_price, "position_average_price")
        if self.last_exit_at is not None:
            utc_timestamp(self.last_exit_at, "last_exit_at")
        if self.position_opened_at is not None:
            utc_timestamp(self.position_opened_at, "position_opened_at")
        if self.maximum_hold_seconds is not None:
            require_positive(self.maximum_hold_seconds, "maximum_hold_seconds")
            if self.position_opened_at is None:
                raise ValueError("maximum hold requires position_opened_at")

    def _validate_flat(self) -> None:
        if (
            self.position_direction is not None
            or self.position_average_price is not None
            or self.position_opened_at is not None
            or self.maximum_hold_seconds is not None
        ):
            raise ValueError(
                "flat position requires null position_direction, price, and hold state"
            )


@dataclass(frozen=True)
class RuntimeDecision:
    """Pure coordinator output for execution and observability boundaries."""

    state: HypervelocityRuntimeState
    commands: tuple[OrderCommand, ...] = ()
    cancellations: tuple[str, ...] = ()
    annotations: tuple[str, ...] = ()
