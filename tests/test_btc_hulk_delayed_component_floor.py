"""Causal policy tests for the BTC Hulk delayed component profit floor."""

from __future__ import annotations

import pytest

from hypervector.live.btc_hulk_delayed_component_floor import (
    BTC_HULK_DELAYED_COMPONENT_EXIT_POLICY,
    BTC_HULK_DELAYED_COMPONENT_FLOOR_POLICY,
    ComponentFloorObservation,
    build_btc_hulk_component_floor_observations,
    evaluate_delayed_component_floor,
)
from hypervector.live.multi_asset_market_bars import CohortMarketBar

_MINUTE_MS = 60_000
_DELAY_MS = 4 * 60 * _MINUTE_MS


def test_v2_policy_freezes_the_partition_robust_candidate() -> None:
    """The current policy must version the candidate that improved every partition."""
    policy = BTC_HULK_DELAYED_COMPONENT_EXIT_POLICY

    assert policy.policy_id == "btc_hulk_delayed_component_exit_v2"
    assert policy.delay_ms == _DELAY_MS
    assert policy.activation_r_multiple == 0.75
    assert policy.floor_r_multiple == 0.50
    assert policy.opposed_components_required == 6


def _row(
    timestamp_ms: int,
    *,
    open_price: float = 99.85,
    high: float = 99.90,
    low: float = 99.20,
    directions: tuple[int | None, ...] = (1, 1, 1, 1, 1, 1),
) -> ComponentFloorObservation:
    return ComponentFloorObservation(
        timestamp_ms=timestamp_ms,
        open=open_price,
        high=high,
        low=low,
        close=open_price,
        component_directions=directions,
    )


def test_delayed_floor_arms_only_after_time_mfe_and_full_opposition() -> None:
    """A pre-delay 1R move cannot arm the floor before its causal boundary."""
    rows = (
        _row(_DELAY_MS - 2 * _MINUTE_MS, high=100.20, low=99.00),
        _row(
            _DELAY_MS - _MINUTE_MS,
            open_price=99.50,
            high=99.60,
            low=99.20,
        ),
        _row(_DELAY_MS, open_price=99.85, high=99.90, low=99.70),
    )

    result = evaluate_delayed_component_floor(
        BTC_HULK_DELAYED_COMPONENT_FLOOR_POLICY,
        side="short",
        observations=rows,
        opened_at_ms=0,
        entry_price=100.0,
        protective_stop_price=100.75,
    )

    assert result.state == "triggered"
    assert result.activation_mode == "profit_floor"
    assert result.activation_timestamp_ms == _DELAY_MS - _MINUTE_MS
    assert result.active_stop_price is None
    assert result.trigger is not None
    assert result.trigger.trigger_timestamp_ms == _DELAY_MS
    assert result.trigger.stop_price == pytest.approx(99.625)
    assert result.trigger.reference_price == pytest.approx(99.85)


def test_activation_bar_cannot_trigger_its_new_floor() -> None:
    """The floor becomes executable only on a later completed bar."""
    activation = _row(
        _DELAY_MS - _MINUTE_MS,
        open_price=99.50,
        high=100.20,
        low=99.00,
    )

    result = evaluate_delayed_component_floor(
        BTC_HULK_DELAYED_COMPONENT_FLOOR_POLICY,
        side="short",
        observations=(activation,),
        opened_at_ms=0,
        entry_price=100.0,
        protective_stop_price=100.75,
    )

    assert result.state == "armed"
    assert result.activation_mode == "profit_floor"
    assert result.activation_timestamp_ms == activation.timestamp_ms
    assert result.active_stop_price == pytest.approx(99.625)
    assert result.trigger is None


def test_late_opposition_arms_named_reversal_containment() -> None:
    """Late opposition is explicit containment rather than a false profit floor."""
    activation = _row(
        _DELAY_MS - _MINUTE_MS,
        open_price=100.10,
        high=100.20,
        low=99.00,
    )
    confirmation = _row(
        _DELAY_MS,
        open_price=100.10,
        high=100.20,
        low=100.00,
    )

    result = evaluate_delayed_component_floor(
        BTC_HULK_DELAYED_COMPONENT_EXIT_POLICY,
        side="short",
        observations=(activation, confirmation),
        opened_at_ms=0,
        entry_price=100.0,
        protective_stop_price=100.75,
    )

    assert result.state == "triggered"
    assert result.activation_mode == "reversal_containment"
    assert result.activation_timestamp_ms == activation.timestamp_ms
    assert result.active_stop_price is None
    assert result.trigger is not None
    assert result.trigger.trigger_timestamp_ms == confirmation.timestamp_ms


def test_retrace_between_floor_and_entry_does_not_arm_containment() -> None:
    """A still-profitable retrace is neither a floor nor a loss-containment exit."""
    ambiguous = _row(
        _DELAY_MS - _MINUTE_MS,
        open_price=99.80,
        high=99.90,
        low=99.00,
    )

    result = evaluate_delayed_component_floor(
        BTC_HULK_DELAYED_COMPONENT_EXIT_POLICY,
        side="short",
        observations=(ambiguous,),
        opened_at_ms=0,
        entry_price=100.0,
        protective_stop_price=100.75,
    )

    assert result.state == "not_activated"
    assert result.activation_mode is None
    assert result.trigger is None


def test_floor_requires_every_declared_component_to_oppose() -> None:
    """Five opposed components and one neutral component cannot arm the policy."""
    row = _row(
        _DELAY_MS - _MINUTE_MS,
        low=99.00,
        directions=(1, 1, 1, 1, 1, 0),
    )

    result = evaluate_delayed_component_floor(
        BTC_HULK_DELAYED_COMPONENT_FLOOR_POLICY,
        side="short",
        observations=(row,),
        opened_at_ms=0,
        entry_price=100.0,
        protective_stop_price=100.75,
    )

    assert result.state == "not_activated"
    assert result.maximum_opposed_components == 5
    assert result.trigger is None


def test_missing_component_evidence_is_counted_without_inventing_opposition() -> None:
    """Unavailable component values fail closed and remain observable."""
    row = _row(
        _DELAY_MS - _MINUTE_MS,
        low=99.00,
        directions=(1, 1, 1, 1, 1, None),
    )

    result = evaluate_delayed_component_floor(
        BTC_HULK_DELAYED_COMPONENT_FLOOR_POLICY,
        side="short",
        observations=(row,),
        opened_at_ms=0,
        entry_price=100.0,
        protective_stop_price=100.75,
    )

    assert result.state == "not_activated"
    assert result.unavailable_gate_observations == 1


def test_component_projection_is_causal_under_one_future_bar() -> None:
    """A future completed bar cannot revise an earlier component observation."""
    bars = tuple(
        CohortMarketBar(
            "BTC",
            index * _MINUTE_MS,
            100.0 + index / 100.0,
            100.2 + index / 100.0,
            99.8 + index / 100.0,
            100.1 + index / 100.0,
            1.0 + index % 7,
        )
        for index in range(1, 902)
    )
    start = 600 * _MINUTE_MS

    prefix = build_btc_hulk_component_floor_observations(
        bars[:-1], lifecycle_start_ms=start
    )
    extended = build_btc_hulk_component_floor_observations(
        bars, lifecycle_start_ms=start
    )

    assert prefix == extended[:-1]
    assert all(value is not None for value in prefix[-1].component_directions)
