"""Resolved trade-ledger fixture for cohort audit tests."""

from __future__ import annotations

from datetime import datetime, timezone

_HULK = "test_trend_5m"


def traded_asset_rows(run_id: str) -> list[dict[str, object]]:
    """Return one complete attributed BTC trade lifecycle."""
    payloads = (
        _initial_payloads()
        + _entry_payloads()
        + _open_state_payloads()
        + _exit_payloads()
        + _final_payloads()
    )
    return [
        _row(sequence, event_type, payload, run_id)
        for sequence, (event_type, payload) in enumerate(payloads, start=1)
    ]


def _initial_payloads() -> list[tuple[str, dict[str, object]]]:
    return [
        ("configuration_identity", {"strategy_name": "cohort_asset", "symbol": "BTC"}),
        ("reconciliation", {"account_value_usd": 503.16, "open_order_ids": []}),
    ]


def _entry_payloads() -> list[tuple[str, dict[str, object]]]:
    return [
        (
            "regime_decision",
            {
                "strategy_id": _HULK,
                "decision_time_ms": 1_785_600_000_000,
                "decision_action": "enter_long",
                "primary_regime": "TREND_UP",
                "state_1m": "TREND_UP",
                "state_5m": "TREND_UP",
                "context_15m": "TREND_UP",
                "confidence": 0.8,
            },
        ),
        (
            "order_intent",
            {
                "operation": "entry",
                "client_order_id": "0xentry",
                "side": "long",
                "requested_notional_usd": 25.0,
                "mark_price": 100.0,
            },
        ),
        (
            "order_acknowledgement",
            {
                "operation": "entry",
                "accepted": True,
                "oid": 11,
                "status": "filled",
                "error": None,
                "client_order_id": "0xentry",
            },
        ),
        (
            "fill",
            {
                "trade_id": 101,
                "oid": 11,
                "venue_timestamp_ms": 1_785_600_000_100,
                "price": 100.01,
                "size": 0.25,
                "side": "B",
                "direction": "Open Long",
                "closed_pnl_usd": 0.0,
                "fee_usd": 0.01,
            },
        ),
    ]


def _open_state_payloads() -> list[tuple[str, dict[str, object]]]:
    return [
        ("position", {"size_signed": 0.25, "margin_used_usd": 5.0, "leverage": 5}),
        ("liquidation_price", {"value": 80.0}),
        ("funding", {"venue_timestamp_ms": 1_785_600_010_000, "usdc_delta": -0.01}),
    ]


def _exit_payloads() -> list[tuple[str, dict[str, object]]]:
    return [
        (
            "regime_decision",
            {
                "strategy_id": _HULK,
                "decision_time_ms": 1_785_600_020_000,
                "decision_action": "long_exit",
                "primary_regime": "TRANSITION",
                "state_1m": "TRANSITION",
                "state_5m": "TRANSITION",
                "context_15m": "TREND_UP",
                "confidence": 0.6,
            },
        ),
        (
            "order_intent",
            {
                "operation": "reduce_only_close",
                "client_order_id": "0xexit",
                "mark_price": 104.0,
            },
        ),
        (
            "close",
            {
                "operation": "reduce_only_close",
                "accepted": True,
                "oid": 22,
                "status": "filled",
                "error": None,
                "client_order_id": "0xexit",
            },
        ),
        (
            "fill",
            {
                "trade_id": 202,
                "oid": 22,
                "venue_timestamp_ms": 1_785_600_030_000,
                "price": 103.98,
                "size": 0.25,
                "side": "A",
                "direction": "Close Long",
                "closed_pnl_usd": 1.0,
                "fee_usd": 0.01,
            },
        ),
    ]


def _final_payloads() -> list[tuple[str, dict[str, object]]]:
    return [
        (
            "close",
            {"reason": "opposite_strategy_intent", "oid": 22, "verified_flat": True},
        ),
        ("reconciliation", {"account_value_usd": 504.13, "open_order_ids": []}),
        ("position", {"size_signed": 0.0, "margin_used_usd": 0.0}),
        (
            "state_transition",
            {
                "state": "STOPPED",
                "position_size_signed": 0.0,
                "stop_oid": None,
                "stop_reason": "operator_stop",
                "last_fault": None,
            },
        ),
    ]


def _row(
    sequence: int,
    event_type: str,
    payload: dict[str, object],
    run_id: str,
) -> dict[str, object]:
    observed_ms = 1_785_600_000_000 - 2_000 + sequence * 1_000
    profile = "btc-profile"
    return {
        "schema_version": 1,
        "sequence": sequence,
        "event_type": event_type,
        "observed_at_utc": datetime.fromtimestamp(
            observed_ms / 1_000, timezone.utc
        ).isoformat(),
        "execution_mode": "live",
        "live_armed": True,
        "execution_authority": "hyperliquid_mainnet",
        "profile_id": profile,
        "profile_fingerprint": f"{profile}-fingerprint",
        "run_fingerprint": f"{profile}-run",
        "run_id": run_id,
        "payload": payload,
    }
