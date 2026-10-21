"""Causal lifecycle fixtures shared by cohort reflection tests."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

from cohort_live_audit_trade_fixture import traded_asset_rows
from test_multi_asset_live_audit import (
    _HULK,
    _RANGE,
    _RUN_ID,
    _cohort_rows_with_trade,
)


def reflection_cohort_rows() -> list[dict[str, object]]:
    """Return one closed lifecycle with matched entry and exit contexts."""
    rows = _cohort_rows_with_trade()
    routes = [row for row in rows if row["event_type"] == "intent_routing"]
    routes[1]["payload"]["evaluations"] = deepcopy(routes[1]["payload"]["evaluations"])
    _configure_route(routes[0], 1_785_600_000_000, entering=True)
    _configure_route(routes[1], 1_785_600_300_000, entering=False)
    market = next(row for row in rows if row["event_type"] == "market_candles")
    bars = market["payload"]["bars"]["BTC"]
    for offset, bar in enumerate(bars):
        close = 104.0 + offset * 0.1
        bar.update(
            {
                "open": close,
                "high": close + 0.05,
                "low": close - 0.05,
                "close": close,
            }
        )
    return _with_canonical_copies(rows)


def _with_canonical_copies(
    source: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Publish each cycle's regime context as a telemetry-only canonical event."""
    rows: list[dict[str, object]] = []
    for row in source:
        rows.append(row)
        if row["event_type"] != "intent_routing":
            continue
        canonical = [
            deepcopy(value)
            for value in row["payload"]["evaluations"]
            if value["strategy_id"] == _RANGE
        ]
        if canonical:
            rows.append(_canonical_event(row, canonical))
    for sequence, row in enumerate(rows, start=1):
        row["sequence"] = sequence
    return rows


def independent_canonical_rows(
    source: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Drop the provider rows that share the regime context, keeping canonical events."""
    for row in source:
        if row["event_type"] == "intent_routing":
            row["payload"]["evaluations"] = [
                value
                for value in row["payload"]["evaluations"]
                if value["strategy_id"] != _RANGE
            ]
    return source


def _canonical_event(
    source: dict[str, object],
    evaluations: list[dict[str, object]],
) -> dict[str, object]:
    event = deepcopy(source)
    event["event_type"] = "canonical_regime_evaluations"
    event["payload"] = {
        "contract": {
            "execution_authority": "none",
            "intents_emitted": False,
            "configured_route": False,
        },
        "evaluations": evaluations,
    }
    for value in evaluations:
        value.update(
            strategy_id="canonical_regime_telemetry_v1",
            decision_action="regime_observation",
            eligible=False,
            reason="canonical_regime_observation",
            side=None,
            backend_non_action_reason="telemetry_only_no_execution_authority",
        )
    decision_time = max(value["decision_time_ms"] for value in evaluations)
    event["observed_at_utc"] = datetime.fromtimestamp(
        decision_time / 1_000,
        tz=UTC,
    ).isoformat()
    return event


def reflection_asset_rows() -> list[dict[str, object]]:
    """Return matching asset-ledger rows with an armed protective stop."""
    rows = traded_asset_rows(_RUN_ID)
    entry_index = next(
        index
        for index, row in enumerate(rows)
        if row["event_type"] == "order_acknowledgement"
        and row["payload"].get("operation") == "entry"
    )
    stop_intent = deepcopy(rows[entry_index])
    stop_intent.update(
        {
            "event_type": "order_intent",
            "payload": {
                "operation": "protective_stop",
                "client_order_id": "0xstop",
                "position_size_signed": 0.25,
                "trigger_price": 99.0,
            },
        }
    )
    stop_ack = deepcopy(rows[entry_index])
    stop_ack.update(
        {
            "event_type": "stop_order",
            "payload": {
                "operation": "protective_stop",
                "accepted": True,
                "oid": 33,
                "client_order_id": "0xstop",
                "status": "resting",
            },
        }
    )
    rows[entry_index + 1 : entry_index + 1] = [stop_intent, stop_ack]
    for sequence, row in enumerate(rows, start=1):
        row["sequence"] = sequence
    for row in rows:
        payload = row["payload"]
        if (
            row["event_type"] == "regime_decision"
            and payload.get("decision_action") == "long_exit"
        ):
            payload["decision_time_ms"] = 1_785_600_300_000
        if row["event_type"] == "fill" and payload.get("trade_id") == 202:
            payload["venue_timestamp_ms"] = 1_785_600_330_000
    return rows


def open_reflection_cohort_rows() -> list[dict[str, object]]:
    """Return the same cohort lifecycle while its position remains open."""
    rows = reflection_cohort_rows()
    projected_entry = {
        "symbol": "BTC",
        "trade_id": 101,
        "price": 100.01,
        "size": 0.25,
        "fee_usd": 0.01,
        "slippage_bps": 1.0,
        "acknowledgement_latency_ms": 40,
        "markout_bps": 3.0,
    }
    for row in rows:
        if row["event_type"] != "cohort_snapshot":
            continue
        snapshot = row["payload"]
        btc = next(asset for asset in snapshot["assets"] if asset["symbol"] == "BTC")
        btc.update(
            {
                "state": "OPEN",
                "position_size_signed": 0.25,
                "position_side": "long",
                "entry_price": 100.01,
                "mark_price": 104.5,
                "liquidation_price": 80.0,
                "liquidation_distance_pct": 23.45,
                "margin_used_usd": 5.0,
                "position_value_usd": 26.125,
                "unrealized_pnl_usd": 1.1225,
                "leverage": 5,
                "fees_net_usd": 0.01,
                "funding_net_usd": 0.0,
                "realized_pnl_usd": 0.0,
            }
        )
        snapshot.update(
            {
                "account_value_usd": 504.2825,
                "withdrawable_usd": 499.2825,
                "total_margin_used_usd": 5.0,
                "total_notional_position_usd": 26.125,
                "open_position_count": 1,
                "recent_fills": [projected_entry],
            }
        )
    return rows


def open_reflection_asset_rows() -> list[dict[str, object]]:
    """Return asset rows truncated before the synthetic exit lifecycle."""
    rows = reflection_asset_rows()
    exit_index = next(
        index
        for index, row in enumerate(rows)
        if row["event_type"] == "regime_decision"
        and row["payload"].get("decision_action") == "long_exit"
    )
    return rows[:exit_index]


def _configure_route(
    row: dict[str, object], decision_time_ms: int, *, entering: bool
) -> None:
    payload = row["payload"]
    evaluations = payload["evaluations"]
    for evaluation in evaluations:
        evaluation["decision_time_ms"] = decision_time_ms
        evaluation["reference_price"] = 100.0 if entering else 104.0
        if evaluation["symbol"] != "BTC":
            continue
        if evaluation["strategy_id"] == _HULK:
            evaluation.update(
                {
                    "decision_action": "enter_long" if entering else "hold",
                    "eligible": entering,
                    "side": "long",
                    "primary_regime": "TREND_UP" if entering else "TRANSITION",
                    "state_1m": "TREND_UP" if entering else "TRANSITION",
                    "state_5m": "TREND_UP" if entering else "TRANSITION",
                    "context_15m": "TREND_UP",
                    "confidence": 0.8 if entering else 0.6,
                }
            )
        elif evaluation["strategy_id"] == _RANGE:
            evaluation.update(
                {
                    "primary_regime": "RANGE",
                    "state_1m": "RANGE",
                    "state_5m": "RANGE",
                    "context_15m": "TREND_UP",
                    "confidence": 0.7,
                }
            )
    payload["actions"] = [
        {
            "action": "enter" if entering else "close",
            "strategy_id": _HULK if entering else "cohort_maximum_hold",
            "symbol": "BTC",
            "side": "long",
            "decision_time_ms": decision_time_ms,
            "reference_price": 100.0 if entering else 104.0,
        }
    ]
