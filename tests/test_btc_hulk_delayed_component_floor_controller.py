"""Live-controller integration for the BTC Hulk delayed component floor."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pytest

from hypervector.live.bidirectional_intents import RoutingAction
from hypervector.live.btc_hulk_delayed_component_floor import (
    BTC_HULK_DELAYED_COMPONENT_EXIT_POLICY,
    BTC_HULK_DELAYED_COMPONENT_FLOOR_POLICY,
    ComponentFloorObservation,
)
from hypervector.live.btc_hulk_robust_short_provider import (
    HULK_ROBUST_SHORT_STRATEGY,
)
from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.live.cohort_profit_lock_controller import CohortProfitLockController
from hypervector.live.multi_asset_market_bars import CohortMarketBar
from hypervector.live.sol_range_onset_state import SolLiveSnapshot, SolLiveState

_SYMBOL = "BTC"
_MINUTE_MS = 60_000
_DELAY_MS = 4 * 60 * _MINUTE_MS
_WARMUP_MS = BTC_HULK_DELAYED_COMPONENT_FLOOR_POLICY.warmup_ms
_OPENED_MS = 2 * _WARMUP_MS
_LIFECYCLE_FIRST_MS = _OPENED_MS + _MINUTE_MS
_SEED_START_MS = _LIFECYCLE_FIRST_MS - _WARMUP_MS


@dataclass
class _Engine:
    current: SolLiveSnapshot

    @property
    def snapshot(self) -> SolLiveSnapshot:
        return self.current


class _Telemetry:
    def __init__(self) -> None:
        self.decisions: dict[str, dict[str, object]] = {}
        self.degraded: list[tuple[str, str]] = []

    def recorded_profit_lock_decision(
        self, decision_id: str
    ) -> Mapping[str, object] | None:
        return self.decisions.get(decision_id)

    def emit_profit_lock_decision(self, payload: Mapping[str, object]) -> None:
        self.decisions[str(payload["decision_id"])] = dict(payload)

    def emit_poll_degraded(self, *, source: str, reason: str) -> None:
        self.degraded.append((source, reason))


def _snapshot() -> SolLiveSnapshot:
    contract = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="structural_clamped_bps",
        minimum_stop_bps=20.0,
        maximum_stop_bps=75.0,
        target_policy="reward_risk",
        target_r_multiple=3.0,
        maximum_hold_seconds=86_400,
        profit_lock_policy=BTC_HULK_DELAYED_COMPONENT_EXIT_POLICY.policy_id,
    )
    plan = contract.bind(
        strategy_id=HULK_ROBUST_SHORT_STRATEGY,
        stop_anchor=101.0,
    )
    return SolLiveSnapshot(
        state=SolLiveState.OPEN,
        entry_oid=7,
        stop_oid=8,
        target_oid=9,
        position_size_signed=-1.0,
        opened_at_ms=_OPENED_MS,
        execution_plan=plan,
    )


def _bars(
    last_timestamp_ms: int, *, first_timestamp_ms: int = _SEED_START_MS
) -> tuple[CohortMarketBar, ...]:
    return tuple(
        CohortMarketBar(_SYMBOL, value, 100.0, 100.1, 99.9, 100.0, 1.0)
        for value in range(first_timestamp_ms, last_timestamp_ms + 1, _MINUTE_MS)
    )


def test_specialized_reversal_containment_preserves_the_existing_3r_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bound 3R plan can add one causal delayed-floor close authority."""
    observations = (
        ComponentFloorObservation(
            _OPENED_MS + _DELAY_MS - _MINUTE_MS,
            100.1,
            100.2,
            99.0,
            100.1,
            (1, 1, 1, 1, 1, 1),
        ),
        ComponentFloorObservation(
            _OPENED_MS + _DELAY_MS,
            100.1,
            100.2,
            100.0,
            100.1,
            (1, 1, 1, 1, 1, 1),
        ),
    )

    def observations_from_anchored_bars(
        bars: tuple[CohortMarketBar, ...], *, lifecycle_start_ms: int
    ) -> tuple[ComponentFloorObservation, ...]:
        assert lifecycle_start_ms == _LIFECYCLE_FIRST_MS
        assert bars[0].timestamp_ms == _SEED_START_MS
        return observations

    monkeypatch.setattr(
        "hypervector.live.cohort_profit_lock_controller."
        "build_btc_hulk_component_floor_observations",
        observations_from_anchored_bars,
    )
    telemetry = _Telemetry()
    observed_ms = _OPENED_MS + _DELAY_MS + 2 * _MINUTE_MS
    controller = CohortProfitLockController(
        symbols=(_SYMBOL,),
        engines={_SYMBOL: _Engine(_snapshot())},
        telemetry=telemetry,
    )

    closing, actions = controller.actions(
        observed_ms=observed_ms,
        reference_prices={_SYMBOL: 100.12},
        entry_prices={_SYMBOL: 100.0},
        market_bars={
            _SYMBOL: _bars(
                observed_ms - _MINUTE_MS,
                first_timestamp_ms=_SEED_START_MS - 10 * _MINUTE_MS,
            )
        },
        excluded_symbols=set(),
    )

    assert closing == {_SYMBOL}
    assert actions == (
        RoutingAction(
            "close",
            HULK_ROBUST_SHORT_STRATEGY,
            _SYMBOL,
            "short",
            _OPENED_MS + _DELAY_MS + _MINUTE_MS,
            100.12,
            exit_reason="btc_hulk_delayed_component_reversal_containment",
        ),
    )
    decision = telemetry.decisions[f"{_SYMBOL}:7:profit_lock_exit"]
    assert decision["profit_lock_policy"] == (
        BTC_HULK_DELAYED_COMPONENT_EXIT_POLICY.policy_id
    )
    assert decision["component_exit_activation_mode"] == "reversal_containment"
    assert decision["target_policy"] == "reward_risk"
    assert decision["target_r_multiple"] == 3.0


def test_specialized_floor_withholds_when_anchored_warmup_is_incomplete() -> None:
    """Missing component seed history degrades one cycle without inventing a gate."""
    telemetry = _Telemetry()
    observed_ms = _OPENED_MS + _DELAY_MS + 2 * _MINUTE_MS
    controller = CohortProfitLockController(
        symbols=(_SYMBOL,),
        engines={_SYMBOL: _Engine(_snapshot())},
        telemetry=telemetry,
    )

    closing, actions = controller.actions(
        observed_ms=observed_ms,
        reference_prices={_SYMBOL: 99.84},
        entry_prices={_SYMBOL: 100.0},
        market_bars={
            _SYMBOL: _bars(
                observed_ms - _MINUTE_MS,
                first_timestamp_ms=_SEED_START_MS + _MINUTE_MS,
            )
        },
        excluded_symbols=set(),
    )

    assert closing == set()
    assert actions == ()
    assert controller.cycle_degraded is True
    assert telemetry.degraded[0][0] == "profit_lock_component_candles"
