"""Tests for read-only SOL live lifecycle attribution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.live.sol_range_onset_live_journal import build_live_journal


def _record(
    sequence: int,
    event_type: str,
    payload: dict[str, object],
    *,
    observed: str = "2026-07-31T12:00:00+00:00",
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "sequence": sequence,
        "event_type": event_type,
        "observed_at_utc": observed,
        "execution_mode": "live",
        "effective_mode": "LIVE ARMED",
        "live_armed": True,
        "execution_authority": "hyperliquid_mainnet",
        "profile_id": "fixture_sol_range_onset",
        "profile_fingerprint": "profile",
        "run_fingerprint": "run",
        "run_id": "run-1",
        "payload": payload,
    }


def _completed_trade_records() -> list[dict[str, object]]:
    return [
        _record(1, "reconciliation", {"account_value_usd": 150.0}),
        _record(
            2,
            "regime_decision",
            {
                "decision_time_ms": 1_785_499_200_000,
                "reference_price": 73.0,
                "decision_action": "enter_long",
                "primary_regime": "BREAKOUT",
                "state_1m": "TREND_UP",
                "state_5m": "BREAKOUT",
                "context_15m": "TREND_UP",
                "confidence": 0.82,
            },
        ),
        _record(
            3,
            "order_intent",
            {
                "operation": "entry",
                "client_order_id": "0xentry",
                "side": "long",
                "requested_notional_usd": 22.5,
                "mark_price": 73.0,
            },
        ),
        _record(
            4,
            "order_acknowledgement",
            {
                "operation": "entry",
                "accepted": True,
                "oid": 101,
                "client_order_id": "0xentry",
                "status": "filled",
            },
        ),
        _record(
            5,
            "fill",
            {
                "oid": 101,
                "venue_timestamp_ms": 1_785_499_200_500,
                "price": 73.10,
                "size": 0.30,
                "side": "B",
                "direction": "Open Long",
                "closed_pnl_usd": 0.0,
                "fee_usd": 0.00987,
                "fee_token": "USDC",
            },
        ),
        _record(
            6,
            "position",
            {
                "size_signed": 0.30,
                "entry_price": 73.10,
                "margin_used_usd": 4.386,
                "position_value_usd": 21.93,
                "unrealized_pnl_usd": 0.0,
                "leverage_type": "isolated",
                "leverage": 5.0,
            },
        ),
        _record(7, "liquidation_price", {"value": 60.5}),
        _record(
            8,
            "book_observation",
            {"exchange_ts_ms": 1_785_499_201_000, "mid_px": 73.25},
        ),
        _record(
            9,
            "funding",
            {
                "venue_timestamp_ms": 1_785_499_300_000,
                "usdc_delta": -0.001,
                "position_size_signed": 0.30,
                "funding_rate": 0.00005,
            },
        ),
        _record(
            10,
            "regime_decision",
            {
                "decision_time_ms": 1_785_502_800_000,
                "reference_price": 74.0,
                "decision_action": "long_exit",
                "primary_regime": "TREND_DOWN",
                "state_1m": "TREND_DOWN",
                "state_5m": "TRANSITION",
                "context_15m": "TREND_UP",
                "confidence": 0.67,
            },
        ),
        _record(
            11,
            "order_intent",
            {
                "operation": "reduce_only_close",
                "client_order_id": "0xclose",
                "position_size_signed": 0.30,
                "mark_price": 74.0,
            },
        ),
        _record(
            12,
            "close",
            {
                "operation": "reduce_only_close",
                "accepted": True,
                "oid": 303,
                "client_order_id": "0xclose",
                "status": "filled",
            },
        ),
        _record(
            13,
            "fill",
            {
                "oid": 303,
                "venue_timestamp_ms": 1_785_502_800_400,
                "price": 73.90,
                "size": 0.30,
                "side": "A",
                "direction": "Close Long",
                "closed_pnl_usd": 0.24,
                "fee_usd": 0.00998,
                "fee_token": "USDC",
            },
        ),
        _record(
            14, "close", {"reason": "signal_exit", "oid": 303, "verified_flat": True}
        ),
        _record(15, "reconciliation", {"account_value_usd": 150.21915}),
        _record(16, "state_transition", {"state": "FLAT", "position_size_signed": 0.0}),
    ]


def test_build_live_journal_attributes_complete_trade_and_friction() -> None:
    report = build_live_journal(_completed_trade_records())

    assert report["integrity"]["sequence_complete"] is True
    assert report["summary"]["closed_trades"] == 1
    assert report["summary"]["net_pnl_usd"] == pytest.approx(0.21915)
    trade = report["trades"][0]
    assert trade["direction"] == "long"
    assert trade["entry_regime"]["state_5m"] == "BREAKOUT"
    assert trade["exit_regime"]["state_5m"] == "TRANSITION"
    assert trade["entry"]["slippage_bps"] == pytest.approx(13.69863)
    assert trade["exit"]["slippage_bps"] == pytest.approx(13.51351)
    assert trade["fees_usd"] == pytest.approx(0.01985)
    assert trade["funding_usd"] == pytest.approx(-0.001)
    assert trade["closed_pnl_before_friction_usd"] == pytest.approx(0.24)
    assert trade["net_pnl_usd"] == pytest.approx(0.21915)
    assert trade["exit_reason"] == "signal_exit"
    assert trade["liquidation_price"] == pytest.approx(60.5)
    assert trade["account_value_change_usd"] == pytest.approx(0.21915)


def test_live_journal_resolves_filled_oid_from_bracket_close() -> None:
    """A verified bracket close identifies the filled member of owned OIDs."""
    records = _completed_trade_records()
    records[13]["payload"] = {
        "reason": "target",
        "owned_oids": [202, 303],
        "verified_flat": True,
    }

    trade = build_live_journal(records)["trades"][0]

    assert trade["exit_oid"] == 303
    assert trade["exit_reason"] == "target"
    assert trade["status"] == "closed"


def test_live_journal_retains_target_limit_as_exit_reference() -> None:
    """An exact target acknowledgement retains its submitted limit price."""
    records = _completed_trade_records()
    records[10]["payload"] = {
        "operation": "target",
        "client_order_id": "0xtarget",
        "limit_price": 74.0,
    }
    records[11]["event_type"] = "target_order"
    records[11]["payload"] = {
        "operation": "target",
        "accepted": True,
        "oid": 303,
        "client_order_id": "0xtarget",
        "status": "resting",
    }
    records[13]["payload"] = {
        "reason": "target",
        "owned_oids": [202, 303],
        "verified_flat": True,
    }

    trade = build_live_journal(records)["trades"][0]

    assert trade["exit"]["expected_reference_price"] == pytest.approx(74.0)
    assert trade["exit"]["slippage_bps"] == pytest.approx(13.5135135)


def test_build_live_journal_retains_incomplete_open_lifecycle() -> None:
    records = _completed_trade_records()[:10]

    report = build_live_journal(records)

    assert report["summary"]["closed_trades"] == 0
    assert report["summary"]["open_lifecycles"] == 1
    lifecycle = report["open_lifecycles"][0]
    assert lifecycle["entry_oid"] == 101
    assert lifecycle["status"] == "open"
    assert lifecycle["fees_usd"] == pytest.approx(0.00987)
    assert lifecycle["funding_usd"] == pytest.approx(-0.001)


def test_live_journal_binds_accepted_protective_stop_to_entry() -> None:
    """A lifecycle retains the exact accepted venue stop and submitted trigger."""
    records = _completed_trade_records()
    records[4:4] = [
        _record(
            0,
            "order_intent",
            {
                "operation": "protective_stop",
                "client_order_id": "0xstop",
                "position_size_signed": 0.30,
                "trigger_price": 72.5152,
            },
        ),
        _record(
            0,
            "stop_order",
            {
                "operation": "protective_stop",
                "accepted": True,
                "oid": 202,
                "client_order_id": "0xstop",
                "status": "resting",
            },
        ),
    ]
    for sequence, record in enumerate(records, start=1):
        record["sequence"] = sequence

    trade = build_live_journal(records)["trades"][0]

    assert trade["protective_stop"] == {
        "oid": 202,
        "trigger_price": pytest.approx(72.5152),
    }


def test_live_journal_rejects_noncontiguous_sequence() -> None:
    records = _completed_trade_records()
    records[3]["sequence"] = 99

    with pytest.raises(ValueError, match="sequence"):
        build_live_journal(records)


def test_live_journal_snapshot_from_ledger_publishes_immutably(
    tmp_path: Path,
) -> None:
    """A ledger snapshot is attributed read-only and published exactly once."""
    ledger = tmp_path / "decisions.jsonl"
    ledger.write_text(
        "".join(json.dumps(record) + "\n" for record in _completed_trade_records()),
        encoding="utf-8",
    )
    output = tmp_path / "journal.json"
    records = [
        json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()
    ]

    write_immutable_json(output, build_live_journal(records))
    published = output.read_bytes()
    report = json.loads(published)

    assert report["execution_authority"] == "none"
    assert report["runtime_strategy_changed"] is False
    assert report["summary"]["closed_trades"] == 1
    assert report["integrity"]["record_count"] == 16
    assert report["integrity"]["run_ids"] == ["run-1"]
    with pytest.raises(FileExistsError, match="immutable JSON output exists"):
        write_immutable_json(output, build_live_journal(records))
    assert output.read_bytes() == published
