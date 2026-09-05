"""Exact open-lifecycle execution-contract validation for V79."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math

from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.research.v79_execution_fill_guard import (
    open_lifecycle_entry_matches,
)

Record = Mapping[str, object]

_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE", "ZEC", "xyz:SPCX", "xyz:SNDK")
_VENUE_ROUNDING_TOLERANCE_BPS = 1.0


@dataclass(frozen=True)
class OpenLifecycleValidation:
    """V79 open-lifecycle rejection reasons and observed open count."""

    reasons: tuple[str, ...]
    open_positions: int


def validate_v79_open_lifecycles(
    checkpoint: Record,
    audit: Record,
    config: MultiAssetLiveConfig,
) -> OpenLifecycleValidation:
    """Validate open state, route, stop, target, and bound exit-plan evidence."""
    lifecycle = _mapping(checkpoint.get("lifecycle"), "checkpoint lifecycle")
    states = _mapping(lifecycle.get("asset_states"), "asset states")
    health = _mapping(audit.get("health"), "audit health")
    assets = _mapping(health.get("assets"), "asset health")
    execution = _mapping(audit.get("execution"), "audit execution")
    fills = _record_list(execution.get("fill_details"), "fill details")
    positions, position_count_matches = _position_index(execution)
    reasons = _state_reasons(states, health, assets)
    open_symbols = _open_symbols(states, assets, reasons)
    reflections, count_matches = _reflection_index(audit)
    exact_symbols = set(reflections) == set(positions) == set(open_symbols)
    if not count_matches or not position_count_matches or not exact_symbols:
        reasons.append("open_lifecycle_projection_mismatch")
    if not open_symbols:
        return OpenLifecycleValidation(tuple(reasons), 0)
    for symbol in set(open_symbols).intersection(reflections):
        reasons.extend(
            _reflection_reasons(
                symbol,
                reflections[symbol],
                positions.get(symbol),
                assets[symbol],
                fills,
                execution.get("history_run_ids"),
                config,
            )
        )
    return OpenLifecycleValidation(tuple(reasons), len(open_symbols))


def _state_reasons(states: Record, health: Record, assets: Record) -> list[str]:
    reasons: list[str] = []
    if set(states) != set(_SYMBOLS) or set(assets) != set(_SYMBOLS):
        reasons.append("asset_health_roster_mismatch")
    if _nonnegative_int(health.get("faults"), "health faults") != 0:
        reasons.append("runtime_faults_present")
    return reasons


def _open_symbols(states: Record, assets: Record, reasons: list[str]) -> list[str]:
    output: list[str] = []
    for symbol in set(_SYMBOLS).intersection(states, assets):
        row = _mapping(assets[symbol], f"{symbol} health")
        state = row.get("final_state")
        if state not in {"FLAT", "OPEN"} or states[symbol] != state:
            reasons.append(f"asset_state_inconsistent:{symbol}")
        if state != "OPEN":
            continue
        output.append(symbol)
        if row.get("protected_if_open") is not True or row.get("stop_oid") is None:
            reasons.append(f"open_position_unprotected:{symbol}")
    return output


def _reflection_index(audit: Record) -> tuple[dict[str, Record], bool]:
    value = audit.get("open_trade_reflections")
    if value is None:
        return {}, True
    section = _mapping(value, "open trade reflections")
    rows = _record_list(section.get("trades"), "open trade reflection trades")
    declared = _nonnegative_int(
        section.get("open_lifecycles"), "open trade reflection count"
    )
    output: dict[str, Record] = {}
    for row in rows:
        symbol = _text(row.get("symbol"), "open trade reflection symbol")
        if symbol in output:
            raise ValueError(f"duplicate open trade reflection for {symbol}")
        output[symbol] = row
    return output, declared == len(rows)


def _position_index(execution: Record) -> tuple[dict[str, Record], bool]:
    rows = _record_list(execution.get("open_positions"), "open positions")
    declared = _nonnegative_int(execution.get("open_lifecycles"), "open count")
    output: dict[str, Record] = {}
    for row in rows:
        symbol = _text(row.get("symbol"), "open position symbol")
        if symbol in output:
            raise ValueError(f"duplicate open position for {symbol}")
        output[symbol] = row
    return output, declared == len(rows)


def _reflection_reasons(
    symbol: str,
    reflection: Record,
    position: Record | None,
    health: object,
    fills: tuple[Record, ...],
    history_run_ids: object,
    config: MultiAssetLiveConfig,
) -> list[str]:
    strategy = reflection.get("strategy_id")
    side = reflection.get("side")
    contract = _route_contract(config, strategy, symbol, side)
    if contract is None:
        return [f"open_route_contract_invalid:{symbol}"]
    health_row = _mapping(health, f"{symbol} health")
    entry = _mapping(reflection.get("entry"), f"{symbol} open entry")
    entry_price = _positive_float(entry.get("price"))
    reasons: list[str] = []
    if not open_lifecycle_entry_matches(reflection, fills, history_run_ids):
        reasons.append(f"open_entry_fill_invalid:{symbol}")
    if not _position_matches(reflection, position, health_row, entry_price, side):
        reasons.append(f"open_position_projection_invalid:{symbol}")
    stop_distance = _stop_distance_bps(
        reflection.get("protective_stop"), health_row, entry_price, side
    )
    if not _stop_distance_matches(stop_distance, contract):
        reasons.append(f"open_stop_contract_invalid:{symbol}")
    if not _target_matches(
        reflection.get("target_order"),
        health_row,
        entry_price,
        side,
        stop_distance,
        contract,
    ):
        reasons.append(f"open_target_contract_invalid:{symbol}")
    if not _exit_plan_matches(reflection.get("exit_plan"), contract):
        reasons.append(f"open_exit_plan_contract_invalid:{symbol}")
    return reasons


def _position_matches(
    reflection: Record,
    position: Record | None,
    health: Record,
    entry_price: float | None,
    side: object,
) -> bool:
    marked = reflection.get("marked_economics")
    if position is None or not isinstance(marked, Mapping) or entry_price is None:
        return False
    position_price = _positive_float(position.get("entry_price"))
    position_size = _signed_float(position.get("size_signed"))
    health_size = _signed_float(health.get("position_size_signed"))
    sign_matches = position_size is not None and (
        (side == "long" and position_size > 0.0)
        or (side == "short" and position_size < 0.0)
    )
    return (
        dict(marked) == dict(position)
        and position.get("status") == "provisional_open"
        and position.get("symbol") == reflection.get("symbol")
        and position.get("side") == side
        and reflection.get("target_order") == position.get("target_order")
        and position_price is not None
        and math.isclose(position_price, entry_price, rel_tol=1e-12, abs_tol=1e-9)
        and sign_matches
        and health_size is not None
        and math.isclose(health_size, position_size, abs_tol=1e-9)
    )


def _route_contract(
    config: MultiAssetLiveConfig,
    strategy: object,
    symbol: str,
    side: object,
) -> ProviderExecutionContract | None:
    if not isinstance(strategy, str) or side not in {"long", "short"}:
        return None
    matches = [
        provider
        for provider in config.providers
        if provider.strategy_id == strategy and symbol in provider.execution_symbols
    ]
    if len(matches) != 1 or side not in matches[0].executable_sides(symbol):
        return None
    return matches[0].execution_for(symbol, side)


def _stop_distance_bps(
    value: object,
    health: Record,
    entry_price: float | None,
    side: object,
) -> float | None:
    if not isinstance(value, Mapping) or entry_price is None:
        return None
    oid = _positive_int(value.get("oid"))
    trigger = _positive_float(value.get("trigger_price"))
    open_orders = health.get("open_order_ids")
    if oid is None or trigger is None or not isinstance(open_orders, list):
        return None
    if health.get("stop_oid") != oid or oid not in open_orders:
        return None
    adverse = trigger < entry_price if side == "long" else trigger > entry_price
    if not adverse:
        return None
    return abs(trigger - entry_price) / entry_price * 10_000.0


def _stop_distance_matches(
    distance_bps: float | None,
    contract: ProviderExecutionContract,
) -> bool:
    if distance_bps is None:
        return False
    tolerance = _VENUE_ROUNDING_TOLERANCE_BPS
    if contract.stop_policy == "fixed_bps":
        return abs(distance_bps - float(contract.stop_bps or 0.0)) <= tolerance
    minimum = float(contract.minimum_stop_bps or 0.0)
    maximum = float(contract.maximum_stop_bps or 0.0)
    return minimum - tolerance <= distance_bps <= maximum + tolerance


def _target_matches(
    value: object,
    health: Record,
    entry_price: float | None,
    side: object,
    stop_distance_bps: float | None,
    contract: ProviderExecutionContract,
) -> bool:
    if contract.target_policy == "none":
        return value is None
    if not isinstance(value, Mapping) or entry_price is None:
        return False
    oid = _positive_int(value.get("oid"))
    price = _positive_float(value.get("limit_price"))
    open_orders = health.get("open_order_ids")
    if oid is None or price is None or not isinstance(open_orders, list):
        return False
    favorable = price > entry_price if side == "long" else price < entry_price
    if not favorable or oid not in open_orders:
        return False
    distance = abs(price - entry_price) / entry_price * 10_000.0
    return _target_distance_matches(distance, stop_distance_bps, contract)


def _target_distance_matches(
    distance_bps: float,
    stop_distance_bps: float | None,
    contract: ProviderExecutionContract,
) -> bool:
    tolerance = _VENUE_ROUNDING_TOLERANCE_BPS
    if contract.target_policy == "fixed_bps":
        expected = float(contract.target_bps or 0.0)
        return abs(distance_bps - expected) <= tolerance
    if contract.target_policy == "reward_risk" and stop_distance_bps is not None:
        multiple = float(contract.target_r_multiple or 0.0)
        return abs(distance_bps - stop_distance_bps * multiple) <= tolerance * (
            1.0 + multiple
        )
    return contract.target_policy == "absolute_anchor"


def _exit_plan_matches(value: object, contract: ProviderExecutionContract) -> bool:
    if not isinstance(value, Mapping):
        return False
    expected = {
        "source": "bound_execution_plan",
        "controller": "cohort_maximum_hold",
        "maximum_hold_seconds": contract.maximum_hold_seconds,
        "maximum_hold_policy": contract.maximum_hold_policy,
        "hard_maximum_hold_seconds": contract.hard_maximum_hold_seconds,
        "provider_recipe_exit_policy": contract.provider_recipe_exit_policy,
        "profit_lock_policy": contract.profit_lock_policy,
        "profit_lock_activation_bps": contract.profit_lock_activation_bps,
        "profit_lock_floor_bps": contract.profit_lock_floor_bps,
        "profit_lock_giveback_bps": contract.profit_lock_giveback_bps,
        "opposite_intent_exit_scope": (
            "selected_opposite_from_any_executable_provider_same_symbol"
        ),
        "opposite_intent_arbitration": "regime_then_priority",
    }
    return all(
        _equal_contract_value(value.get(key), expected_value)
        for key, expected_value in expected.items()
    )


def _equal_contract_value(observed: object, expected: object) -> bool:
    if isinstance(expected, float):
        parsed = _positive_float(observed)
        return parsed is not None and math.isclose(parsed, expected, abs_tol=1e-12)
    return type(observed) is type(expected) and observed == expected


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _record_list(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, list) or any(
        not isinstance(row, Mapping) for row in value
    ):
        raise ValueError(f"{label} must be an array of objects")
    return tuple(value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def _positive_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) and parsed > 0.0 else None


def _signed_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) and parsed != 0.0 else None
