"""Restart-safe maximum-hold actions for open cohort lifecycles."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.live.bidirectional_intents import RoutingAction
from hypervector.live.cohort_maximum_hold_policy import (
    EvaluationMap,
    maximum_hold_decision_payload,
    maximum_hold_terminal_decision_payload,
    resolve_maximum_hold_exit_reason,
)
from hypervector.live.multi_asset_live_protocols import (
    CohortTelemetryProtocol,
    MultiAssetEngineProtocol,
)
from hypervector.live.multi_asset_live_runner_support import (
    MultiAssetLiveRunnerError,
    position_side,
)
from hypervector.live.sol_range_onset_state import SolLiveSnapshot, SolLiveState


class CohortMaximumHoldController:
    """Resolve timer exits and journal each soft boundary durably once."""

    def __init__(
        self,
        *,
        symbols: tuple[str, ...],
        engines: Mapping[str, MultiAssetEngineProtocol],
        fallback_hold_ms: Mapping[str, int],
        telemetry: CohortTelemetryProtocol,
    ) -> None:
        """Bind exact symbols, protected engines, timers, and durable telemetry."""
        self._symbols = symbols
        self._engines = engines
        self._fallback_hold_ms = fallback_hold_ms
        self._telemetry = telemetry

    def actions(
        self,
        observed_ms: int,
        reference_prices: Mapping[str, float],
        evaluations: EvaluationMap,
    ) -> tuple[set[str], tuple[RoutingAction, ...]]:
        """Return deterministic close actions and their same-cycle exclusions."""
        actions: list[RoutingAction] = []
        expired: set[str] = set()
        for symbol in self._symbols:
            action = self._action(symbol, observed_ms, reference_prices, evaluations)
            if action is None:
                continue
            expired.add(symbol)
            actions.append(action)
        return expired, tuple(actions)

    def _action(
        self,
        symbol: str,
        observed_ms: int,
        reference_prices: Mapping[str, float],
        evaluations: EvaluationMap,
    ) -> RoutingAction | None:
        snapshot = self._engines[symbol].snapshot
        if snapshot.state is not SolLiveState.OPEN:
            return None
        opened = snapshot.opened_at_ms
        if opened is None or opened > observed_ms:
            raise MultiAssetLiveRunnerError(
                f"{symbol} open position has an invalid opened_at_ms"
            )
        side = position_side(snapshot.position_size_signed)
        if side is None:
            raise MultiAssetLiveRunnerError(
                f"{symbol} maximum-hold exit lacks a position side"
            )
        soft_decision = self._soft_decision(
            snapshot, symbol, side, opened, observed_ms, evaluations
        )
        reason = resolve_maximum_hold_exit_reason(
            plan=snapshot.execution_plan,
            symbol=symbol,
            side=side,
            elapsed_ms=observed_ms - opened,
            fallback_hold_ms=self._fallback_hold_ms[symbol],
            evaluations=evaluations,
        )
        terminal = self._terminal_decision(
            snapshot=snapshot,
            symbol=symbol,
            side=side,
            opened_at_ms=opened,
            observed_ms=observed_ms,
            evaluations=evaluations,
            soft_decision=soft_decision,
            current_reason=reason,
        )
        reason = _persisted_exit_reason(terminal or soft_decision, reason)
        if reason is None:
            return None
        return _close_action(symbol, side, observed_ms, reference_prices, reason)

    def _soft_decision(
        self,
        snapshot: SolLiveSnapshot,
        symbol: str,
        side: str,
        opened_at_ms: int,
        observed_ms: int,
        evaluations: EvaluationMap,
    ) -> Mapping[str, object] | None:
        plan, entry_oid = snapshot.execution_plan, snapshot.entry_oid
        if plan is None or entry_oid is None:
            return None
        payload = maximum_hold_decision_payload(
            plan=plan,
            symbol=symbol,
            entry_oid=entry_oid,
            side=side,
            opened_at_ms=opened_at_ms,
            observed_ms=observed_ms,
            evaluations=evaluations,
        )
        if payload is None:
            return None
        return self._record_once(payload)

    def _terminal_decision(
        self,
        *,
        snapshot: SolLiveSnapshot,
        symbol: str,
        side: str,
        opened_at_ms: int,
        observed_ms: int,
        evaluations: EvaluationMap,
        soft_decision: Mapping[str, object] | None,
        current_reason: str | None,
    ) -> Mapping[str, object] | None:
        if soft_decision is None or soft_decision.get("outcome") != "extend":
            return None
        lifecycle_id = str(soft_decision["lifecycle_id"])
        decision_id = f"{lifecycle_id}:terminal_maximum_hold"
        existing = self._telemetry.recorded_maximum_hold_decision(decision_id)
        if existing is not None:
            _validate_terminal_identity(existing, soft_decision, decision_id)
            return existing
        plan, entry_oid = snapshot.execution_plan, snapshot.entry_oid
        if current_reason is None or plan is None or entry_oid is None:
            return None
        payload = maximum_hold_terminal_decision_payload(
            plan=plan,
            symbol=symbol,
            entry_oid=entry_oid,
            side=side,
            opened_at_ms=opened_at_ms,
            observed_ms=observed_ms,
            evaluations=evaluations,
            soft_decision_id=str(soft_decision["decision_id"]),
        )
        if payload.get("exit_reason") != current_reason:
            raise MultiAssetLiveRunnerError(
                "terminal maximum-hold reason changed within one decision cycle"
            )
        return self._record_once(payload)

    def _record_once(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        decision_id = str(payload["decision_id"])
        existing = self._telemetry.recorded_maximum_hold_decision(decision_id)
        if existing is not None:
            _validate_recorded_identity(existing, payload)
            return existing
        self._telemetry.emit_maximum_hold_decision(payload)
        return payload


def _validate_recorded_identity(
    recorded: Mapping[str, object], current: Mapping[str, object]
) -> None:
    identity_keys = ("decision_id", "lifecycle_id", "symbol", "strategy_id", "side")
    if any(recorded.get(key) != current.get(key) for key in identity_keys):
        raise MultiAssetLiveRunnerError(
            "persisted maximum-hold decision identity conflicts with open lifecycle"
        )


def _close_action(
    symbol: str,
    side: str,
    observed_ms: int,
    reference_prices: Mapping[str, float],
    reason: str,
) -> RoutingAction:
    mark = reference_prices.get(symbol)
    if mark is None:
        raise MultiAssetLiveRunnerError(
            f"{symbol} maximum-hold exit lacks a reference price"
        )
    return RoutingAction(
        "close",
        "cohort_maximum_hold",
        symbol,
        side,
        observed_ms,
        mark,
        exit_reason=reason,
    )


def _validate_terminal_identity(
    recorded: Mapping[str, object],
    soft: Mapping[str, object],
    decision_id: str,
) -> None:
    expected = {
        "decision_id": decision_id,
        "lifecycle_id": soft.get("lifecycle_id"),
        "symbol": soft.get("symbol"),
        "strategy_id": soft.get("strategy_id"),
        "side": soft.get("side"),
        "decision_stage": "terminal",
        "outcome": "exit",
        "trigger_decision_id": soft.get("decision_id"),
    }
    if any(recorded.get(key) != value for key, value in expected.items()):
        raise MultiAssetLiveRunnerError(
            "persisted terminal maximum-hold decision conflicts with open lifecycle"
        )


def _persisted_exit_reason(
    decision: Mapping[str, object] | None,
    current_reason: str | None,
) -> str | None:
    if decision is None or decision.get("outcome") != "exit":
        return current_reason
    reason = decision.get("exit_reason")
    if not isinstance(reason, str) or not reason.strip():
        raise MultiAssetLiveRunnerError(
            "persisted maximum-hold exit decision lacks an exit reason"
        )
    return reason
