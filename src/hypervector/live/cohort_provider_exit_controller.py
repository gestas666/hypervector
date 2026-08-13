"""Lifecycle-bound exits from causal provider recipe evaluations."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.live.bidirectional_intents import RoutingAction
from hypervector.live.cohort_maximum_hold_policy import EvaluationMap
from hypervector.live.multi_asset_live_protocols import MultiAssetEngineProtocol
from hypervector.live.multi_asset_live_protocols import CohortTelemetryProtocol
from hypervector.live.multi_asset_live_runner_support import (
    MultiAssetLiveRunnerError,
    entry_provider_strategy_id,
    position_side,
)
from hypervector.live.sol_range_onset_state import SolLiveState


class CohortProviderExitController:
    """Close an open lifecycle only from its bound provider's exit state."""

    def __init__(
        self,
        *,
        symbols: tuple[str, ...],
        engines: Mapping[str, MultiAssetEngineProtocol],
        telemetry: CohortTelemetryProtocol,
    ) -> None:
        """Bind the exact symbol engines owned by the cohort runner."""
        if not symbols or set(symbols) != set(engines):
            raise MultiAssetLiveRunnerError(
                "provider exit controller symbols and engines must agree"
            )
        self._symbols = symbols
        self._engines = engines
        self._telemetry = telemetry

    def actions(
        self,
        *,
        observed_ms: int,
        reference_prices: Mapping[str, float],
        evaluations: EvaluationMap,
        excluded_symbols: set[str],
    ) -> tuple[set[str], tuple[RoutingAction, ...]]:
        """Return close actions without allowing cross-provider lifecycle exits."""
        actions: list[RoutingAction] = []
        closing: set[str] = set()
        for symbol in self._symbols:
            if symbol in excluded_symbols:
                continue
            action = self._action(
                symbol,
                observed_ms,
                reference_prices,
                evaluations,
            )
            if action is None:
                continue
            closing.add(symbol)
            actions.append(action)
        return closing, tuple(actions)

    def _action(
        self,
        symbol: str,
        observed_ms: int,
        reference_prices: Mapping[str, float],
        evaluations: EvaluationMap,
    ) -> RoutingAction | None:
        snapshot = self._engines[symbol].snapshot
        plan = snapshot.execution_plan
        if snapshot.state is not SolLiveState.OPEN or plan is None:
            return None
        if plan.provider_recipe_exit_policy != "honor":
            return None
        side = position_side(snapshot.position_size_signed)
        if side is None:
            raise MultiAssetLiveRunnerError(
                f"{symbol} provider recipe exit lacks a position side"
            )
        provider = entry_provider_strategy_id(plan.strategy_id)
        opened_at_ms = snapshot.opened_at_ms
        entry_oid = snapshot.entry_oid
        if opened_at_ms is None or entry_oid is None:
            raise MultiAssetLiveRunnerError(
                f"{symbol} provider recipe exit lacks lifecycle identity"
            )
        decision = self._decision(
            provider=provider,
            symbol=symbol,
            side=side,
            entry_oid=entry_oid,
            opened_at_ms=opened_at_ms,
            observed_ms=observed_ms,
            evaluations=evaluations,
        )
        if decision is None:
            return None
        mark = reference_prices.get(symbol)
        if mark is None:
            raise MultiAssetLiveRunnerError(
                f"{symbol} provider recipe exit lacks a reference price"
            )
        return RoutingAction(
            "close",
            provider,
            symbol,
            side,
            _integer(decision.get("decision_time_ms"), "decision_time_ms"),
            mark,
            exit_reason=_text(decision.get("exit_reason"), "exit_reason"),
        )

    def _decision(
        self,
        *,
        provider: str,
        symbol: str,
        side: str,
        entry_oid: int,
        opened_at_ms: int,
        observed_ms: int,
        evaluations: EvaluationMap,
    ) -> Mapping[str, object] | None:
        decision_id = f"{symbol}:{entry_oid}:provider_recipe_exit"
        recorded = self._telemetry.recorded_provider_exit_decision(decision_id)
        if recorded is not None:
            _validate_recorded(
                recorded, decision_id, provider, symbol, side, opened_at_ms, observed_ms
            )
            return recorded
        evaluation = evaluations.get((provider, symbol))
        if evaluation is None or side not in evaluation.exit_sides:
            return None
        if evaluation.decision_time_ms < opened_at_ms:
            return None
        if evaluation.decision_time_ms > observed_ms:
            raise MultiAssetLiveRunnerError(
                f"{symbol} provider recipe exit lies in the future"
            )
        payload: dict[str, object] = {
            "decision_id": decision_id,
            "lifecycle_id": f"{symbol}:{entry_oid}",
            "strategy_id": provider,
            "symbol": symbol,
            "side": side,
            "outcome": "exit",
            "exit_reason": evaluation.exit_reason,
            "decision_time_ms": evaluation.decision_time_ms,
        }
        self._telemetry.emit_provider_exit_decision(payload)
        return payload


def _validate_recorded(
    payload: Mapping[str, object],
    decision_id: str,
    provider: str,
    symbol: str,
    side: str,
    opened_at_ms: int,
    observed_ms: int,
) -> None:
    expected: dict[str, object] = {
        "decision_id": decision_id,
        "lifecycle_id": decision_id.removesuffix(":provider_recipe_exit"),
        "strategy_id": provider,
        "symbol": symbol,
        "side": side,
        "outcome": "exit",
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise MultiAssetLiveRunnerError(
            "persisted provider recipe exit conflicts with open lifecycle"
        )
    decision_time_ms = _integer(payload.get("decision_time_ms"), "decision_time_ms")
    _text(payload.get("exit_reason"), "exit_reason")
    if decision_time_ms < opened_at_ms or decision_time_ms > observed_ms:
        raise MultiAssetLiveRunnerError(
            "persisted provider recipe exit has an invalid causal boundary"
        )


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MultiAssetLiveRunnerError(
            f"persisted provider recipe exit {label} must be an integer"
        )
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MultiAssetLiveRunnerError(
            f"persisted provider recipe exit {label} must be non-empty"
        )
    return value.strip()
