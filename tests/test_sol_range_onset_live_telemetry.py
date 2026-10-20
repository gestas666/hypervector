"""Authoritative fill/fee projection tests for SOL live telemetry."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from hypervector.live.hyperliquid_protocol import (
    Hip3MarketFeeMetadata,
    HyperliquidFeeSchedule,
    SolAccountSnapshot,
    SolBookLevel,
    SolBookSnapshot,
    SolFill,
    SolFundingPayment,
    SolMarketMetadata,
    SolOpenOrder,
    SolPositionSnapshot,
    SolReconciliationSnapshot,
    SolVenuePreflight,
)
from hypervector.live.sol_range_onset_config import load_sol_range_onset_config
from hypervector.live.sol_range_onset_ledger import SolLiveLedger
from hypervector.live.sol_range_onset_live_telemetry import SolLiveTelemetry


def _now() -> datetime:
    return datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


def test_reconciliation_emits_each_venue_fill_and_fee_exactly_once(
    tmp_path: Path,
) -> None:
    """Repeated account polling cannot duplicate a fill in the live ledger."""
    path = tmp_path / "data" / "live" / "sol_range_onset_canary" / "decisions.jsonl"
    config = replace(
        load_sol_range_onset_config(
            Path("tests/fixtures/profiles/sol_range_onset.toml"),
            mode="live",
            enabled=True,
            accepts_live_risk=True,
        ),
        live_ledger=path,
    )
    ledger = SolLiveLedger(
        path=path,
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id="run-fill",
    )
    telemetry = SolLiveTelemetry(config=config, ledger=ledger, now_fn=_now)
    fill = SolFill(
        oid=101,
        price=73.10,
        size=0.30,
        side="B",
        timestamp_ms=1_785_499_200_123,
        fee_usd=0.00987,
        fee_token="USDC",
        closed_pnl_usd=0.0,
        crossed=True,
        direction="Open Long",
        transaction_hash="0xfill",
        trade_id=1_001,
    )
    flat = SolPositionSnapshot(0.0, None, None, 0.0, 0.0, 0.0, None, None)
    venue = SolReconciliationSnapshot(
        account=SolAccountSnapshot(150.0, 150.0, 0.0, 0.0, flat),
        open_orders=(
            SolOpenOrder(
                oid=202,
                size=0.30,
                original_size=0.30,
                side="A",
                reduce_only=True,
                is_trigger=True,
                trigger_price=72.515,
                order_type="Stop Market",
                timestamp_ms=1_785_499_201_000,
            ),
        ),
        fills=(fill,),
    )

    telemetry.emit_reconciliation(venue)
    telemetry.emit_reconciliation(venue)

    records = ledger.read_all()
    fills = [record for record in records if record["event_type"] == "fill"]
    fill_fees = [
        record
        for record in records
        if record["event_type"] == "fee"
        and isinstance(record["payload"], dict)
        and record["payload"].get("source") == "fill"
    ]
    assert len(fills) == 1
    assert len(fill_fees) == 1
    payload = fills[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["oid"] == 101
    assert payload["venue_timestamp_ms"] == 1_785_499_200_123
    assert payload["price"] == 73.10
    assert payload["size"] == 0.30
    assert payload["trade_id"] == 1_001
    assert fill_fees[0]["payload"]["fee_usd"] == 0.00987
    assert fill_fees[0]["payload"]["trade_id"] == 1_001
    reconciliation = next(
        record for record in records if record["event_type"] == "reconciliation"
    )
    assert reconciliation["payload"]["open_orders"] == [
        {
            "oid": 202,
            "size": 0.30,
            "side": "A",
            "reduce_only": True,
            "is_trigger": True,
            "trigger_price": 72.515,
            "order_type": "Stop Market",
        }
    ]


def test_distinct_partial_fills_emit_distinct_fill_and_fee_rows(tmp_path: Path) -> None:
    """Venue trade IDs prevent same-order same-time partial fills from collapsing."""
    path = tmp_path / "data/live/sol_range_onset_canary/decisions.jsonl"
    config = replace(
        load_sol_range_onset_config(
            Path("tests/fixtures/profiles/sol_range_onset.toml"),
            mode="live",
            enabled=True,
            accepts_live_risk=True,
        ),
        live_ledger=path,
    )
    ledger = SolLiveLedger(
        path=path,
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id="partial-fills",
    )
    first = SolFill(
        101,
        73.10,
        0.10,
        "B",
        1_785_499_200_123,
        0.003,
        "USDC",
        0.0,
        True,
        "Open Long",
        "0xshared",
        2_001,
    )
    second = replace(first, size=0.20, fee_usd=0.006, trade_id=2_002)
    flat = SolPositionSnapshot(0.0, None, None, 0.0, 0.0, 0.0, None, None)
    venue = SolReconciliationSnapshot(
        SolAccountSnapshot(150.0, 150.0, 0.0, 0.0, flat),
        (),
        (first, second),
    )

    SolLiveTelemetry(config=config, ledger=ledger, now_fn=_now).emit_reconciliation(
        venue
    )

    fills = [row for row in ledger.read_all() if row["event_type"] == "fill"]
    fees = [
        row
        for row in ledger.read_all()
        if row["event_type"] == "fee" and row["payload"].get("source") == "fill"
    ]
    assert [row["payload"]["trade_id"] for row in fills] == [2_001, 2_002]
    assert [row["payload"]["trade_id"] for row in fees] == [2_001, 2_002]


def test_exact_funding_payment_is_restart_deduplicated(tmp_path: Path) -> None:
    """Hourly user-funding ledger updates remain exact and idempotent."""
    path = tmp_path / "data" / "live" / "sol_range_onset_canary" / "decisions.jsonl"
    config = replace(
        load_sol_range_onset_config(
            Path("tests/fixtures/profiles/sol_range_onset.toml"),
            mode="live",
            enabled=True,
            accepts_live_risk=True,
        ),
        live_ledger=path,
    )
    ledger = SolLiveLedger(
        path=path,
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id="run-funding",
    )
    payment = SolFundingPayment(
        timestamp_ms=1_785_499_200_068,
        usdc_delta=-0.001234,
        position_size_signed=0.30,
        funding_rate=0.000056,
        transaction_hash="0xfunding",
    )

    SolLiveTelemetry(config=config, ledger=ledger, now_fn=_now).emit_funding_payments(
        (payment,)
    )
    SolLiveTelemetry(config=config, ledger=ledger, now_fn=_now).emit_funding_payments(
        (payment,)
    )

    records = ledger.read_all()
    funding = [record for record in records if record["event_type"] == "funding"]
    assert len(funding) == 1
    payload = funding[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["venue_timestamp_ms"] == 1_785_499_200_068
    assert payload["usdc_delta"] == -0.001234
    assert payload["funding_rate"] == 0.000056


def test_preflight_identity_contains_complete_read_only_tui_contract(
    tmp_path: Path,
) -> None:
    """Live configuration identity exposes settings but no credential values."""
    path = tmp_path / "data" / "live" / "sol_range_onset_canary" / "decisions.jsonl"
    config = replace(
        load_sol_range_onset_config(
            Path("tests/fixtures/profiles/sol_range_onset.toml"),
            mode="live",
            enabled=True,
            accepts_live_risk=True,
        ),
        live_ledger=path,
    )
    ledger = SolLiveLedger(
        path=path,
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id="run-identity",
    )
    flat = SolPositionSnapshot(0.0, None, None, 0.0, 0.0, 0.0, None, None)
    venue = SolReconciliationSnapshot(
        account=SolAccountSnapshot(150.0, 150.0, 0.0, 0.0, flat),
        open_orders=(),
        fills=(),
    )
    preflight = SolVenuePreflight(
        SolMarketMetadata("SOL", 2, 20),
        73.0,
        0.001,
        0.01,
        HyperliquidFeeSchedule(0.00015, 0.00045),
        150.0,
        150.0,
        flat,
    )

    SolLiveTelemetry(config=config, ledger=ledger, now_fn=_now).emit_preflight(
        preflight,
        venue,
    )

    identity = ledger.read_all()[0]["payload"]
    assert isinstance(identity, dict)
    assert identity["strategy_name"] == config.strategy_id
    assert identity["backend_ledger_path"] == str(config.live_ledger)
    assert identity["risk"] == {"margin_fraction": 0.03, "max_notional_usd": 22.5}
    assert identity["execution"]["market_slippage_cap_fraction"] == 0.01
    assert identity["wallet_configured"] is True
    assert identity["signing_key_configured"] is True
    assert "private_key" not in identity
    effective_mode = next(
        record["payload"]
        for record in ledger.read_all()
        if record["event_type"] == "effective_mode"
    )
    assert effective_mode["account_abstraction_mode"] == "disabled"


def _hip3_fee_event(
    tmp_path: Path,
    growth_mode: bool | None,
    deployer_fee_scale: float | None = 1.0,
) -> dict[str, object]:
    path = tmp_path / "data/live/bidirectional_cohort/xyz:sndk.jsonl"
    config = replace(
        load_sol_range_onset_config(
            Path("tests/fixtures/profiles/sol_range_onset.toml"),
            mode="live",
            enabled=True,
            accepts_live_risk=True,
        ),
        symbol="xyz:SNDK",
        live_ledger=path,
    )
    ledger = SolLiveLedger(
        path=path,
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id="hip3-fees",
    )
    flat = SolPositionSnapshot(0.0, None, None, 0.0, 0.0, 0.0, None, None)
    preflight = SolVenuePreflight(
        market=SolMarketMetadata("xyz:SNDK", 3, 10),
        mark_price=1_255.0,
        price_tick=0.1,
        size_step=0.001,
        fees=HyperliquidFeeSchedule(0.00015, 0.00045, 0.04),
        account_value_usd=500.0,
        withdrawable_usd=485.0,
        position=flat,
        hip3_fee_metadata=Hip3MarketFeeMetadata(deployer_fee_scale, growth_mode, 0),
    )
    venue = SolReconciliationSnapshot(
        SolAccountSnapshot(500.0, 485.0, 0.0, 0.0, flat), (), ()
    )

    SolLiveTelemetry(config=config, ledger=ledger, now_fn=_now).emit_preflight(
        preflight, venue
    )
    return next(
        row["payload"] for row in ledger.read_all() if row["event_type"] == "fee"
    )


@pytest.mark.parametrize(
    ("growth_mode", "status", "maker_rate", "taker_rate"),
    (
        (True, "resolved_hip3", 0.0000288, 0.0000864),
        (None, "unresolved_growth_mode", None, None),
    ),
)
def test_hip3_preflight_emits_effective_fee_evidence_for_tui(
    tmp_path: Path,
    growth_mode: bool | None,
    status: str,
    maker_rate: float | None,
    taker_rate: float | None,
) -> None:
    """HIP-3 ledgers expose effective fees or an explicit unresolved state."""
    fee = _hip3_fee_event(tmp_path, growth_mode)

    assert fee["source"] == "effective_hip3_fee_schedule"
    assert fee["effective_fee_status"] == status
    assert fee["account_base_taker_fee_rate"] == pytest.approx(0.00045)
    if maker_rate is None:
        assert fee["maker_rate"] is None
        assert fee["taker_rate"] is None
    else:
        assert fee["maker_rate"] == pytest.approx(maker_rate)
        assert fee["taker_rate"] == pytest.approx(taker_rate)


def test_hip3_missing_deployer_scale_is_explicitly_unresolved(
    tmp_path: Path,
) -> None:
    """Startup can manage exposure without publishing invented fee economics."""
    fee = _hip3_fee_event(tmp_path, True, None)

    assert fee["source"] == "unresolved_hip3_fee_schedule"
    assert fee["effective_fee_status"] == "unresolved_deployer_fee_scale"
    assert fee["deployer_fee_scale"] is None
    assert fee["maker_rate"] is None
    assert fee["taker_rate"] is None


def test_book_snapshot_is_projected_for_read_only_tui(tmp_path: Path) -> None:
    """Venue L2 depth and pressure are persisted without becoming strategy logic."""
    path = tmp_path / "data" / "live" / "sol_range_onset_canary" / "decisions.jsonl"
    config = replace(
        load_sol_range_onset_config(
            Path("tests/fixtures/profiles/sol_range_onset.toml"),
            mode="live",
            enabled=True,
            accepts_live_risk=True,
        ),
        live_ledger=path,
    )
    ledger = SolLiveLedger(
        path=path,
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id="run-book",
    )
    book = SolBookSnapshot(
        1_785_499_200_123,
        (SolBookLevel(73.67, 10.0, 3),),
        (SolBookLevel(73.68, 6.0, 2),),
        73.675,
        1.3576518493383034,
        10.0,
        6.0,
        0.25,
    )

    SolLiveTelemetry(config=config, ledger=ledger, now_fn=_now).emit_book(book)

    record = ledger.read_all()[0]
    assert record["event_type"] == "book_observation"
    assert record["payload"]["mid_px"] == 73.675
    assert record["payload"]["opi"] == 0.25
    assert record["payload"]["bid_depth_ratio"] == pytest.approx(10.0 / 6.0)
    assert record["payload"]["bids"] == [{"price": 73.67, "size": 10.0}]
