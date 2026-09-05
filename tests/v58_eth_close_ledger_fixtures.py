"""Ledger fixtures for the V58 ETH live-close reconciler tests."""

from __future__ import annotations

from copy import deepcopy

_ASSET_PROFILE = "multi_asset_growth_first_5000_eight_asset_incremental_v58_eth"
_ASSET_FINGERPRINT = "b443e05b2c7d41a61ae0688f36ddc4e0295a56910e90485742d5014b98e0ed85"


def split_active_exit_fills() -> list[dict[str, object]]:
    """Return the active-close fixture with two exit fills and fee rows."""
    rows = deepcopy(ActiveCloseFixture.rows)
    rows = [
        row
        for row in rows
        if not (
            row.get("payload", {}).get("oid") == 520200000000
            and row.get("event_type") in {"fill", "fee"}
        )
    ]
    rows.extend(_split_exit_fill_rows())
    return rows


def protective_stop_context() -> dict[str, object]:
    """Return a closed context resolved through its resting protective stop."""
    context = deepcopy(ClosedContextFixture.value)
    close = context["actual_close_reconciliation"]
    assert isinstance(close, dict)
    entry = close["entry"]
    assert isinstance(entry, dict)
    size = float(entry["size"])
    gross = (2185.6 - float(entry["price"])) * size
    close["exit"] = {
        "oid": 520161149035,
        "price": 2185.6,
        "size": size,
        "venue_timestamp_ms": 1787173800000,
        "slippage_bps": 0.4575,
    }
    close["exit_reason"] = "protective_stop"
    close["holding_time_ms"] = 880_418
    close["gross_market_pnl_usd"] = gross
    close["fees_usd"] = 0.63
    close["funding_usd"] = -0.02
    close["net_pnl_usd"] = gross - 0.63 - 0.02
    context["actual_net_pnl_usd"] = close["net_pnl_usd"]
    return context


def _split_exit_fill_rows() -> list[dict[str, object]]:
    return [
        ActiveCloseFixture.common
        | {
            "event_type": event_type,
            "observed_at_utc": f"2026-08-20T08:55:02.70{index}000+00:00",
            "payload": payload,
        }
        for index, (event_type, payload) in enumerate(_split_exit_payloads())
    ]


def _split_exit_payloads() -> list[tuple[str, dict[str, object]]]:
    fills = [
        (9001, 1787216102600, 0.1, 0.1256, 6.22),
        (9002, 1787216102601, 0.2317, 0.29105, 14.41174),
    ]
    output: list[tuple[str, dict[str, object]]] = []
    for trade_id, timestamp, size, fee, pnl in fills:
        base = {
            "oid": 520200000000,
            "trade_id": trade_id,
            "venue_timestamp_ms": timestamp,
            "fee_usd": fee,
        }
        output.append(
            (
                "fill",
                base
                | {
                    "price": 2261.1,
                    "size": size,
                    "direction": "Close Long",
                    "closed_pnl_usd": pnl,
                },
            )
        )
        output.append(("fee", base | {"source": "fill"}))
    return output


class ProtectiveStopFixture:
    """Exact raw rows for a venue-native protective-stop close."""

    common = {
        "run_id": "bidirectional-live-1787166474078",
        "profile_id": _ASSET_PROFILE,
        "profile_fingerprint": _ASSET_FINGERPRINT,
    }
    rows: list[dict[str, object]] = [
        common
        | {
            "event_type": "fill",
            "observed_at_utc": "2026-08-19T20:55:24+00:00",
            "payload": {
                "oid": 520161109446,
                "trade_id": 9000,
                "venue_timestamp_ms": 1787172919582,
                "price": 2198.9,
                "size": 0.3317,
                "direction": "Open Long",
                "fee_usd": 0.31509,
                "closed_pnl_usd": 0.0,
            },
        },
        common
        | {
            "event_type": "fee",
            "observed_at_utc": "2026-08-19T20:55:24+00:00",
            "payload": {
                "source": "fill",
                "trade_id": 9000,
                "oid": 520161109446,
                "venue_timestamp_ms": 1787172919582,
                "fee_usd": 0.31509,
            },
        },
        common
        | {
            "event_type": "fee",
            "observed_at_utc": "2026-08-19T21:10:00.200000+00:00",
            "payload": {
                "source": "fill",
                "trade_id": 9002,
                "oid": 520161149035,
                "venue_timestamp_ms": 1787173800000,
                "fee_usd": 0.31491,
            },
        },
        common
        | {
            "event_type": "funding",
            "observed_at_utc": "2026-08-19T21:00:00+00:00",
            "payload": {
                "venue_timestamp_ms": 1787173200000,
                "usdc_delta": -0.02,
            },
        },
        common
        | {
            "event_type": "order_intent",
            "observed_at_utc": "2026-08-19T20:55:21+00:00",
            "payload": {
                "operation": "protective_stop",
                "client_order_id": "stop-1",
                "trigger_price": 2185.7,
            },
        },
        common
        | {
            "event_type": "stop_order",
            "observed_at_utc": "2026-08-19T20:55:22+00:00",
            "payload": {
                "accepted": True,
                "oid": 520161149035,
                "client_order_id": "stop-1",
            },
        },
        common
        | {
            "event_type": "fill",
            "observed_at_utc": "2026-08-19T21:10:00.200000+00:00",
            "payload": {
                "oid": 520161149035,
                "trade_id": 9002,
                "venue_timestamp_ms": 1787173800000,
                "price": 2185.6,
                "size": 0.3317,
                "side": "A",
                "direction": "Close Long",
                "closed_pnl_usd": -4.41161,
                "fee_usd": 0.31491,
            },
        },
        common
        | {
            "event_type": "close",
            "observed_at_utc": "2026-08-19T21:10:01+00:00",
            "payload": {
                "reason": "protective_stop",
                "oid": 520161149035,
                "verified_flat": True,
            },
        },
    ]


class ClosedContextFixture:
    """Backend-authored reflected close and frozen policy comparison fixture."""

    value: dict[str, object] = {
        "route": "eth_breakout_precompression_pullback_bidirectional_v1|ETH",
        "lifecycle_state": "closed",
        "lifecycle_id": "ETH:520161109446",
        "side": "long",
        "actual_net_pnl_usd": 20.0,
        "actual_close_reconciliation": {
            "lifecycle_id": "ETH:520161109446",
            "source_run_id": "bidirectional-live-1787166474078",
            "source_profile_fingerprint": (
                "8a04636c9ff60a7eae141381cb540d7c6ceed081097cda7d5e465d48faa5022b"
            ),
            "strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
            "symbol": "ETH",
            "side": "long",
            "entry": {
                "oid": 520161109446,
                "price": 2198.9,
                "size": 0.3317,
                "venue_timestamp_ms": 1787172919582,
                "slippage_bps": -25.4,
            },
            "exit": {
                "oid": 520200000000,
                "price": 2261.1,
                "size": 0.3317,
                "venue_timestamp_ms": 1787216102600,
                "slippage_bps": 1.25,
            },
            "protective_stop": {"oid": 520161149035, "trigger_price": 2185.7},
            "exit_reason": "maximum_hold_seconds",
            "holding_time_ms": 43_183_018,
            "gross_market_pnl_usd": 20.63174,
            "fees_usd": 0.73174,
            "funding_usd": 0.1,
            "net_pnl_usd": 20.0,
            "accounting_reconciled": True,
            "ledger": {
                "final_state": "FLAT",
                "position_size_signed": 0.0,
                "open_order_ids": [],
                "protected_if_open": True,
            },
            "ledger_flat_order_free": True,
        },
        "policies": {
            "r5_floor2_trail2": {
                "estimated_net_pnl_usd": 38.0,
                "estimated_minus_actual_net_usd": 18.0,
            }
        },
        "strategy_change_supported": False,
        "execution_authority": "none",
    }


class ActiveCloseFixture:
    """Exact raw rows for a backend-routed maximum-hold close."""

    common = {
        "run_id": "bidirectional-live-1787166474078",
        "profile_id": _ASSET_PROFILE,
        "profile_fingerprint": _ASSET_FINGERPRINT,
    }
    rows: list[dict[str, object]] = [
        common
        | {
            "event_type": "fill",
            "observed_at_utc": "2026-08-19T20:55:24+00:00",
            "payload": {
                "oid": 520161109446,
                "trade_id": 9000,
                "venue_timestamp_ms": 1787172919582,
                "price": 2198.9,
                "size": 0.3317,
                "direction": "Open Long",
                "fee_usd": 0.31509,
                "closed_pnl_usd": 0.0,
            },
        },
        common
        | {
            "event_type": "fee",
            "observed_at_utc": "2026-08-19T20:55:24+00:00",
            "payload": {
                "source": "fill",
                "trade_id": 9000,
                "oid": 520161109446,
                "venue_timestamp_ms": 1787172919582,
                "fee_usd": 0.31509,
            },
        },
        common
        | {
            "event_type": "fee",
            "observed_at_utc": "2026-08-20T08:55:02.700000+00:00",
            "payload": {
                "source": "fill",
                "trade_id": 9001,
                "oid": 520200000000,
                "venue_timestamp_ms": 1787216102600,
                "fee_usd": 0.41665,
            },
        },
        common
        | {
            "event_type": "funding",
            "observed_at_utc": "2026-08-20T00:00:00+00:00",
            "payload": {
                "venue_timestamp_ms": 1787184000000,
                "usdc_delta": 0.1,
            },
        },
        common
        | {
            "event_type": "regime_decision",
            "observed_at_utc": "2026-08-20T08:55:00+00:00",
            "payload": {
                "strategy_id": "cohort_maximum_hold",
                "symbol": "ETH",
                "side": "long",
                "decision_time_ms": 1787216100000,
                "routing_action": "close",
                "exit_reason": "maximum_hold_seconds",
            },
        },
        common
        | {
            "event_type": "close",
            "observed_at_utc": "2026-08-20T08:55:01+00:00",
            "payload": {
                "reason": "maximum_hold_seconds",
                "intent": True,
                "stop_oid": 520161149035,
            },
        },
        common
        | {
            "event_type": "order_intent",
            "observed_at_utc": "2026-08-20T08:55:01.200000+00:00",
            "payload": {
                "operation": "reduce_only_close",
                "client_order_id": "close-1",
                "position_size_signed": 0.3317,
                "mark_price": 2261.0,
            },
        },
        common
        | {
            "event_type": "close",
            "observed_at_utc": "2026-08-20T08:55:02.200000+00:00",
            "payload": {
                "operation": "reduce_only_close",
                "accepted": True,
                "oid": 520200000000,
                "client_order_id": "close-1",
            },
        },
        common
        | {
            "event_type": "fill",
            "observed_at_utc": "2026-08-20T08:55:02.700000+00:00",
            "payload": {
                "oid": 520200000000,
                "trade_id": 9001,
                "venue_timestamp_ms": 1787216102600,
                "price": 2261.1,
                "size": 0.3317,
                "side": "A",
                "direction": "Close Long",
                "closed_pnl_usd": 20.63174,
                "fee_usd": 0.41665,
            },
        },
        common
        | {
            "event_type": "close",
            "observed_at_utc": "2026-08-20T08:55:03+00:00",
            "payload": {
                "reason": "maximum_hold_seconds",
                "oid": 520200000000,
                "verified_flat": True,
            },
        },
    ]
