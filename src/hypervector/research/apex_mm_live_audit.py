"""Report-only evidence attribution for Apex MM live canary ledgers."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from statistics import median

from hypervector.research.apex_mm_live_audit_coverage import (
    ApexCoverageEvidence,
    audit_coverage,
)
from hypervector.research.apex_mm_live_audit_quality import (
    audit_quality_attribution,
    quality_attribution_gaps,
)
from hypervector.research.apex_mm_live_audit_markout import audit_markout_horizons


Record = Mapping[str, object]
_STRATEGY_ID = "apex_regime_mm_v2"


def audit_apex_mm_live_run(
    records: Sequence[Record],
    *,
    run_id: str | None = None,
) -> dict[str, object]:
    """Build a non-mutating, strategy-attributed audit of one live run."""
    validated = _validated_records(records)
    selected, identity = _select_run(validated, run_id)
    fills = _event_rows(selected, "fill")
    acknowledgements = _event_rows(selected, "order_acknowledgement")
    qualities = _event_rows(selected, "execution_quality")
    markouts = _event_rows(selected, "fill_markout")
    positions = _event_rows(selected, "position")
    distances = _event_rows(selected, "liquidation_distance")
    funding = _event_rows(selected, "funding")
    quality_attribution = audit_quality_attribution(selected)
    quote_submission, quote_submission_gaps = _quote_submission_summary(
        selected,
        identity,
    )
    horizon_summary, horizon_gaps = audit_markout_horizons(
        _payload(identity), [_payload(row) for row in markouts]
    )
    reconstructed_inventory, reconstructed_final = _reconstructed_inventory(fills)
    final_state = _final_state(selected)
    return {
        "schema_version": 1,
        "mode": "apex_mm_live_canary_audit",
        "run": _run_identity(selected, identity),
        "experiment_contract": _experiment_contract(),
        "event_counts": dict(
            sorted(Counter(_event_type(row) for row in selected).items())
        ),
        "execution": _execution_summary(selected, fills, acknowledgements),
        "latency_ms": _latency_summary(acknowledgements),
        "quote_submission": quote_submission,
        "slippage_bps": _numeric_summary(qualities, "slippage_bps"),
        "markout_bps": _numeric_summary(markouts, "markout_bps"),
        "markout_horizon_ms": horizon_summary,
        "quality_attribution": quality_attribution,
        "inventory": _inventory_summary(fills, positions, distances),
        "final_state": final_state,
        "faults": _fault_summary(selected),
        "coverage": audit_coverage(
            ApexCoverageEvidence(
                records=selected,
                fills=fills,
                acknowledgements=acknowledgements,
                qualities=qualities,
                markouts=markouts,
                positions=positions,
                distances=distances,
                funding=funding,
                evidence_gaps=[
                    *quality_attribution_gaps(quality_attribution),
                    *horizon_gaps,
                    *quote_submission_gaps,
                ],
                markout_horizon_valid=not horizon_gaps,
                quote_freshness_status=str(quote_submission["freshness_status"]),
                reconstructed_inventory=reconstructed_inventory,
                reconstructed_final=reconstructed_final,
                observed_final=final_state["position_size_signed"],
            )
        ),
        "limitations": [
            "Hyperliquid does not expose the canary's true private queue rank",
            "book and liquidation distance are sampled observations, not every venue tick",
            "sparse or losing performance remains valid evidence and is not an abort gate",
            "this report has no execution authority and cannot mutate the strategy",
        ],
    }


def _validated_records(records: Sequence[Record]) -> tuple[Record, ...]:
    if not records:
        raise ValueError("Apex MM live audit requires at least one record")
    validated = tuple(records)
    for expected, record in enumerate(validated, start=1):
        if not isinstance(record, Mapping):
            raise ValueError(f"live record {expected} must be an object")
        if record.get("sequence") != expected:
            raise ValueError(f"live record sequence must be contiguous at {expected}")
        if record.get("execution_mode") != "live":
            raise ValueError(f"live record {expected} is not live mode")
        if record.get("execution_authority") != "hyperliquid_mainnet":
            raise ValueError(f"live record {expected} has wrong execution authority")
        _payload(record)
    return validated


def _select_run(
    records: Sequence[Record],
    requested: str | None,
) -> tuple[tuple[Record, ...], Record]:
    identities = _event_rows(records, "configuration_identity")
    if not identities:
        raise ValueError("Apex MM live audit requires configuration_identity")
    chosen = requested or _required_text(identities[-1].get("run_id"), "run_id")
    selected = tuple(row for row in records if row.get("run_id") == chosen)
    if not selected:
        raise ValueError(f"Apex MM live run_id not found: {chosen}")
    run_identities = _event_rows(selected, "configuration_identity")
    if not run_identities:
        raise ValueError(f"run {chosen} lacks configuration_identity")
    identity = run_identities[-1]
    strategy = _payload(identity).get("strategy_name")
    if strategy != _STRATEGY_ID:
        raise ValueError(f"run {chosen} has unexpected strategy identity: {strategy!r}")
    _require_single_identity(selected, "profile_id")
    _require_single_identity(selected, "profile_fingerprint")
    _require_single_identity(selected, "run_fingerprint")
    return selected, identity


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


def _execution_summary(
    records: Sequence[Record],
    fills: Sequence[Record],
    acknowledgements: Sequence[Record],
) -> dict[str, object]:
    fill_values = [_fill_values(row) for row in fills]
    funding = _event_rows(records, "funding")
    fees_usd = sum(fee for _, _, fee, _, _ in fill_values)
    closed_pnl = sum(pnl for _, _, _, pnl, _ in fill_values)
    funding_usd = sum(_number(row, "usdc_delta") for row in funding)
    return {
        "quote_observations": len(_event_rows(records, "theoretical_quote")),
        "order_intents": len(_event_rows(records, "order_intent")),
        "acknowledgements": len(acknowledgements),
        "accepted_acknowledgements": sum(
            _payload(row).get("accepted") is True for row in acknowledgements
        ),
        "fills": len(fills),
        "maker_fills": sum(not crossed for _, _, _, _, crossed in fill_values),
        "taker_fills": sum(crossed for _, _, _, _, crossed in fill_values),
        "fill_notional_usd": sum(price * size for price, size, _, _, _ in fill_values),
        "fees_usd": fees_usd,
        "closed_pnl_before_fees_usd": closed_pnl,
        "closed_pnl_after_recorded_fees_usd": closed_pnl - fees_usd,
        "funding_usd": funding_usd,
        "net_cashflow_usd": closed_pnl - fees_usd + funding_usd,
    }


def _fill_values(row: Record) -> tuple[float, float, float, float, bool]:
    payload = _payload(row)
    price = _positive_number(payload.get("price"), "fill price")
    size = _positive_number(payload.get("size"), "fill size")
    fee = _nonnegative_number(payload.get("fee_usd"), "fill fee")
    closed_pnl = _required_number(payload.get("closed_pnl_usd"), "fill closed PnL")
    crossed = payload.get("crossed")
    if not isinstance(crossed, bool):
        raise ValueError("fill crossed must be boolean")
    return price, size, fee, closed_pnl, crossed


def _numeric_summary(records: Sequence[Record], key: str) -> dict[str, object]:
    values = [
        value for row in records if (value := _optional_number(row, key)) is not None
    ]
    return _value_summary(values)


def _value_summary(values: Sequence[float]) -> dict[str, object]:
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


def _quote_submission_summary(
    records: Sequence[Record],
    identity: Record,
) -> tuple[dict[str, object], list[str]]:
    execution = _optional_mapping(_payload(identity).get("execution"))
    transport = execution.get("submission_transport", "not_recorded")
    maximum_age = _optional_mapping_number(execution, "maximum_book_age_ms")
    latest_book_timestamp: float | None = None
    ages: list[float] = []
    ages_by_side: dict[str, list[float]] = {"buy": [], "sell": []}
    maker_intents = 0
    batch_ids: set[str] = set()
    for record in records:
        payload = _payload(record)
        if _event_type(record) == "book_observation":
            latest_book_timestamp = _optional_mapping_number(
                payload,
                "exchange_ts_ms",
            )
            continue
        if _event_type(record) != "order_intent":
            continue
        if payload.get("operation") != "maker_quote":
            continue
        maker_intents += 1
        side = _required_text(payload.get("side"), "maker quote side")
        if side not in ages_by_side:
            raise ValueError("maker quote side must be buy or sell")
        batch_id = payload.get("quote_batch_id")
        if isinstance(batch_id, str) and batch_id:
            batch_ids.add(batch_id)
        book_timestamp = _optional_mapping_number(
            payload,
            "book_exchange_timestamp_ms",
        )
        if book_timestamp is None:
            book_timestamp = latest_book_timestamp
        submitted_at = _optional_mapping_number(
            payload,
            "batch_submission_started_at_ms",
        )
        if submitted_at is None:
            submitted_at = _observed_at_ms(record)
        if book_timestamp is not None:
            age = submitted_at - book_timestamp
            ages.append(age)
            ages_by_side[side].append(age)
    stale = sum(age > maximum_age for age in ages) if maximum_age is not None else 0
    stale_by_side = {
        side: (
            sum(age > maximum_age for age in side_ages)
            if maximum_age is not None
            else 0
        )
        for side, side_ages in ages_by_side.items()
    }
    gaps: list[str] = []
    if maker_intents == 0:
        status = "not_applicable_no_maker_intents"
    elif len(ages) != maker_intents:
        status = "missing"
        gaps.append("maker_quote_book_age_missing")
    elif maximum_age is None:
        status = "observed_without_config_limit"
        gaps.append("maximum_book_age_missing_for_maker_quotes")
    elif stale:
        status = "observed_stale"
        gaps.append("maker_quote_intent_exceeded_maximum_book_age")
    else:
        status = "observed_within_limit"
    return (
        {
            "transport": transport,
            "maker_intents": maker_intents,
            "explicit_batches": len(batch_ids),
            "maximum_book_age_ms": maximum_age,
            "book_age_at_submission_ms": _value_summary(ages),
            "book_age_at_submission_ms_by_side": {
                side: _value_summary(side_ages)
                for side, side_ages in ages_by_side.items()
            },
            "intents_over_maximum_book_age": stale,
            "intents_over_maximum_book_age_by_side": stale_by_side,
            "freshness_status": status,
        },
        gaps,
    )


def _latency_summary(records: Sequence[Record]) -> dict[str, object]:
    summary = _numeric_summary(records, "round_trip_latency_ms")
    summary.pop("mean")
    return summary


def _inventory_summary(
    fills: Sequence[Record],
    positions: Sequence[Record],
    distances: Sequence[Record],
) -> dict[str, object]:
    notionals = [abs(_number(row, "position_value_usd")) for row in positions]
    reconstructed_maximum, reconstructed_final = _reconstructed_inventory(fills)
    distance_values = [
        value
        for row in distances
        if (value := _optional_number(row, "distance_pct")) is not None
    ]
    return {
        "position_observations": len(positions),
        "maximum_absolute_notional_usd": max(notionals, default=0.0),
        "maximum_reconstructed_notional_usd": reconstructed_maximum,
        "reconstructed_final_size_signed": reconstructed_final,
        "liquidation_distance_observations": len(distance_values),
        "minimum_liquidation_distance_pct": min(distance_values, default=None),
    }


def _reconstructed_inventory(fills: Sequence[Record]) -> tuple[float, float]:
    ordered = sorted(fills, key=lambda row: _number(row, "venue_timestamp_ms"))
    size_signed = 0.0
    maximum_notional = 0.0
    for row in ordered:
        payload = _payload(row)
        side = _required_text(payload.get("side"), "fill side")
        size = _positive_number(payload.get("size"), "fill size")
        price = _positive_number(payload.get("price"), "fill price")
        if side not in {"A", "B"}:
            raise ValueError("fill side must be A or B")
        size_signed += size if side == "B" else -size
        maximum_notional = max(maximum_notional, abs(size_signed * price))
    return maximum_notional, size_signed


def _final_state(records: Sequence[Record]) -> dict[str, object]:
    position = _latest(records, "position")
    reconciliation = _latest(records, "reconciliation")
    state = _latest(records, "state_transition")
    size = _optional_number(position, "size_signed") if position else None
    order_ids = (
        _payload(reconciliation).get("open_order_ids") if reconciliation else None
    )
    flat = size == 0.0 and isinstance(order_ids, list) and not order_ids
    return {
        "lifecycle_state": _payload(state).get("state") if state else None,
        "position_size_signed": size,
        "open_order_ids": order_ids,
        "account_value_usd": _optional_number(reconciliation, "account_value_usd")
        if reconciliation
        else None,
        "withdrawable_usd": _optional_number(reconciliation, "withdrawable_usd")
        if reconciliation
        else None,
        "flat": flat if position is not None and reconciliation is not None else None,
    }


def _fault_summary(records: Sequence[Record]) -> dict[str, object]:
    faults = _event_rows(records, "fault")
    return {
        "count": len(faults),
        "messages": [_payload(row).get("message") for row in faults],
    }


def _event_rows(records: Sequence[Record], event_type: str) -> list[Record]:
    return [row for row in records if row.get("event_type") == event_type]


def _latest(records: Sequence[Record], event_type: str) -> Record | None:
    return next(
        (row for row in reversed(records) if row.get("event_type") == event_type), None
    )


def _event_type(record: Record) -> str:
    return _required_text(record.get("event_type"), "event_type")


def _payload(record: Record) -> Mapping[str, object]:
    payload = record.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("live record payload must be an object")
    return payload


def _optional_mapping(value: object) -> Mapping[str, object]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("execution identity must be an object")
    return value


def _optional_mapping_number(
    values: Mapping[str, object],
    key: str,
) -> float | None:
    value = values.get(key)
    return None if value is None else _required_number(value, key)


def _observed_at_ms(record: Record) -> float:
    raw = _required_text(record.get("observed_at_utc"), "observed_at_utc")
    try:
        observed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("observed_at_utc must be ISO-8601") from exc
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("observed_at_utc must be timezone-aware")
    return observed.timestamp() * 1_000.0


def _number(record: Record, key: str) -> float:
    return _required_number(_payload(record).get(key), key)


def _optional_number(record: Record, key: str) -> float | None:
    value = _payload(record).get(key)
    if value is None:
        return None
    return _required_number(value, key)


def _required_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    observed = float(value)
    if observed != observed or observed in {float("inf"), float("-inf")}:
        raise ValueError(f"{name} must be finite")
    return observed


def _positive_number(value: object, name: str) -> float:
    observed = _required_number(value, name)
    if observed <= 0.0:
        raise ValueError(f"{name} must be positive")
    return observed


def _nonnegative_number(value: object, name: str) -> float:
    observed = _required_number(value, name)
    if observed < 0.0:
        raise ValueError(f"{name} must be nonnegative")
    return observed


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value


def _require_single_identity(records: Sequence[Record], key: str) -> None:
    values = {row.get(key) for row in records}
    if len(values) != 1 or None in values:
        raise ValueError(f"Apex MM live run has mixed {key}")
