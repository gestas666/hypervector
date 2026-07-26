"""Declared safe migrations for persistent shadow portfolio specifications."""

from __future__ import annotations

from typing import Mapping


_EVENT_ADDITIONS: dict[str, object] = {
    "legacy_comparator": "legacy_bar_through_v1",
    "submit_latency_ms": 50,
    "cancel_latency_ms": 50,
    "update_latency_ms": 50,
    "max_event_age_ms": 3000,
    "restart_queue_policy": "requeue_behind_displayed_liquidity",
    "liquidation_execution_model": "hyperliquid_market_liquidation_v2",
    "partial_liquidation_supported": True,
    "partial_liquidation_threshold_usd": 100_000.0,
    "partial_liquidation_fraction": 0.20,
    "liquidation_cooldown_ms": 30_000,
    "backstop_liquidation_supported": True,
    "backstop_maintenance_fraction": 2.0 / 3.0,
    "backstop_accounting_model": "isolated_margin_transfer_composite_v1",
}


def migrated_portfolio_spec(
    recorded_spec: Mapping[str, object],
    expected_spec: Mapping[str, object],
) -> dict[str, object] | None:
    """Return a declared safe migration, or None for an incompatible change."""
    recorded = recorded_spec.get("execution")
    expected = expected_spec.get("execution")
    if not isinstance(recorded, dict) or not isinstance(expected, dict):
        return None
    execution = dict(recorded)
    changed = _add_entry_policies(execution, expected)
    changed |= _migrate_event_authority(execution, expected)
    changed |= _add_expected_event_fields(execution, expected)
    changed |= _migrate_liquidation_model(execution, expected)
    if not changed:
        return None
    return {**recorded_spec, "execution": execution}


def _add_entry_policies(
    execution: dict[str, object],
    expected: Mapping[str, object],
) -> bool:
    changed = False
    for key in ("expired_entry_rearm_policy", "same_direction_reentry_policy"):
        if key not in execution and expected.get(key) == "regime_reset":
            execution[key] = "regime_reset"
            changed = True
    return changed


def _migrate_event_authority(
    execution: dict[str, object],
    expected: Mapping[str, object],
) -> bool:
    legacy = (
        execution.get("fill_rule") == "through_one_tick"
        and execution.get("fill_model") == "post_only_limit_through_v1"
    )
    event = (
        expected.get("fill_rule") == "public_l2_trade_event_tape"
        and expected.get("fill_model") == "nautilus_event_v1"
    )
    if not legacy or not event:
        return False
    execution["fill_rule"] = "public_l2_trade_event_tape"
    execution["fill_model"] = "nautilus_event_v1"
    return True


def _add_expected_event_fields(
    execution: dict[str, object],
    expected: Mapping[str, object],
) -> bool:
    changed = False
    for key, required in _EVENT_ADDITIONS.items():
        if key not in execution and expected.get(key) == required:
            execution[key] = required
            changed = True
    return changed


def _migrate_liquidation_model(
    execution: dict[str, object],
    expected: Mapping[str, object],
) -> bool:
    legacy = (
        execution.get("liquidation_execution_model")
        == "full_at_mark_shadow_approximation_v1"
        and execution.get("partial_liquidation_supported") is False
    )
    event = (
        expected.get("liquidation_execution_model")
        == "hyperliquid_market_liquidation_v2"
        and expected.get("partial_liquidation_supported") is True
    )
    if not legacy or not event:
        return False
    execution["liquidation_execution_model"] = "hyperliquid_market_liquidation_v2"
    execution["partial_liquidation_supported"] = True
    return True
