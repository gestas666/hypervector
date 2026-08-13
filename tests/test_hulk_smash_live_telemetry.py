from dataclasses import replace
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.live.hulk_smash_live_config import (
    HulkSmashLiveConfig,
    load_hulk_smash_live_config,
)
from hypervector.live.hulk_smash_live_decisions import HulkSmashLiveDecision
from hypervector.live.hulk_smash_live_ledger import HulkSmashLiveLedger
from hypervector.live.hulk_smash_live_telemetry import HulkSmashLiveTelemetry
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


class _Clock:
    """Deterministic aware clock for local lifecycle latency assertions."""

    def __init__(self) -> None:
        self.now = datetime(2026, 8, 1, 12, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, milliseconds: int) -> None:
        self.now += timedelta(milliseconds=milliseconds)


def test_disarmed_hulk_telemetry_matches_the_tui_contract(tmp_path: Path) -> None:
    path = tmp_path / "data/live/hulk_smash/decisions.jsonl"
    base = load_hulk_smash_live_config(
        "configs/hulk_smash_short_robust_v3_canary.toml",
        mode="observe",
    )
    config = replace(base, backend_ledger=path)
    ledger = HulkSmashLiveLedger(
        path=path,
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id="observe-1",
    )
    telemetry = HulkSmashLiveTelemetry(
        config=config,
        ledger=ledger,
        armed=False,
        wallet_configured=True,
        signing_key_configured=False,
        now_fn=lambda: datetime(2026, 8, 1, 12, tzinfo=UTC),
    )

    telemetry.emit_preflight(_preflight(), _venue())
    telemetry.emit_book(_book())
    telemetry.emit_history(_decision(eligible=False))
    telemetry.emit_decision(_decision(eligible=True))

    records = [json.loads(line) for line in path.read_text().splitlines()]
    identity = next(
        row for row in records if row["event_type"] == "configuration_identity"
    )
    decision = next(row for row in records if row["event_type"] == "regime_decision")
    assert identity["live_armed"] is False
    assert identity["execution_authority"] == "none"
    assert identity["payload"]["strategy_name"] == "hulk_expansion_short_robust_v3"
    assert (
        identity["payload"]["regime_policy"]["classification"]
        == "NOT_A_REGIME_CLASSIFIER"
    )
    assert identity["payload"]["exits"]["target_r_multiple"] == 3.0
    assert identity["payload"]["execution"]["maximum_entry_delay_seconds"] == 60
    assert identity["payload"]["execution"]["markout_horizon_ms"] == 5_000
    assert identity["payload"]["execution"]["fill_identity"] == "hyperliquid_tid"
    assert decision["payload"]["hulk_score"] == 8
    assert decision["payload"]["entry_allowed"] is True
    encoded = "\n".join(json.dumps(row).lower() for row in records)
    assert "private_key" not in encoded
    assert "api_key" not in encoded


def test_hulk_telemetry_does_not_attribute_unowned_btc_fill(
    tmp_path: Path,
) -> None:
    path = tmp_path / "data/live/hulk_smash/decisions.jsonl"
    config = _config(path)
    ledger = _ledger(config, run_id="prior-run")
    ledger.append(
        event_type="state_transition",
        observed_at_utc="2026-08-01T11:00:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={"state": "FLAT", "position_size_signed": 0.0},
    )
    telemetry = HulkSmashLiveTelemetry(
        config=config,
        ledger=_ledger(config, run_id="restart"),
        armed=True,
        wallet_configured=True,
        signing_key_configured=True,
        now_fn=lambda: datetime(2026, 8, 1, 12, tzinfo=UTC),
    )
    venue = replace(_venue(), fills=(_fill(999),))

    telemetry.emit_preflight(_preflight(), venue)

    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert not any(record["event_type"] == "fill" for record in records)
    assert not any(
        record["event_type"] == "fee" and record["payload"].get("source") == "fill"
        for record in records
    )


def test_hulk_order_ack_records_local_round_trip_latency(tmp_path: Path) -> None:
    """A durable intent and its acknowledgement retain measured local latency."""
    clock = _Clock()
    telemetry, ledger = _live_telemetry(tmp_path, clock)
    client_order_id = "0x" + "1" * 32
    telemetry.emit_order_intent(
        operation="entry",
        side="sell",
        mark_price=100.0,
        client_order_id=client_order_id,
    )
    clock.advance(37)

    telemetry.emit_ack(
        "entry",
        HyperliquidOrderAck(
            True,
            7,
            "filled",
            client_order_id=client_order_id,
        ),
    )

    ack = next(
        row for row in ledger.read_all() if row["event_type"] == "order_acknowledgement"
    )
    assert ack["payload"]["round_trip_latency_ms"] == 37


def test_hulk_fill_records_slippage_and_directional_markout(tmp_path: Path) -> None:
    """An owned short fill gets expected-price slippage and a due markout."""
    clock = _Clock()
    telemetry, ledger = _live_telemetry(tmp_path, clock)
    telemetry.emit_preflight(_preflight(), _venue())
    client_order_id = "0x" + "2" * 32
    telemetry.emit_order_intent(
        operation="entry",
        side="sell",
        mark_price=100.0,
        client_order_id=client_order_id,
    )
    telemetry.emit_ack(
        "entry",
        HyperliquidOrderAck(
            True,
            7,
            "filled",
            client_order_id=client_order_id,
        ),
    )
    fill_timestamp_ms = int(clock.now.timestamp() * 1_000)
    fill = _custom_fill(
        oid=7,
        timestamp_ms=fill_timestamp_ms,
        price=99.9,
        side="A",
        direction="Open Short",
    )

    telemetry.emit_reconciliation(replace(_venue(), fills=(fill,)))
    telemetry.emit_book(_book_at(fill_timestamp_ms + 5_000, midpoint=99.0))

    records = ledger.read_all()
    quality = next(row for row in records if row["event_type"] == "execution_quality")
    markout = next(row for row in records if row["event_type"] == "fill_markout")
    assert quality["payload"]["expected_price"] == 100.0
    assert quality["payload"]["slippage_bps"] == pytest.approx(10.0)
    assert markout["payload"]["horizon_ms"] == 5_000
    assert markout["payload"]["target_horizon_ms"] == 5_000
    assert markout["payload"]["horizon_lateness_ms"] == 0
    assert markout["payload"]["recovered_after_restart"] is False
    assert markout["payload"]["markout_bps"] == pytest.approx(90.0900900901)


def test_hulk_partial_fills_keep_distinct_fee_quality_and_markout_rows(
    tmp_path: Path,
) -> None:
    """Every owned venue trade ID retains its complete execution evidence."""
    clock = _Clock()
    telemetry, ledger = _live_telemetry(tmp_path, clock)
    telemetry.emit_preflight(_preflight(), _venue())
    client_order_id = "0x" + "4" * 32
    telemetry.emit_order_intent(
        operation="entry",
        side="sell",
        mark_price=100.0,
        client_order_id=client_order_id,
    )
    telemetry.emit_ack(
        "entry",
        HyperliquidOrderAck(True, 7, "filled", client_order_id=client_order_id),
    )
    timestamp_ms = int(clock.now.timestamp() * 1_000)
    first = _custom_fill(
        oid=7,
        timestamp_ms=timestamp_ms,
        price=99.9,
        side="A",
        direction="Open Short",
        trade_id=7_001,
    )
    second = replace(first, price=99.8, size=0.002, trade_id=7_002)

    telemetry.emit_reconciliation(replace(_venue(), fills=(first, second)))
    telemetry.emit_book(_book_at(timestamp_ms + 5_000, midpoint=99.0))

    records = ledger.read_all()
    for event_type in ("fill", "fee", "execution_quality", "fill_markout"):
        rows = [
            row
            for row in records
            if row["event_type"] == event_type
            and (event_type != "fee" or row["payload"].get("source") == "fill")
        ]
        assert [row["payload"]["trade_id"] for row in rows] == [7_001, 7_002]


def test_hulk_open_position_records_liquidation_distance(tmp_path: Path) -> None:
    """Liquidation distance comes from venue position truth and live midpoint."""
    telemetry, ledger = _live_telemetry(tmp_path)
    telemetry.emit_preflight(_preflight(), _venue())
    position = SolPositionSnapshot(
        -0.5,
        100.0,
        120.0,
        10.0,
        50.0,
        0.0,
        "isolated",
        5,
    )
    account = SolAccountSnapshot(150.0, 140.0, 10.0, 50.0, position)
    telemetry.emit_reconciliation(SolReconciliationSnapshot(account, (), ()))

    telemetry.emit_book(_book_at(2_000, midpoint=100.0))

    distance = next(
        row for row in ledger.read_all() if row["event_type"] == "liquidation_distance"
    )
    assert distance["payload"]["side"] == "short"
    assert distance["payload"]["liquidation_price"] == 120.0
    assert distance["payload"]["distance_pct"] == 20.0


def test_hulk_restart_completes_missing_markout_for_recorded_fill(
    tmp_path: Path,
) -> None:
    """A restart must not silently lose a pending post-fill markout."""
    clock = _Clock()
    first, first_ledger = _live_telemetry(tmp_path, clock)
    first.emit_preflight(_preflight(), _venue())
    identity = "0x" + "3" * 32
    first.emit_order_intent(
        operation="entry",
        side="sell",
        mark_price=100.0,
        client_order_id=identity,
    )
    first.emit_ack(
        "entry",
        HyperliquidOrderAck(True, 8, "filled", client_order_id=identity),
    )
    fill_timestamp_ms = int(clock.now.timestamp() * 1_000)
    fill = _custom_fill(
        oid=8,
        timestamp_ms=fill_timestamp_ms,
        price=100.0,
        side="A",
        direction="Open Short",
    )
    first.emit_reconciliation(replace(_venue(), fills=(fill,)))

    config = _config(tmp_path / "data/live/hulk_smash/decisions.jsonl")
    restarted = HulkSmashLiveTelemetry(
        config=config,
        ledger=_ledger(config, run_id="restart-markout"),
        armed=True,
        wallet_configured=True,
        signing_key_configured=True,
        now_fn=clock,
    )
    restarted.emit_book(_book_at(fill_timestamp_ms + 7_300, midpoint=99.5))

    markouts = [
        row for row in first_ledger.read_all() if row["event_type"] == "fill_markout"
    ]
    assert len(markouts) == 1
    assert markouts[0]["payload"]["oid"] == 8
    assert markouts[0]["payload"]["horizon_ms"] == 7_300
    assert markouts[0]["payload"]["target_horizon_ms"] == 5_000
    assert markouts[0]["payload"]["horizon_lateness_ms"] == 2_300
    assert markouts[0]["payload"]["recovered_after_restart"] is True


def _config(path: Path) -> HulkSmashLiveConfig:
    base = load_hulk_smash_live_config(
        "configs/hulk_smash_short_robust_v3_canary.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    return replace(base, backend_ledger=path)


def _ledger(config: HulkSmashLiveConfig, *, run_id: str) -> HulkSmashLiveLedger:
    return HulkSmashLiveLedger(
        path=config.backend_ledger,
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id=run_id,
    )


def _live_telemetry(
    tmp_path: Path,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[HulkSmashLiveTelemetry, HulkSmashLiveLedger]:
    path = tmp_path / "data/live/hulk_smash/decisions.jsonl"
    config = _config(path)
    ledger = _ledger(config, run_id="live-telemetry")
    return (
        HulkSmashLiveTelemetry(
            config=config,
            ledger=ledger,
            armed=True,
            wallet_configured=True,
            signing_key_configured=True,
            now_fn=now_fn or (lambda: datetime(2026, 8, 1, 12, tzinfo=UTC)),
        ),
        ledger,
    )


def _fill(oid: int) -> SolFill:
    return SolFill(
        oid=oid,
        timestamp_ms=int(datetime(2026, 8, 1, 12, tzinfo=UTC).timestamp() * 1_000),
        price=63_800.0,
        size=0.001,
        side="B",
        direction="Close Short",
        closed_pnl_usd=1.0,
        crossed=True,
        transaction_hash=f"0x{oid:064x}",
        fee_usd=0.03,
        fee_token="USDC",
        trade_id=oid,
    )


def _custom_fill(
    *,
    oid: int,
    timestamp_ms: int,
    price: float,
    side: str,
    direction: str,
    trade_id: int | None = None,
) -> SolFill:
    return SolFill(
        oid=oid,
        timestamp_ms=timestamp_ms,
        price=price,
        size=0.001,
        side=side,
        direction=direction,
        closed_pnl_usd=0.0,
        crossed=True,
        transaction_hash=f"0x{oid:064x}",
        fee_usd=0.03,
        fee_token="USDC",
        trade_id=oid if trade_id is None else trade_id,
    )


def _decision(*, eligible: bool) -> HulkSmashLiveDecision:
    return HulkSmashLiveDecision(
        decision_time_ms=1_785_549_600_000,
        bar_open_at=pd.Timestamp("2026-08-01T11:30:00Z"),
        reference_price=63_790.0,
        open_price=63_850.0,
        high_price=63_880.0,
        low_price=63_750.0,
        volume=180.0,
        candidate="hulk_rebuilt_expansion_v1",
        score=8,
        minimum_score=7,
        trigger="squeeze_release",
        evidence=("squeeze_release", "supertrend", "adx_usable"),
        stop_anchor=63_880.0,
        entry_eligible=eligible,
        reason="eligible" if eligible else "history_only",
    )


def _position() -> SolPositionSnapshot:
    return SolPositionSnapshot(0.0, None, None, 0.0, 0.0, 0.0, None, None)


def _venue() -> SolReconciliationSnapshot:
    account = SolAccountSnapshot(150.0, 150.0, 0.0, 0.0, _position())
    return SolReconciliationSnapshot(account, (), ())


def _preflight() -> SolVenuePreflight:
    return SolVenuePreflight(
        market=SolMarketMetadata("BTC", 5, 40),
        mark_price=63_790.0,
        price_tick=1.0,
        size_step=0.00001,
        fees=HyperliquidFeeSchedule(0.00015, 0.00045),
        account_value_usd=150.0,
        withdrawable_usd=150.0,
        position=_position(),
    )


def _book() -> SolBookSnapshot:
    bid = SolBookLevel(63_789.0, 1.0, 1)
    ask = SolBookLevel(63_791.0, 1.2, 1)
    return SolBookSnapshot(1, (bid,), (ask,), 63_790.0, 0.31, 1.0, 1.2, -0.09)


def _book_at(timestamp_ms: int, *, midpoint: float) -> SolBookSnapshot:
    bid = SolBookLevel(midpoint - 0.5, 1.0, 1)
    ask = SolBookLevel(midpoint + 0.5, 1.2, 1)
    spread_bps = (ask.price - bid.price) / midpoint * 10_000.0
    return SolBookSnapshot(
        timestamp_ms,
        (bid,),
        (ask,),
        midpoint,
        spread_bps,
        1.0,
        1.2,
        -0.09,
    )
