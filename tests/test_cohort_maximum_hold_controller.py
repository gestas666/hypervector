"""Restart-safe maximum-hold control tests."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.live.cohort_maximum_hold_controller import (
    CohortMaximumHoldController,
)
from hypervector.live.cohort_maximum_hold_policy import EvaluationKey
from hypervector.live.provider_evaluation import ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness
from hypervector.live.sol_range_onset_state import SolLiveSnapshot, SolLiveState


class _Engine:
    def __init__(self, snapshot: SolLiveSnapshot) -> None:
        self._snapshot = snapshot

    @property
    def snapshot(self) -> SolLiveSnapshot:
        return self._snapshot


class _Telemetry:
    def __init__(self) -> None:
        self.decisions: dict[str, dict[str, object]] = {}

    def recorded_maximum_hold_decision(
        self, decision_id: str
    ) -> Mapping[str, object] | None:
        return self.decisions.get(decision_id)

    def emit_maximum_hold_decision(self, payload: Mapping[str, object]) -> None:
        decision_id = str(payload["decision_id"])
        existing = self.decisions.get(decision_id)
        if existing is not None and existing != dict(payload):
            raise ValueError("conflicting maximum-hold decision")
        self.decisions[decision_id] = dict(payload)


def test_supported_soft_decision_is_idempotent_across_controller_restart() -> None:
    """Recovery consults the durable decision rather than an empty local cache."""
    opened_at_ms = 1_000_000
    observed_ms = opened_at_ms + 28_800_000
    engine = _Engine(_open_snapshot(opened_at_ms))
    telemetry = _Telemetry()
    evaluations = _supported_evaluations(observed_ms)

    first = _controller(engine, telemetry)
    assert first.actions(observed_ms, {"HYPE": 55.0}, evaluations) == (set(), ())
    restarted = _controller(engine, telemetry)
    assert restarted.actions(
        observed_ms + 60_000,
        {"HYPE": 55.1},
        _supported_evaluations(observed_ms + 60_000),
    ) == (set(), ())

    assert tuple(telemetry.decisions) == ("HYPE:99:soft_maximum_hold",)
    assert telemetry.decisions["HYPE:99:soft_maximum_hold"]["outcome"] == "extend"


def test_extended_lifecycle_records_terminal_exit_once_across_restart() -> None:
    """The exit after an extension has one durable causal terminal record."""
    opened_at_ms = 1_000_000
    soft_ms = opened_at_ms + 28_800_000
    engine = _Engine(_open_snapshot(opened_at_ms))
    telemetry = _Telemetry()
    controller = _controller(engine, telemetry)
    assert controller.actions(
        soft_ms,
        {"HYPE": 55.0},
        _supported_evaluations(soft_ms),
    ) == (set(), ())

    expired, actions = controller.actions(soft_ms + 60_000, {"HYPE": 54.0}, {})

    assert expired == {"HYPE"}
    assert len(actions) == 1
    assert actions[0].exit_reason == "maximum_hold_evidence_missing"
    terminal_id = "HYPE:99:terminal_maximum_hold"
    assert telemetry.decisions[terminal_id]["decision_stage"] == "terminal"
    assert telemetry.decisions[terminal_id]["outcome"] == "exit"
    assert telemetry.decisions[terminal_id]["trigger_decision_id"] == (
        "HYPE:99:soft_maximum_hold"
    )

    _, recovered = _controller(engine, telemetry).actions(
        soft_ms + 120_000,
        {"HYPE": 55.0},
        _supported_evaluations(soft_ms + 120_000),
    )
    assert len(recovered) == 1
    assert recovered[0].exit_reason == "maximum_hold_evidence_missing"
    assert len(telemetry.decisions) == 2


def test_unsupported_soft_boundary_emits_exit_action_and_decision() -> None:
    """A persisted exit remains enforceable after recovery despite regime change."""
    opened_at_ms = 1_000_000
    observed_ms = opened_at_ms + 28_800_000
    engine = _Engine(_open_snapshot(opened_at_ms))
    telemetry = _Telemetry()

    expired, actions = _controller(engine, telemetry).actions(
        observed_ms,
        {"HYPE": 54.0},
        {},
    )

    assert expired == {"HYPE"}
    assert len(actions) == 1
    assert actions[0].action == "close"
    assert actions[0].exit_reason == "maximum_hold_evidence_missing"
    decision = telemetry.decisions["HYPE:99:soft_maximum_hold"]
    assert decision["outcome"] == "exit"
    assert decision["exit_reason"] == "maximum_hold_evidence_missing"
    assert decision["maximum_hold_evidence_status"] == ("maximum_hold_evidence_missing")

    _, recovered_actions = _controller(engine, telemetry).actions(
        observed_ms + 60_000,
        {"HYPE": 55.0},
        _supported_evaluations(observed_ms + 60_000),
    )
    assert len(recovered_actions) == 1
    assert recovered_actions[0].exit_reason == "maximum_hold_evidence_missing"
    assert len(telemetry.decisions) == 1


def _controller(engine: _Engine, telemetry: _Telemetry) -> CohortMaximumHoldController:
    return CohortMaximumHoldController(
        symbols=("HYPE",),
        engines={"HYPE": engine},
        fallback_hold_ms={"HYPE": 28_800_000},
        telemetry=telemetry,
    )


def _open_snapshot(opened_at_ms: int) -> SolLiveSnapshot:
    plan = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=80.0,
        target_policy="none",
        maximum_hold_seconds=28_800,
        maximum_hold_policy="extend_while_regime_supported",
        hard_maximum_hold_seconds=86_400,
        maximum_hold_evidence_maximum_age_seconds=60,
    ).bind(strategy_id="hype", stop_anchor=None)
    return SolLiveSnapshot(
        state=SolLiveState.OPEN,
        entry_oid=99,
        stop_oid=100,
        position_size_signed=1.0,
        opened_at_ms=opened_at_ms,
        execution_plan=plan,
    )


def _supported_evaluations(observed_ms: int) -> dict[EvaluationKey, ProviderEvaluation]:
    return {
        (strategy, "HYPE"): _evaluation(strategy, observed_ms)
        for strategy in ("hype", "range_onset_bidirectional_v1")
    }


def _evaluation(strategy_id: str, observed_ms: int) -> ProviderEvaluation:
    return ProviderEvaluation(
        strategy_id=strategy_id,
        symbol="HYPE",
        decision_time_ms=observed_ms,
        reference_price=55.0,
        decision_action="hold",
        eligible=False,
        reason="test",
        side="long",
        readiness=SignalReadiness("long", 1, 1, (), ("TEST",), {}),
        primary_regime="TREND_UP",
        state_1m="TREND_UP",
        state_5m="TREND_UP",
        context_15m="TREND_UP",
    )
