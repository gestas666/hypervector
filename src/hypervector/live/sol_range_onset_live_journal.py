"""Read-only lifecycle attribution for the append-only SOL live ledger."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence

from hypervector.live.sol_range_onset_live_journal_values import (
    optional_float as _optional_float,
    optional_positive_float as _optional_positive_float,
    payload as _payload,
    payload_value as _payload_value,
    positive_int as _positive_int,
    required_direction as _required_direction,
    required_float as _required_float,
    required_int as _required_int,
    required_positive_int as _required_positive_int,
    sequence as _sequence,
)
from hypervector.live.sol_range_onset_live_journal_protection import (
    protective_stop_attribution,
)

Record = Mapping[str, object]


def build_live_journal(records: Sequence[Record]) -> dict[str, object]:
    """Attribute authoritative live records into closed and open lifecycles."""
    ordered = _validated_records(records)
    entries = _accepted_entry_acks(ordered)
    closed: list[dict[str, object]] = []
    open_lifecycles: list[dict[str, object]] = []
    for index, entry in enumerate(entries):
        end_sequence = _next_entry_sequence(entries, index)
        lifecycle = _build_lifecycle(ordered, entry, end_sequence)
        if lifecycle.get("status") == "closed":
            closed.append(lifecycle)
        else:
            open_lifecycles.append(lifecycle)
    return {
        "schema_version": 1,
        "mode": "sol_range_onset_live_journal_snapshot",
        "execution_authority": "none",
        "source_execution_authority": "hyperliquid_mainnet",
        "runtime_strategy_changed": False,
        "integrity": _integrity(ordered),
        "observations": _observation_summary(ordered),
        "summary": _trade_summary(closed, open_lifecycles),
        "trades": closed,
        "open_lifecycles": open_lifecycles,
        "limitations": [
            "L2 path extrema use sampled midpoint observations, not venue mark ticks",
            "account-value changes can include effects outside one SOL lifecycle",
            "an open lifecycle remains provisional until venue-flat reconciliation",
            "this report observes but cannot mutate strategy or submit orders",
        ],
    }


def _validated_records(records: Sequence[Record]) -> tuple[Record, ...]:
    if not records:
        raise ValueError("live journal requires at least one ledger record")
    ordered = tuple(records)
    for expected, record in enumerate(ordered, start=1):
        if not isinstance(record, Mapping):
            raise ValueError(f"live ledger record {expected} must be an object")
        if record.get("sequence") != expected:
            raise ValueError(f"live ledger sequence must be contiguous at {expected}")
        if record.get("execution_mode") != "live":
            raise ValueError(f"live ledger record {expected} is not live mode")
        if record.get("execution_authority") != "hyperliquid_mainnet":
            raise ValueError(f"live ledger record {expected} has wrong authority")
        _payload(record)
    return ordered


def _accepted_entry_acks(records: Sequence[Record]) -> list[Record]:
    return [
        record
        for record in records
        if record.get("event_type") == "order_acknowledgement"
        and _payload(record).get("operation") == "entry"
        and _payload(record).get("accepted") is True
        and _positive_int(_payload(record).get("oid")) is not None
    ]


def _next_entry_sequence(entries: Sequence[Record], index: int) -> int | None:
    if index + 1 >= len(entries):
        return None
    return _sequence(entries[index + 1])


def _build_lifecycle(
    records: Sequence[Record],
    entry_ack: Record,
    end_sequence: int | None,
) -> dict[str, object]:
    entry_oid = _required_positive_int(_payload(entry_ack).get("oid"), "entry oid")
    start = _sequence(entry_ack)
    window = _window(records, start, end_sequence)
    entry_fills = _fills_for_oid(window, entry_oid)
    entry_intent = _intent_for_ack(records, entry_ack)
    close_event = _verified_close(window)
    base = _entry_attribution(records, entry_ack, entry_intent, entry_fills)
    base["entry_oid"] = entry_oid
    base["protective_stop"] = protective_stop_attribution(window)
    if not entry_fills:
        base.update({"status": "entry_unfilled", "exit_oid": None})
        return base
    if close_event is None:
        entry_stats = _fill_summary(entry_fills)
        entry_time = _required_int(entry_stats.get("venue_timestamp_ms"), "entry time")
        base.update(
            {
                "status": "open",
                "exit_oid": None,
                "fees_usd": _required_float(entry_stats.get("fees_usd")),
                "funding_usd": _funding_between(window, entry_time, None),
            }
        )
        return base
    return _close_attribution(records, window, base, close_event, entry_fills)


def _entry_attribution(
    records: Sequence[Record],
    entry_ack: Record,
    entry_intent: Record | None,
    entry_fills: Sequence[Record],
) -> dict[str, object]:
    intent_payload = _payload(entry_intent) if entry_intent is not None else {}
    side = _direction(intent_payload, entry_fills)
    expected = _optional_positive_float(intent_payload.get("mark_price"))
    fill = _fill_summary(entry_fills)
    before = _last_before(records, "reconciliation", _sequence(entry_ack))
    decision_boundary = _sequence(entry_intent or entry_ack)
    decision = _last_before(records, "regime_decision", decision_boundary)
    position = _first_after(records, "position", _sequence(entry_ack), nonflat=True)
    liquidation = _first_after(records, "liquidation_price", _sequence(entry_ack))
    return {
        "status": "pending",
        "direction": side,
        "entry": _execution_leg(fill, expected, side, entering=True),
        "entry_regime": _regime_payload(decision),
        "requested_notional_usd": _optional_float(
            intent_payload.get("requested_notional_usd")
        ),
        "margin_used_usd": _payload_value(position, "margin_used_usd"),
        "leverage": _payload_value(position, "leverage"),
        "liquidation_price": _payload_value(liquidation, "value"),
        "account_value_before_usd": _payload_value(before, "account_value_usd"),
    }


def _close_attribution(
    records: Sequence[Record],
    window: Sequence[Record],
    base: dict[str, object],
    close_event: Record,
    entry_fills: Sequence[Record],
) -> dict[str, object]:
    exit_oid = _resolved_exit_oid(close_event, window)
    exit_fills = _fills_for_oid(window, exit_oid)
    if not exit_fills:
        base.update({"status": "close_unfilled", "exit_oid": exit_oid})
        return base
    direction = _required_direction(base.get("direction"))
    exit_intent = _intent_for_oid(records, exit_oid)
    expected = _exit_reference(exit_intent)
    entry_stats = _fill_summary(entry_fills)
    exit_stats = _fill_summary(exit_fills)
    entry_time = _required_int(entry_stats.get("venue_timestamp_ms"), "entry time")
    exit_time = _required_int(exit_stats.get("venue_timestamp_ms"), "exit time")
    funding = _funding_between(window, entry_time, exit_time)
    fees = _required_float(entry_stats.get("fees_usd")) + _required_float(
        exit_stats.get("fees_usd")
    )
    gross = sum(_fill_closed_pnl(record) for record in exit_fills)
    account_after_usd = _account_after_usd(records, close_event)
    exit_decision = _last_before(records, "regime_decision", _sequence(close_event) + 1)
    base.update(
        {
            "status": "closed",
            "exit_oid": exit_oid,
            "exit": _execution_leg(exit_stats, expected, direction, entering=False),
            "exit_regime": _regime_payload(exit_decision),
            "exit_reason": _payload(close_event).get("reason"),
            "holding_time_ms": exit_time - entry_time,
            "closed_pnl_before_friction_usd": gross,
            "fees_usd": fees,
            "funding_usd": funding,
            "net_pnl_usd": gross - fees + funding,
            "account_value_after_usd": account_after_usd,
            "sampled_mid_path": _path_attribution(
                window,
                direction,
                _required_float(entry_stats.get("price")),
                entry_time,
                exit_time,
            ),
        }
    )
    base["account_value_change_usd"] = _account_delta(base)
    return base


def _resolved_exit_oid(close_event: Record, window: Sequence[Record]) -> int:
    direct = _positive_int(_payload(close_event).get("oid"))
    if direct is not None:
        return direct
    owned = _payload(close_event).get("owned_oids")
    if not isinstance(owned, list):
        raise ValueError("live journal bracket close owned_oids must be a list")
    owned_oids = {_required_positive_int(value, "owned oid") for value in owned}
    filled_oids = {
        _required_positive_int(_payload(record).get("oid"), "fill oid")
        for record in window
        if record.get("event_type") == "fill"
        and str(_payload(record).get("direction", "")).lower().startswith("close ")
        and _positive_int(_payload(record).get("oid")) in owned_oids
    }
    if len(filled_oids) != 1:
        raise ValueError(
            "live journal bracket close must have exactly one filled owned oid"
        )
    return next(iter(filled_oids))


def _account_after_usd(records: Sequence[Record], close_event: Record) -> object:
    account = _first_after(records, "reconciliation", _sequence(close_event))
    return _payload_value(account, "account_value_usd")


def _execution_leg(
    fill: Mapping[str, object],
    expected: float | None,
    direction: str,
    *,
    entering: bool,
) -> dict[str, object]:
    actual = _optional_positive_float(fill.get("price"))
    return {
        "venue_timestamp_ms": fill.get("venue_timestamp_ms"),
        "price": actual,
        "size": fill.get("size"),
        "expected_reference_price": expected,
        "slippage_bps": _slippage_bps(expected, actual, direction, entering),
    }


def _fill_summary(records: Sequence[Record]) -> dict[str, object]:
    if not records:
        return {"venue_timestamp_ms": None, "price": None, "size": 0.0, "fees_usd": 0.0}
    sizes = [_required_float(_payload(record).get("size")) for record in records]
    total = sum(sizes)
    if total <= 0.0:
        raise ValueError("live fill size must be positive")
    prices = [_required_float(_payload(record).get("price")) for record in records]
    fees = sum(_required_float(_payload(record).get("fee_usd")) for record in records)
    timestamps = [
        _required_int(_payload(record).get("venue_timestamp_ms"), "fill time")
        for record in records
    ]
    return {
        "venue_timestamp_ms": min(timestamps),
        "price": sum(price * size for price, size in zip(prices, sizes, strict=True))
        / total,
        "size": total,
        "fees_usd": fees,
    }


def _path_attribution(
    records: Sequence[Record],
    direction: str,
    entry_price: float,
    start_ms: int,
    end_ms: int,
) -> dict[str, object]:
    mids = [
        _required_float(_payload(record).get("mid_px"))
        for record in records
        if record.get("event_type") == "book_observation"
        and start_ms
        <= _required_int(_payload(record).get("exchange_ts_ms"), "book time")
        <= end_ms
    ]
    if not mids:
        return {
            "observations": 0,
            "maximum_favorable_pct": None,
            "maximum_adverse_pct": None,
        }
    returns = [
        (mid / entry_price - 1.0) * (1.0 if direction == "long" else -1.0) * 100.0
        for mid in mids
    ]
    return {
        "observations": len(mids),
        "maximum_favorable_pct": max(returns),
        "maximum_adverse_pct": min(returns),
    }


def _trade_summary(
    closed: Sequence[Mapping[str, object]],
    open_lifecycles: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    pnls = [_required_float(trade.get("net_pnl_usd")) for trade in closed]
    profits = sum(value for value in pnls if value > 0.0)
    losses = -sum(value for value in pnls if value < 0.0)
    return {
        "closed_trades": len(closed),
        "open_lifecycles": len(open_lifecycles),
        "wins": sum(value > 0.0 for value in pnls),
        "losses": sum(value < 0.0 for value in pnls),
        "net_pnl_usd": sum(pnls),
        "fees_usd": sum(_required_float(trade.get("fees_usd")) for trade in closed),
        "funding_usd": sum(
            _required_float(trade.get("funding_usd")) for trade in closed
        ),
        "profit_factor": profits / losses if losses else None,
    }


def _observation_summary(records: Sequence[Record]) -> dict[str, object]:
    event_counts = Counter(str(record.get("event_type")) for record in records)
    decisions = [
        record for record in records if record.get("event_type") == "regime_decision"
    ]
    actions = Counter(
        str(_payload(record).get("decision_action")) for record in decisions
    )
    regimes = Counter(
        str(_payload(record).get("primary_regime")) for record in decisions
    )
    return {
        "event_counts": dict(sorted(event_counts.items())),
        "decision_actions": dict(sorted(actions.items())),
        "primary_regimes": dict(sorted(regimes.items())),
    }


def _integrity(records: Sequence[Record]) -> dict[str, object]:
    return {
        "sequence_complete": True,
        "record_count": len(records),
        "first_observed_at_utc": records[0].get("observed_at_utc"),
        "last_observed_at_utc": records[-1].get("observed_at_utc"),
        "run_ids": sorted({str(record.get("run_id")) for record in records}),
        "profile_fingerprints": sorted(
            {str(record.get("profile_fingerprint")) for record in records}
        ),
    }


def _window(records: Sequence[Record], start: int, end: int | None) -> list[Record]:
    return [
        record
        for record in records
        if _sequence(record) >= start and (end is None or _sequence(record) < end)
    ]


def _fills_for_oid(records: Sequence[Record], oid: int) -> list[Record]:
    return [
        record
        for record in records
        if record.get("event_type") == "fill" and _payload(record).get("oid") == oid
    ]


def _verified_close(records: Sequence[Record]) -> Record | None:
    return next(
        (
            record
            for record in records
            if record.get("event_type") == "close"
            and _payload(record).get("verified_flat") is True
        ),
        None,
    )


def _intent_for_ack(records: Sequence[Record], ack: Record) -> Record | None:
    client_id = _payload(ack).get("client_order_id")
    if not isinstance(client_id, str):
        return None
    return next(
        (
            record
            for record in reversed(records[: _sequence(ack) - 1])
            if record.get("event_type") == "order_intent"
            and _payload(record).get("client_order_id") == client_id
        ),
        None,
    )


def _intent_for_oid(records: Sequence[Record], oid: int) -> Record | None:
    ack = next(
        (
            record
            for record in records
            if record.get("event_type")
            in {"close", "stop_order", "target_order", "order_acknowledgement"}
            and _payload(record).get("oid") == oid
            and isinstance(_payload(record).get("client_order_id"), str)
        ),
        None,
    )
    return _intent_for_ack(records, ack) if ack is not None else None


def _last_before(
    records: Sequence[Record], event_type: str, sequence: int
) -> Record | None:
    matches = [
        record
        for record in records
        if record.get("event_type") == event_type and _sequence(record) < sequence
    ]
    return matches[-1] if matches else None


def _first_after(
    records: Sequence[Record], event_type: str, sequence: int, *, nonflat: bool = False
) -> Record | None:
    for record in records:
        if record.get("event_type") != event_type or _sequence(record) <= sequence:
            continue
        if not nonflat or _payload(record).get("size_signed") not in {None, 0, 0.0}:
            return record
    return None


def _regime_payload(record: Record | None) -> dict[str, object] | None:
    if record is None:
        return None
    payload = _payload(record)
    keys = (
        "strategy_id",
        "decision_time_ms",
        "decision_action",
        "primary_regime",
        "state_1m",
        "state_5m",
        "context_15m",
        "confidence",
    )
    return {key: payload.get(key) for key in keys}


def _funding_between(
    records: Sequence[Record], start_ms: int, end_ms: int | None
) -> float:
    return sum(
        _required_float(_payload(record).get("usdc_delta"))
        for record in records
        if record.get("event_type") == "funding"
        and start_ms
        <= _required_int(_payload(record).get("venue_timestamp_ms"), "funding time")
        and (
            end_ms is None
            or _required_int(_payload(record).get("venue_timestamp_ms"), "funding time")
            <= end_ms
        )
    )


def _fill_closed_pnl(record: Record) -> float:
    return _required_float(_payload(record).get("closed_pnl_usd"))


def _exit_reference(intent: Record | None) -> float | None:
    if intent is None:
        return None
    payload = _payload(intent)
    return _optional_positive_float(
        payload.get("mark_price")
        or payload.get("trigger_price")
        or payload.get("limit_price")
    )


def _direction(intent: Mapping[str, object], fills: Sequence[Record]) -> str:
    side = intent.get("side")
    if isinstance(side, str) and side.lower() in {"long", "short"}:
        return side.lower()
    if fills:
        label = str(_payload(fills[0]).get("direction", "")).lower()
        if "long" in label:
            return "long"
        if "short" in label:
            return "short"
    raise ValueError("live lifecycle entry direction is unavailable")


def _slippage_bps(
    expected: float | None, actual: float | None, direction: str, entering: bool
) -> float | None:
    if expected is None or actual is None:
        return None
    buy = (direction == "long" and entering) or (direction == "short" and not entering)
    signed = actual - expected if buy else expected - actual
    return signed / expected * 10_000.0


def _account_delta(values: Mapping[str, object]) -> float | None:
    before = _optional_float(values.get("account_value_before_usd"))
    after = _optional_float(values.get("account_value_after_usd"))
    return None if before is None or after is None else after - before
