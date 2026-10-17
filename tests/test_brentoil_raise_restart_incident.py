"""Replay the 2026-09-24 V93 BRENTOIL raise-recovery crash loop from its recorded ledger.

The fixture holds the recorded rows of profile ``d263b135…`` (every control row of
the lifecycle plus the complete raise-era tail, and one foreign-profile row), read
only from ``data/live/bidirectional_cohort/xyz:brentoil.jsonl``. Two launches each
journaled a ``raise_protective_stop`` intent and crashed before any venue call; the
next launch faulted on "multiple unresolved order intents remain" after preflight.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from hypervector.live.hyperliquid_protocol import (
    Hip3MarketFeeMetadata,
    HyperliquidFeeSchedule,
    HyperliquidOrderStatus,
    SolAccountSnapshot,
    SolFill,
    SolMarketMetadata,
    SolOpenOrder,
    SolPositionSnapshot,
    SolReconciliationSnapshot,
    SolVenuePreflight,
)
from hypervector.live.hyperliquid_sol_parsing import HyperliquidOrderUnavailableError
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.sol_order_restart import (
    MULTIPLE_UNRESOLVED_INTENTS,
    SolOrderRestartError,
    pending_order_intent,
)
from hypervector.live.sol_order_submission import SolOrderSubmission
from hypervector.live.sol_partial_protective_recovery import (
    SolPartialProtectiveRecovery,
)
from hypervector.live.sol_range_onset_consistency import SolReconciliationPoller
from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError
from hypervector.live.sol_range_onset_engine_events import SolLiveEngineEvents
from hypervector.live.sol_range_onset_ledger import SolLiveLedger
from hypervector.live.sol_range_onset_live_telemetry import SolLiveTelemetry
from hypervector.live.sol_range_onset_startup import (
    UNINDEXED_RAISE_STATUS,
    prepare_sol_live_startup,
)
from hypervector.live.sol_range_onset_state import SolLiveState, SolLiveStateMachine

FIXTURE = (
    Path(__file__).parent / "fixtures" / "brentoil_v93_raise_restart_records.jsonl"
)
PROFILE = Path("tests/fixtures/profiles/multi_asset_growth_first_5000_exit_v2_v93_proposal.toml")
FINGERPRINT = "d263b1355a219024dfe0ede088a482b8bf8a293661ab53ae42049029bf96a1e7"
ENTRY_OID = 555018656094
STOP_OID = 555018726035
RAISE_IDS = (
    "0x5a708b7a38e85039f83879115555d965",
    "0x81fffdd8ef62855f9bea6a5249c6afd0",
)
VENUE_STOP_TRIGGER = 97.554  # the recorded venue view of the 97.55440485009709 intent
MUTATIONS = frozenset(
    {
        "configure_isolated_leverage",
        "submit_entry",
        "place_protective_stop",
        "submit_target",
        "modify_protective_stop",
        "cancel_order",
        "close_position",
    }
)


class RecordedBrentVenue:
    """Read-only venue as recorded at 16:01 UTC; every mutation is an error."""

    def __init__(
        self, *, indexed: dict[str, HyperliquidOrderStatus] | None = None
    ) -> None:
        self.indexed = dict(indexed or {})
        self.calls: list[tuple[str, object]] = []

    def preflight(self, *, expected_max_leverage: int) -> SolVenuePreflight:
        self.calls.append(("preflight", expected_max_leverage))
        return SolVenuePreflight(
            market=SolMarketMetadata("xyz:BRENTOIL", 2, 20),
            mark_price=102.15,
            price_tick=0.01,
            size_step=0.01,
            fees=HyperliquidFeeSchedule(0.00015, 0.00045, 0.04),
            account_value_usd=4845.73254749,
            withdrawable_usd=4599.75760249,
            position=_position(),
            account_abstraction_mode="unifiedAccount",
            hip3_fee_metadata=Hip3MarketFeeMetadata(1.0, True, 0),
        )

    def reconcile(self) -> SolReconciliationSnapshot:
        self.calls.append(("reconcile", None))
        return SolReconciliationSnapshot(
            account=SolAccountSnapshot(
                account_value_usd=4845.73254749,
                withdrawable_usd=4599.75760249,
                total_margin_used_usd=90.569506,
                total_notional_position_usd=596.556,
                position=_position(),
            ),
            open_orders=(
                SolOpenOrder(
                    oid=STOP_OID,
                    size=5.84,
                    original_size=5.84,
                    side="A",
                    reduce_only=True,
                    is_trigger=True,
                    trigger_price=VENUE_STOP_TRIGGER,
                    order_type="Stop Market",
                    timestamp_ms=1_790_236_817_000,
                    limit_price=VENUE_STOP_TRIGGER,
                ),
            ),
            fills=(
                SolFill(
                    oid=ENTRY_OID,
                    price=99.05,
                    size=5.84,
                    side="B",
                    timestamp_ms=1_790_236_814_037,
                    fee_usd=0.049978,
                    fee_token="USDC",
                    closed_pnl_usd=0.0,
                    crossed=True,
                    direction="Open Long",
                    transaction_hash=(
                        "0xe7713751a29bd734e8ea04451733750202e000373d9ef6068b39e2a4619fb11f"
                    ),
                    trade_id=851991582715904,
                ),
            ),
        )

    def order_status_by_client_id(self, client_order_id: str) -> HyperliquidOrderStatus:
        self.calls.append(("order_status_by_client_id", client_order_id))
        if client_order_id in self.indexed:
            return self.indexed[client_order_id]
        raise HyperliquidOrderUnavailableError(
            f"order {client_order_id} status is not yet visible"
        )

    def _refuse(self, name: str, *args: object, **kwargs: object) -> object:
        self.calls.append((name, (args, kwargs)))
        raise AssertionError(f"startup must not call {name}")

    def configure_isolated_leverage(self, *args: object, **kwargs: object) -> object:
        return self._refuse("configure_isolated_leverage", *args, **kwargs)

    def submit_entry(self, *args: object, **kwargs: object) -> object:
        return self._refuse("submit_entry", *args, **kwargs)

    def place_protective_stop(self, *args: object, **kwargs: object) -> object:
        return self._refuse("place_protective_stop", *args, **kwargs)

    def submit_target(self, *args: object, **kwargs: object) -> object:
        return self._refuse("submit_target", *args, **kwargs)

    def modify_protective_stop(self, *args: object, **kwargs: object) -> object:
        return self._refuse("modify_protective_stop", *args, **kwargs)

    def cancel_order(self, *args: object, **kwargs: object) -> object:
        return self._refuse("cancel_order", *args, **kwargs)

    def close_position(self, *args: object, **kwargs: object) -> object:
        return self._refuse("close_position", *args, **kwargs)

    def order_status(self, *args: object, **kwargs: object) -> object:
        return self._refuse("order_status", *args, **kwargs)

    def book_snapshot(self, *args: object, **kwargs: object) -> object:
        return self._refuse("book_snapshot", *args, **kwargs)

    def funding_payments(self, *args: object, **kwargs: object) -> object:
        return self._refuse("funding_payments", *args, **kwargs)


def _position() -> SolPositionSnapshot:
    return SolPositionSnapshot(
        size_signed=5.84,
        entry_price=99.05,
        liquidation_price=88.8631004566,
        margin_used_usd=90.569506,
        position_value_usd=596.556,
        unrealized_pnl_usd=18.104,
        leverage_type="isolated",
        leverage=8,
    )


def _no_new_client_order_id() -> str:
    raise AssertionError("startup must not mint a new client order id")


def _now() -> datetime:
    return datetime(2026, 9, 24, 16, 30, tzinfo=timezone.utc)


def _recorded_rows() -> list[dict[str, object]]:
    return [json.loads(line) for line in FIXTURE.read_text().splitlines()]


def _failed_startup_segment(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """The recorded launch-3 attempt, from its session start to its FAULTED state."""
    start = max(
        index for index, row in enumerate(rows) if row["event_type"] == "session_start"
    )
    return [dict(row, run_id="bidirectional-live-repeat") for row in rows[start:]]


def _config():
    config = load_multi_asset_live_config(
        PROFILE, mode="live", enabled=True, accepts_live_risk=True
    )
    asset = next(asset for asset in config.assets if asset.symbol == "xyz:BRENTOIL")
    assert asset.profile_fingerprint == FINGERPRINT
    return asset


def _seed_ledger(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    """Write the recorded rows as a valid ledger (sequence must equal line number)."""
    path = tmp_path / "live" / "bidirectional_cohort" / "xyz:brentoil.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        "".join(
            json.dumps({**row, "sequence": number}, separators=(",", ":")) + "\n"
            for number, row in enumerate(rows, start=1)
        )
    )
    return path


def _start(path: Path, venue: RecordedBrentVenue) -> tuple[SolLiveStateMachine, object]:
    config = _config()
    ledger = SolLiveLedger(
        path=path,
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id="bidirectional-live-hotfix-proof",
    )
    machine = SolLiveStateMachine()
    events = SolLiveEngineEvents(
        telemetry=SolLiveTelemetry(config=config, ledger=ledger, now_fn=_now),
        machine=machine,
    )
    orders = SolOrderSubmission(
        adapter=venue,
        events=events,
        client_order_id_fn=_no_new_client_order_id,
        sleep_fn=lambda _: None,
    )
    poller = SolReconciliationPoller(
        adapter=venue, attempts=4, delay_seconds=0.0, sleep_fn=lambda _: None
    )

    def emergency_flatten(**kwargs: object) -> None:
        raise AssertionError(f"startup must not flatten: {kwargs}")

    result = prepare_sol_live_startup(
        config=config,
        adapter=venue,
        ledger=ledger,
        machine=machine,
        events=events,
        orders=orders,
        poller=poller,
        emergency_flatten=emergency_flatten,
        partial_protective=SolPartialProtectiveRecovery(
            machine=machine, events=events, orders=orders, poller=poller, now_fn=_now
        ),
    )
    return machine, result


def _rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_fixture_is_the_recorded_incident() -> None:
    rows = _recorded_rows()
    owned = [row for row in rows if row["profile_fingerprint"] == FINGERPRINT]
    assert len(owned) == len(rows) - 1, (
        "exactly one foreign-profile row proves filtering"
    )
    intents = [row["payload"] for row in owned if row["event_type"] == "order_intent"]
    raises = [p for p in intents if p["operation"] == "raise_protective_stop"]
    assert [p["client_order_id"] for p in raises] == list(RAISE_IDS)
    assert {p["oid"] for p in raises} == {STOP_OID}
    assert owned[-1]["event_type"] == "state_transition"
    assert owned[-1]["payload"]["state"] == "FAULTED"
    assert owned[-1]["payload"]["last_fault"] == MULTIPLE_UNRESOLVED_INTENTS
    with pytest.raises(SolOrderRestartError, match=MULTIPLE_UNRESOLVED_INTENTS):
        pending_order_intent(owned)


@pytest.mark.parametrize("repeated_failures", [0, 2])
def test_recorded_brent_history_restores_open_with_its_original_stop(
    tmp_path: Path, repeated_failures: int
) -> None:
    rows = _recorded_rows()
    for _ in range(repeated_failures):
        rows += _failed_startup_segment(_recorded_rows())
    path = _seed_ledger(tmp_path, rows)
    before = len(rows)
    venue = RecordedBrentVenue()

    machine, result = _start(path, venue)

    assert result is None
    snapshot = machine.snapshot
    assert snapshot.state is SolLiveState.OPEN
    assert (snapshot.entry_oid, snapshot.stop_oid) == (ENTRY_OID, STOP_OID)
    assert snapshot.position_size_signed == 5.84
    assert snapshot.opened_at_ms == 1_790_236_800_000
    assert snapshot.execution_plan is not None
    assert not [name for name, _ in venue.calls if name in MUTATIONS]
    assert [
        value for name, value in venue.calls if name == "order_status_by_client_id"
    ] == list(RAISE_IDS)
    written = _rows(path)[before:]
    assert all(row["profile_fingerprint"] == FINGERPRINT for row in written)
    kinds = [row["event_type"] for row in written]
    assert "fault" not in kinds
    assert not {"order_intent", "cancel_intent"} & set(kinds)
    resolutions = [
        row["payload"] for row in written if row["event_type"] == "stop_order"
    ]
    assert [p["client_order_id"] for p in resolutions] == list(RAISE_IDS)
    for payload in resolutions:
        assert payload["operation"] == "protective_stop_raise_restart_recovery"
        assert payload["accepted"] is False and payload["oid"] is None
        assert payload["status"] == UNINDEXED_RAISE_STATUS
        assert payload["recovered_after_restart"] is True
        assert isinstance(payload["error"], str) and payload["error"]
    states = [
        row["payload"] for row in written if row["event_type"] == "state_transition"
    ]
    assert [state["state"] for state in states] == ["PREFLIGHT", "OPEN"]
    assert states[-1]["stop_oid"] == STOP_OID
    owned = [row for row in _rows(path) if row["profile_fingerprint"] == FINGERPRINT]
    assert pending_order_intent(owned) is None


def test_the_next_restart_after_recovery_needs_no_further_resolution(
    tmp_path: Path,
) -> None:
    path = _seed_ledger(tmp_path, _recorded_rows())
    _start(path, RecordedBrentVenue())
    recovered = len(_rows(path))
    venue = RecordedBrentVenue()

    machine, _ = _start(path, venue)

    assert machine.snapshot.state is SolLiveState.OPEN
    assert machine.snapshot.stop_oid == STOP_OID
    assert not [name for name, _ in venue.calls if name == "order_status_by_client_id"]
    assert not [name for name, _ in venue.calls if name in MUTATIONS]
    written = _rows(path)[recovered:]
    assert not [row for row in written if row["event_type"] in {"stop_order", "fault"}]


def test_launch_two_history_now_journals_its_single_orphaned_raise(
    tmp_path: Path,
) -> None:
    rows = _recorded_rows()
    first_raise = next(
        index
        for index, row in enumerate(rows)
        if row["event_type"] == "order_intent"
        and row["payload"]["client_order_id"] == RAISE_IDS[0]
    )
    path = _seed_ledger(tmp_path, rows[: first_raise + 1])
    venue = RecordedBrentVenue()

    machine, _ = _start(path, venue)

    assert machine.snapshot.state is SolLiveState.OPEN
    assert machine.snapshot.stop_oid == STOP_OID
    written = _rows(path)[first_raise + 1 :]
    resolutions = [
        row["payload"] for row in written if row["event_type"] == "stop_order"
    ]
    assert [p["client_order_id"] for p in resolutions] == [RAISE_IDS[0]]
    assert resolutions[0]["status"] == UNINDEXED_RAISE_STATUS
    assert not [name for name, _ in venue.calls if name in MUTATIONS]
    owned = [row for row in _rows(path) if row["profile_fingerprint"] == FINGERPRINT]
    assert pending_order_intent(owned) is None


@pytest.mark.parametrize("indexed_id", RAISE_IDS)
@pytest.mark.parametrize("status", ["open", "filled", "canceled"])
def test_any_venue_indexed_raise_among_several_still_fails_closed(
    tmp_path: Path, indexed_id: str, status: str
) -> None:
    path = _seed_ledger(tmp_path, _recorded_rows())
    before = len(_rows(path))
    venue = RecordedBrentVenue(
        indexed={
            indexed_id: HyperliquidOrderStatus(
                555019000001, "xyz:BRENTOIL", status, 5.84, 1, indexed_id
            )
        }
    )

    with pytest.raises(SolLiveEngineError, match=MULTIPLE_UNRESOLVED_INTENTS):
        _start(path, venue)

    written = _rows(path)[before:]
    assert not [row for row in written if row["event_type"] == "stop_order"]
    assert [
        row["payload"]["reason"] for row in written if row["event_type"] == "fault"
    ] == [MULTIPLE_UNRESOLVED_INTENTS]
    assert not [name for name, _ in venue.calls if name in MUTATIONS]


def test_a_non_raise_intent_alongside_keeps_the_ambiguity_fail_closed(
    tmp_path: Path,
) -> None:
    rows = _recorded_rows()
    second_raise = next(
        index
        for index, row in enumerate(rows)
        if row["event_type"] == "order_intent"
        and row["payload"]["client_order_id"] == RAISE_IDS[1]
    )
    close_intent = {
        **rows[second_raise],
        "event_type": "order_intent",
        "payload": {
            "operation": "reduce_only_close",
            "client_order_id": "0x0123456789abcdef0123456789abcdef",
            "position_size_signed": 5.84,
            "mark_price": 102.0,
        },
    }
    path = _seed_ledger(
        tmp_path, [*rows[: second_raise + 1], close_intent, *rows[second_raise + 1 :]]
    )
    before = len(_rows(path))
    venue = RecordedBrentVenue()

    with pytest.raises(SolLiveEngineError, match=MULTIPLE_UNRESOLVED_INTENTS):
        _start(path, venue)

    written = _rows(path)[before:]
    assert not [row for row in written if row["event_type"] == "stop_order"]
    assert not [name for name, _ in venue.calls if name == "order_status_by_client_id"]
    assert not [name for name, _ in venue.calls if name in MUTATIONS]
