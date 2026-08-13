"""Durable one-way ledger adapter for report-only peak observation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hypervector.paper.book import BookSnapshot
from hypervector.paper.ledger import append_paper_decision
from hypervector.paper.peak_protection_observer import PeakProtectionObserver


@dataclass(frozen=True)
class PeakObserverLedgerIdentity:
    """Stable backend identity stamped on every observer transition."""

    run_id: str
    export_id: str
    strategy_name: str
    symbol: str
    timeframe: str


class PeakObserverTelemetryBridge:
    """Persist observer state changes without exposing execution authority."""

    def __init__(
        self,
        *,
        observer: PeakProtectionObserver,
        data_root: Path,
        identity: PeakObserverLedgerIdentity,
    ) -> None:
        self._observer = observer
        self._root = data_root
        self._identity = identity

    def sync_position(
        self,
        *,
        quantity: float,
        average_price: float | None,
        observed_at: str,
        coverage_complete_since_entry: bool,
    ) -> None:
        """Persist observer transitions caused by actual position changes."""
        events = self._observer.sync_position(
            quantity=quantity,
            average_price=average_price,
            observed_at=observed_at,
            coverage_complete_since_entry=coverage_complete_since_entry,
        )
        self._record(events)

    def observe_mark(
        self,
        *,
        mark_price: float,
        observed_at: str,
        book: BookSnapshot | None,
        evidence_fresh: bool,
    ) -> None:
        """Persist state changes from one causal venue-mark sample."""
        events = self._observer.observe_mark(
            mark_price=mark_price,
            observed_at=observed_at,
            book=book,
            evidence_fresh=evidence_fresh,
        )
        self._record(events)

    def _record(self, events: tuple[dict[str, object], ...]) -> None:
        identity = self._identity
        for event in events:
            append_paper_decision(
                self._root,
                {
                    **event,
                    "run_id": identity.run_id,
                    "export_id": identity.export_id,
                    "strategy_name": identity.strategy_name,
                    "symbol": identity.symbol,
                    "timeframe": identity.timeframe,
                    "execution_model": "nautilus_event_v1",
                    "execution_mode": "shadow",
                },
            )
