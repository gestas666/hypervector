"""Completed-bar strategy decisions for the SOL live execution lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol

from hypervector.live.sol_range_onset_config import SolRangeOnsetConfig
from hypervector.live.sol_range_onset_state import SolLiveSnapshot, SolLiveState
from hypervector.live.provider_readiness import SignalReadiness


class SolLiveControllerError(RuntimeError):
    """A strategy decision cannot be safely mapped to the live lifecycle."""


class SolLiveEngineProtocol(Protocol):
    """Execution operations consumed by the completed-bar controller."""

    @property
    def snapshot(self) -> SolLiveSnapshot:
        """Return current venue-backed lifecycle state."""
        ...

    def record_strategy_decision(self, payload: dict[str, object]) -> None:
        """Persist the full decision before executing it."""
        ...

    def enter(
        self,
        *,
        side: str,
        mark_price: float,
        decision_time_ms: int | None = None,
    ) -> SolLiveSnapshot:
        """Submit and protect one entry."""
        ...

    def exit(self, *, mark_price: float, reason: str) -> SolLiveSnapshot:
        """Close and verify flat."""
        ...


@dataclass(frozen=True)
class SolLiveDecision:
    """One causal completed-bar signal and its regime provenance."""

    decision_time_ms: int
    reference_price: float
    long_entry: bool
    short_entry: bool
    long_exit: bool
    short_exit: bool
    primary_regime: str
    state_1m: str
    state_5m: str
    context_15m: str
    confidence: float
    structural_direction: str
    regime_admitted: bool
    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
    volume: float | None = None
    readiness: SignalReadiness | None = None
    breakout_side: str | None = None

    def __post_init__(self) -> None:
        """Reject ambiguous direction, malformed time, or invalid telemetry."""
        if (
            isinstance(self.decision_time_ms, bool)
            or not isinstance(self.decision_time_ms, int)
            or self.decision_time_ms < 0
        ):
            raise ValueError("decision_time_ms must be a nonnegative integer")
        if not math.isfinite(self.reference_price) or self.reference_price <= 0.0:
            raise ValueError("reference_price must be positive and finite")
        for name in (
            "long_entry",
            "short_entry",
            "long_exit",
            "short_exit",
            "regime_admitted",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be boolean")
        if self.long_entry and self.short_entry:
            raise ValueError("decision cannot contain both long and short entry")
        if not math.isfinite(self.confidence):
            raise ValueError("confidence must be finite")
        for name in ("primary_regime", "state_1m", "state_5m", "context_15m"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must be non-empty")
        if self.structural_direction not in {"long", "short", "neutral"}:
            raise ValueError("structural_direction must be long, short, or neutral")
        if self.breakout_side not in {None, "long", "short"}:
            raise ValueError("breakout_side must be long, short, or unavailable")
        _validate_optional_bar_values(self)

    @property
    def decision_action(self) -> str:
        """Return the deterministic signal action label."""
        if self.long_entry:
            return "long_onset" if self.short_exit else "enter_long"
        if self.short_entry:
            return "short_onset" if self.long_exit else "enter_short"
        if self.long_exit:
            return "long_exit"
        if self.short_exit:
            return "short_exit"
        return "hold"

    def as_payload(self) -> dict[str, object]:
        """Return JSON-safe live-ledger strategy telemetry."""
        payload: dict[str, object] = {
            "decision_time_ms": self.decision_time_ms,
            "reference_price": self.reference_price,
            "long_entry": self.long_entry,
            "short_entry": self.short_entry,
            "long_exit": self.long_exit,
            "short_exit": self.short_exit,
            "primary_regime": self.primary_regime,
            "state_1m": self.state_1m,
            "state_5m": self.state_5m,
            "context_15m": self.context_15m,
            "confidence": self.confidence,
            "structural_direction": self.structural_direction,
            "regime_admitted": self.regime_admitted,
            "decision_action": self.decision_action,
        }
        if self.open_price is not None:
            payload["open"] = self.open_price
            payload["high"] = self.high_price
            payload["low"] = self.low_price
            payload["volume"] = self.volume
        if self.readiness is not None:
            payload["readiness"] = self.readiness.as_payload()
        if self.breakout_side is not None:
            payload["breakout_side"] = self.breakout_side
        return payload


class SolRangeOnsetLiveController:
    """Route causal strategy decisions without duplicate or same-bar reversal."""

    def __init__(
        self,
        *,
        engine: SolLiveEngineProtocol,
        config: SolRangeOnsetConfig,
    ) -> None:
        self._engine = engine
        self._maximum_hold_ms = config.maximum_hold_seconds * 1_000
        self._last_decision_time_ms: int | None = None

    def process(self, decision: SolLiveDecision) -> SolLiveSnapshot:
        """Persist then route one strictly increasing completed-bar decision."""
        self._require_new_decision(decision.decision_time_ms)
        self._engine.record_strategy_decision(decision.as_payload())
        self._last_decision_time_ms = decision.decision_time_ms
        snapshot = self._engine.snapshot
        if snapshot.state is SolLiveState.FLAT:
            return self._process_flat(decision)
        if snapshot.state is SolLiveState.OPEN:
            return self._process_open(decision, snapshot)
        raise SolLiveControllerError(
            f"cannot process strategy decision while {snapshot.state.value}"
        )

    def _process_flat(self, decision: SolLiveDecision) -> SolLiveSnapshot:
        if decision.long_entry:
            return self._engine.enter(
                side="long",
                mark_price=decision.reference_price,
                decision_time_ms=decision.decision_time_ms,
            )
        if decision.short_entry:
            return self._engine.enter(
                side="short",
                mark_price=decision.reference_price,
                decision_time_ms=decision.decision_time_ms,
            )
        return self._engine.snapshot

    def _process_open(
        self,
        decision: SolLiveDecision,
        snapshot: SolLiveSnapshot,
    ) -> SolLiveSnapshot:
        opened = snapshot.opened_at_ms
        if opened is None:
            raise SolLiveControllerError("OPEN state is missing opened_at_ms")
        if decision.decision_time_ms - opened >= self._maximum_hold_ms:
            return self._engine.exit(
                mark_price=decision.reference_price,
                reason="maximum_hold",
            )
        is_long = snapshot.position_size_signed > 0.0
        is_short = snapshot.position_size_signed < 0.0
        opposite = (is_long and decision.short_entry) or (
            is_short and decision.long_entry
        )
        directional_exit = (is_long and decision.long_exit) or (
            is_short and decision.short_exit
        )
        if opposite or directional_exit:
            return self._engine.exit(
                mark_price=decision.reference_price,
                reason="opposite_signal" if opposite else "signal_exit",
            )
        if not is_long and not is_short:
            raise SolLiveControllerError("OPEN state has zero position size")
        return snapshot

    def _require_new_decision(self, decision_time_ms: int) -> None:
        prior = self._last_decision_time_ms
        if prior is not None and decision_time_ms <= prior:
            raise ValueError("live decisions must be strictly increasing")


def _validate_optional_bar_values(decision: SolLiveDecision) -> None:
    values = (
        decision.open_price,
        decision.high_price,
        decision.low_price,
        decision.volume,
    )
    if all(value is None for value in values):
        return
    if any(value is None for value in values):
        raise ValueError("live decision OHLCV values must be all present or all absent")
    if not all(math.isfinite(float(value)) for value in values if value is not None):
        raise ValueError("live decision OHLCV values must be finite")
    if min(float(value) for value in values[:3] if value is not None) <= 0.0:
        raise ValueError("live decision OHLC prices must be positive")
    if decision.volume is not None and decision.volume < 0.0:
        raise ValueError("live decision volume must be nonnegative")
