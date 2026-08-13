"""Risk-plan compatibility helpers for the shared protected lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from typing import NoReturn, Protocol

from hypervector.live.cohort_entry_sizing import CohortEntrySizing
from hypervector.live.cohort_execution_plan import (
    BoundExecutionPlan,
    ProviderExecutionContract,
)
from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError


class SolExecutionConfigProtocol(Protocol):
    """Configuration fields required by generic entry risk calculations."""

    strategy_id: str
    stop_bps: float
    maximum_hold_seconds: int
    margin_fraction: float
    leverage: float
    max_notional_usd: float


class EmergencyFlattenProtocol(Protocol):
    """Emergency position-close callback owned by the live engine."""

    def __call__(
        self,
        *,
        position_size_signed: float,
        mark_price: float,
        reason: str,
        stop_oid: int | None = None,
    ) -> NoReturn: ...


def legacy_execution_plan(config: SolExecutionConfigProtocol) -> BoundExecutionPlan:
    """Build the exact historical symbol-level fallback for old ledgers."""
    return ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=config.stop_bps,
        target_policy="none",
        maximum_hold_seconds=config.maximum_hold_seconds,
    ).bind(strategy_id=config.strategy_id, stop_anchor=None)


def entry_notional(
    config: SolExecutionConfigProtocol,
    account_value_usd: float,
    *,
    fault: Callable[[str], None],
    sizing: CohortEntrySizing | None = None,
) -> float:
    """Return bounded notional or durably fault a non-positive live account."""
    if account_value_usd <= 0.0:
        reason = "live account value must be positive"
        fault(reason)
        raise SolLiveEngineError(reason)
    policy = sizing or CohortEntrySizing(
        config.margin_fraction,
        config.max_notional_usd,
    )
    if policy.max_notional_usd > config.max_notional_usd:
        reason = "provider entry sizing exceeds asset adapter ceiling"
        fault(reason)
        raise SolLiveEngineError(reason)
    return policy.planned_notional(
        account_value_usd=account_value_usd,
        leverage=config.leverage,
    )


def validate_entry_direction(
    *,
    side: str,
    observed_size: float,
    mark_price: float,
    fault: Callable[[str], None],
    emergency_flatten: EmergencyFlattenProtocol,
) -> None:
    """Reject unsupported or venue-mismatched entry direction."""
    normalized = side.strip().lower()
    expected_positive = normalized in {"long", "buy", "b"}
    expected_negative = normalized in {"short", "sell", "s"}
    if not expected_positive and not expected_negative:
        reason = f"unsupported entry side: {side!r}"
        fault(reason)
        raise SolLiveEngineError(reason)
    direction_ok = observed_size > 0.0 if expected_positive else observed_size < 0.0
    if direction_ok:
        return
    reason = f"entry fill direction mismatch: side={side} position={observed_size:g}"
    if observed_size != 0.0:
        emergency_flatten(
            position_size_signed=observed_size,
            mark_price=mark_price,
            reason=reason,
        )
    fault(reason)
    raise SolLiveEngineError(reason)
