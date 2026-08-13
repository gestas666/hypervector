"""Reusable causal cohort rows for signal-outcome tests."""

from __future__ import annotations

from datetime import datetime, timezone

RUN_ID = "cohort-signal-a"
STRATEGY = "hulk_expansion_bidirectional_tuned_v2"
DECISION_MS = 1_785_600_000_000


def cohort_rows() -> list[dict[str, object]]:
    """Build a complete causal cohort journal."""
    payloads = [
        ("configuration_identity", identity()),
        (
            "intent_routing",
            {"actions": [], "withheld": [], "evaluations": [evaluation()]},
        ),
        ("market_candles", {"timeframe": "1m", "bars": {"BTC": bars()}}),
        ("cohort_snapshot", snapshot()),
        ("heartbeat", {"status": "running"}),
    ]
    rows = [
        row(index, event, value) for index, (event, value) in enumerate(payloads, 1)
    ]
    rows[-1]["observed_at_utc"] = datetime.fromtimestamp(
        (DECISION_MS + 5_000) / 1_000,
        timezone.utc,
    ).isoformat()
    return rows


def evaluation() -> dict[str, object]:
    """Build one eligible long provider evaluation."""
    return {
        "strategy_id": STRATEGY,
        "symbol": "BTC",
        "decision_time_ms": DECISION_MS,
        "reference_price": 100.0,
        "decision_action": "enter_long",
        "eligible": True,
        "reason": "eligible",
        "side": "long",
        "readiness": {
            "side": "long",
            "conditions_met": 6,
            "conditions_required": 6,
            "readiness_fraction": 1.0,
            "blockers": [],
            "indicators": ["FIXTURE"],
            "metrics": {"adx": 18.0},
        },
    }


def bars() -> list[dict[str, object]]:
    """Build five completed one-minute bars after the decision."""
    return [
        {
            "timestamp_ms": DECISION_MS + offset * 60_000,
            "open": 100.0 + offset,
            "high": 102.0 + offset,
            "low": 99.0 + offset,
            "close": 101.0 + offset,
            "volume": 10.0,
        }
        for offset in range(5)
    ]


def identity() -> dict[str, object]:
    """Build one-provider runtime configuration identity."""
    return {
        "strategy_name": "multi_asset_bidirectional_cohort",
        "enabled_symbols": ["BTC"],
        "assets": [{"symbol": "BTC"}],
        "providers": [
            {
                "strategy_id": STRATEGY,
                "symbols": ["BTC"],
                "execution_symbols": ["BTC"],
            }
        ],
        "position_policy": {
            "max_positions_per_symbol": 1,
            "maximum_concurrent_positions": 1,
        },
    }


def snapshot() -> dict[str, object]:
    """Build a flat $500 cohort snapshot."""
    return {
        "account_value_usd": 500.0,
        "withdrawable_usd": 500.0,
        "total_margin_used_usd": 0.0,
        "total_notional_position_usd": 0.0,
        "open_position_count": 0,
        "assets": [
            {
                "symbol": "BTC",
                "state": "FLAT",
                "position_size_signed": 0.0,
                "position_side": None,
                "last_fault": None,
            }
        ],
        "recent_fills": [],
    }


def payload(value: dict[str, object]) -> dict[str, object]:
    """Return a row payload with a structural assertion."""
    result = value["payload"]
    assert isinstance(result, dict)
    return result


def first_object(values: dict[str, object], key: str) -> dict[str, object]:
    """Return the first mapping in a named list."""
    value = values[key]
    assert isinstance(value, list) and value and isinstance(value[0], dict)
    return value[0]


def nested_list(
    values: dict[str, object],
    key: str,
    nested_key: str,
) -> list[object]:
    """Return a nested list with structural assertions."""
    value = values[key]
    assert isinstance(value, dict)
    nested = value[nested_key]
    assert isinstance(nested, list)
    return nested


def asset_rows() -> list[dict[str, object]]:
    """Build the matching single-asset journal."""
    payloads = [
        ("configuration_identity", {"strategy_name": "cohort_asset", "symbol": "BTC"}),
        (
            "book_observation",
            {
                "exchange_ts_ms": DECISION_MS - 1_100,
                "recv_ts_ms": DECISION_MS - 1_000,
                "mid_px": 100.0,
                "opi": 0.5,
                "spread_bps": 0.2,
                "bid_depth_ratio": 3.0,
            },
        ),
        ("reconciliation", {"account_value_usd": 500.0, "open_order_ids": []}),
        ("position", {"size_signed": 0.0, "margin_used_usd": 0.0}),
        ("liquidation_price", {"value": None}),
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
    return [
        row(index, event, value) for index, (event, value) in enumerate(payloads, 1)
    ]


def row(
    sequence: int,
    event_type: str,
    value: dict[str, object],
) -> dict[str, object]:
    """Wrap a payload in one armed-live journal row."""
    observed_ms = DECISION_MS - 2_000 + sequence * 1_000
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
        "profile_id": "cohort-profile",
        "profile_fingerprint": "cohort-fingerprint",
        "run_fingerprint": "cohort-run",
        "run_id": RUN_ID,
        "payload": value,
    }
