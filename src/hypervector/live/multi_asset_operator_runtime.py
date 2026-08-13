"""Backend-owned processing for manual and staged-profile cohort requests."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol

from hypervector.live.bidirectional_intents import RoutingAction
from hypervector.live.cohort_operator_commands import (
    CohortOperatorClaim,
    CohortOperatorCommand,
    CohortProfileSettings,
)
from hypervector.live.cohort_transition_drain import CohortTransitionDrainError
from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError
from hypervector.live.sol_range_onset_state import SolLiveSnapshot


class OperatorCommandSourceProtocol(Protocol):
    """Atomic local request source owned by one backend process."""

    def claim_pending(self) -> tuple[CohortOperatorClaim, ...]: ...

    def finalize(
        self,
        claim: CohortOperatorClaim,
        *,
        status: str,
        reason: str,
    ) -> None: ...


class OperatorTelemetryProtocol(Protocol):
    """Audited command event sink."""

    def emit_operator_command(self, payload: Mapping[str, object]) -> None: ...


class OperatorEngineProtocol(Protocol):
    """Minimum venue-protected lifecycle used by manual overrides."""

    @property
    def snapshot(self) -> SolLiveSnapshot: ...


class CohortOperatorExecutionError(RuntimeError):
    """A claimed live request failed inside the protected engine."""


class _CommandLifecycle:
    def __init__(
        self,
        source: OperatorCommandSourceProtocol,
        telemetry: OperatorTelemetryProtocol,
    ) -> None:
        self.source = source
        self.telemetry = telemetry

    def emit(
        self,
        claim: CohortOperatorClaim,
        status: str,
        reason: str | None,
    ) -> None:
        command = claim.command
        self.telemetry.emit_operator_command(
            {
                "request_id": claim.request_id,
                "status": status,
                "reason": reason,
                "action": command.action if command else None,
                "symbol": command.symbol if command else None,
                "provider": command.provider if command else None,
                "side": command.side if command else None,
            }
        )

    def reject(self, claim: CohortOperatorClaim, reason: str) -> None:
        self.source.finalize(claim, status="rejected", reason=reason)
        self.emit(claim, "rejected", reason)

    def complete(self, claim: CohortOperatorClaim, reason: str) -> None:
        self.source.finalize(claim, status="completed", reason=reason)
        self.emit(claim, "completed", reason)


class LiveOperatorCommandProcessor:
    """Revalidate and execute manual requests through protected live engines."""

    def __init__(
        self,
        *,
        source: OperatorCommandSourceProtocol,
        telemetry: OperatorTelemetryProtocol,
        engines: Mapping[str, OperatorEngineProtocol],
        executable_provider_symbols: frozenset[tuple[str, str]],
        executable_provider_directions: frozenset[tuple[str, str, str]],
        maximum_positions: int,
        activate_transition_drain: Callable[[str, str], str] | None = None,
        transition_drain_active: Callable[[], bool] | None = None,
    ) -> None:
        self._lifecycle = _CommandLifecycle(source, telemetry)
        self._engines = engines
        self._executable = executable_provider_symbols
        self._executable_directions = executable_provider_directions
        self._maximum_positions = maximum_positions
        self._activate_transition_drain = activate_transition_drain
        self._transition_drain_active = transition_drain_active or (lambda: False)

    def process(
        self,
        *,
        reference_prices: Mapping[str, float],
        observed_ms: int,
        execute: Callable[[RoutingAction], None],
    ) -> tuple[tuple[RoutingAction, ...], set[str]]:
        actions: list[RoutingAction] = []
        affected: set[str] = set()
        claims = self._lifecycle.source.claim_pending()
        ordered = sorted(claims, key=_transition_drain_priority)
        for claim in ordered:
            self._lifecycle.emit(claim, "received", claim.issue)
            if _is_transition_drain(claim):
                self._process_transition_drain(claim)
                continue
            action, issue = self._action(claim, reference_prices, observed_ms, affected)
            if issue is not None or action is None:
                self._lifecycle.reject(claim, issue or "request rejected")
                continue
            self._lifecycle.emit(claim, "accepted", "backend constraints passed")
            try:
                execute(action)
            except SolLiveEngineError as exc:
                self._lifecycle.reject(claim, f"execution failed: {exc}")
                raise CohortOperatorExecutionError(
                    f"operator command {claim.request_id} failed closed"
                ) from exc
            self._lifecycle.complete(claim, "venue lifecycle reconciled")
            actions.append(action)
            affected.add(action.symbol)
        return tuple(actions), affected

    def _process_transition_drain(self, claim: CohortOperatorClaim) -> None:
        activate = self._activate_transition_drain
        command = claim.command
        if command is None or activate is None:
            self._lifecycle.reject(claim, "transition drain control is unavailable")
            return
        self._lifecycle.emit(claim, "accepted", "run identity and drain schema passed")
        try:
            reason = activate(claim.request_id, command.created_at_utc)
        except CohortTransitionDrainError as exc:
            self._lifecycle.reject(claim, f"transition drain failed: {exc}")
            return
        self._lifecycle.complete(claim, reason)

    def _action(
        self,
        claim: CohortOperatorClaim,
        prices: Mapping[str, float],
        observed_ms: int,
        affected: set[str],
    ) -> tuple[RoutingAction | None, str | None]:
        command = claim.command
        if command is None:
            return None, claim.issue or "invalid request"
        if command.action == "stage_profile":
            return None, "configuration staging is refused while live armed"
        if command.symbol in affected:
            return None, "one operator action per symbol is allowed each cycle"
        if command.symbol not in self._engines or command.symbol not in prices:
            return None, "command symbol is unavailable"
        current = _side(self._engines[command.symbol].snapshot.position_size_signed)
        if command.action == "manual_close":
            return self._close_action(command, prices, observed_ms, current)
        return self._entry_action(command, prices, observed_ms, current)

    def _entry_action(
        self,
        command: CohortOperatorCommand,
        prices: Mapping[str, float],
        observed_ms: int,
        current: str | None,
    ) -> tuple[RoutingAction | None, str | None]:
        if self._transition_drain_active():
            return None, "manual entry is disabled by transition drain"
        if command.provider is None or command.side is None:
            return None, "manual entry is missing provider or side"
        if (command.provider, command.symbol, command.side) not in (
            self._executable_directions
        ):
            return None, "provider, symbol, and side lack execution authority"
        if current is not None:
            return None, "manual entry requires a flat symbol"
        open_count = sum(
            _side(engine.snapshot.position_size_signed) is not None
            for engine in self._engines.values()
        )
        if open_count >= self._maximum_positions:
            return None, "portfolio position capacity is full"
        return RoutingAction(
            "enter",
            f"operator_override:{command.provider}",
            command.symbol,
            command.side,
            observed_ms,
            prices[command.symbol],
        ), None

    @staticmethod
    def _close_action(
        command: CohortOperatorCommand,
        prices: Mapping[str, float],
        observed_ms: int,
        current: str | None,
    ) -> tuple[RoutingAction | None, str | None]:
        if current is None:
            return None, "manual close requires an open position"
        return RoutingAction(
            "close",
            "operator_override:manual_close",
            command.symbol,
            current,
            observed_ms,
            prices[command.symbol],
        ), None


class ObserverProfileCommandProcessor:
    """Accept only validated profile staging while execution is disarmed."""

    def __init__(
        self,
        *,
        source: OperatorCommandSourceProtocol,
        telemetry: OperatorTelemetryProtocol,
        stage: Callable[[CohortProfileSettings], str],
    ) -> None:
        self._lifecycle = _CommandLifecycle(source, telemetry)
        self._stage = stage

    def process(self) -> None:
        """Reject execution requests and stage valid next-run profiles."""
        for claim in self._lifecycle.source.claim_pending():
            self._lifecycle.emit(claim, "received", claim.issue)
            command = claim.command
            if command is None:
                self._lifecycle.reject(claim, claim.issue or "invalid request")
                continue
            if command.action != "stage_profile" or command.settings is None:
                self._lifecycle.reject(
                    claim,
                    "manual execution is unavailable in observe mode",
                )
                continue
            try:
                reason = self._stage(command.settings)
            except ValueError as exc:
                self._lifecycle.reject(claim, f"profile validation failed: {exc}")
                continue
            self._lifecycle.emit(claim, "accepted", "profile validation passed")
            self._lifecycle.complete(claim, reason)


def _side(size: float) -> str | None:
    if size > 0.0:
        return "long"
    if size < 0.0:
        return "short"
    return None


def _is_transition_drain(claim: CohortOperatorClaim) -> bool:
    command = claim.command
    return command is not None and command.action == "transition_drain"


def _transition_drain_priority(claim: CohortOperatorClaim) -> int:
    return 0 if _is_transition_drain(claim) else 1
