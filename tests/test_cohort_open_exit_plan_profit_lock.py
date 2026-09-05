"""Open-lifecycle projection of authoritative profit-lock contracts."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_open_exit_plan import build_open_exit_plan


def test_bound_profit_lock_is_projected_with_timer_contract() -> None:
    """The checkpoint exposes exact enabled lock settings from the bound plan."""
    plan = _asset_contract() | {
        "strategy_id": "provider",
        "profit_lock_policy": "completed_bar_trailing",
        "profit_lock_activation_bps": 25.0,
        "profit_lock_floor_bps": 15.0,
        "profit_lock_giveback_bps": 10.0,
    }

    projected = build_open_exit_plan(
        "BTC",
        "provider",
        {"venue_timestamp_ms": 1_000},
        2_000,
        _records(plan),
        "mixed_or_transition",
        1_000,
    )

    assert projected["profit_lock_policy"] == "completed_bar_trailing"
    assert projected["profit_lock_activation_bps"] == pytest.approx(25.0)
    assert projected["profit_lock_floor_bps"] == pytest.approx(15.0)
    assert projected["profit_lock_giveback_bps"] == pytest.approx(10.0)


def test_bound_btc_component_floor_projects_named_policy_without_fixed_bps() -> None:
    """The BTC component-floor policy owns its parameters outside generic bps fields."""
    plan = _asset_contract() | {
        "strategy_id": "provider",
        "profit_lock_policy": "btc_hulk_delayed_component_floor_v1",
        "profit_lock_activation_bps": None,
        "profit_lock_floor_bps": None,
        "profit_lock_giveback_bps": None,
    }

    projected = build_open_exit_plan(
        "BTC",
        "provider",
        {"venue_timestamp_ms": 1_000},
        2_000,
        _records(plan),
        "still_directionally_supported",
        1_000,
    )

    assert projected["profit_lock_policy"] == "btc_hulk_delayed_component_floor_v1"
    assert projected["profit_lock_activation_bps"] is None
    assert projected["profit_lock_floor_bps"] is None
    assert projected["profit_lock_giveback_bps"] is None


def test_legacy_asset_timer_projects_disabled_profit_lock() -> None:
    """A planless legacy position cannot acquire hidden profit-lock authority."""
    projected = build_open_exit_plan(
        "BTC",
        "provider",
        {"venue_timestamp_ms": 1_000},
        2_000,
        _records(None),
        "unavailable",
        None,
    )

    assert projected["profit_lock_policy"] == "none"
    assert projected["profit_lock_activation_bps"] is None
    assert projected["profit_lock_floor_bps"] is None
    assert projected["profit_lock_giveback_bps"] is None


def _records(plan: dict[str, object] | None) -> tuple[dict[str, object], ...]:
    configured = {"symbol": "BTC"} | _asset_contract()
    rows: list[dict[str, object]] = [
        {
            "event_type": "configuration_identity",
            "payload": {"assets": [configured]},
        }
    ]
    if plan is not None:
        rows.append(
            {
                "event_type": "cohort_snapshot",
                "payload": {"assets": [{"symbol": "BTC", "execution_plan": plan}]},
            }
        )
    return tuple(rows)


def _asset_contract() -> dict[str, object]:
    return {
        "entry_liquidity": "taker_ioc",
        "stop_policy": "fixed_bps",
        "stop_bps": 80.0,
        "target_policy": "none",
        "maximum_hold_seconds": 86_400,
        "maximum_hold_policy": "fixed",
        "provider_recipe_exit_policy": "ignore",
    }
