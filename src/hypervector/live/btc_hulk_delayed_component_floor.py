"""Causal delayed profit floor for the BTC Hulk robust short route."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math
from numbers import Real
from typing import Literal

import pandas as pd

from hypervector.cohort_profit_lock_policy import ProfitLockTrigger
from hypervector.live.multi_asset_market_bars import CohortMarketBar
from hypervector.regime.component_telemetry import build_regime_component_frame

_MINUTE_MS = 60_000
_COMPONENT_FIELDS = (
    "ema_21_55_direction",
    "sma_100_200_direction",
    "cipher_a_direction",
    "harsi_direction",
    "mtf_5m_bias",
    "mtf_15m_bias",
)

ComponentFloorState = Literal["not_activated", "armed", "triggered"]
ComponentFloorActivationMode = Literal["profit_floor", "reversal_containment"]


@dataclass(frozen=True)
class DelayedComponentFloorPolicy:
    """Exact time, excursion, floor, and opposition contract."""

    policy_id: str
    warmup_ms: int
    delay_ms: int
    activation_r_multiple: float
    floor_r_multiple: float
    opposed_components_required: int

    def __post_init__(self) -> None:
        """Reject incomplete or internally inconsistent policy values."""
        if not self.policy_id.strip():
            raise ValueError("component-floor policy ID must be non-empty")
        times = (self.warmup_ms, self.delay_ms)
        if any(value < _MINUTE_MS or value % _MINUTE_MS for value in times):
            raise ValueError("component-floor timing must align to a positive minute")
        values = (self.activation_r_multiple, self.floor_r_multiple)
        if any(not math.isfinite(value) or value <= 0.0 for value in values):
            raise ValueError("component-floor R multiples must be positive and finite")
        if self.floor_r_multiple > self.activation_r_multiple:
            raise ValueError("component-floor floor cannot exceed activation")
        if not 1 <= self.opposed_components_required <= len(_COMPONENT_FIELDS):
            raise ValueError("component-floor opposition count is invalid")


BTC_HULK_DELAYED_COMPONENT_FLOOR_POLICY = DelayedComponentFloorPolicy(
    policy_id="btc_hulk_delayed_component_floor_v1",
    warmup_ms=24 * 60 * _MINUTE_MS,
    delay_ms=4 * 60 * _MINUTE_MS,
    activation_r_multiple=0.75,
    floor_r_multiple=0.50,
    opposed_components_required=len(_COMPONENT_FIELDS),
)

BTC_HULK_DELAYED_COMPONENT_EXIT_POLICY = DelayedComponentFloorPolicy(
    policy_id="btc_hulk_delayed_component_exit_v2",
    warmup_ms=24 * 60 * _MINUTE_MS,
    delay_ms=4 * 60 * _MINUTE_MS,
    activation_r_multiple=0.75,
    floor_r_multiple=0.50,
    opposed_components_required=len(_COMPONENT_FIELDS),
)

BTC_HULK_DELAYED_COMPONENT_POLICY_IDS = frozenset(
    {
        BTC_HULK_DELAYED_COMPONENT_FLOOR_POLICY.policy_id,
        BTC_HULK_DELAYED_COMPONENT_EXIT_POLICY.policy_id,
    }
)


def delayed_component_policy(policy_id: str) -> DelayedComponentFloorPolicy:
    """Resolve one supported versioned delayed-component policy."""
    policies = {
        BTC_HULK_DELAYED_COMPONENT_FLOOR_POLICY.policy_id: (
            BTC_HULK_DELAYED_COMPONENT_FLOOR_POLICY
        ),
        BTC_HULK_DELAYED_COMPONENT_EXIT_POLICY.policy_id: (
            BTC_HULK_DELAYED_COMPONENT_EXIT_POLICY
        ),
    }
    try:
        return policies[policy_id]
    except KeyError as error:
        raise ValueError("unsupported delayed-component policy") from error


@dataclass(frozen=True)
class ComponentFloorObservation:
    """One completed minute plus causal trend-component directions."""

    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float
    component_directions: tuple[int | None, ...]

    def __post_init__(self) -> None:
        """Reject malformed timestamps, OHLC values, or component states."""
        if self.timestamp_ms < 0 or self.timestamp_ms % _MINUTE_MS:
            raise ValueError("component-floor timestamp must align to a minute")
        prices = (self.open, self.high, self.low, self.close)
        valid_ohlc = (
            all(math.isfinite(value) and value > 0.0 for value in prices)
            and self.high >= max(self.open, self.close)
            and self.low <= min(self.open, self.close)
        )
        if not valid_ohlc or self.low > self.high:
            raise ValueError("component-floor OHLC values are invalid")
        if len(self.component_directions) != len(_COMPONENT_FIELDS):
            raise ValueError(
                "component-floor observation has the wrong component count"
            )
        if any(value not in {-1, 0, 1, None} for value in self.component_directions):
            raise ValueError("component-floor direction is invalid")


@dataclass(frozen=True)
class DelayedComponentFloorResult:
    """Complete activation, trigger, and evidence diagnostics."""

    state: ComponentFloorState
    activation_mode: ComponentFloorActivationMode | None
    activation_timestamp_ms: int | None
    active_stop_price: float | None
    best_completed_price: float
    trigger: ProfitLockTrigger | None
    maximum_opposed_components: int
    unavailable_gate_observations: int


def evaluate_delayed_component_floor(
    policy: DelayedComponentFloorPolicy,
    *,
    side: str,
    observations: Sequence[ComponentFloorObservation],
    opened_at_ms: int,
    entry_price: float,
    protective_stop_price: float,
) -> DelayedComponentFloorResult:
    """Arm after a delayed 0.75R move and trigger a later fixed exit."""
    sign, risk = _validated_inputs(
        side, observations, opened_at_ms, entry_price, protective_stop_price
    )
    best, activation, stop = entry_price, None, None
    activation_mode: ComponentFloorActivationMode | None = None
    maximum_opposed, unavailable = 0, 0
    for row in observations:
        if stop is not None and _crossed(side, row, stop):
            trigger = _trigger(side, row, stop, activation, best)
            return _result(
                "triggered",
                activation_mode,
                activation,
                None,
                best,
                trigger,
                maximum_opposed,
                unavailable,
            )
        best = max(best, row.high) if side == "long" else min(best, row.low)
        if (
            activation is not None
            or row.timestamp_ms + _MINUTE_MS < opened_at_ms + policy.delay_ms
        ):
            continue
        opposed, missing = _opposition(row.component_directions, sign)
        maximum_opposed = max(maximum_opposed, opposed)
        unavailable += int(missing)
        favorable_r = sign * (best - entry_price) / risk
        candidate_stop = entry_price + sign * policy.floor_r_multiple * risk
        if (
            not missing
            and opposed >= policy.opposed_components_required
            and favorable_r >= policy.activation_r_multiple
        ):
            protected = sign * (row.close - candidate_stop) > 0.0
            adverse = sign * (row.close - entry_price) <= 0.0
            if (
                policy.policy_id == BTC_HULK_DELAYED_COMPONENT_EXIT_POLICY.policy_id
                and not protected
                and not adverse
            ):
                continue
            activation = row.timestamp_ms
            stop = candidate_stop
            activation_mode = "profit_floor" if protected else "reversal_containment"
    state: ComponentFloorState = "armed" if activation is not None else "not_activated"
    return _result(
        state,
        activation_mode,
        activation,
        stop,
        best,
        None,
        maximum_opposed,
        unavailable,
    )


def build_btc_hulk_component_floor_observations(
    bars: Sequence[CohortMarketBar],
    *,
    lifecycle_start_ms: int,
) -> tuple[ComponentFloorObservation, ...]:
    """Project exact component directions from completed venue minute bars."""
    if not bars:
        return ()
    _validate_market_bars(bars, lifecycle_start_ms)
    frame = _component_frame(bars)
    components = build_regime_component_frame(frame)
    rows: list[ComponentFloorObservation] = []
    for bar in bars:
        if bar.timestamp_ms < lifecycle_start_ms:
            continue
        values = components.loc[pd.to_datetime(bar.timestamp_ms, unit="ms", utc=True)]
        directions = tuple(
            _component_direction(values[name]) for name in _COMPONENT_FIELDS
        )
        rows.append(
            ComponentFloorObservation(
                bar.timestamp_ms, bar.open, bar.high, bar.low, bar.close, directions
            )
        )
    return tuple(rows)


def component_floor_policy_payload(
    policy: DelayedComponentFloorPolicy = BTC_HULK_DELAYED_COMPONENT_EXIT_POLICY,
) -> dict[str, object]:
    """Return the complete immutable policy declaration for telemetry."""
    return {
        "policy_id": policy.policy_id,
        "warmup_ms": policy.warmup_ms,
        "delay_ms": policy.delay_ms,
        "activation_r_multiple": policy.activation_r_multiple,
        "floor_r_multiple": policy.floor_r_multiple,
        "opposed_components_required": policy.opposed_components_required,
        "component_fields": list(_COMPONENT_FIELDS),
        "activation_modes": ["profit_floor", "reversal_containment"],
    }


def _validated_inputs(
    side: str,
    rows: Sequence[ComponentFloorObservation],
    opened_at_ms: int,
    entry: float,
    stop: float,
) -> tuple[int, float]:
    if side not in {"long", "short"}:
        raise ValueError("component-floor side must be long or short")
    if opened_at_ms < 0:
        raise ValueError("component-floor opened time must be nonnegative")
    if any(not math.isfinite(value) or value <= 0.0 for value in (entry, stop)):
        raise ValueError("component-floor prices must be positive and finite")
    adverse = stop < entry if side == "long" else stop > entry
    if not adverse:
        raise ValueError("component-floor protective stop must be adverse")
    sign = 1 if side == "long" else -1
    risk = abs(stop - entry)
    times = [row.timestamp_ms for row in rows]
    if times != sorted(set(times)):
        raise ValueError("component-floor observations must be strictly chronological")
    return sign, risk


def _opposition(values: tuple[int | None, ...], side_sign: int) -> tuple[int, bool]:
    missing = any(value is None for value in values)
    return sum(value == -side_sign for value in values), missing


def _crossed(side: str, row: ComponentFloorObservation, stop: float) -> bool:
    return row.low <= stop if side == "long" else row.high >= stop


def _trigger(
    side: str,
    row: ComponentFloorObservation,
    stop: float,
    activation: int | None,
    best: float,
) -> ProfitLockTrigger:
    if activation is None:
        raise ValueError("component-floor trigger lacks activation")
    reference = min(row.open, stop) if side == "long" else max(row.open, stop)
    return ProfitLockTrigger(activation, row.timestamp_ms, reference, stop, best)


def _result(
    state: ComponentFloorState,
    activation_mode: ComponentFloorActivationMode | None,
    activation: int | None,
    stop: float | None,
    best: float,
    trigger: ProfitLockTrigger | None,
    maximum_opposed: int,
    unavailable: int,
) -> DelayedComponentFloorResult:
    return DelayedComponentFloorResult(
        state,
        activation_mode,
        activation,
        stop,
        best,
        trigger,
        maximum_opposed,
        unavailable,
    )


def _validate_market_bars(
    bars: Sequence[CohortMarketBar], lifecycle_start_ms: int
) -> None:
    if lifecycle_start_ms < 0 or lifecycle_start_ms % _MINUTE_MS:
        raise ValueError("component-floor lifecycle start must align to a minute")
    symbols = {bar.symbol for bar in bars}
    times = [bar.timestamp_ms for bar in bars]
    if len(symbols) != 1 or times != sorted(set(times)):
        raise ValueError("component-floor market bars have invalid identity or order")
    if any(value % _MINUTE_MS for value in times):
        raise ValueError("component-floor market bars must align to a minute")


def _component_frame(bars: Sequence[CohortMarketBar]) -> pd.DataFrame:
    index = pd.to_datetime([bar.timestamp_ms for bar in bars], unit="ms", utc=True)
    return pd.DataFrame(
        {
            "open": [bar.open for bar in bars],
            "high": [bar.high for bar in bars],
            "low": [bar.low for bar in bars],
            "close": [bar.close for bar in bars],
            "volume": [bar.volume for bar in bars],
        },
        index=index,
    )


def _component_direction(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return 1 if number > 0.0 else -1 if number < 0.0 else 0
