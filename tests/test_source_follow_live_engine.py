"""Offline lifecycle tests for the BTC 5m source-follow live engine."""

from dataclasses import replace
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest

from hypervector.live.hyperliquid_protocol import (
    HyperliquidFeeSchedule,
    HyperliquidOrderAck,
    SolAccountSnapshot,
    SolBookLevel,
    SolBookSnapshot,
    SolFill,
    SolMarketMetadata,
    SolOpenOrder,
    SolPositionSnapshot,
    SolReconciliationSnapshot,
    SolVenuePreflight,
)
from hypervector.live.source_follow_live_config import load_source_follow_live_config
from hypervector.live.source_follow_live_engine import (
    SourceFollowLiveEngine,
    SourceFollowLiveState,
)
from hypervector.live.source_follow_live_ledger import SourceFollowLiveLedger
from hypervector.regime.source_follow_runtime import (
    SourceFollowDecision,
    SourceLongObservation,
)

CONFIG = Path("configs/hypervelocity_source_follow_minrange12_alloc35_canary.toml")
BIDIRECTIONAL_CONFIG = Path(
    "configs/hypervelocity_source_follow_bidirectional_minrange12_alloc35_canary.toml"
)


class _Venue:
    def __init__(self) -> None:
        self.position = _position()
        self.orders: tuple[SolOpenOrder, ...] = ()
        self.fills: tuple[SolFill, ...] = ()
        self.calls: list[tuple[str, object]] = []

    def preflight(self, *, expected_max_leverage: int) -> SolVenuePreflight:
        return SolVenuePreflight(
            market=SolMarketMetadata("BTC", 5, expected_max_leverage),
            mark_price=64_000.0,
            price_tick=1.0,
            size_step=0.00001,
            fees=HyperliquidFeeSchedule(0.00015, 0.00045),
            account_value_usd=153.61,
            withdrawable_usd=153.61,
            position=self.position,
        )

    def book_snapshot(self, *, depth_levels: int) -> SolBookSnapshot:
        return SolBookSnapshot(
            exchange_timestamp_ms=1_785_513_900_000,
            bids=(SolBookLevel(63_999.0, 1.0, 1),),
            asks=(SolBookLevel(64_001.0, 1.0, 1),),
            mid_price=64_000.0,
            spread_bps=0.3125,
            bid_depth=1.0,
            ask_depth=1.0,
            order_pressure=0.0,
        )

    def configure_isolated_leverage(self, leverage: int) -> None:
        self.calls.append(("leverage", leverage))

    def reconcile(self) -> SolReconciliationSnapshot:
        account = SolAccountSnapshot(
            account_value_usd=153.61,
            withdrawable_usd=100.0 if self.position.size_signed else 153.61,
            total_margin_used_usd=self.position.margin_used_usd,
            total_notional_position_usd=self.position.position_value_usd,
            position=self.position,
        )
        return SolReconciliationSnapshot(account, self.orders, self.fills)

    def submit_entry(self, **kwargs: object) -> HyperliquidOrderAck:
        self.calls.append(("entry", kwargs))
        side = "B" if kwargs.get("side") == "long" else "A"
        self.orders = (_order(101, reduce_only=False, side=side),)
        return HyperliquidOrderAck(True, 101, "resting")

    def submit_target(self, **kwargs: object) -> HyperliquidOrderAck:
        self.calls.append(("target", kwargs))
        position = float(kwargs["position_size_signed"])
        side = "A" if position > 0.0 else "B"
        price = float(kwargs["limit_price"])
        self.orders = (_order(202, reduce_only=True, limit_price=price, side=side),)
        return HyperliquidOrderAck(True, 202, "resting")

    def cancel_order(self, oid: int) -> HyperliquidOrderAck:
        self.calls.append(("cancel", oid))
        self.orders = tuple(order for order in self.orders if order.oid != oid)
        return HyperliquidOrderAck(True, oid, "canceled")

    def close_position(self, **kwargs: object) -> HyperliquidOrderAck:
        self.calls.append(("close", kwargs))
        return HyperliquidOrderAck(True, 303, "filled")

    def funding_payments(self, **kwargs: int) -> tuple[()]:
        return ()


def _position(
    size: float = 0.0,
    *,
    entry: float | None = None,
) -> SolPositionSnapshot:
    return SolPositionSnapshot(
        size_signed=size,
        entry_price=entry,
        liquidation_price=66_010.0 if size else None,
        margin_used_usd=53.34 if size else 0.0,
        position_value_usd=1_600.0 if size else 0.0,
        unrealized_pnl_usd=0.0,
        leverage_type="isolated" if size else None,
        leverage=30 if size else None,
    )


def _order(
    oid: int,
    *,
    reduce_only: bool,
    limit_price: float = 64_001.0,
    side: str | None = None,
) -> SolOpenOrder:
    return SolOpenOrder(
        oid=oid,
        size=0.025,
        original_size=0.025,
        side=side or ("B" if reduce_only else "A"),
        reduce_only=reduce_only,
        is_trigger=False,
        trigger_price=None,
        order_type="Limit",
        timestamp_ms=1_785_513_900_000,
        limit_price=limit_price,
    )


def _target_fill(
    oid: int,
    *,
    timestamp_ms: int = 1_785_513_960_000,
) -> SolFill:
    return SolFill(
        oid=oid,
        price=63_830.33,
        size=0.02499,
        side="B",
        timestamp_ms=timestamp_ms,
        fee_usd=0.2393,
        fee_token="USDC",
        closed_pnl_usd=4.2658,
        crossed=False,
        direction="Close Short",
        transaction_hash="0xtarget",
        trade_id=timestamp_ms + oid,
    )


def _long_target_fill(oid: int) -> SolFill:
    return SolFill(
        oid=oid,
        price=64_169.664,
        size=0.025,
        side="A",
        timestamp_ms=1_785_513_960_000,
        fee_usd=0.2406,
        fee_token="USDC",
        closed_pnl_usd=4.2666,
        crossed=False,
        direction="Close Long",
        transaction_hash="0xlongtarget",
        trade_id=20_202,
    )


def _entry_fill(oid: int, timestamp_ms: int) -> SolFill:
    return SolFill(
        oid=oid,
        price=64_001.0,
        size=0.02499,
        side="A",
        timestamp_ms=timestamp_ms,
        fee_usd=0.24,
        fee_token="USDC",
        closed_pnl_usd=0.0,
        crossed=False,
        direction="Open Short",
        transaction_hash="0xentry",
        trade_id=timestamp_ms + oid,
    )


class _ImmediateTargetVenue(_Venue):
    def submit_target(self, **kwargs: object) -> HyperliquidOrderAck:
        self.calls.append(("target", kwargs))
        self.position = _position()
        self.orders = ()
        self.fills = (_target_fill(202),)
        return HyperliquidOrderAck(True, 202, "filled")


class _CloseFlattensVenue(_Venue):
    def close_position(self, **kwargs: object) -> HyperliquidOrderAck:
        self.calls.append(("close", kwargs))
        self.position = _position()
        self.orders = ()
        return HyperliquidOrderAck(True, 303, "filled")


class _TargetRejectVenue(_CloseFlattensVenue):
    def submit_target(self, **kwargs: object) -> HyperliquidOrderAck:
        self.calls.append(("target", kwargs))
        self.orders = ()
        return HyperliquidOrderAck(False, None, "rejected", error="ALO rejected")


class _TargetRejectStuckVenue(_Venue):
    def submit_target(self, **kwargs: object) -> HyperliquidOrderAck:
        self.calls.append(("target", kwargs))
        self.orders = ()
        return HyperliquidOrderAck(False, None, "rejected", error="ALO rejected")


class _TargetFillsDuringCancelVenue(_Venue):
    def cancel_order(self, oid: int) -> HyperliquidOrderAck:
        if oid != 202:
            return super().cancel_order(oid)
        self.calls.append(("cancel", oid))
        self.position = _position()
        self.orders = ()
        self.fills = (_target_fill(oid),)
        return HyperliquidOrderAck(True, oid, "canceled")


class _ResidualCancelRejectVenue(_Venue):
    def cancel_order(self, oid: int) -> HyperliquidOrderAck:
        self.calls.append(("cancel", oid))
        return HyperliquidOrderAck(False, oid, "rejected", error="cancel rejected")


def _decision(at: datetime) -> SourceFollowDecision:
    return SourceFollowDecision(
        label_time_utc=at - timedelta(minutes=5),
        available_at_utc=at,
        primary="TREND_DOWN",
        secondary=None,
        confidence=0.82,
        primary_onset=True,
        source_event=True,
        signal_range_bps=18.0,
        entry_eligible=True,
        entry_direction="short",
        maximum_hold_seconds=86_400.0,
        exclusion_reason=None,
        bar_open=63_950.0,
        bar_high=64_020.0,
        bar_low=63_900.0,
        bar_close=64_000.0,
        bar_volume=123.45,
    )


def _long_decision(at: datetime) -> SourceFollowDecision:
    return SourceFollowDecision(
        label_time_utc=at - timedelta(minutes=5),
        available_at_utc=at,
        primary="TREND_UP",
        secondary=None,
        confidence=0.82,
        primary_onset=True,
        source_event=True,
        signal_range_bps=18.0,
        entry_eligible=True,
        entry_direction="long",
        maximum_hold_seconds=86_400.0,
        exclusion_reason=None,
        bar_open=63_950.0,
        bar_high=64_020.0,
        bar_low=63_900.0,
        bar_close=64_000.0,
        bar_volume=123.45,
    )


def _engine(
    tmp_path: Path,
    venue: _Venue,
    now: datetime | Callable[[], datetime],
    config_path: Path = CONFIG,
) -> SourceFollowLiveEngine:
    config = load_source_follow_live_config(
        config_path,
        enabled=True,
        accepts_live_risk=True,
    )
    ledger_path = tmp_path / "data/live/hypervelocity_source_follow/decisions.jsonl"
    config = replace(
        config, backend_ledger=ledger_path, stop_file=ledger_path.parent / "STOP"
    )
    ledger = SourceFollowLiveLedger(
        path=ledger_path,
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id="btc-live-test",
    )
    now_fn = now if callable(now) else lambda: now
    return SourceFollowLiveEngine(
        config=config,
        adapter=venue,
        ledger=ledger,
        credentials_present=True,
        now_fn=now_fn,
        client_order_id_fn=lambda: "0x0123456789abcdef0123456789abcdef",
    )


def test_bidirectional_signal_submits_long_and_places_matching_target(
    tmp_path: Path,
) -> None:
    """A qualified uptrend opens at the bid and protects the reconciled long."""
    now = datetime(2026, 7, 31, 16, 5, tzinfo=UTC)
    venue = _Venue()
    engine = _engine(tmp_path, venue, now, BIDIRECTIONAL_CONFIG)
    engine.start()

    pending = engine.process(_long_decision(now))

    assert pending.state is SourceFollowLiveState.ENTRY_PENDING
    entry = next(payload for operation, payload in venue.calls if operation == "entry")
    assert isinstance(entry, dict)
    assert entry["side"] == "long"
    assert entry["limit_price"] == pytest.approx(63_999.0)
    venue.position = _position(0.025, entry=63_999.0)

    protected = engine.process(None)

    assert protected.state is SourceFollowLiveState.OPEN_TARGET_RESTING
    target = next(
        payload for operation, payload in venue.calls if operation == "target"
    )
    assert isinstance(target, dict)
    assert target["position_size_signed"] == pytest.approx(0.025)
    assert target["limit_price"] == pytest.approx(64_169.664)
    assert venue.orders[0].side == "A"
    ledger = tmp_path / "data/live/hypervelocity_source_follow/decisions.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    identity = next(
        row for row in rows if row["event_type"] == "configuration_identity"
    )
    assert identity["payload"]["regime_policy"]["side"] == "bidirectional"
    assert identity["payload"]["regime_policy"]["breakout_requires_direction"] is True
    assert identity["payload"]["network"] == "mainnet"
    assert identity["payload"]["metalabel_policy"] == {
        "observation_type": "annotation_collection",
        "inference_active": False,
        "bundle_id": None,
        "probabilities_emitted": False,
        "may_filter": False,
        "may_scale": False,
        "execution_authority": "none",
    }
    target_intent = next(
        row
        for row in rows
        if row["event_type"] == "order_intent"
        and row["payload"].get("operation") == "target"
    )
    assert target_intent["payload"]["side"] == "sell"
    regime = next(row for row in rows if row["event_type"] == "regime_decision")
    assert regime["payload"]["entry_direction"] == "long"
    assert regime["payload"]["long_entry"] is True
    assert regime["payload"]["short_entry"] is False
    assert regime["payload"]["decision_action"] == "enter_long"


def test_bidirectional_restart_recovers_an_isolated_long_target(tmp_path: Path) -> None:
    """A restart adopts one valid long and its exact reduce-only sell target."""
    now = datetime(2026, 7, 31, 16, 5, tzinfo=UTC)
    venue = _Venue()
    venue.position = _position(0.025, entry=63_999.0)
    venue.orders = (_order(202, reduce_only=True, limit_price=64_169.664, side="A"),)

    snapshot = _engine(tmp_path, venue, now, BIDIRECTIONAL_CONFIG).start()

    assert snapshot.state is SourceFollowLiveState.OPEN_TARGET_RESTING
    assert snapshot.position_size_signed == pytest.approx(0.025)
    assert snapshot.target_oid == 202
    assert not [call for call in venue.calls if call[0] == "entry"]


def test_short_only_wrapper_refuses_an_existing_long(tmp_path: Path) -> None:
    """A wrong wrapper cannot silently adopt exposure outside its side contract."""
    now = datetime(2026, 7, 31, 16, 5, tzinfo=UTC)
    venue = _Venue()
    venue.position = _position(0.025, entry=63_999.0)

    with pytest.raises(RuntimeError, match="refuses a BTC long"):
        _engine(tmp_path, venue, now).start()


def test_bidirectional_long_target_fill_is_verified_before_close_attribution(
    tmp_path: Path,
) -> None:
    """The long lifecycle records TP only after venue-flat matching fill evidence."""
    now = datetime(2026, 7, 31, 16, 5, tzinfo=UTC)
    venue = _Venue()
    engine = _engine(tmp_path, venue, now, BIDIRECTIONAL_CONFIG)
    engine.start()
    engine.process(_long_decision(now))
    venue.position = _position(0.025, entry=63_999.0)
    engine.process(None)
    venue.position = _position()
    venue.orders = ()
    venue.fills = (_long_target_fill(202),)

    assert engine.process(None).state is SourceFollowLiveState.FLAT

    ledger = tmp_path / "data/live/hypervelocity_source_follow/decisions.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    closes = [
        row
        for row in rows
        if row["event_type"] == "close" and row["payload"].get("reason") == "target"
    ]
    assert len(closes) == 1
    assert closes[0]["payload"]["oid"] == 202


def test_fresh_signal_submits_one_capped_post_only_short(tmp_path: Path) -> None:
    """A qualified completed-5m onset creates exactly one maker entry."""
    now = datetime(2026, 7, 31, 16, 5, tzinfo=UTC)
    venue = _Venue()
    engine = _engine(tmp_path, venue, now)
    assert engine.start().state is SourceFollowLiveState.FLAT

    snapshot = engine.process(_decision(now))

    assert snapshot.state is SourceFollowLiveState.ENTRY_PENDING
    entry = next(payload for operation, payload in venue.calls if operation == "entry")
    assert isinstance(entry, dict)
    assert entry["side"] == "short"
    assert entry["limit_price"] == pytest.approx(64_001.0)
    assert entry["requested_notional_usd"] == pytest.approx(1_612.905)
    ledger = tmp_path / "data/live/hypervelocity_source_follow/decisions.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    identity = next(
        row for row in rows if row["event_type"] == "configuration_identity"
    )
    assert identity["payload"]["exits"] == {
        "fixed_stop": "none",
        "maximum_hold_seconds": 86_400.0,
        "mode": "target_or_maximum_hold_no_fixed_stop",
        "range_policy": "hold_until_target_or_maximum_hold",
        "target_basis": "gross_margin_return_before_fees_and_funding",
        "target_margin_pct": 8.0,
        "target_price_fraction": pytest.approx(8.0 / 30.0 / 100.0),
    }
    assert identity["payload"]["observer_policies"] == {
        "execution_authority": "none",
        "side": "long",
        "recipes": [
            "bk_up_asia_conf06",
            "fade_td_eu",
            "bk_up_24h_challenger",
            "trend_up_24h_challenger",
            "trend_down_24h_direction_challenger",
        ],
    }
    regime = next(row for row in rows if row["event_type"] == "regime_decision")
    assert regime["payload"]["state_1m"] == "NOT_CLASSIFIED"
    assert regime["payload"]["context_15m"] == "NOT_CLASSIFIED"
    assert (
        regime["payload"]["regime_score_source"]
        == "pinned_hypertrader_classifier_confidence"
    )
    assert regime["payload"]["primary_onset"] is True
    assert regime["payload"]["source_event"] is True
    assert regime["payload"]["feed_ts"] == "2026-07-31T16:00:00+00:00"
    assert regime["payload"]["reference_price"] == 64_000.0
    assert regime["payload"]["open"] == 63_950.0
    assert regime["payload"]["high"] == 64_020.0
    assert regime["payload"]["low"] == 63_900.0
    assert regime["payload"]["volume"] == 123.45
    assert regime["payload"]["entry_pulse_expires_at_utc"] == (
        "2026-07-31T16:06:00+00:00"
    )


def test_warm_history_is_visible_but_cannot_submit_an_order(tmp_path: Path) -> None:
    """Warm chart candles remain explicitly outside the execution path."""
    now = datetime(2026, 7, 31, 16, 5, tzinfo=UTC)
    venue = _Venue()
    engine = _engine(tmp_path, venue, now, BIDIRECTIONAL_CONFIG)
    engine.start()

    engine.record_history((_decision(now),))

    assert not [call for call in venue.calls if call[0] == "entry"]
    ledger = tmp_path / "data/live/hypervelocity_source_follow/decisions.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    history = next(row for row in rows if row["event_type"] == "regime_history")
    assert history["payload"]["entry_allowed"] is False
    assert history["payload"]["decision_action"] == "history_only"
    assert history["payload"]["reference_price"] == 64_000.0


def test_exact_source_long_observation_cannot_submit_a_live_order(
    tmp_path: Path,
) -> None:
    """Creator-source long evidence remains annotation-only in an armed engine."""
    now = datetime(2026, 7, 31, 16, 5, tzinfo=UTC)
    venue = _Venue()
    engine = _engine(tmp_path, venue, now)
    engine.start()
    observed = SourceFollowDecision(
        label_time_utc=now - timedelta(minutes=5),
        available_at_utc=now,
        primary="TREND_DOWN",
        secondary=None,
        confidence=0.4,
        primary_onset=True,
        source_event=False,
        signal_range_bps=18.0,
        entry_eligible=False,
        entry_direction=None,
        maximum_hold_seconds=None,
        exclusion_reason="source_confidence",
        bar_open=63_950.0,
        bar_high=64_020.0,
        bar_low=63_900.0,
        bar_close=64_000.0,
        bar_volume=123.45,
        source_long_observation=SourceLongObservation(
            recipe_id="fade_td_eu",
            maximum_hold_seconds=86_400.0,
        ),
    )

    engine.process(observed)

    assert not [call for call in venue.calls if call[0] == "entry"]
    ledger = tmp_path / "data/live/hypervelocity_source_follow/decisions.jsonl"
    records = [json.loads(line) for line in ledger.read_text().splitlines()]
    regime = next(row for row in records if row["event_type"] == "regime_decision")
    assert regime["payload"]["source_long_observer"] == {
        "authority": "observe_only",
        "recipe_id": "fade_td_eu",
        "side": "long",
        "maximum_hold_seconds": 86_400.0,
    }
    assert regime["payload"]["long_entry"] is False
    assert regime["payload"]["entry_allowed"] is False


def test_new_live_ledger_baselines_preexisting_venue_fills(tmp_path: Path) -> None:
    """Historical account fills must not become trades in a fresh canary run."""
    now = datetime(2026, 7, 31, 16, 5, tzinfo=UTC)
    venue = _Venue()
    venue.fills = (_target_fill(900, timestamp_ms=1_785_513_840_000),)
    engine = _engine(tmp_path, venue, now)

    engine.start()

    ledger = tmp_path / "data/live/hypervelocity_source_follow/decisions.jsonl"
    startup = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert not [row for row in startup if row["event_type"] == "fill"]
    assert not [
        row
        for row in startup
        if row["event_type"] == "fee" and row["payload"].get("source") == "fill"
    ]

    venue.fills = (*venue.fills, _target_fill(901))
    engine.process(None)

    records = [json.loads(line) for line in ledger.read_text().splitlines()]
    fills = [row for row in records if row["event_type"] == "fill"]
    assert [row["payload"]["oid"] for row in fills] == [901]


def test_restart_retains_historical_fill_baseline_and_recovers_new_fill(
    tmp_path: Path,
) -> None:
    """Restart must ignore pre-run fills but recover a post-start unlogged fill."""
    first_now = datetime(2026, 7, 31, 16, 5, tzinfo=UTC)
    venue = _Venue()
    historical = _target_fill(900, timestamp_ms=1_785_513_840_000)
    venue.fills = (historical,)
    _engine(tmp_path, venue, first_now).start()

    venue.fills = (historical, _target_fill(901))
    restarted_at = datetime(2026, 7, 31, 16, 7, tzinfo=UTC)
    _engine(tmp_path, venue, restarted_at).start()

    ledger = tmp_path / "data/live/hypervelocity_source_follow/decisions.jsonl"
    records = [json.loads(line) for line in ledger.read_text().splitlines()]
    fills = [row for row in records if row["event_type"] == "fill"]
    assert [row["payload"]["oid"] for row in fills] == [901]


def test_partial_entry_is_canceled_then_protected_by_exact_target(
    tmp_path: Path,
) -> None:
    """Reconciled exposure owns one target and no residual opening order."""
    now = datetime(2026, 7, 31, 16, 5, tzinfo=UTC)
    venue = _Venue()
    engine = _engine(tmp_path, venue, now)
    engine.start()
    engine.process(_decision(now))
    venue.position = _position(-0.02499, entry=64_001.0)

    snapshot = engine.process(None)

    assert snapshot.state is SourceFollowLiveState.OPEN_TARGET_RESTING
    assert snapshot.target_oid == 202
    assert ("cancel", 101) in venue.calls
    target = next(
        payload for operation, payload in venue.calls if operation == "target"
    )
    assert isinstance(target, dict)
    assert target["position_size_signed"] == pytest.approx(-0.02499)
    assert target["limit_price"] == pytest.approx(63_830.3306667)


def test_residual_cancel_rejection_faults_without_crashing(tmp_path: Path) -> None:
    """An uncanceled opening residual remains visible as a durable fault."""
    now = datetime(2026, 7, 31, 16, 5, tzinfo=UTC)
    venue = _ResidualCancelRejectVenue()
    engine = _engine(tmp_path, venue, now)
    engine.start()
    engine.process(_decision(now))
    venue.position = _position(-0.01, entry=64_001.0)

    snapshot = engine.process(None)

    assert snapshot.state is SourceFollowLiveState.FAULT
    assert snapshot.last_fault == "entry residual cancellation failed"
    ledger = tmp_path / "data/live/hypervelocity_source_follow/decisions.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert any(
        row["event_type"] == "fault"
        and row["payload"]["reason"] == "entry residual cancellation failed"
        for row in rows
    )


def test_target_rejection_closes_and_verifies_flat(tmp_path: Path) -> None:
    """A missing target cannot leave live exposure unmanaged."""
    now = datetime(2026, 7, 31, 16, 5, tzinfo=UTC)
    venue = _TargetRejectVenue()
    engine = _engine(tmp_path, venue, now)
    engine.start()
    engine.process(_decision(now))
    venue.position = _position(-0.02499, entry=64_001.0)

    snapshot = engine.process(None)

    assert snapshot.state is SourceFollowLiveState.FLAT
    assert any(operation == "close" for operation, _ in venue.calls)
    ledger = tmp_path / "data/live/hypervelocity_source_follow/decisions.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    close = next(
        row
        for row in rows
        if row["event_type"] == "close" and row["payload"].get("verified_flat") is True
    )
    assert close["payload"]["reason"] == "target_submission_failure"


def test_target_rejection_faults_when_close_never_reconciles_flat(
    tmp_path: Path,
) -> None:
    """A successful close acknowledgment cannot substitute for flat exposure."""
    now = datetime(2026, 7, 31, 16, 5, tzinfo=UTC)
    venue = _TargetRejectStuckVenue()
    engine = _engine(tmp_path, venue, now)
    engine.start()
    engine.process(_decision(now))
    venue.position = _position(-0.02499, entry=64_001.0)

    snapshot = engine.process(None)

    assert snapshot.state is SourceFollowLiveState.FAULT
    assert snapshot.last_fault == (
        "target_submission_failure close did not reconcile flat"
    )


def test_restart_preserves_the_venue_entry_time_for_maximum_hold(
    tmp_path: Path,
) -> None:
    """Restart recovery cannot reset an existing position's hold clock."""
    opened_at_ms = 1_785_513_900_000
    now = datetime.fromtimestamp((opened_at_ms + 300_000) / 1_000, tz=UTC)
    venue = _Venue()
    venue.position = _position(-0.02499, entry=64_001.0)
    venue.fills = (_entry_fill(101, opened_at_ms),)

    snapshot = _engine(tmp_path, venue, now).start()

    assert snapshot.state is SourceFollowLiveState.OPEN_TARGET_RESTING
    assert snapshot.opened_at_ms == opened_at_ms


def test_immediate_target_fill_emits_a_verified_close(tmp_path: Path) -> None:
    """A target filled before its first poll still closes the journal lifecycle."""
    now = datetime(2026, 7, 31, 16, 5, tzinfo=UTC)
    venue = _ImmediateTargetVenue()
    engine = _engine(tmp_path, venue, now)
    engine.start()
    engine.process(_decision(now))
    venue.position = _position(-0.02499, entry=64_001.0)

    snapshot = engine.process(None)

    assert snapshot.state is SourceFollowLiveState.FLAT
    ledger = tmp_path / "data/live/hypervelocity_source_follow/decisions.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    close = next(
        row
        for row in rows
        if row["event_type"] == "close" and row["payload"].get("reason") == "target"
    )
    assert close["payload"]["oid"] == 202
    assert close["payload"]["verified_flat"] is True


def test_reconciled_target_fill_records_verified_target_close(tmp_path: Path) -> None:
    """A venue-flat target lifecycle carries an explicit journal exit reason."""
    now = datetime(2026, 7, 31, 16, 5, tzinfo=UTC)
    venue = _Venue()
    engine = _engine(tmp_path, venue, now)
    engine.start()
    engine.process(_decision(now))
    venue.position = _position(-0.02499, entry=64_001.0)
    engine.process(None)
    venue.position = _position()
    venue.orders = ()
    venue.fills = (_target_fill(202),)

    snapshot = engine.process(None)

    assert snapshot.state is SourceFollowLiveState.FLAT
    ledger = tmp_path / "data/live/hypervelocity_source_follow/decisions.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    target_close = next(
        row
        for row in rows
        if row["event_type"] == "close" and row["payload"].get("reason") == "target"
    )
    assert target_close["payload"] == {
        "oid": 202,
        "reason": "target",
        "verified_flat": True,
    }


def test_unattributed_flat_does_not_claim_strategy_target(tmp_path: Path) -> None:
    """A different close order remains unattributed instead of becoming a false TP."""
    now = datetime(2026, 7, 31, 16, 5, tzinfo=UTC)
    venue = _Venue()
    engine = _engine(tmp_path, venue, now)
    engine.start()
    engine.process(_decision(now))
    venue.position = _position(-0.02499, entry=64_001.0)
    engine.process(None)
    venue.position = _position()
    venue.orders = ()
    venue.fills = (_target_fill(404),)

    assert engine.process(None).state is SourceFollowLiveState.FLAT

    ledger = tmp_path / "data/live/hypervelocity_source_follow/decisions.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert not any(
        row["event_type"] == "close" and row["payload"].get("reason") == "target"
        for row in rows
    )


def test_unfilled_entry_expires_after_exact_sixty_second_ttl(tmp_path: Path) -> None:
    """An old maker quote is canceled and cannot chase the same onset."""
    clock = [datetime(2026, 7, 31, 16, 5, tzinfo=UTC)]
    venue = _Venue()
    engine = _engine(tmp_path, venue, lambda: clock[0])
    engine.start()
    engine.process(_decision(clock[0]))
    venue.orders = (
        replace(venue.orders[0], timestamp_ms=int(clock[0].timestamp() * 1_000)),
    )
    clock[0] += timedelta(seconds=60)

    snapshot = engine.process(None)

    assert snapshot.state is SourceFollowLiveState.FLAT
    assert ("cancel", 101) in venue.calls


def test_maximum_hold_cancels_target_before_reduce_only_close(tmp_path: Path) -> None:
    """The bounded hold exits from fresh venue state without leaving a target."""
    clock = [datetime(2026, 7, 31, 16, 5, tzinfo=UTC)]
    venue = _CloseFlattensVenue()
    engine = _engine(tmp_path, venue, lambda: clock[0])
    engine.start()
    engine.process(_decision(clock[0]))
    venue.position = _position(-0.02499, entry=64_001.0)
    engine.process(None)
    clock[0] += timedelta(seconds=86_400)

    snapshot = engine.process(None)

    assert snapshot.state is SourceFollowLiveState.FLAT
    assert ("cancel", 202) in venue.calls
    close = next(payload for operation, payload in venue.calls if operation == "close")
    assert isinstance(close, dict)
    assert close["position_size_signed"] == pytest.approx(-0.02499)


def test_target_fill_during_maximum_hold_cancel_avoids_stale_close(
    tmp_path: Path,
) -> None:
    """A cancel/fill race re-reconciles before any reduce-only close request."""
    clock = [datetime(2026, 7, 31, 16, 5, tzinfo=UTC)]
    venue = _TargetFillsDuringCancelVenue()
    engine = _engine(tmp_path, venue, lambda: clock[0])
    engine.start()
    engine.process(_decision(clock[0]))
    venue.position = _position(-0.02499, entry=64_001.0)
    engine.process(None)
    clock[0] += timedelta(seconds=86_400)

    snapshot = engine.process(None)

    assert snapshot.state is SourceFollowLiveState.FLAT
    assert not any(operation == "close" for operation, _ in venue.calls)
    ledger = tmp_path / "data/live/hypervelocity_source_follow/decisions.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert any(
        row["event_type"] == "close"
        and row["payload"].get("reason") == "target"
        and row["payload"].get("verified_flat") is True
        for row in rows
    )
