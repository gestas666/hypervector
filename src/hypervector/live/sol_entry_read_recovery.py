"""Protect directly acknowledged IOC fills when post-entry venue reads fail."""

from dataclasses import dataclass
import math
from typing import NoReturn

from hyperliquid.utils.error import ClientError, ServerError  # type: ignore[import-untyped]
from requests import RequestException

from hypervector.live.cohort_execution_plan import BoundExecutionPlan
from hypervector.live.entry_submission_deadline import (
    EntryDeadlineExpired,
    EntrySubmissionDeadline,
)
from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    SolReconciliationSnapshot,
)
from hypervector.live.hyperliquid_sol_parsing import HyperliquidAdapterError
from hypervector.live.sol_order_submission import SolOrderSubmission
from hypervector.live.sol_range_onset_config import SolRangeOnsetConfig
from hypervector.live.sol_range_onset_consistency import SolReconciliationPoller
from hypervector.live.sol_range_onset_engine_contract import (
    SolEntryNotFilledError,
    SolLiveEngineError,
    is_expected_ioc_no_fill,
)
from hypervector.live.sol_range_onset_engine_events import SolLiveEngineEvents
from hypervector.live.sol_range_onset_execution_plan import legacy_execution_plan
from hypervector.live.sol_range_onset_state import SolLiveSnapshot, SolLiveStateMachine
from hypervector.live.sol_range_onset_stop_entry import (
    EmergencyFlatten,
    place_and_verify_entry_protection,
)

_READ_FAILURES = (RequestException, ClientError, ServerError, HyperliquidAdapterError)


class EntryReconciliationUnavailable(Exception):
    """Carry the exact acknowledged order and failed read without inventing state."""

    def __init__(
        self, acknowledgement: HyperliquidOrderAck, failure: Exception
    ) -> None:
        super().__init__("venue reconciliation unavailable after entry acknowledgement")
        self.acknowledgement = acknowledgement
        self.failure = failure


@dataclass(frozen=True)
class EntrySubmissionRuntime:
    """Bind the existing lifecycle services for one entry and its recovery path."""

    config: SolRangeOnsetConfig
    machine: SolLiveStateMachine
    events: SolLiveEngineEvents
    orders: SolOrderSubmission
    poller: SolReconciliationPoller

    def submit_and_reconcile(
        self,
        *,
        side: str,
        mark_price: float,
        notional: float,
        plan: BoundExecutionPlan,
        entry_deadline: EntrySubmissionDeadline | None,
    ) -> tuple[HyperliquidOrderAck, SolReconciliationSnapshot]:
        """Retain normal submission and reconciliation, exposing only known read failures."""
        self.machine.begin_entry(execution_plan=plan)
        self.events.emit_state()
        ack = self._submit(side, mark_price, notional, entry_deadline)
        if not ack.accepted or ack.oid is None:
            if is_expected_ioc_no_fill(plan, ack):
                self._confirm_ioc_no_fill(ack)
            reason = f"entry rejected: {ack.error or ack.status}"
            self.events.fault(reason)
            raise SolLiveEngineError(reason)
        self.machine.acknowledge_entry(ack.oid)
        try:
            venue = self.poller.wait_for(
                lambda snapshot: snapshot.position.size_signed != 0.0
            )
        except _READ_FAILURES as exc:
            raise EntryReconciliationUnavailable(ack, exc) from exc
        return ack, venue

    def _submit(
        self,
        side: str,
        mark_price: float,
        notional: float,
        entry_deadline: EntrySubmissionDeadline | None,
    ) -> HyperliquidOrderAck:
        try:
            ack = self.orders.submit_entry(
                side=side,
                requested_notional_usd=notional,
                mark_price=mark_price,
                entry_deadline=entry_deadline,
            )
        except EntryDeadlineExpired:
            self.machine.confirm_entry_not_filled()
            self.events.emit_state()
            raise
        self.events.emit_ack(
            "entry",
            ack,
            extra_payload=(
                entry_deadline.last_observation.as_payload() if entry_deadline else None
            ),
        )
        return ack

    def _confirm_ioc_no_fill(self, ack: HyperliquidOrderAck) -> NoReturn:
        venue = self.poller.wait_for(lambda snapshot: snapshot.is_flat)
        self.events.emit_reconciliation(venue)
        if not venue.is_flat:
            reason = "IOC no-fill acknowledgement conflicts with venue exposure"
            self.events.fault(reason)
            raise SolLiveEngineError(reason)
        reason = f"IOC entry not filled: {ack.error}"
        self.events.confirm_entry_not_filled(reason=reason)
        raise SolEntryNotFilledError(reason)

    def protect_after_read_failure(
        self,
        *,
        failure: EntryReconciliationUnavailable,
        side: str,
        mark_price: float,
        opened_at_ms: int,
        emergency_flatten: EmergencyFlatten,
    ) -> SolLiveSnapshot:
        """Attempt the configured stop from qualified fill evidence, then verify normally."""
        ack = failure.acknowledgement
        plan = self.machine.snapshot.execution_plan or legacy_execution_plan(
            self.config
        )
        fill = _direct_ioc_fill(ack, side=side, plan=plan)
        self.events.emit(
            "entry_reconciliation_failure",
            {
                "entry_oid": ack.oid,
                "exception_type": type(failure.failure).__name__,
                "acknowledgement_status": ack.status,
                "venue_snapshot_available": False,
                "recovery_action": "protect_acknowledged_fill"
                if fill
                else "unresolved",
                "position_source": "direct_entry_fill_acknowledgement"
                if fill
                else None,
            },
        )
        if fill is None:
            raise failure.failure
        oid, size, price = fill
        self.machine.begin_protection(
            position_size_signed=size, opened_at_ms=opened_at_ms
        )
        self.events.emit_state()
        trigger = plan.stop_price(entry_price=price, side=side)
        return place_and_verify_entry_protection(
            config=self.config,
            entry_oid=oid,
            position_size_signed=size,
            trigger_price=trigger,
            mark_price=mark_price,
            machine=self.machine,
            events=self.events,
            orders=self.orders,
            poller=self.poller,
            emergency_flatten=emergency_flatten,
        )


def _direct_ioc_fill(
    ack: HyperliquidOrderAck,
    *,
    side: str,
    plan: BoundExecutionPlan,
) -> tuple[int, float, float] | None:
    if (
        side not in {"long", "short"}
        or plan.entry_liquidity != "taker_ioc"
        or ack.accepted is not True
        or ack.status != "filled"
        or ack.error is not None
        or type(ack.oid) is not int
        or ack.oid <= 0
        or ack.recovered_after_transport_error
        or ack.recovered_after_restart
    ):
        return None
    quantity, price = ack.filled_size, ack.average_price
    if (
        isinstance(quantity, bool)
        or not isinstance(quantity, (int, float))
        or isinstance(price, bool)
        or not isinstance(price, (int, float))
        or not math.isfinite(quantity)
        or quantity <= 0
        or not math.isfinite(price)
        or price <= 0
    ):
        return None
    return (
        ack.oid,
        float(quantity) if side == "long" else -float(quantity),
        float(price),
    )
