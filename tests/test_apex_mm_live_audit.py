"""Report-only evidence audit contracts for the Apex MM live canary."""

from __future__ import annotations

import importlib

import pytest


def _row(
    sequence: int,
    event_type: str,
    payload: dict[str, object],
    *,
    run_id: str = "run-a",
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "sequence": sequence,
        "event_type": event_type,
        "observed_at_utc": f"2026-08-01T12:00:{sequence:02d}+00:00",
        "execution_mode": "live",
        "live_armed": True,
        "execution_authority": "hyperliquid_mainnet",
        "profile_id": "apex_regime_mm_canary_v1",
        "profile_fingerprint": "profile",
        "run_fingerprint": "run",
        "run_id": run_id,
        "payload": payload,
    }


def _audit(
    rows: list[dict[str, object]],
    run_id: str | None = None,
) -> dict[str, object]:
    module = importlib.import_module("hypervector.research.apex_mm_live_audit")
    return module.audit_apex_mm_live_run(rows, run_id=run_id)


def _complete_rows() -> list[dict[str, object]]:
    client_order_id = "0x" + "1" * 32
    close_client_order_id = "0x" + "2" * 32
    return [
        _row(
            1,
            "configuration_identity",
            {
                "strategy_name": "apex_regime_mm_v2",
                "execution": {
                    "markout_horizon_ms": 1_000,
                    "maximum_book_age_ms": 1_000,
                    "submission_transport": "single_bulk_orders_action",
                    "fill_identity": "hyperliquid_tid",
                },
            },
        ),
        _row(2, "theoretical_quote", {"active": True, "bid_price": 100.0}),
        _row(
            3,
            "order_intent",
            {
                "operation": "maker_quote",
                "side": "buy",
                "limit_price": 100.0,
                "client_order_id": client_order_id,
                "quote_batch_id": client_order_id,
                "book_exchange_timestamp_ms": 1_000,
                "batch_submission_started_at_ms": 1_500,
            },
        ),
        _row(
            4,
            "order_acknowledgement",
            {
                "operation": "quote_buy",
                "accepted": True,
                "oid": 7,
                "round_trip_latency_ms": 37,
                "client_order_id": client_order_id,
            },
        ),
        _row(
            5,
            "fill",
            {
                "oid": 7,
                "trade_id": 7_001,
                "price": 100.0,
                "size": 0.1,
                "crossed": False,
                "fee_usd": 0.0015,
                "closed_pnl_usd": 0.0,
                "side": "B",
                "venue_timestamp_ms": 10,
            },
        ),
        _row(
            6,
            "fee",
            {
                "source": "fill",
                "oid": 7,
                "trade_id": 7_001,
                "venue_timestamp_ms": 10,
                "fee_usd": 0.0015,
            },
        ),
        _row(
            7,
            "execution_quality",
            {
                "oid": 7,
                "trade_id": 7_001,
                "fill_timestamp_ms": 10,
                "expected_quote_price": 100.0,
                "slippage_bps": 0.0,
            },
        ),
        _row(8, "funding", {"usdc_delta": -0.01, "funding_rate": 0.0001}),
        _row(9, "position", {"size_signed": 0.1, "position_value_usd": 10.0}),
        _row(10, "liquidation_price", {"value": 70.0}),
        _row(11, "liquidation_distance", {"distance_pct": 30.0}),
        _row(
            12,
            "fill_markout",
            {
                "oid": 7,
                "trade_id": 7_001,
                "fill_timestamp_ms": 10,
                "horizon_ms": 1_000,
                "markout_bps": 1.5,
            },
        ),
        _row(
            13,
            "order_intent",
            {
                "operation": "close_operator_stop",
                "side": "sell",
                "limit_price": 101.0,
                "client_order_id": close_client_order_id,
            },
        ),
        _row(
            14,
            "order_acknowledgement",
            {
                "operation": "close_operator_stop",
                "accepted": True,
                "oid": 8,
                "round_trip_latency_ms": 45,
                "client_order_id": close_client_order_id,
            },
        ),
        _row(
            15,
            "fill",
            {
                "oid": 8,
                "trade_id": 8_001,
                "price": 101.0,
                "size": 0.1,
                "crossed": True,
                "fee_usd": 0.0045,
                "closed_pnl_usd": 0.1,
                "side": "A",
                "venue_timestamp_ms": 20,
            },
        ),
        _row(
            16,
            "fee",
            {
                "source": "fill",
                "oid": 8,
                "trade_id": 8_001,
                "venue_timestamp_ms": 20,
                "fee_usd": 0.0045,
            },
        ),
        _row(
            17,
            "execution_quality",
            {
                "oid": 8,
                "trade_id": 8_001,
                "fill_timestamp_ms": 20,
                "expected_quote_price": 101.0,
                "slippage_bps": 0.0,
            },
        ),
        _row(
            18,
            "fill_markout",
            {
                "oid": 8,
                "trade_id": 8_001,
                "fill_timestamp_ms": 20,
                "horizon_ms": 1_500,
                "markout_bps": -0.5,
            },
        ),
        _row(
            19,
            "state_transition",
            {"state": "STOPPED", "bid_oid": None, "ask_oid": None},
        ),
        _row(20, "position", {"size_signed": 0.0, "position_value_usd": 0.0}),
        _row(
            21,
            "reconciliation",
            {
                "account_value_usd": 149.98,
                "withdrawable_usd": 149.98,
                "open_order_ids": [],
            },
        ),
    ]


def test_audit_attributes_every_requested_live_execution_metric() -> None:
    report = _audit(_complete_rows())

    assert report["run"]["strategy_id"] == "apex_regime_mm_v2"
    assert report["execution"] == {
        "quote_observations": 1,
        "order_intents": 2,
        "acknowledgements": 2,
        "accepted_acknowledgements": 2,
        "fills": 2,
        "maker_fills": 1,
        "taker_fills": 1,
        "fill_notional_usd": 20.1,
        "fees_usd": 0.006,
        "closed_pnl_before_fees_usd": 0.1,
        "closed_pnl_after_recorded_fees_usd": 0.094,
        "funding_usd": -0.01,
        "net_cashflow_usd": 0.084,
    }
    assert report["latency_ms"] == {
        "count": 2,
        "minimum": 37.0,
        "median": 41.0,
        "maximum": 45.0,
    }
    assert report["quote_submission"] == {
        "transport": "single_bulk_orders_action",
        "maker_intents": 1,
        "explicit_batches": 1,
        "maximum_book_age_ms": 1_000,
        "book_age_at_submission_ms": {
            "count": 1,
            "minimum": 500.0,
            "median": 500.0,
            "maximum": 500.0,
            "mean": 500.0,
        },
        "book_age_at_submission_ms_by_side": {
            "buy": {
                "count": 1,
                "minimum": 500.0,
                "median": 500.0,
                "maximum": 500.0,
                "mean": 500.0,
            },
            "sell": {
                "count": 0,
                "minimum": None,
                "median": None,
                "maximum": None,
                "mean": None,
            },
        },
        "intents_over_maximum_book_age": 0,
        "intents_over_maximum_book_age_by_side": {"buy": 0, "sell": 0},
        "freshness_status": "observed_within_limit",
    }
    assert report["slippage_bps"]["mean"] == 0.0
    assert report["markout_bps"]["mean"] == 0.5
    assert report["inventory"]["maximum_absolute_notional_usd"] == 10.0
    assert report["inventory"]["minimum_liquidation_distance_pct"] == 30.0
    assert report["final_state"]["flat"] is True
    assert report["coverage"]["complete"] is True
    assert report["coverage"]["technical_gaps"] == []
    assert report["coverage"]["metrics"]["funding"] == "observed"


def test_sparse_run_is_reported_without_a_performance_gate() -> None:
    report = _audit(
        [_row(1, "configuration_identity", {"strategy_name": "apex_regime_mm_v2"})]
    )

    assert report["execution"]["fills"] == 0
    assert report["coverage"]["metrics"]["slippage"] == "not_applicable_no_fills"
    assert report["coverage"]["metrics"]["markout"] == "not_applicable_no_fills"
    assert report["coverage"]["metrics"]["funding"] == "not_observed_no_settlement"
    assert report["coverage"]["complete"] is True
    assert report["experiment_contract"]["performance_gate"] is False


def test_audit_flags_stale_maker_intent_as_technical_gap() -> None:
    rows = [
        _row(
            1,
            "configuration_identity",
            {
                "strategy_name": "apex_regime_mm_v2",
                "execution": {
                    "maximum_book_age_ms": 1_000,
                    "submission_transport": "legacy_serial_order_actions",
                },
            },
        ),
        _row(
            2,
            "order_intent",
            {
                "operation": "maker_quote",
                "side": "sell",
                "client_order_id": "0x" + "1" * 32,
                "book_exchange_timestamp_ms": 1_000,
                "batch_submission_started_at_ms": 2_501,
            },
        ),
    ]

    report = _audit(rows)

    assert report["quote_submission"]["intents_over_maximum_book_age"] == 1
    assert report["quote_submission"]["freshness_status"] == "observed_stale"
    assert report["coverage"]["complete"] is False
    assert (
        "maker_quote_intent_exceeded_maximum_book_age"
        in report["coverage"]["technical_gaps"]
    )


def test_filled_run_surfaces_missing_metrics_instead_of_hiding_them() -> None:
    rows = _complete_rows()
    rows = [row for row in rows if row["event_type"] != "execution_quality"]
    for sequence, row in enumerate(rows, start=1):
        row["sequence"] = sequence

    report = _audit(rows)

    assert report["coverage"]["complete"] is False
    assert "slippage_missing_for_fills" in report["coverage"]["technical_gaps"]


def test_audit_rejects_equal_count_quality_for_wrong_trade_id() -> None:
    """A matching order ID cannot conceal a quality row for another partial fill."""
    rows = _complete_rows()
    quality = next(row for row in rows if row["event_type"] == "execution_quality")
    quality["payload"]["trade_id"] = 999

    report = _audit(rows)

    assert report["coverage"]["complete"] is False
    assert "slippage_missing_for_fills" in report["coverage"]["technical_gaps"]
    assert "slippage_without_run_fill" in report["coverage"]["technical_gaps"]


def test_audit_rejects_markout_observed_after_configured_tolerance() -> None:
    rows = _complete_rows()
    markouts = [row for row in rows if row["event_type"] == "fill_markout"]
    markouts[0]["payload"]["horizon_ms"] = 10_513

    report = _audit(rows)

    assert report["markout_horizon_ms"] == {
        "requested": 1_000,
        "maximum_accepted": 2_000,
        "count": 2,
        "minimum": 1_500.0,
        "median": 6_006.5,
        "maximum": 10_513.0,
        "mean": 6_006.5,
        "within_tolerance": 1,
    }
    assert report["coverage"]["complete"] is False
    assert "markout_horizon_exceeded_tolerance" in report["coverage"]["technical_gaps"]
    assert report["coverage"]["metrics"]["markout"] == "observed_outside_horizon"


def test_audit_rejects_orphan_quality_metrics_as_complete_evidence() -> None:
    rows = [
        _row(1, "configuration_identity", {"strategy_name": "apex_regime_mm_v2"}),
        _row(
            2,
            "fill_markout",
            {
                "oid": 7,
                "trade_id": 7_001,
                "fill_timestamp_ms": 10,
                "markout_bps": 999.0,
            },
        ),
        _row(
            3,
            "execution_quality",
            {
                "oid": 7,
                "trade_id": 7_001,
                "fill_timestamp_ms": 10,
                "slippage_bps": 0.0,
            },
        ),
    ]

    report = _audit(rows)

    assert report["coverage"]["complete"] is False
    assert "markout_without_run_fill" in report["coverage"]["technical_gaps"]
    assert "slippage_without_run_fill" in report["coverage"]["technical_gaps"]
    assert report["coverage"]["metrics"]["markout"] == "invalid_orphan_metrics"
    assert report["coverage"]["metrics"]["slippage"] == "invalid_orphan_metrics"


def test_audit_reconstructs_inventory_missed_between_position_samples() -> None:
    rows = [
        _row(1, "configuration_identity", {"strategy_name": "apex_regime_mm_v2"}),
        _row(
            2,
            "fill",
            {
                "oid": 7,
                "trade_id": 7_001,
                "price": 100.0,
                "size": 0.1,
                "crossed": False,
                "fee_usd": 0.0015,
                "closed_pnl_usd": 0.0,
                "side": "B",
                "venue_timestamp_ms": 10,
            },
        ),
        _row(3, "position", {"size_signed": 0.0, "position_value_usd": 0.0}),
        _row(
            4,
            "fill",
            {
                "oid": 8,
                "trade_id": 8_001,
                "price": 99.0,
                "size": 0.1,
                "crossed": True,
                "fee_usd": 0.0045,
                "closed_pnl_usd": -0.1,
                "side": "A",
                "venue_timestamp_ms": 20,
            },
        ),
        _row(5, "position", {"size_signed": 0.0, "position_value_usd": 0.0}),
    ]

    report = _audit(rows)

    assert report["inventory"]["maximum_absolute_notional_usd"] == 0.0
    assert report["inventory"]["maximum_reconstructed_notional_usd"] == 10.0
    assert report["inventory"]["reconstructed_final_size_signed"] == 0.0
    assert "inventory_path_missing_for_fills" in report["coverage"]["technical_gaps"]
    assert (
        "liquidation_distance_missing_for_filled_inventory"
        in report["coverage"]["technical_gaps"]
    )
    assert report["coverage"]["metrics"]["inventory"] == "partial_reconstructed_only"
    assert report["coverage"]["metrics"]["liquidation_distance"] == "missing"


def test_audit_rejects_unjournaled_cleanup_fill_behind_flat_final_state() -> None:
    rows = [
        row
        for row in _complete_rows()
        if not (
            row["payload"].get("oid") == 8
            or row["payload"].get("client_order_id") == "0x" + "2" * 32
        )
    ]
    for sequence, row in enumerate(rows, start=1):
        row["sequence"] = sequence
    report = _audit(rows)

    assert report["final_state"]["flat"] is True
    assert report["inventory"]["reconstructed_final_size_signed"] == 0.1
    assert report["coverage"]["complete"] is False
    assert (
        "fill_inventory_reconciliation_mismatch" in report["coverage"]["technical_gaps"]
    )


def test_audit_rejects_quality_price_that_differs_from_submitted_order() -> None:
    client_order_id = "0x" + "1" * 32
    rows = [
        _row(1, "configuration_identity", {"strategy_name": "apex_regime_mm_v2"}),
        _row(
            2,
            "order_intent",
            {
                "operation": "maker_quote",
                "side": "buy",
                "client_order_id": client_order_id,
                "limit_price": 100.0,
            },
        ),
        _row(
            3,
            "order_acknowledgement",
            {
                "operation": "quote_buy",
                "accepted": True,
                "oid": 7,
                "client_order_id": client_order_id,
                "round_trip_latency_ms": 10,
            },
        ),
        _row(
            4,
            "fill",
            {
                "oid": 7,
                "trade_id": 7_001,
                "price": 100.0,
                "size": 0.1,
                "crossed": False,
                "fee_usd": 0.0015,
                "closed_pnl_usd": 0.0,
                "side": "B",
                "venue_timestamp_ms": 10,
            },
        ),
        _row(
            5,
            "execution_quality",
            {
                "oid": 7,
                "trade_id": 7_001,
                "fill_timestamp_ms": 10,
                "expected_quote_price": 99.0,
                "slippage_bps": 101.01,
            },
        ),
    ]

    report = _audit(rows)

    assert report["quality_attribution"]["mismatched_oids"] == [7]
    assert report["coverage"]["complete"] is False
    assert "slippage_expected_price_mismatch" in report["coverage"]["technical_gaps"]


def test_audit_rejects_noncontiguous_or_wrong_authority_evidence() -> None:
    rows = _complete_rows()
    rows[1]["sequence"] = 99
    with pytest.raises(ValueError, match="sequence must be contiguous"):
        _audit(rows)

    rows = _complete_rows()
    rows[1]["execution_authority"] = "none"
    with pytest.raises(ValueError, match="execution authority"):
        _audit(rows)
