"""Source-compatible close reconciliation for the first V58 ETH lifecycle."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from math import isclose, isfinite

from hypervector.research.v58_eth_live_close_ledger import (
    fill_events,
    fill_time,
    reconcile_eth_close_ledger,
)

Record = Mapping[str, object]

_PROFILE = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_ASSET_PROFILE = f"{_PROFILE}_eth"
_ASSET_FINGERPRINT = "b443e05b2c7d41a61ae0688f36ddc4e0295a56910e90485742d5014b98e0ed85"
_STRATEGY = "eth_breakout_precompression_pullback_bidirectional_v1"
_ROUTE = f"{_STRATEGY}|ETH"
_ACTIVE_REASONS = frozenset(
    {"maximum_hold", "maximum_hold_seconds", "opposite_strategy_intent"}
)


def build_v58_eth_live_close_reconciliation(
    preregistration: Record,
    closed_context: Record,
    ledger_rows: Sequence[Record],
    venue_preflight: Record,
    observer_resolution: Record,
) -> dict[str, object]:
    """Reconcile one exact V58 ETH close without changing live behavior."""
    identity = _preregistered_identity(preregistration)
    close = _close_context(closed_context, identity)
    timing = _exit_timing(ledger_rows, close, identity)
    cleanup = _cleanup(close, venue_preflight, identity)
    observer = _observer_comparison(observer_resolution)
    actual = _actual_close_payload(close, timing)
    return {
        "schema_version": 1,
        "mode": "v58_eth_first_live_close_reconciliation_v1",
        "status": "reconciled",
        "frozen_identity": identity,
        "actual_live_close": actual,
        "cleanup": cleanup,
        "observer_comparison": observer,
        "frozen_counterfactuals": dict(
            _mapping(closed_context.get("policies"), "counterfactual policies")
        ),
        "interpretation": "one resolved long lifecycle is diagnostic only",
        "strategy_change_supported": False,
        "contract": _report_only_contract(),
    }


def _preregistered_identity(preregistration: Record) -> dict[str, object]:
    contract = _mapping(preregistration.get("contract"), "preregistration contract")
    if dict(contract) != _report_only_contract():
        raise ValueError("V58 ETH close preregistration contract changed")
    identity = _mapping(preregistration.get("frozen_identity"), "frozen identity")
    expected = {
        "profile_id": _PROFILE,
        "strategy_id": _STRATEGY,
        "route": _ROUTE,
        "symbol": "ETH",
        "side": "long",
    }
    if any(identity.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 ETH close frozen identity changed")
    result = dict(identity)
    _sha256(result.get("profile_fingerprint"), "profile fingerprint")
    _text(result.get("run_id"), "run id")
    _lifecycle(result.get("lifecycle_id"))
    return result


def _close_context(context: Record, identity: Record) -> dict[str, object]:
    if context.get("route") != _ROUTE or context.get("lifecycle_state") != "closed":
        raise ValueError("V58 ETH close context is not the frozen closed route")
    if context.get("strategy_change_supported") is not False:
        raise ValueError("V58 ETH close context proposes a strategy change")
    close = dict(_mapping(context.get("actual_close_reconciliation"), "close"))
    expected = {
        "lifecycle_id": identity["lifecycle_id"],
        "source_run_id": identity["run_id"],
        "source_profile_fingerprint": identity["profile_fingerprint"],
        "strategy_id": _STRATEGY,
        "symbol": "ETH",
        "side": "long",
        "accounting_reconciled": True,
        "ledger_flat_order_free": True,
    }
    if any(close.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 ETH close context identity or accounting differs")
    reason = _text(close.get("exit_reason"), "exit reason")
    if reason not in _ACTIVE_REASONS | {"protective_stop"}:
        raise ValueError("V58 ETH close reason is outside the frozen exit contract")
    _reconcile_close_cash(close)
    return close


def _reconcile_close_cash(close: Record) -> None:
    entry = _trade_leg(close.get("entry"), "entry")
    exit_leg = _trade_leg(close.get("exit"), "exit")
    if not isclose(entry["size"], exit_leg["size"], abs_tol=1e-12):
        raise ValueError("V58 ETH close size differs from entry")
    gross = (exit_leg["price"] - entry["price"]) * entry["size"]
    fees = _nonnegative(close.get("fees_usd"), "fees")
    funding = _number(close.get("funding_usd"), "funding")
    net = _number(close.get("net_pnl_usd"), "net PnL")
    if not isclose(
        gross, _number(close.get("gross_market_pnl_usd"), "gross PnL"), abs_tol=1e-8
    ):
        raise ValueError("V58 ETH close gross price accounting differs")
    if not isclose(net, gross - fees + funding, abs_tol=1e-8):
        raise ValueError("V58 ETH close net cash accounting differs")


def _exit_timing(
    rows: Sequence[Record], close: Record, identity: Record
) -> dict[str, object]:
    ledger = reconcile_eth_close_ledger(
        rows,
        close,
        run_id=_text(identity.get("run_id"), "run id"),
        profile_id=_ASSET_PROFILE,
        profile_fingerprint=_ASSET_FINGERPRINT,
    )
    scoped = ledger.rows
    close = _close_with_order_ids(close, ledger.entry_oid, ledger.exit_oid)
    exit_leg = _mapping(close.get("exit"), "exit")
    exit_oid = _positive_int(exit_leg.get("oid"), "exit oid")
    fills = fill_events(scoped, exit_oid)
    reason = _text(close.get("exit_reason"), "exit reason")
    timing = (
        _protective_stop_timing(scoped, close, fills)
        if reason == "protective_stop"
        else _active_close_timing(scoped, close, fills)
    )
    verified = _one_event(
        scoped,
        "close",
        lambda row: _payload(row).get("oid") == exit_oid
        and _payload(row).get("verified_flat") is True,
    )
    if _payload(verified).get("reason") != reason:
        raise ValueError("V58 ETH verified-flat close reason differs")
    return timing


def _close_with_order_ids(close: Record, entry_oid: int, exit_oid: int) -> Record:
    output = dict(close)
    output["entry"] = {**_mapping(close.get("entry"), "entry"), "oid": entry_oid}
    output["exit"] = {**_mapping(close.get("exit"), "exit"), "oid": exit_oid}
    return output


def _active_close_timing(
    rows: Sequence[Record], close: Record, fills: Sequence[Record]
) -> dict[str, object]:
    reason = _text(close.get("exit_reason"), "exit reason")
    decision = _one_event(
        rows,
        "regime_decision",
        lambda row: _payload(row).get("routing_action") == "close"
        and _payload(row).get("symbol") == "ETH"
        and _payload(row).get("exit_reason") == reason,
    )
    intent = _one_event(
        rows,
        "order_intent",
        lambda row: _payload(row).get("operation") == "reduce_only_close",
    )
    client_id = _text(_payload(intent).get("client_order_id"), "close client id")
    exit_oid = _positive_int(_mapping(close.get("exit"), "exit").get("oid"), "exit oid")
    acknowledgement = _one_event(
        rows,
        "close",
        lambda row: _payload(row).get("accepted") is True
        and _payload(row).get("oid") == exit_oid
        and _payload(row).get("client_order_id") == client_id,
    )
    decision_ms = _positive_int(
        _payload(decision).get("decision_time_ms"), "decision time"
    )
    return _timing_payload(
        decision_ms,
        "backend_routing_decision",
        _observed_ms(intent),
        _observed_ms(acknowledgement),
        fill_time(fills),
        len(fills),
    )


def _protective_stop_timing(
    rows: Sequence[Record], close: Record, fills: Sequence[Record]
) -> dict[str, object]:
    stop = _mapping(close.get("protective_stop"), "protective stop")
    stop_oid = _positive_int(stop.get("oid"), "protective stop oid")
    exit_oid = _positive_int(_mapping(close.get("exit"), "exit").get("oid"), "exit oid")
    if exit_oid != stop_oid:
        raise ValueError("V58 ETH protective-stop exit oid differs")
    acknowledgement = _one_event(
        rows,
        "stop_order",
        lambda row: _payload(row).get("accepted") is True
        and _payload(row).get("oid") == stop_oid,
    )
    client_id = _text(
        _payload(acknowledgement).get("client_order_id"), "stop client id"
    )
    intent = _one_event(
        rows,
        "order_intent",
        lambda row: _payload(row).get("operation") == "protective_stop"
        and _payload(row).get("client_order_id") == client_id,
    )
    fill_ms = fill_time(fills)
    return _timing_payload(
        fill_ms,
        "venue_native_protective_stop_fill",
        _observed_ms(intent),
        _observed_ms(acknowledgement),
        fill_ms,
        len(fills),
    )


def _timing_payload(
    decision_ms: int,
    source: str,
    submission_ms: int,
    ack_ms: int,
    fill_ms: int,
    fill_count: int,
) -> dict[str, object]:
    if submission_ms > ack_ms or submission_ms > fill_ms:
        raise ValueError(
            "V58 ETH close submission must precede acknowledgement and fill"
        )
    return {
        "decision_time_ms": decision_ms,
        "decision_time_source": source,
        "submission_time_ms": submission_ms,
        "acknowledgement_time_ms": ack_ms,
        "fill_time_ms": fill_ms,
        "submission_to_acknowledgement_ms": ack_ms - submission_ms,
        "submission_to_fill_ms": fill_ms - submission_ms,
        "exit_fill_count": fill_count,
    }


def _cleanup(close: Record, venue: Record, identity: Record) -> dict[str, object]:
    authority = _mapping(venue.get("authority"), "venue authority")
    if (
        authority.get("execution_authority") != "none"
        or authority.get("execution_client_constructed") is not False
    ):
        raise ValueError("V58 ETH venue cleanup evidence has execution authority")
    venue_identity = _mapping(venue.get("identity"), "venue identity")
    if (
        venue_identity.get("active_profile_id") != identity["profile_id"]
        or venue_identity.get("active_profile_fingerprint")
        != identity["profile_fingerprint"]
        or venue_identity.get("network") != "mainnet"
    ):
        raise ValueError("V58 ETH venue cleanup identity differs")
    assets = _records(venue.get("assets"), "venue assets")
    matches = [row for row in assets if row.get("symbol") == "ETH"]
    if len(matches) != 1:
        raise ValueError("V58 ETH venue cleanup coverage differs")
    eth = matches[0]
    position = _mapping(eth.get("position"), "venue ETH position")
    orders = eth.get("open_orders")
    ledger = _mapping(eth.get("ledger_reconciliation"), "venue ETH ledger")
    flags = ("matches", "orders_match", "position_matches")
    flat = (
        _number(position.get("size_signed"), "venue ETH size") == 0.0 and orders == []
    )
    if not flat or any(ledger.get(key) is not True for key in flags):
        raise ValueError("V58 ETH venue cleanup is not flat and reconciled")
    if ledger.get("venue_owned_order_ids") != []:
        raise ValueError("V58 ETH venue cleanup retains an owned order")
    return {
        "ledger_flat_order_free": close.get("ledger_flat_order_free") is True,
        "venue_eth_flat_order_free": True,
        "venue_ledger_reconciled": True,
        "protective_stop_absent": True,
        "venue_observed_at_utc": _text(venue.get("observed_at_utc"), "venue time"),
    }


def _observer_comparison(resolution: Record) -> dict[str, object]:
    expected = {
        "status": "resolved",
        "source_run_id": "bidirectional-observe-1787127644202",
        "strategy_id": _STRATEGY,
        "symbol": "ETH",
        "side": "long",
        "decision_time_ms": 1787172900000,
        "entry_notional_usd": 750.0,
        "net_return_scope": "exact_depth_fee_and_funding",
    }
    if any(resolution.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 ETH observer comparison identity or scope differs")
    return {
        "source_run_id": resolution["source_run_id"],
        "strategy_id": resolution["strategy_id"],
        "symbol": resolution["symbol"],
        "side": resolution["side"],
        "decision_time_ms": resolution["decision_time_ms"],
        "notional_usd": 750.0,
        "entry_time_ms": _positive_int(
            resolution.get("entry_time_ms"), "observer entry"
        ),
        "exit_time_ms": _positive_int(resolution.get("exit_time_ms"), "observer exit"),
        "exit_reason": _text(resolution.get("exit_reason"), "observer exit reason"),
        "net_return_bps": _number(
            resolution.get("net_return_bps"), "observer net return"
        ),
        "simulated_net_pnl_usd": _number(
            resolution.get("simulated_net_pnl_usd"), "observer PnL"
        ),
        "net_return_scope": resolution["net_return_scope"],
        "actual_orders_or_fills_claimed": False,
    }


def _actual_close_payload(close: Record, timing: Record) -> dict[str, object]:
    entry = _trade_leg(close.get("entry"), "entry")
    exit_leg = _trade_leg(close.get("exit"), "exit")
    notional = entry["price"] * entry["size"]
    net = _number(close.get("net_pnl_usd"), "net PnL")
    return {
        "lifecycle_id": close["lifecycle_id"],
        "exit_reason": close["exit_reason"],
        **dict(timing),
        "fill_price": exit_leg["price"],
        "exit_slippage_bps": _number(
            _mapping(close.get("exit"), "exit").get("slippage_bps"), "exit slippage"
        ),
        "holding_time_ms": _positive_int(close.get("holding_time_ms"), "holding time"),
        "entry_notional_usd": notional,
        "gross_market_pnl_usd": _number(close.get("gross_market_pnl_usd"), "gross PnL"),
        "fees_usd": _nonnegative(close.get("fees_usd"), "fees"),
        "funding_usd": _number(close.get("funding_usd"), "funding"),
        "net_pnl_usd": net,
        "net_return_on_entry_notional_bps": net / notional * 10_000.0,
        "actual_orders_and_fills_claimed": True,
    }


def _one_event(
    rows: Sequence[Record], event_type: str, predicate: Callable[[Record], bool]
) -> Record:
    matches = [
        row for row in rows if row.get("event_type") == event_type and predicate(row)
    ]
    if len(matches) != 1:
        raise ValueError(f"V58 ETH close requires one {event_type} event")
    return matches[0]


def _payload(row: Record) -> Record:
    return _mapping(row.get("payload"), "ledger payload")


def _observed_ms(row: Record) -> int:
    value = _text(row.get("observed_at_utc"), "observed_at")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("V58 ETH close observed_at is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError("V58 ETH close observed_at must be timezone-aware")
    return int(parsed.timestamp() * 1000)


def _trade_leg(value: object, label: str) -> dict[str, float]:
    leg = _mapping(value, label)
    return {
        "price": _positive(leg.get("price"), f"{label} price"),
        "size": _positive(leg.get("size"), f"{label} size"),
    }


def _report_only_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "performance_gate": False,
        "runtime_strategy_changed": False,
        "approval_requested": False,
    }


def _lifecycle(value: object) -> str:
    text = _text(value, "lifecycle id")
    if not text.startswith("ETH:") or not text.removeprefix("ETH:").isdigit():
        raise ValueError("V58 ETH lifecycle id is invalid")
    return text


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, list):
        raise ValueError(f"V58 ETH {label} must be a list")
    return tuple(_mapping(row, label) for row in value)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"V58 ETH {label} must be a mapping")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"V58 ETH {label} must be non-empty text")
    return value


def _sha256(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"V58 ETH {label} must be lowercase sha256")
    return text


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"V58 ETH {label} must be numeric")
    output = float(value)
    if not isfinite(output):
        raise ValueError(f"V58 ETH {label} must be finite")
    return output


def _positive(value: object, label: str) -> float:
    output = _number(value, label)
    if output <= 0.0:
        raise ValueError(f"V58 ETH {label} must be positive")
    return output


def _nonnegative(value: object, label: str) -> float:
    output = _number(value, label)
    if output < 0.0:
        raise ValueError(f"V58 ETH {label} must be nonnegative")
    return output


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"V58 ETH {label} must be a positive integer")
    return value
