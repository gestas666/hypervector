"""Build compact, fail-closed evidence for the continuous research mandate."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.research.cohort_mandate_execution_outcomes import (
    mandate_order_rejections,
)

Record = Mapping[str, object]

_REPORT_ONLY_CONTRACT = {
    "report_only": True,
    "execution_authority": "none",
    "automatic_live_change": False,
}


def build_mandate_evidence(audit: Record) -> dict[str, object]:
    """Summarize measured mandate evidence without execution authority."""
    return {
        "contract": dict(_REPORT_ONLY_CONTRACT),
        "execution": _execution(audit),
        "trades": _trades(audit),
        "opportunities": _opportunities(audit),
        "portfolio_interactions": _portfolio_interactions(audit),
        "regimes": _regimes(audit),
    }


def _execution(audit: Record) -> dict[str, object]:
    execution = _optional_mapping(audit.get("execution"), "execution")
    routing = _optional_mapping(audit.get("routing"), "routing")
    if execution is None or routing is None:
        return _unavailable("execution_or_routing_unavailable")
    fills = _nonnegative_int(execution.get("fills"), "execution fills")
    friction = _optional_mapping(execution.get("friction_parity"), "friction parity")
    health = _optional_mapping(audit.get("health"), "health")
    actions = _nonnegative_int(routing.get("actions"), "routing actions")
    lifecycle_actions = _nonnegative_int(
        routing.get("lifecycle_actions"), "lifecycle actions"
    )
    withheld = _nonnegative_int(routing.get("withheld"), "withheld intents")
    return {
        "status": "measured_zero_fills" if fills == 0 else "measured",
        "scope": _text(execution.get("scope"), "execution scope"),
        "fills": fills,
        "current_run_fills": _nonnegative_int(
            execution.get("current_run_fills"), "current-run fills"
        ),
        "cycles": _nonnegative_int(routing.get("cycles"), "routing cycles"),
        "strategy_intents": _nonnegative_int(
            routing.get("strategy_intents"), "strategy intents"
        ),
        "actions": actions,
        "lifecycle_actions": lifecycle_actions,
        "withheld": withheld,
        "withheld_reasons": _withheld_reasons(routing, withheld),
        "economics": _execution_economics(execution),
        "fill_quality": _fill_quality(execution),
        "friction_parity": _friction_summary(friction),
        "faults": _optional_nonnegative_int(health, "faults"),
        "order_rejections": mandate_order_rejections(execution, actions),
    }


def _withheld_reasons(routing: Record, expected: int) -> dict[str, int]:
    reasons = _mapping(routing.get("withheld_reasons"), "withheld reasons")
    result = {
        _text(reason, "withheld reason"): _nonnegative_int(count, "withheld reason")
        for reason, count in reasons.items()
    }
    if sum(result.values()) != expected:
        raise ValueError("withheld reason counts disagree")
    return dict(sorted(result.items()))


def _execution_economics(execution: Record) -> dict[str, object]:
    open_count = _nonnegative_int(
        execution.get("open_lifecycles"), "execution open lifecycles"
    )
    open_positions, open_totals = _open_economics(execution, open_count)
    closed_net = _number(execution.get("net_pnl_usd"), "execution net PnL")
    return {
        "closed_trades": _nonnegative_int(
            execution.get("closed_trades"), "execution closed trades"
        ),
        "open_lifecycles": open_count,
        "wins": _nonnegative_int(execution.get("wins"), "execution wins"),
        "losses": _nonnegative_int(execution.get("losses"), "execution losses"),
        "net_pnl_usd": closed_net,
        "fees_usd": _number(execution.get("fees_usd"), "execution fees"),
        "funding_usd": _number(execution.get("funding_usd"), "execution funding"),
        "open_positions": open_positions,
        "open_totals": open_totals,
        "combined_closed_plus_open_marked_pnl_usd": (
            closed_net + open_totals["marked_net_pnl_usd"]
        ),
    }


def _open_economics(
    execution: Record, expected: int
) -> tuple[list[dict[str, object]], dict[str, float]]:
    """Return provisional economics separately from resolved trade totals."""
    raw = execution.get("open_positions")
    rows = [] if raw is None and expected == 0 else _records(raw, "open positions")
    if len(rows) != expected:
        raise ValueError("execution open position count disagrees")
    positions = [_open_position(row) for row in rows]
    fields = (
        "fees_usd",
        "funding_usd",
        "realized_pnl_usd",
        "unrealized_pnl_usd",
        "marked_net_pnl_usd",
        "margin_used_usd",
        "position_value_usd",
    )
    return positions, {
        field: sum(float(row[field]) for row in positions) for field in fields
    }


def _open_position(row: Record) -> dict[str, object]:
    """Validate one backend-authored open position economics row."""
    return {
        "symbol": _text(row.get("symbol"), "open position symbol"),
        "side": _text(row.get("side"), "open position side"),
        "fees_usd": _number(row.get("fees_usd"), "open position fees"),
        "funding_usd": _number(row.get("funding_usd"), "open position funding"),
        "realized_pnl_usd": _number(
            row.get("realized_pnl_usd"), "open position realized PnL"
        ),
        "unrealized_pnl_usd": _number(
            row.get("unrealized_pnl_usd"), "open position unrealized PnL"
        ),
        "marked_net_pnl_usd": _number(
            row.get("active_lifecycle_marked_net_pnl_usd"),
            "open position marked net PnL",
        ),
        "margin_used_usd": _number(row.get("margin_used_usd"), "open position margin"),
        "position_value_usd": _number(
            row.get("position_value_usd"), "open position value"
        ),
    }


def _fill_quality(execution: Record) -> dict[str, object]:
    return {
        key: dict(_mapping(execution.get(key), key.replace("_", " ")))
        for key in ("slippage_bps", "acknowledgement_latency_ms", "markout_bps")
    }


def _friction_summary(friction: Record | None) -> dict[str, object]:
    if friction is None:
        return _unavailable("friction_parity_unavailable")
    return dict(_mapping(friction.get("summary"), "friction parity summary"))


def _trades(audit: Record) -> dict[str, object]:
    closed = _optional_mapping(audit.get("trade_reflections"), "trade reflections")
    if closed is None:
        return _unavailable("trade_reflections_unavailable")
    _validate_report_only(closed, "trade reflections")
    open_rows = _mapping(audit.get("open_trade_reflections"), "open reflections")
    archive = _mapping(audit.get("portfolio_archive"), "portfolio archive")
    _validate_report_only(open_rows, "open trade reflections")
    _validate_report_only(archive, "portfolio archive")
    closed_count = _nonnegative_int(closed.get("closed_trades"), "closed trades")
    open_count = _nonnegative_int(open_rows.get("open_lifecycles"), "open lifecycles")
    _reconcile_trade_counts(audit, closed, open_rows, closed_count, open_count)
    performance = _mapping(closed.get("performance"), "trade performance")
    current = _mapping(performance.get("current_run"), "current-run performance")
    all_live = _mapping(performance.get("all_time_live"), "all-live performance")
    archive_coverage = _mapping(archive.get("coverage"), "archive coverage")
    archive_performance = _mapping(archive.get("performance"), "archive performance")
    return {
        "status": "measured_zero" if closed_count + open_count == 0 else "measured",
        "closed_lifecycles": closed_count,
        "open_lifecycles": open_count,
        "reflection_reconciliation": "exact",
        "current_run": _performance_total(current),
        "compatible_profile": _compatible_profile(closed),
        "accounting_epoch": _accounting_epoch(
            archive, archive_coverage, archive_performance
        ),
        "mixed_contract_all_live": {
            **_performance_total(all_live),
            "comparability": "descriptive_mixed_contracts",
        },
    }


def _reconcile_trade_counts(
    audit: Record,
    closed: Record,
    open_rows: Record,
    closed_count: int,
    open_count: int,
) -> None:
    execution = _optional_mapping(audit.get("execution"), "execution")
    reflected = len(_records(closed.get("trades"), "closed trade rows"))
    reflected_open = len(_records(open_rows.get("trades"), "open trade rows"))
    execution_closed = (
        closed_count
        if execution is None
        else _nonnegative_int(execution.get("closed_trades"), "execution closed trades")
    )
    execution_open = (
        open_count
        if execution is None
        else _nonnegative_int(
            execution.get("open_lifecycles"), "execution open lifecycles"
        )
    )
    if len({closed_count, reflected, execution_closed}) != 1:
        raise ValueError("closed lifecycle counts disagree")
    if len({open_count, reflected_open, execution_open}) != 1:
        raise ValueError("open lifecycle counts disagree")


def _performance_total(container: Record) -> dict[str, object]:
    total = _mapping(container.get("total"), "performance total")
    return _performance_fields(total)


def _compatible_profile(closed: Record) -> dict[str, object]:
    performance = _mapping(closed.get("performance"), "trade performance")
    total = performance.get("total")
    if total is None:
        current = _mapping(performance.get("current_run"), "current-run performance")
        return _performance_total(current)
    return _performance_fields(_mapping(total, "compatible performance total"))


def _accounting_epoch(
    archive: Record,
    coverage: Record,
    performance: Record,
) -> dict[str, object]:
    total = _mapping(performance.get("total"), "archive performance total")
    epoch = _optional_mapping(archive.get("accounting_epoch"), "accounting epoch")
    result = _performance_fields(total)
    result["closed_orders"] = _nonnegative_int(
        coverage.get("closed_orders"), "archive closed orders"
    )
    result["epoch_id"] = None if epoch is None else epoch.get("epoch_id")
    return result


def _performance_fields(total: Record) -> dict[str, object]:
    return {
        "closed_trades": _nonnegative_int(total.get("closed_trades"), "closed trades"),
        "wins": _nonnegative_int(total.get("wins"), "wins"),
        "losses": _nonnegative_int(total.get("losses"), "losses"),
        "breakeven": _nonnegative_int(total.get("breakeven"), "breakeven"),
        "net_pnl_usd": _number(total.get("net_pnl_usd"), "net PnL"),
    }


def _opportunities(audit: Record) -> dict[str, object]:
    outcomes = _optional_mapping(audit.get("signal_outcomes"), "signal outcomes")
    orderbook = _optional_mapping(audit.get("orderbook_opportunity"), "orderbook")
    if outcomes is None or orderbook is None:
        return _unavailable("signal_or_orderbook_opportunity_unavailable")
    _validate_signal_contract(outcomes)
    _validate_report_only(orderbook, "orderbook opportunity")
    eligible = _nonnegative_int(
        outcomes.get("eligible_evaluations"), "eligible signals"
    )
    coverage = _mapping(orderbook.get("coverage"), "orderbook coverage")
    outcome_coverage = _mapping(outcomes.get("coverage"), "signal coverage")
    return {
        "status": "measured_no_eligible_signals" if eligible == 0 else "measured",
        "provider_evaluations": _nonnegative_int(
            outcomes.get("evaluations"), "provider evaluations"
        ),
        "directional_evaluations": _nonnegative_int(
            outcomes.get("directional_evaluations"), "directional evaluations"
        ),
        "eligible_evaluations": eligible,
        "direction_conflicts": _nonnegative_int(
            outcomes.get("direction_conflicts"), "direction conflicts"
        ),
        "right_censored_observations": _nonnegative_int(
            outcome_coverage.get("right_censored_observations"), "right censored"
        ),
        "exact_one_blocker_candidates": _coverage_count(
            coverage, "exact_one_blocker_candidates"
        ),
        "book_matched_candidates": _coverage_count(coverage, "book_matched"),
        "book_missing_candidates": _coverage_count(coverage, "book_missing"),
        "book_stale_candidates": _coverage_count(coverage, "book_stale"),
        "missed_trade_claimed": False,
        "rejected_order_claimed": False,
    }


def _portfolio_interactions(audit: Record) -> dict[str, object]:
    portfolio = _optional_mapping(audit.get("portfolio"), "portfolio")
    risk = _optional_mapping(audit.get("risk_utilization"), "risk utilization")
    if portfolio is None or risk is None:
        return _unavailable("portfolio_or_risk_utilization_unavailable")
    _validate_report_only(risk, "risk utilization")
    by_asset = _mapping(risk.get("by_asset"), "risk by asset")
    summary = _mapping(risk.get("summary"), "risk summary")
    planned = _planned_portfolio(by_asset, summary)
    maximum_open = _nonnegative_int(
        portfolio.get("maximum_open_positions"), "maximum open positions"
    )
    return {
        "status": "measured_flat" if maximum_open == 0 else "measured",
        "realized": {
            "maximum_open_positions": maximum_open,
            "maximum_margin_used_usd": _number(
                portfolio.get("maximum_margin_used_usd"), "maximum margin"
            ),
            "maximum_notional_usd": _number(
                portfolio.get("maximum_notional_usd"), "maximum notional"
            ),
            "maximum_drawdown_pct": _number(
                portfolio.get("maximum_drawdown_pct"), "maximum drawdown"
            ),
            "snapshot_count": _nonnegative_int(
                portfolio.get("snapshot_count"), "portfolio snapshots"
            ),
        },
        "planned": planned,
        "correlation_evidence": {"status": "unavailable_no_overlap_projection"},
    }


def _planned_portfolio(by_asset: Record, summary: Record) -> dict[str, object]:
    margins = [
        _number(
            _mapping(row, f"risk asset {symbol}").get("planned_margin_usd"), "margin"
        )
        for symbol, row in by_asset.items()
    ]
    notionals = [
        _number(
            _mapping(row, f"risk asset {symbol}").get("planned_notional_usd"),
            "notional",
        )
        for symbol, row in by_asset.items()
    ]
    margin = sum(margins)
    configured = _nonnegative_int(summary.get("configured_assets"), "configured assets")
    maximum = _nonnegative_int(
        summary.get("configured_maximum_positions"), "maximum positions"
    )
    return {
        "configured_assets": configured,
        "configured_maximum_positions": maximum,
        "practical_asset_slots": min(configured, maximum),
        "planned_margin_usd": margin,
        "planned_notional_usd": sum(notionals),
        "maximum_simultaneous_effective_margin_fraction": _number(
            summary.get("maximum_simultaneous_effective_margin_fraction"),
            "maximum margin fraction",
        ),
        "largest_margin_share": 0.0
        if margin == 0.0
        else max(margins, default=0.0) / margin,
        "cap_bound_assets": _nonnegative_int(
            summary.get("cap_bound_assets"), "cap-bound assets"
        ),
    }


def _regimes(audit: Record) -> dict[str, object]:
    regime = _optional_mapping(audit.get("canonical_regime_telemetry"), "regime")
    if regime is None:
        return _unavailable("canonical_regime_telemetry_unavailable")
    contract = _mapping(regime.get("contract"), "regime contract")
    if (
        contract.get("execution_authority") != "none"
        or contract.get("intents_emitted") is not False
    ):
        raise ValueError("canonical regime telemetry is not report-only")
    by_symbol = _mapping(regime.get("by_symbol"), "regime symbols")
    return {
        "status": "measured",
        "evaluations": _nonnegative_int(
            regime.get("evaluations"), "regime evaluations"
        ),
        "dedicated_symbols": sorted(
            _text(symbol, "regime symbol") for symbol in by_symbol
        ),
        "coverage_scope": "dedicated_canonical_stream_only",
    }


def _validate_report_only(container: Record, label: str) -> None:
    contract = _mapping(container.get("contract"), f"{label} contract")
    if (
        contract.get("report_only") is not True
        or contract.get("execution_authority") != "none"
    ):
        raise ValueError(f"{label} is not report-only")
    if contract.get("runtime_strategy_changed") not in {None, False}:
        raise ValueError(f"{label} reports a runtime strategy change")


def _validate_signal_contract(outcomes: Record) -> None:
    contract = _mapping(outcomes.get("contract"), "signal outcome contract")
    expected = {
        "counterfactual_only": True,
        "execution_authority": "none",
        "fills_assumed": False,
        "pnl_claimed": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("signal outcomes are not report-only")


def _unavailable(reason: str) -> dict[str, object]:
    return {"status": "unavailable", "reason": reason}


def _coverage_count(coverage: Record, key: str) -> int:
    return _nonnegative_int(coverage.get(key), key.replace("_", " "))


def _optional_nonnegative_int(source: Record | None, key: str) -> int | None:
    return (
        None
        if source is None or source.get(key) is None
        else _nonnegative_int(source.get(key), key)
    )


def _optional_mapping(value: object, label: str) -> Record | None:
    return None if value is None else _mapping(value, label)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _records(value: object, label: str) -> list[Record]:
    if not isinstance(value, list) or any(
        not isinstance(row, Mapping) for row in value
    ):
        raise ValueError(f"{label} must be an array of objects")
    return list(value)


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        raise ValueError(f"{label} must be finite")
    return number


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be non-empty text")
    return value
