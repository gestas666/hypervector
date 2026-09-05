"""Safety contracts for lifecycle-bound provider recipe exits."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

import pytest

from hypervector.live.bidirectional_intents import RoutingAction
from hypervector.live.cohort_execution_plan import (
    BoundExecutionPlan,
    ProviderExecutionContract,
)
from hypervector.live.cohort_provider_exit_controller import (
    CohortProviderExitController,
)
from hypervector.live.multi_asset_live_runner_support import MultiAssetLiveRunnerError
from hypervector.live.multi_asset_signal_source import ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness
from hypervector.live.sol_range_onset_state import SolLiveSnapshot, SolLiveState

_PROVIDER = "hip3_swing_ha_sndk_gold_brent_bidirectional_v1"
_SYMBOL = "xyz:GOLD"
_OPENED_MS = 1_785_584_600_000
_DECISION_MS = 1_785_585_600_000


@dataclass
class _Engine:
    current: SolLiveSnapshot

    @property
    def snapshot(self) -> SolLiveSnapshot:
        return self.current


class _Telemetry:
    def __init__(self) -> None:
        self.decisions: dict[str, dict[str, object]] = {}

    def recorded_provider_exit_decision(
        self, decision_id: str
    ) -> Mapping[str, object] | None:
        return self.decisions.get(decision_id)

    def emit_provider_exit_decision(self, payload: Mapping[str, object]) -> None:
        decision_id = str(payload["decision_id"])
        existing = self.decisions.get(decision_id)
        if existing is not None and existing != dict(payload):
            raise ValueError("conflicting provider exit decision")
        self.decisions[decision_id] = dict(payload)


def _plan(
    strategy_id: str = _PROVIDER,
    *,
    provider_recipe_exit_policy: str = "honor",
) -> BoundExecutionPlan:
    contract = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=80.0,
        target_policy="none",
        maximum_hold_seconds=86_400,
        provider_recipe_exit_policy=provider_recipe_exit_policy,
    )
    return contract.bind(strategy_id=strategy_id, stop_anchor=None)


def _snapshot(
    *,
    side: str = "long",
    strategy_id: str = _PROVIDER,
) -> SolLiveSnapshot:
    return SolLiveSnapshot(
        state=SolLiveState.OPEN,
        entry_oid=1,
        stop_oid=2,
        position_size_signed=1.0 if side == "long" else -1.0,
        opened_at_ms=_OPENED_MS,
        execution_plan=_plan(strategy_id),
    )


def _evaluation(
    *,
    strategy_id: str = _PROVIDER,
    exit_side: str = "long",
    decision_time_ms: int = _DECISION_MS,
) -> ProviderEvaluation:
    return ProviderEvaluation(
        strategy_id=strategy_id,
        symbol=_SYMBOL,
        decision_time_ms=decision_time_ms,
        reference_price=4_350.0,
        decision_action=f"close_{exit_side}",
        eligible=False,
        reason="hip3_swing_ha_flip",
        side=exit_side,
        readiness=SignalReadiness(
            exit_side,
            3,
            4,
            ("heikin_ashi_color_mismatch",),
            ("HA COLOR -1",),
            {"exit_mode": "ha_flip"},
        ),
        exit_sides=frozenset({exit_side}),
        exit_reason="hip3_swing_ha_flip",
    )


def _actions(
    snapshot: SolLiveSnapshot,
    evaluation: ProviderEvaluation | None,
    *,
    observed_ms: int = _DECISION_MS,
    prices: dict[str, float] | None = None,
    telemetry: _Telemetry | None = None,
) -> tuple[set[str], tuple[RoutingAction, ...]]:
    controller = CohortProviderExitController(
        symbols=(_SYMBOL,),
        engines={_SYMBOL: _Engine(snapshot)},
        telemetry=telemetry or _Telemetry(),
    )
    return controller.actions(
        observed_ms=observed_ms,
        reference_prices=prices if prices is not None else {_SYMBOL: 4_349.5},
        evaluations=(
            {}
            if evaluation is None
            else {(evaluation.strategy_id, _SYMBOL): evaluation}
        ),
        excluded_symbols=set(),
    )


def test_exact_bound_provider_exit_preserves_reason_and_current_mark() -> None:
    closing, actions = _actions(_snapshot(), _evaluation())

    assert closing == {_SYMBOL}
    assert len(actions) == 1
    assert actions[0].strategy_id == _PROVIDER
    assert actions[0].side == "long"
    assert actions[0].reference_price == 4_349.5
    assert actions[0].exit_reason == "hip3_swing_ha_flip"


def test_manual_provider_entry_retains_automatic_recipe_exit() -> None:
    snapshot = _snapshot(strategy_id=f"operator_override:{_PROVIDER}")

    closing, actions = _actions(snapshot, _evaluation())

    assert closing == {_SYMBOL}
    assert actions[0].strategy_id == _PROVIDER


@pytest.mark.parametrize(
    ("snapshot", "evaluation"),
    (
        (_snapshot(), _evaluation(strategy_id="different_provider")),
        (_snapshot(side="short"), _evaluation(exit_side="long")),
        (_snapshot(), _evaluation(decision_time_ms=_OPENED_MS - 1)),
    ),
)
def test_unbound_wrong_side_or_preentry_exit_cannot_close(
    snapshot: SolLiveSnapshot,
    evaluation: ProviderEvaluation,
) -> None:
    assert _actions(snapshot, evaluation) == (set(), ())


def test_future_recipe_exit_fails_closed() -> None:
    with pytest.raises(MultiAssetLiveRunnerError, match="lies in the future"):
        _actions(
            _snapshot(),
            _evaluation(decision_time_ms=_DECISION_MS + 1),
        )


def test_recipe_exit_requires_current_execution_reference() -> None:
    with pytest.raises(MultiAssetLiveRunnerError, match="reference price"):
        _actions(_snapshot(), _evaluation(), prices={})


def test_recipe_exit_is_telemetry_only_without_explicit_plan_authority() -> None:
    """The selected deployed default must keep rejected signal exits inactive."""
    snapshot = SolLiveSnapshot(
        state=SolLiveState.OPEN,
        entry_oid=1,
        stop_oid=2,
        position_size_signed=1.0,
        opened_at_ms=_OPENED_MS,
        execution_plan=_plan(provider_recipe_exit_policy="ignore"),
    )
    telemetry = _Telemetry()

    assert _actions(snapshot, _evaluation(), telemetry=telemetry) == (set(), ())
    assert telemetry.decisions == {}


def test_persisted_recipe_exit_replays_after_controller_restart() -> None:
    """A one-bar exit remains enforceable after its source evaluation disappears."""
    telemetry = _Telemetry()
    closing, actions = _actions(_snapshot(), _evaluation(), telemetry=telemetry)

    assert closing == {_SYMBOL}
    assert len(actions) == 1
    assert tuple(telemetry.decisions) == (f"{_SYMBOL}:1:provider_recipe_exit",)

    recovered_closing, recovered = _actions(
        _snapshot(),
        None,
        observed_ms=_DECISION_MS + 60_000,
        prices={_SYMBOL: 4_351.0},
        telemetry=telemetry,
    )

    assert recovered_closing == {_SYMBOL}
    assert len(recovered) == 1
    assert recovered[0].decision_time_ms == _DECISION_MS
    assert recovered[0].reference_price == 4_351.0
    assert recovered[0].exit_reason == "hip3_swing_ha_flip"


def test_restart_closes_when_recipe_exit_scan_does_not_cover_open_lifecycle() -> None:
    """An old position must not survive an unverifiable missed-exit interval."""
    readiness = replace(
        _evaluation().readiness,
        metrics={
            "pre_activation_scan_start_ms": _OPENED_MS + 1,
            "pre_activation_scan_end_ms": _DECISION_MS,
        },
    )
    seed = replace(
        _evaluation(),
        decision_action="hold",
        reason="entry_condition_absent",
        readiness=readiness,
        exit_sides=frozenset(),
        exit_reason=None,
        backend_non_action_reason="pre_activation_readiness_seed",
    )

    closing, actions = _actions(_snapshot(), seed)

    assert closing == {_SYMBOL}
    assert actions[0].decision_time_ms == _DECISION_MS
    assert actions[0].exit_reason == "provider_recipe_exit_recovery_unverified"


def test_restart_keeps_position_when_scan_covers_it_without_an_exit() -> None:
    """A complete post-entry scan must not manufacture a recipe exit."""
    readiness = replace(
        _evaluation().readiness,
        metrics={
            "pre_activation_scan_start_ms": _OPENED_MS,
            "pre_activation_scan_end_ms": _DECISION_MS,
        },
    )
    seed = replace(
        _evaluation(),
        decision_action="hold",
        reason="entry_condition_absent",
        readiness=readiness,
        exit_sides=frozenset(),
        exit_reason=None,
        backend_non_action_reason="pre_activation_readiness_seed",
    )

    assert _actions(_snapshot(), seed) == (set(), ())
