"""Report-only evidence audit for Hulk Smash live-canary ledgers."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from statistics import median

from hypervector.live.hyperliquid_fill_identity import FillKey, ledger_fill_key

Record = Mapping[str, object]
_STRATEGY_ID = "hulk_expansion_short_robust_v3"


def audit_hulk_smash_live_run(
    records: Sequence[Record],
    *,
    run_id: str | None = None,
) -> dict[str, object]:
    """Build a non-mutating audit of one explicitly armed Hulk live run."""
    validated = _validated_records(records)
    selected, identity = _select_live_run(validated, run_id)
    fills = _event_rows(selected, "fill")
    qualities = _event_rows(selected, "execution_quality")
    markouts = _event_rows(selected, "fill_markout")
    fees = _fill_fee_rows(selected)
    acknowledgements = _acknowledgements(selected)
    positions = _event_rows(selected, "position")
    distances = _event_rows(selected, "liquidation_distance")
    exits = _exit_summary(selected)
    final_state = _final_state(selected)
    markout_summary = _markout_summary(identity, markouts)
    coverage = _coverage(
        fills=fills,
        fees=fees,
        acknowledgements=acknowledgements,
        qualities=qualities,
        markouts=markouts,
        positions=positions,
        distances=distances,
        exits=exits,
        final_state=final_state,
        faults=_event_rows(selected, "fault"),
        markout_summary=markout_summary,
    )
    return {
        "schema_version": 1,
        "mode": "hulk_smash_live_canary_audit",
        "run": _run_identity(selected, identity),
        "experiment_contract": _experiment_contract(),
        "event_counts": _event_counts(selected),
        "decisions": _decision_summary(selected),
        "execution": _execution_summary(selected, fills, acknowledgements),
        "latency_ms": _numeric_summary(acknowledgements, "round_trip_latency_ms"),
        "slippage_bps": _numeric_summary(qualities, "slippage_bps"),
        "markout": markout_summary,
        "liquidation_distance_pct": _numeric_summary(distances, "distance_pct"),
        "exits": exits,
        "final_state": final_state,
        "faults": _fault_summary(selected),
        "coverage": coverage,
        "limitations": _limitations(),
    }


def _validated_records(records: Sequence[Record]) -> tuple[Record, ...]:
    if not records:
        raise ValueError("Hulk live audit requires at least one record")
    validated = tuple(records)
    for expected, record in enumerate(validated, start=1):
        if not isinstance(record, Mapping):
            raise ValueError(f"ledger row {expected} must be an object")
        if record.get("sequence") != expected:
            raise ValueError(f"ledger sequence must be contiguous at {expected}")
        _payload(record)
    return validated


def _select_live_run(
    records: Sequence[Record],
    requested: str | None,
) -> tuple[tuple[Record, ...], Record]:
    identities = _event_rows(records, "configuration_identity")
    if requested is None:
        live_identities = [row for row in identities if _is_armed_live(row)]
        if not live_identities:
            raise ValueError("Hulk live audit found no armed live run")
        chosen = _required_text(live_identities[-1].get("run_id"), "run_id")
    else:
        chosen = requested
    selected = tuple(row for row in records if row.get("run_id") == chosen)
    if not selected:
        raise ValueError(f"Hulk live run_id not found: {chosen}")
    if not all(_is_armed_live(row) for row in selected):
        raise ValueError(f"run {chosen} is not an armed live run")
    run_identities = _event_rows(selected, "configuration_identity")
    if not run_identities:
        raise ValueError(f"run {chosen} lacks configuration_identity")
    identity = run_identities[-1]
    strategy = _payload(identity).get("strategy_name")
    if strategy != _STRATEGY_ID:
        raise ValueError(f"run {chosen} has unexpected strategy identity: {strategy!r}")
    for key in ("profile_id", "profile_fingerprint", "run_fingerprint"):
        _require_single_identity(selected, key)
    return selected, identity


def _is_armed_live(record: Record) -> bool:
    return (
        record.get("execution_mode") == "live"
        and record.get("live_armed") is True
        and record.get("execution_authority") == "hyperliquid_mainnet"
    )


def _run_identity(records: Sequence[Record], identity: Record) -> dict[str, object]:
    return {
        "run_id": identity.get("run_id"),
        "profile_id": identity.get("profile_id"),
        "profile_fingerprint": identity.get("profile_fingerprint"),
        "run_fingerprint": identity.get("run_fingerprint"),
        "strategy_id": _STRATEGY_ID,
        "row_count": len(records),
        "first_sequence": records[0].get("sequence"),
        "last_sequence": records[-1].get("sequence"),
        "first_observed_at_utc": records[0].get("observed_at_utc"),
        "last_observed_at_utc": records[-1].get("observed_at_utc"),
    }


def _experiment_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "performance_gate": False,
    }


def _event_counts(records: Sequence[Record]) -> dict[str, int]:
    return dict(sorted(Counter(_event_type(row) for row in records).items()))


def _decision_summary(records: Sequence[Record]) -> dict[str, int]:
    decisions = _event_rows(records, "regime_decision")
    return {
        "completed_bar_decisions": len(decisions),
        "eligible_entries": sum(
            _payload(row).get("entry_allowed") is True for row in decisions
        ),
        "entry_intents": sum(
            _payload(row).get("operation") == "entry"
            for row in _event_rows(records, "order_intent")
        ),
    }


def _execution_summary(
    records: Sequence[Record],
    fills: Sequence[Record],
    acknowledgements: Sequence[Record],
) -> dict[str, object]:
    fill_payloads = [_payload(row) for row in fills]
    return {
        "order_intents": len(_event_rows(records, "order_intent")),
        "acknowledgements": len(acknowledgements),
        "accepted_acknowledgements": sum(
            _payload(row).get("accepted") is True for row in acknowledgements
        ),
        "fills": len(fills),
        "maker_fills": sum(
            payload.get("crossed") is False for payload in fill_payloads
        ),
        "taker_fills": sum(payload.get("crossed") is True for payload in fill_payloads),
        "fill_notional_usd": sum(_fill_notional(payload) for payload in fill_payloads),
        "fill_fees_usd": sum(
            _number(payload.get("fee_usd"), "fill fee") for payload in fill_payloads
        ),
        "closed_pnl_usd": sum(
            _number(payload.get("closed_pnl_usd"), "closed PnL")
            for payload in fill_payloads
        ),
        "funding_usd": sum(
            _number(_payload(row).get("usdc_delta"), "funding delta")
            for row in _event_rows(records, "funding")
        ),
    }


def _fill_notional(payload: Record) -> float:
    price = _positive_number(payload.get("price"), "fill price")
    size = _positive_number(payload.get("size"), "fill size")
    crossed = payload.get("crossed")
    if not isinstance(crossed, bool):
        raise ValueError("fill crossed must be boolean")
    return price * size


def _markout_summary(identity: Record, markouts: Sequence[Record]) -> dict[str, object]:
    execution = _payload(identity).get("execution")
    target = None
    if isinstance(execution, Mapping):
        target = _optional_number(execution.get("markout_horizon_ms"), "markout target")
    targets = {
        int(value)
        for row in markouts
        if (
            value := _optional_number(
                _payload(row).get("target_horizon_ms"), "markout target"
            )
        )
        is not None
    }
    return {
        "markout_bps": _numeric_summary(markouts, "markout_bps"),
        "actual_horizon_ms": _numeric_summary(markouts, "horizon_ms"),
        "lateness_ms": _numeric_summary(markouts, "horizon_lateness_ms"),
        "target_horizon_ms": int(target) if target is not None else None,
        "reported_target_horizons_ms": sorted(targets),
        "recovered_after_restart": sum(
            _payload(row).get("recovered_after_restart") is True for row in markouts
        ),
    }


def _exit_summary(records: Sequence[Record]) -> dict[str, object]:
    closes = [
        row
        for row in _event_rows(records, "close")
        if _payload(row).get("verified_flat") is True
    ]
    reasons = Counter(
        _required_text(_payload(row).get("reason"), "close reason") for row in closes
    )
    return {
        "verified_flat_closes": len(closes),
        "reasons": dict(sorted(reasons.items())),
    }


def _final_state(records: Sequence[Record]) -> dict[str, object]:
    position = _latest(records, "position")
    reconciliation = _latest(records, "reconciliation")
    transition = _latest(records, "state_transition")
    size = _optional_payload_number(position, "size_signed")
    orders = _payload(reconciliation).get("open_order_ids") if reconciliation else None
    lifecycle = _payload(transition).get("state") if transition else None
    flat = size == 0.0 and isinstance(orders, list) and not orders
    return {
        "lifecycle_state": lifecycle,
        "position_size_signed": size,
        "open_order_ids": orders,
        "account_value_usd": _optional_payload_number(
            reconciliation, "account_value_usd"
        ),
        "flat": flat if position is not None and reconciliation is not None else None,
    }


def _coverage(
    *,
    fills: Sequence[Record],
    fees: Sequence[Record],
    acknowledgements: Sequence[Record],
    qualities: Sequence[Record],
    markouts: Sequence[Record],
    positions: Sequence[Record],
    distances: Sequence[Record],
    exits: Mapping[str, object],
    final_state: Mapping[str, object],
    faults: Sequence[Record],
    markout_summary: Mapping[str, object],
) -> dict[str, object]:
    fill_keys = _fill_keys(fills, "venue_timestamp_ms")
    gaps: list[str] = []
    _compare_keys(fill_keys, _fill_keys(fees, "venue_timestamp_ms"), "fee", gaps)
    _compare_keys(
        fill_keys, _fill_keys(qualities, "fill_timestamp_ms"), "slippage", gaps
    )
    _compare_keys(fill_keys, _fill_keys(markouts, "fill_timestamp_ms"), "markout", gaps)
    if fills and not acknowledgements:
        gaps.append("acknowledgement_missing_for_fills")
    if fills and exits.get("verified_flat_closes") == 0:
        gaps.append("close_attribution_missing_for_filled_run")
    if fills and not positions:
        gaps.append("position_observations_missing_for_fills")
    if _has_active_position(positions) and not distances:
        gaps.append("liquidation_distance_missing_for_active_position")
    if final_state.get("flat") is not True:
        gaps.append("final_flat_state_not_proven")
    if faults:
        gaps.append("faults_recorded")
    gaps.extend(_markout_gaps(markouts, markout_summary))
    unique_gaps = sorted(set(gaps))
    return {
        "complete": not unique_gaps,
        "technical_gaps": unique_gaps,
        "metrics": _metric_statuses(fills, qualities, markouts, distances),
    }


def _compare_keys(
    expected: set[FillKey],
    observed: set[FillKey],
    label: str,
    gaps: list[str],
) -> None:
    if expected - observed:
        gaps.append(f"{label}_missing_for_fills")
    if observed - expected:
        gaps.append(f"{label}_without_run_fill")


def _markout_gaps(
    markouts: Sequence[Record],
    summary: Mapping[str, object],
) -> list[str]:
    if not markouts:
        return []
    target = summary.get("target_horizon_ms")
    targets = summary.get("reported_target_horizons_ms")
    if not isinstance(target, int):
        return ["configured_markout_target_missing"]
    if targets != [target]:
        return ["markout_target_identity_mismatch"]
    actual = [
        _number(_payload(row).get("horizon_ms"), "markout horizon") for row in markouts
    ]
    if any(value > target * 2 for value in actual):
        return ["markout_horizon_exceeded_tolerance"]
    return []


def _metric_statuses(
    fills: Sequence[Record],
    qualities: Sequence[Record],
    markouts: Sequence[Record],
    distances: Sequence[Record],
) -> dict[str, str]:
    fill_keys = _fill_keys(fills, "venue_timestamp_ms")
    return {
        "slippage": _fill_metric_status(
            fill_keys, _fill_keys(qualities, "fill_timestamp_ms")
        ),
        "markout": _fill_metric_status(
            fill_keys, _fill_keys(markouts, "fill_timestamp_ms")
        ),
        "liquidation_distance": "observed" if distances else "not_observed",
    }


def _fill_metric_status(expected: set[FillKey], observed: set[FillKey]) -> str:
    if not expected and not observed:
        return "not_applicable_no_fills"
    if observed - expected:
        return "invalid_orphan_metrics"
    if expected - observed:
        return "incomplete"
    return "observed"


def _fill_keys(records: Sequence[Record], timestamp_key: str) -> set[FillKey]:
    keys: set[FillKey] = set()
    for row in records:
        payload = _payload(row)
        keys.add(
            ledger_fill_key(payload, timestamp_key=timestamp_key, label="Hulk fill")
        )
    return keys


def _has_active_position(records: Sequence[Record]) -> bool:
    return any(
        abs(_number(_payload(row).get("size_signed"), "position size")) > 0.0
        for row in records
    )


def _fault_summary(records: Sequence[Record]) -> dict[str, object]:
    faults = _event_rows(records, "fault")
    return {
        "count": len(faults),
        "reasons": [_payload(row).get("reason") for row in faults],
    }


def _numeric_summary(records: Sequence[Record], key: str) -> dict[str, object]:
    values = [
        value
        for row in records
        if (value := _optional_number(_payload(row).get(key), key)) is not None
    ]
    if not values:
        return {
            "count": 0,
            "minimum": None,
            "median": None,
            "maximum": None,
            "mean": None,
        }
    return {
        "count": len(values),
        "minimum": min(values),
        "median": float(median(values)),
        "maximum": max(values),
        "mean": sum(values) / len(values),
    }


def _acknowledgements(records: Sequence[Record]) -> tuple[Record, ...]:
    return tuple(
        row
        for row in records
        if _event_type(row)
        in {"order_acknowledgement", "stop_order", "target_order", "close"}
        and isinstance(_payload(row).get("accepted"), bool)
    )


def _fill_fee_rows(records: Sequence[Record]) -> tuple[Record, ...]:
    return tuple(
        row
        for row in _event_rows(records, "fee")
        if _payload(row).get("source") == "fill"
    )


def _event_rows(records: Sequence[Record], event_type: str) -> tuple[Record, ...]:
    return tuple(row for row in records if _event_type(row) == event_type)


def _event_type(record: Record) -> str:
    return _required_text(record.get("event_type"), "event_type")


def _latest(records: Sequence[Record], event_type: str) -> Record | None:
    return next(
        (row for row in reversed(records) if _event_type(row) == event_type), None
    )


def _payload(record: Record) -> Record:
    payload = record.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("ledger payload must be an object")
    return payload


def _require_single_identity(records: Sequence[Record], key: str) -> object:
    values = {row.get(key) for row in records}
    if len(values) != 1 or None in values:
        raise ValueError(f"run has inconsistent {key}")
    return next(iter(values))


def _optional_payload_number(record: Record | None, key: str) -> float | None:
    if record is None:
        return None
    return _optional_number(_payload(record).get(key), key)


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be non-empty text")
    return value


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _positive_number(value: object, label: str) -> float:
    number = _number(value, label)
    if number <= 0.0:
        raise ValueError(f"{label} must be positive")
    return number


def _optional_number(value: object, label: str) -> float | None:
    if value is None:
        return None
    return _number(value, label)


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    return float(value)


def _limitations() -> list[str]:
    return [
        "public market data cannot reveal private queue position",
        "liquidation distance and markout are sampled observations",
        "closed PnL, fees, and funding are reported separately rather than combined into an inferred return",
        "sparse or losing results remain valid evidence and are never a performance abort gate",
        "this report has no execution authority and cannot mutate strategy state",
    ]
