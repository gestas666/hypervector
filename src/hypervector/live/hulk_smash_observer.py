"""Least-privilege mainnet observer for Hulk signal and account telemetry."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from hypervector.live.hulk_smash_live_config import HulkSmashLiveConfig
from hypervector.live.hulk_smash_live_decisions import HulkSmashLiveDecision
from hypervector.live.hulk_smash_live_telemetry import HulkSmashLiveTelemetry
from hypervector.live.hyperliquid_protocol import (
    SolBookSnapshot,
    SolFundingPayment,
    SolReconciliationSnapshot,
    SolVenuePreflight,
)
from hypervector.research.backtest_lab_cipher_adapter import (
    inspect_backtest_lab_sources,
)

_FUNDING_LOOKBACK_MS = 86_400_000


class HulkReadOnlyVenueProtocol(Protocol):
    """Read-only venue surface; order mutations are intentionally absent."""

    def preflight(self, *, expected_max_leverage: int) -> SolVenuePreflight: ...

    def reconcile(self) -> SolReconciliationSnapshot: ...

    def book_snapshot(self, *, depth_levels: int) -> SolBookSnapshot: ...

    def funding_payments(
        self, *, start_time_ms: int, end_time_ms: int
    ) -> tuple[SolFundingPayment, ...]: ...


class HulkSmashObserverError(RuntimeError):
    """The disarmed observer cannot preserve its source or telemetry contract."""


class HulkSmashObserver:
    """Publish real market/account data while possessing no order authority."""

    def __init__(
        self,
        *,
        config: HulkSmashLiveConfig,
        reader: HulkReadOnlyVenueProtocol,
        telemetry: HulkSmashLiveTelemetry,
        now_fn: Callable[[], datetime],
    ) -> None:
        if config.mode != "observe":
            raise HulkSmashObserverError("observer requires observe mode")
        self._config = config
        self._reader = reader
        self._telemetry = telemetry
        self._now_fn = now_fn
        self._started = False
        self._funding_cursor_ms = 0

    def start(self) -> None:
        """Validate source identity, then record read-only venue preflight."""
        if self._started:
            raise HulkSmashObserverError("Hulk observer already started")
        validate_hulk_signal_source(self._config)
        preflight = self._reader.preflight(
            expected_max_leverage=int(self._config.venue_max_leverage)
        )
        venue = self._reader.reconcile()
        self._telemetry.emit_preflight(preflight, venue)
        self._telemetry.emit_book(self._reader.book_snapshot(depth_levels=5))
        self._funding_cursor_ms = max(0, self._timestamp_ms() - _FUNDING_LOOKBACK_MS)
        self._started = True

    def record_history(self, decisions: tuple[HulkSmashLiveDecision, ...]) -> None:
        """Publish bounded completed-bar history without execution authority."""
        self._require_started()
        for decision in decisions:
            self._telemetry.emit_history(decision)

    def process(self, decision: HulkSmashLiveDecision) -> None:
        """Publish one fresh strategy decision; no order method is available."""
        self._require_started()
        self._telemetry.emit_decision(decision)

    def poll_market(self) -> None:
        """Refresh venue account, fills, funding, and L2 telemetry."""
        self._require_started()
        observed_ms = self._timestamp_ms()
        venue = self._reader.reconcile()
        self._telemetry.emit_reconciliation(venue)
        self._telemetry.emit_funding_payments(
            self._reader.funding_payments(
                start_time_ms=self._funding_cursor_ms,
                end_time_ms=observed_ms,
            )
        )
        self._telemetry.emit_book(self._reader.book_snapshot(depth_levels=5))
        self._funding_cursor_ms = observed_ms

    def _require_started(self) -> None:
        if not self._started:
            raise HulkSmashObserverError("Hulk observer is not started")

    def _timestamp_ms(self) -> int:
        value = self._now_fn()
        if value.tzinfo is None or value.utcoffset() is None:
            raise HulkSmashObserverError("observer clock must be timezone-aware")
        return int(value.timestamp() * 1_000)


def validate_hulk_signal_source(config: HulkSmashLiveConfig) -> None:
    """Fail if live indicator source differs from the researched source tree."""
    try:
        identity = inspect_backtest_lab_sources(config.backtest_lab_root)
    except OSError as exc:
        raise HulkSmashObserverError(
            f"Hulk signal source cannot be inspected: {exc}"
        ) from exc
    observed = identity.get("python_primitives_tree_sha256")
    if observed != config.backtest_lab_tree_sha256:
        raise HulkSmashObserverError(
            "Backtest Lab source hash differs from the validated Hulk research input"
        )
