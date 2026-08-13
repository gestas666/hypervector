"""Backend-authoritative telemetry contracts for the Apex MM canary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from hypervector.live.apex_mm_live_config import load_apex_mm_live_config
from hypervector.live.apex_mm_live_ledger import ApexMMLiveLedger
from hypervector.live.apex_mm_live_models import ApexMMLiveSnapshot, ApexMMLiveState
from hypervector.live.apex_mm_live_telemetry import ApexMMLiveTelemetry
from hypervector.live.hyperliquid_protocol import (
    HyperliquidFeeSchedule,
    HyperliquidOrderAck,
    SolAccountSnapshot,
    SolBookLevel,
    SolBookSnapshot,
    SolFill,
    SolMarketMetadata,
    SolPositionSnapshot,
    SolReconciliationSnapshot,
    SolVenuePreflight,
)
from hypervector.research.apex_regime_mm_policy import ApexMMQuote


def _position() -> SolPositionSnapshot:
    return SolPositionSnapshot(0.0, None, None, 0.0, 0.0, 0.0, None, None)


def _venue(*fills: SolFill) -> SolReconciliationSnapshot:
    position = _position()
    account = SolAccountSnapshot(150.0, 150.0, 0.0, 0.0, position)
    return SolReconciliationSnapshot(account, (), tuple(fills))


def _active_venue(size: float, liquidation_price: float) -> SolReconciliationSnapshot:
    position = SolPositionSnapshot(
        size,
        100.0,
        liquidation_price,
        10.0,
        abs(size) * 100.0,
        0.0,
        "isolated",
        3,
    )
    account = SolAccountSnapshot(150.0, 140.0, 10.0, abs(size) * 100.0, position)
    return SolReconciliationSnapshot(account, (), ())


def _preflight() -> SolVenuePreflight:
    return SolVenuePreflight(
        SolMarketMetadata("BTC", 5, 40),
        100.5,
        1.0,
        0.00001,
        HyperliquidFeeSchedule(0.00015, 0.00045),
        150.0,
        150.0,
        _position(),
        "unifiedAccount",
    )


def _book(timestamp_ms: int, midpoint: float = 100.5) -> SolBookSnapshot:
    bid = midpoint - 0.5
    ask = midpoint + 0.5
    return SolBookSnapshot(
        timestamp_ms,
        (SolBookLevel(bid, 2.0, 1),),
        (SolBookLevel(ask, 2.0, 1),),
        midpoint,
        (ask - bid) / midpoint * 10_000.0,
        2.0,
        2.0,
        0.0,
    )


def _telemetry(
    tmp_path: Path,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[ApexMMLiveTelemetry, ApexMMLiveLedger]:
    config = load_apex_mm_live_config(
        "configs/apex_regime_mm_canary.toml",
        enabled=True,
        accepts_live_risk=True,
    )
    ledger = ApexMMLiveLedger(
        path=tmp_path / "data/live/apex_regime_mm/decisions.jsonl",
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id="run-id",
    )
    telemetry = ApexMMLiveTelemetry(
        config=config,
        ledger=ledger,
        now_fn=now_fn or (lambda: datetime(2026, 8, 1, 12, 0, tzinfo=UTC)),
    )
    return telemetry, ledger


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, milliseconds: int) -> None:
        self.now += timedelta(milliseconds=milliseconds)


def test_configuration_quote_and_state_are_strategy_attributed(tmp_path: Path) -> None:
    telemetry, ledger = _telemetry(tmp_path)
    telemetry.emit_preflight(_preflight(), _venue())
    telemetry.emit_quote(
        ApexMMQuote(True, "active", 100.5, 100.0, 101.0, 0.1, 0.1, 99.5, 0.0),
        0.0,
    )
    telemetry.emit_state(ApexMMLiveSnapshot(ApexMMLiveState.QUOTING, 1, 2, 0.0, 1_000))

    records = ledger.read_all()
    identity = next(
        row for row in records if row["event_type"] == "configuration_identity"
    )
    quote = next(row for row in records if row["event_type"] == "theoretical_quote")
    state = next(row for row in records if row["event_type"] == "state_transition")

    assert identity["payload"]["strategy_name"] == "apex_regime_mm_v2"
    assert identity["payload"]["execution"]["maximum_book_age_ms"] == 1_000
    assert identity["payload"]["execution"]["depth_levels"] == 5
    assert identity["payload"]["execution"]["minimum_order_notional_usd"] == 10.0
    assert identity["payload"]["execution"]["submission_transport"] == (
        "single_bulk_orders_action"
    )
    assert identity["payload"]["execution"]["fill_identity"] == "hyperliquid_tid"
    assert quote["payload"]["bid_price"] == 100.0
    assert quote["payload"]["ask_price"] == 101.0
    assert state["payload"]["bid_oid"] == 1
    assert state["payload"]["ask_oid"] == 2


def test_new_maker_fill_gets_one_second_directional_markout(tmp_path: Path) -> None:
    telemetry, ledger = _telemetry(tmp_path)
    telemetry.emit_preflight(_preflight(), _venue())
    telemetry.emit_quote(
        ApexMMQuote(True, "active", 100.5, 100.0, 101.0, 0.1, 0.1, 99.5, 0.0),
        0.0,
    )
    telemetry.emit_state(
        ApexMMLiveSnapshot(
            ApexMMLiveState.QUOTING,
            7,
            8,
            0.0,
            1_785_585_600_000,
        )
    )
    fill = SolFill(
        7,
        100.0,
        0.1,
        "B",
        1_785_585_600_000,
        0.0015,
        "USDC",
        0.0,
        False,
        "Open Long",
        "0xfill",
        7_001,
    )

    telemetry.emit_reconciliation(_venue(fill))
    telemetry.emit_book(_book(1_785_585_601_000, midpoint=101.0))

    records = ledger.read_all()
    markout = next(row for row in records if row["event_type"] == "fill_markout")
    quality = next(row for row in records if row["event_type"] == "execution_quality")
    assert markout["payload"]["oid"] == 7
    assert markout["payload"]["markout_bps"] == 100.0
    assert markout["payload"]["liquidity_side"] == "maker"
    assert quality["payload"]["expected_quote_price"] == 100.0
    assert quality["payload"]["slippage_bps"] == 0.0


def test_resting_order_keeps_its_submitted_price_when_theoretical_quote_moves(
    tmp_path: Path,
) -> None:
    telemetry, ledger = _telemetry(tmp_path)
    telemetry.emit_preflight(_preflight(), _venue())
    telemetry.emit_quote(
        ApexMMQuote(True, "active", 100.5, 100.0, 101.0, 0.1, 0.1, 99.5, 0.0),
        0.0,
    )
    telemetry.emit_ack("quote_buy", HyperliquidOrderAck(True, 7, "resting"))
    telemetry.emit_state(
        ApexMMLiveSnapshot(
            ApexMMLiveState.QUOTING,
            7,
            8,
            0.0,
            1_785_585_600_000,
        )
    )
    telemetry.emit_quote(
        ApexMMQuote(True, "active", 100.0, 99.0, 101.0, 0.1, 0.1, 199.0, 0.0),
        0.0,
    )
    telemetry.emit_state(
        ApexMMLiveSnapshot(
            ApexMMLiveState.QUOTING,
            7,
            8,
            0.0,
            1_785_585_600_000,
        )
    )
    fill = SolFill(
        7,
        100.0,
        0.1,
        "B",
        1_785_585_600_500,
        0.0015,
        "USDC",
        0.0,
        False,
        "Open Long",
        "0xresting-fill",
        7_002,
    )

    telemetry.emit_reconciliation(_venue(fill))

    quality = next(
        row for row in ledger.read_all() if row["event_type"] == "execution_quality"
    )
    assert quality["payload"]["expected_quote_price"] == 100.0
    assert quality["payload"]["slippage_bps"] == 0.0


def test_active_inventory_emits_liquidation_distance_from_backend_facts(
    tmp_path: Path,
) -> None:
    telemetry, ledger = _telemetry(tmp_path)
    telemetry.emit_preflight(_preflight(), _venue())
    telemetry.emit_reconciliation(_active_venue(0.1, 70.0))

    telemetry.emit_book(_book(2_000, midpoint=100.0))

    distance = next(
        row for row in ledger.read_all() if row["event_type"] == "liquidation_distance"
    )
    assert distance["payload"]["side"] == "long"
    assert distance["payload"]["mark_price"] == 100.0
    assert distance["payload"]["liquidation_price"] == 70.0
    assert distance["payload"]["distance_pct"] == 30.0


def test_order_ack_records_explicit_local_round_trip_latency(tmp_path: Path) -> None:
    clock = _Clock()
    telemetry, ledger = _telemetry(tmp_path, clock)
    client_order_id = "0x" + "1" * 32
    telemetry.emit_order_intent(
        operation="maker_quote",
        side="buy",
        quantity_or_notional=12.5,
        limit_price=100.0,
        client_order_id=client_order_id,
    )
    clock.advance(37)

    telemetry.emit_ack(
        "quote_buy",
        HyperliquidOrderAck(
            True,
            7,
            "resting",
            client_order_id=client_order_id,
        ),
    )

    ack = next(
        row for row in ledger.read_all() if row["event_type"] == "order_acknowledgement"
    )
    assert ack["payload"]["round_trip_latency_ms"] == 37


def test_cleanup_fill_uses_its_own_submitted_price_for_slippage(tmp_path: Path) -> None:
    telemetry, ledger = _telemetry(tmp_path)
    telemetry.emit_preflight(_preflight(), _venue())
    client_order_id = "0x" + "2" * 32
    telemetry.emit_order_intent(
        operation="close_operator_stop",
        side="sell",
        quantity_or_notional=10.0,
        limit_price=100.0,
        client_order_id=client_order_id,
    )
    telemetry.emit_ack(
        "close_operator_stop",
        HyperliquidOrderAck(
            True,
            9,
            "filled",
            client_order_id=client_order_id,
        ),
    )
    fill = SolFill(
        9,
        100.0,
        0.1,
        "A",
        1_785_585_600_000,
        0.0045,
        "USDC",
        0.0,
        True,
        "Close Long",
        "0xcleanup",
        9_001,
    )

    telemetry.emit_reconciliation(_venue(fill))

    quality = next(
        row for row in ledger.read_all() if row["event_type"] == "execution_quality"
    )
    assert quality["payload"]["expected_quote_price"] == 100.0
    assert quality["payload"]["slippage_bps"] == 0.0


def test_preflight_baselines_historical_fills_without_markout(tmp_path: Path) -> None:
    telemetry, ledger = _telemetry(tmp_path)
    old = SolFill(
        1,
        100.0,
        0.1,
        "B",
        1_000,
        0.0,
        "USDC",
        0.0,
        False,
        "Open Long",
        "old",
        1_001,
    )

    telemetry.emit_preflight(_preflight(), _venue(old))
    telemetry.emit_book(_book(10_000, midpoint=110.0))

    assert not any(row["event_type"] == "fill_markout" for row in ledger.read_all())


def test_late_rest_history_before_run_start_never_becomes_current_markout(
    tmp_path: Path,
) -> None:
    telemetry, ledger = _telemetry(tmp_path)
    telemetry.emit_preflight(_preflight(), _venue())
    telemetry.emit_quote(
        ApexMMQuote(True, "active", 100.5, 100.0, 101.0, 0.1, 0.1, 99.5, 0.0),
        0.0,
    )
    telemetry.emit_state(
        ApexMMLiveSnapshot(
            ApexMMLiveState.QUOTING,
            7,
            8,
            0.0,
            1_785_585_600_000,
        )
    )
    old = SolFill(
        7,
        100.0,
        0.1,
        "B",
        1_785_585_500_000,
        0.0015,
        "USDC",
        0.0,
        False,
        "Open Long",
        "0xlate-history",
        7_003,
    )

    telemetry.emit_reconciliation(_venue(old))
    telemetry.emit_book(_book(1_785_585_601_000, midpoint=110.0))

    event_types = [row["event_type"] for row in ledger.read_all()]
    assert "fill_markout" not in event_types
    assert "execution_quality" not in event_types


def test_apex_partial_fills_keep_distinct_execution_measurements(
    tmp_path: Path,
) -> None:
    """Apex uses each venue trade ID for fill, fee, quality, and markout rows."""
    telemetry, ledger = _telemetry(tmp_path)
    telemetry.emit_preflight(_preflight(), _venue())
    telemetry.emit_quote(
        ApexMMQuote(True, "active", 100.5, 100.0, 101.0, 0.1, 0.1, 99.5, 0.0),
        0.0,
    )
    telemetry.emit_state(
        ApexMMLiveSnapshot(
            ApexMMLiveState.QUOTING,
            7,
            8,
            0.0,
            1_785_585_600_000,
        )
    )
    first = SolFill(
        7,
        100.0,
        0.04,
        "B",
        1_785_585_600_000,
        0.0006,
        "USDC",
        0.0,
        False,
        "Open Long",
        "0xshared",
        7_101,
    )
    second = replace(first, size=0.06, fee_usd=0.0009, trade_id=7_102)

    telemetry.emit_reconciliation(_venue(first, second))
    telemetry.emit_book(_book(1_785_585_601_000, midpoint=101.0))

    records = ledger.read_all()
    for event_type in ("fill", "fee", "execution_quality", "fill_markout"):
        rows = [
            row
            for row in records
            if row["event_type"] == event_type
            and (event_type != "fee" or row["payload"].get("source") == "fill")
        ]
        assert [row["payload"]["trade_id"] for row in rows] == [7_101, 7_102]


def test_fault_record_contains_no_execution_fallback(tmp_path: Path) -> None:
    telemetry, ledger = _telemetry(tmp_path)

    telemetry.emit_fault("paired quote reconciliation failed")

    row = ledger.read_all()[0]
    assert row["event_type"] == "fault"
    assert row["payload"] == {
        "strategy_id": "apex_regime_mm_v2",
        "message": "paired quote reconciliation failed",
    }
