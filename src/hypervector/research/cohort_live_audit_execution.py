"""Closed-trade attribution for cohort live-run audits."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
import math
from statistics import median

from hypervector.live.multi_asset_cohort_history import fill_payloads
from hypervector.research.cohort_friction_parity import build_friction_parity
from hypervector.research.cohort_live_audit_open import open_position_summary
from hypervector.research.cohort_live_audit_values import (
    event_rows,
    integer,
    mapping,
    mapping_list,
    number,
    object_list,
    payload,
    positive_int,
    run_id,
    text,
)
from hypervector.research.cohort_order_submission_outcomes import (
    build_order_submission_outcomes,
)

Record = Mapping[str, object]

_ATTRIBUTION_PLACEHOLDERS = frozenset({"unattributed", "unknown"})
_ATTRIBUTION_FIELDS = frozenset(
    {"strategy_id", "operation", "exit_controller_id", "exit_reason"}
)


def execution_summary(
    cohort: Sequence[Record],
    current_assets: Mapping[str, Sequence[Record]],
    history_assets: Mapping[str, Sequence[Record]],
    journals: Mapping[str, Mapping[str, object]],
    identity: Record,
) -> dict[str, object]:
    """Aggregate exact live execution, cost, and lifecycle evidence."""
    summaries = _journal_summaries(journals)
    fills = _fill_count(history_assets)
    current_fills = _fill_count(current_assets)
    compatible_run_ids = history_run_ids(history_assets)
    fill_details = _fill_details(
        _projected_fills(cohort, compatible_run_ids), history_assets
    )
    trades = [
        trade
        for journal in journals.values()
        for trade in mapping_list(journal.get("trades"), "journal trades")
    ]
    pnls = [number(trade.get("net_pnl_usd"), "trade net PnL") for trade in trades]
    return _execution_payload(
        cohort,
        current_assets,
        history_assets,
        journals,
        identity,
        summaries,
        fill_details,
        trades,
        pnls,
        fills,
        current_fills,
    )


def history_run_ids(assets: Mapping[str, Sequence[Record]]) -> list[str]:
    """Return compatible run identities in first-observed order."""
    return list(dict.fromkeys(run_id(row) for rows in assets.values() for row in rows))


def numeric_summary(values: Sequence[float]) -> dict[str, object]:
    """Summarize a numeric sequence without inventing missing observations."""
    return {
        "count": len(values),
        "minimum": min(values) if values else None,
        "median": float(median(values)) if values else None,
        "maximum": max(values) if values else None,
        "mean": sum(values) / len(values) if values else None,
    }


def _journal_summaries(
    journals: Mapping[str, Mapping[str, object]],
) -> dict[str, Record]:
    return {
        symbol: mapping(journal.get("summary"), "journal summary")
        for symbol, journal in journals.items()
    }


def _fill_count(assets: Mapping[str, Sequence[Record]]) -> int:
    return sum(
        row.get("event_type") == "fill" for rows in assets.values() for row in rows
    )


def _execution_payload(
    cohort: Sequence[Record],
    current_assets: Mapping[str, Sequence[Record]],
    history_assets: Mapping[str, Sequence[Record]],
    journals: Mapping[str, Mapping[str, object]],
    identity: Record,
    summaries: Mapping[str, Record],
    fill_details: Sequence[Record],
    trades: Sequence[Record],
    pnls: Sequence[float],
    fills: int,
    current_fills: int,
) -> dict[str, object]:
    profits = sum(value for value in pnls if value > 0.0)
    losses = -sum(value for value in pnls if value < 0.0)
    return {
        "scope": "compatible_profile_history",
        "history_run_ids": history_run_ids(history_assets),
        "fills": fills,
        "current_run_fills": current_fills,
        "submission_outcomes": build_order_submission_outcomes(
            history_assets, scope="compatible_profile_history"
        ),
        "current_run_submission_outcomes": build_order_submission_outcomes(
            current_assets, scope="current_run"
        ),
        "projected_fills": len(fill_details),
        "fill_details": list(fill_details),
        "fee_rate_bps": fill_fee_rate_summary(fill_details),
        "friction_parity": build_friction_parity(payload(identity), fill_details),
        "closed_trades": _journal_total(summaries, "closed_trades"),
        "open_lifecycles": _journal_total(summaries, "open_lifecycles"),
        "open_positions": open_position_summary(cohort, journals),
        "wins": sum(value > 0.0 for value in pnls),
        "losses": sum(value < 0.0 for value in pnls),
        "net_pnl_usd": sum(pnls),
        "fees_usd": _journal_number_total(summaries, "fees_usd", "fees"),
        "funding_usd": _journal_number_total(summaries, "funding_usd", "funding"),
        "profit_factor": profits / losses if losses else None,
        "slippage_bps": _fill_metric(fill_details, "slippage_bps", fills),
        "acknowledgement_latency_ms": _fill_metric(
            fill_details, "acknowledgement_latency_ms", fills
        ),
        "markout_bps": _fill_metric(fill_details, "markout_bps", fills),
        "by_asset": dict(summaries),
        "by_strategy_side": strategy_side_summary(trades),
    }


def _journal_total(summaries: Mapping[str, Record], key: str) -> int:
    return sum(integer(row, key) for row in summaries.values())


def _journal_number_total(
    summaries: Mapping[str, Record], key: str, label: str
) -> float:
    return sum(number(row.get(key), label) for row in summaries.values())


def _projected_fills(
    records: Sequence[Record], compatible_run_ids: Collection[str]
) -> list[Record]:
    unique: dict[tuple[str, int], Record] = {}
    for row in event_rows(records, "cohort_snapshot"):
        for fill in object_list(payload(row), "recent_fills"):
            origin_run_id = fill.get("origin_run_id")
            if (
                origin_run_id is not None
                and text(origin_run_id, "fill origin run id") not in compatible_run_ids
            ):
                continue
            symbol = text(fill.get("symbol"), "fill symbol")
            trade_id = positive_int(fill.get("trade_id"), "trade id")
            unique[(symbol, trade_id)] = fill
    return list(unique.values())


def _fill_details(
    projected: Sequence[Record],
    history_assets: Mapping[str, Sequence[Record]],
) -> list[Record]:
    exact = {
        (
            text(fill.get("symbol"), "fill symbol"),
            positive_int(fill.get("trade_id"), "trade id"),
        ): fill
        for symbol, rows in history_assets.items()
        for fill in fill_payloads(symbol, [dict(row) for row in rows])
    }
    projections = {
        (
            text(fill.get("symbol"), "fill symbol"),
            positive_int(fill.get("trade_id"), "trade id"),
        ): fill
        for fill in projected
    }
    output = [
        _merge_fill(projections[identity], exact) if identity in projections else detail
        for identity, detail in exact.items()
    ]
    output.extend(
        dict(fill) for identity, fill in projections.items() if identity not in exact
    )
    return output


def _merge_fill(
    projected: Record,
    exact: Mapping[tuple[str, int], Record],
) -> Record:
    identity = (
        text(projected.get("symbol"), "fill symbol"),
        positive_int(projected.get("trade_id"), "trade id"),
    )
    detail = exact.get(identity)
    if detail is None:
        return dict(projected)
    _validate_fill_identity(projected, detail, identity)
    return {
        **projected,
        **_authoritative_exact_values(projected, detail),
    }


def _authoritative_exact_values(projected: Record, detail: Record) -> dict[str, object]:
    values: dict[str, object] = {}
    for key, value in detail.items():
        if value is None:
            continue
        if key in _ATTRIBUTION_FIELDS and _placeholder_erases_attribution(
            projected.get(key), value
        ):
            continue
        values[key] = value
    return values


def _placeholder_erases_attribution(projected: object, exact: object) -> bool:
    if (
        not isinstance(exact, str)
        or exact.strip().lower() not in _ATTRIBUTION_PLACEHOLDERS
    ):
        return False
    return (
        isinstance(projected, str)
        and bool(projected.strip())
        and projected.strip().lower() not in _ATTRIBUTION_PLACEHOLDERS
    )


def _validate_fill_identity(
    projected: Record,
    exact: Record,
    identity: tuple[str, int],
) -> None:
    """Reject disagreement between backend and authoritative asset fill facts."""
    float_fields = {"price", "size", "fee_usd", "closed_pnl_usd"}
    fields = (
        "oid",
        "venue_timestamp_ms",
        "price",
        "size",
        "side",
        "direction",
        "fee_usd",
        "closed_pnl_usd",
    )
    for key in fields:
        _validate_fill_field(projected, exact, identity, key, float_fields)


def _validate_fill_field(
    projected: Record,
    exact: Record,
    identity: tuple[str, int],
    key: str,
    float_fields: set[str],
) -> None:
    backend_value = projected.get(key)
    asset_value = exact.get(key)
    if backend_value is None or asset_value is None:
        return
    agrees = backend_value == asset_value
    if key in float_fields:
        agrees = math.isclose(
            number(backend_value, key),
            number(asset_value, key),
            rel_tol=1e-12,
            abs_tol=1e-12,
        )
    if not agrees:
        raise ValueError(
            f"fill identity conflicts for {identity[0]} trade {identity[1]} "
            f"field {key}: backend={backend_value!r} asset={asset_value!r}"
        )


def _fill_metric(
    fills: Sequence[Record], key: str, fill_count: int
) -> dict[str, object]:
    values = [
        number(value, key) for fill in fills if (value := fill.get(key)) is not None
    ]
    if fill_count == 0:
        return {"status": "not_applicable_no_fills", **numeric_summary([])}
    status = "observed" if len(values) == fill_count else "incomplete"
    return {"status": status, **numeric_summary(values)}


def fill_fee_rate_summary(fills: Sequence[Record]) -> dict[str, object]:
    """Summarize realized fill fees as basis points of executed notional."""
    rates = [_fill_fee_rate_bps(fill) for fill in fills if _has_fee_terms(fill)]
    status = (
        "not_applicable_no_fills"
        if not fills
        else "observed"
        if len(rates) == len(fills)
        else "incomplete"
    )
    return {
        "status": status,
        "count": len(rates),
        "minimum": min(rates) if rates else None,
        "median": float(median(rates)) if rates else None,
        "maximum": max(rates) if rates else None,
        "mean": sum(rates) / len(rates) if rates else None,
    }


def _has_fee_terms(fill: Record) -> bool:
    return all(fill.get(key) is not None for key in ("fee_usd", "price", "size"))


def _fill_fee_rate_bps(fill: Record) -> float:
    fee = number(fill.get("fee_usd"), "fill fee")
    price = number(fill.get("price"), "fill price")
    size = number(fill.get("size"), "fill size")
    if fee < 0.0 or price <= 0.0 or size <= 0.0:
        raise ValueError("fill fee terms are outside their valid ranges")
    return fee / (price * size) * 10_000.0


def strategy_side_summary(trades: Sequence[Record]) -> dict[str, dict[str, object]]:
    """Aggregate net outcomes by entry provider and position direction."""
    grouped: dict[str, list[Record]] = defaultdict(list)
    for trade in trades:
        direction = text(trade.get("direction"), "trade direction")
        regime = mapping(trade.get("entry_regime"), "entry regime")
        strategy = text(regime.get("strategy_id"), "entry strategy")
        grouped[f"{strategy}|{direction}"].append(trade)
    return {key: trade_group_summary(values) for key, values in sorted(grouped.items())}


def trade_group_summary(trades: Sequence[Record]) -> dict[str, object]:
    """Aggregate exact after-cost outcomes for one lifecycle group."""
    pnls = [number(trade.get("net_pnl_usd"), "trade net PnL") for trade in trades]
    profits = sum(value for value in pnls if value > 0.0)
    losses = -sum(value for value in pnls if value < 0.0)
    return {
        "closed_trades": len(trades),
        "wins": sum(value > 0.0 for value in pnls),
        "losses": sum(value < 0.0 for value in pnls),
        "net_pnl_usd": sum(pnls),
        "fees_usd": sum(
            number(trade.get("fees_usd"), "trade fees") for trade in trades
        ),
        "funding_usd": sum(
            number(trade.get("funding_usd"), "trade funding") for trade in trades
        ),
        "profit_factor": profits / losses if losses else None,
    }
