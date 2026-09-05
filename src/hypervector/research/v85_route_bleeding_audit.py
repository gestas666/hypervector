"""Immutable-prefix route diagnosis for the seven-asset V85 cohort."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence

from hypervector.research.v85_route_bleeding_execution import (
    closed_lifecycle_missing_fields,
    lifecycle_size_matches,
    submission_reconciliation,
)
from hypervector.research.v85_route_bleeding_prefix import (
    load_frozen_jsonl_prefix as load_frozen_jsonl_prefix,
)

Record = Mapping[str, object]
JsonObject = dict[str, object]
_CLASSIFICATION_ORDER = (
    "technical_fault",
    "negative_signal",
    "exit_leakage",
    "execution_drag",
    "insufficient_evidence",
    "no_observed_issue",
)


def build_route_bleeding_audit(audit: Record, preregistration: Record) -> JsonObject:
    """Classify every frozen V85 route using technical and economic evidence."""
    _validate_authority(preregistration)
    identity = _mapping(
        preregistration.get("frozen_runtime_identity"), "frozen runtime identity"
    )
    run = _mapping(audit.get("run"), "audit run")
    _validate_identity(run, identity)
    contracts = _route_contracts(preregistration)
    _validate_roster(run, preregistration, contracts)
    _validate_route_coverage(audit, contracts)
    prior = _mapping(
        preregistration.get("frozen_prior_route_evidence", {}),
        "frozen prior route evidence",
    )
    hurdle = _number(
        _mapping(preregistration.get("economic_contract"), "economic contract").get(
            "robust_gross_move_hurdle_bps"
        ),
        "robust gross move hurdle",
    )
    routes = {
        route: _route_report(route, contract, audit, prior, hurdle)
        for route, contract in contracts.items()
    }
    disposition = _successor_disposition(routes, contracts)
    return {
        "schema_version": 1,
        "mode": "v85_route_bleeding_audit",
        "contract": _report_contract(),
        "source": {
            "run_id": run.get("run_id"),
            "profile_id": run.get("profile_id"),
            "profile_fingerprint": run.get("profile_fingerprint"),
        },
        "coverage": dict(_mapping(audit.get("coverage"), "audit coverage")),
        "execution_reconciliation": submission_reconciliation(
            _mapping(audit.get("execution"), "execution")
        ),
        "summary": _summary(routes, contracts),
        "routes": routes,
        "successor_disposition": disposition,
        "limitations": _limitations(),
    }


def _validate_authority(preregistration: Record) -> None:
    if preregistration.get("execution_authority") != "none":
        raise ValueError("route audit preregistration must have no execution authority")
    if preregistration.get("automatic_strategy_mutation") is not False:
        raise ValueError("route audit must prohibit automatic strategy mutation")


def _validate_identity(run: Record, identity: Record) -> None:
    for field in ("run_id", "profile_id", "profile_fingerprint"):
        expected = _text(identity.get(field), f"frozen {field}")
        if run.get(field) != expected:
            raise ValueError(f"audit {field.replace('_', ' ')} mismatch")


def _route_contracts(preregistration: Record) -> dict[str, Record]:
    rows = _records(preregistration.get("route_contracts"), "route contracts")
    contracts: dict[str, Record] = {}
    for row in rows:
        route = _route(row.get("route"))
        if route in contracts:
            raise ValueError(f"duplicate route contract: {route}")
        if not isinstance(row.get("execution_authority_in_v85"), bool):
            raise ValueError(f"route execution authority must be boolean: {route}")
        contracts[route] = row
    if not contracts:
        raise ValueError("route audit requires at least one route contract")
    return contracts


def _validate_roster(
    run: Record, preregistration: Record, contracts: Mapping[str, Record]
) -> None:
    roster = _mapping(preregistration.get("roster_contract"), "roster contract")
    expected_assets = set(_texts(roster.get("required_assets"), "required assets"))
    observed_assets = set(_texts(run.get("symbols"), "run symbols"))
    if observed_assets != expected_assets:
        raise ValueError("audit run symbols differ from the frozen roster")
    expected_executable = {
        route
        for route, contract in contracts.items()
        if contract.get("execution_authority_in_v85") is True
    }
    observed_executable = set(
        _texts(run.get("executable_provider_symbols"), "executable routes")
    )
    if observed_executable != expected_executable:
        raise ValueError("audit executable routes differ from frozen route authority")


def _validate_route_coverage(audit: Record, contracts: Mapping[str, Record]) -> None:
    expected = set(contracts)
    sections = (
        ("readiness", "by_provider_symbol"),
        ("strategy_scorecard", "by_provider_symbol"),
    )
    for section_name, rows_name in sections:
        section = _mapping(audit.get(section_name), section_name)
        rows = _mapping(section.get(rows_name), f"{section_name} routes")
        missing = expected.difference(rows)
        if missing:
            raise ValueError(f"missing monitored routes: {', '.join(sorted(missing))}")
    execution = _mapping(audit.get("execution"), "execution")
    parity = _mapping(execution.get("friction_parity"), "friction parity")
    rows = _mapping(parity.get("by_provider_symbol"), "friction parity routes")
    missing = expected.difference(rows)
    if missing:
        raise ValueError(f"missing monitored routes: {', '.join(sorted(missing))}")


def _route_report(
    route: str,
    contract: Record,
    audit: Record,
    prior_by_route: Record,
    hurdle_bps: float,
) -> JsonObject:
    current_trades = _closed_trades(route, audit)
    current = _economics(current_trades)
    prior = _mapping(prior_by_route.get(route, {}), f"prior evidence {route}")
    combined = _combined_economics(current, prior)
    technical = _technical_findings(route, audit, current_trades)
    leakage = _has_exit_leakage(current_trades, hurdle_bps)
    drag = current["gross_pnl_usd"] > 0.0 and current["net_pnl_usd"] <= 0.0
    corroborated = prior.get("corroborated_negative_test") is True
    negative = (
        corroborated and combined["closed_trades"] > 0 and combined["net_pnl_usd"] < 0.0
    )
    classifications = _classifications(
        technical=bool(technical),
        negative=negative,
        leakage=leakage,
        drag=drag,
        robust_positive=prior.get("robust_positive_test") is True,
    )
    scorecard = _mapping(
        _mapping(audit.get("strategy_scorecard"), "strategy scorecard").get(
            "by_provider_symbol"
        ),
        "strategy scorecard routes",
    )
    return {
        "symbol": route.rpartition("|")[2],
        "execution_authority_in_v85": contract.get("execution_authority_in_v85"),
        "directions": list(_texts(contract.get("directions"), "route directions")),
        "classifications": classifications,
        "confidence": _classification_confidence(classifications, combined),
        "technical_findings": technical,
        "current_run_economics": current,
        "combined_exact_live_economics": combined,
        "lifecycle_diagnostics": [_lifecycle_diagnostic(row) for row in current_trades],
        "research_evidence": dict(_mapping(scorecard.get(route), f"scorecard {route}")),
    }


def _closed_trades(route: str, audit: Record) -> list[Record]:
    strategy, _, symbol = route.rpartition("|")
    reflections = _mapping(audit.get("trade_reflections"), "trade reflections")
    return [
        row
        for row in _records(reflections.get("trades", []), "closed reflections")
        if row.get("entry_strategy_id") == strategy and row.get("symbol") == symbol
    ]


def _open_trades(route: str, audit: Record) -> list[Record]:
    strategy, _, symbol = route.rpartition("|")
    reflections = _mapping(audit.get("open_trade_reflections"), "open reflections")
    return [
        row
        for row in _records(reflections.get("trades", []), "open reflections")
        if row.get("strategy_id") == strategy and row.get("symbol") == symbol
    ]


def _economics(trades: Sequence[Record]) -> JsonObject:
    pnl = [_number(row.get("net_pnl_usd"), "trade net PnL") for row in trades]
    fees = [_number(row.get("fees_usd"), "trade fees") for row in trades]
    funding = [_number(row.get("funding_usd"), "trade funding") for row in trades]
    margins = [
        _number(row.get("entry_margin_used_usd"), "entry margin") for row in trades
    ]
    wins = [value for value in pnl if value > 0.0]
    return {
        "closed_trades": len(trades),
        "wins": len(wins),
        "losses": sum(value < 0.0 for value in pnl),
        "breakeven": sum(value == 0.0 for value in pnl),
        "gross_pnl_usd": sum(pnl) + sum(fees) - sum(funding),
        "net_pnl_usd": sum(pnl),
        "fees_usd": sum(fees),
        "funding_usd": sum(funding),
        "entry_margin_used_usd": sum(margins),
        "net_return_on_margin_pct": (
            100.0 * sum(pnl) / sum(margins) if margins else None
        ),
        "net_pnl_excluding_largest_winner_usd": (
            sum(pnl) - max(wins) if wins else None
        ),
        "maximum_drawdown_usd": _maximum_drawdown(pnl),
        "trades_per_24h_observed": _cadence(trades),
        "exit_reasons": dict(
            sorted(Counter(str(row.get("exit_reason")) for row in trades).items())
        ),
        "entry_slippage_bps": _numeric_summary(
            _nested_numbers(trades, "entry", "slippage_bps")
        ),
        "exit_slippage_bps": _numeric_summary(
            _nested_numbers(trades, "exit", "slippage_bps")
        ),
        "maximum_favorable_excursion_bps": _hold_summary(
            trades, "maximum_favorable_excursion_bps"
        ),
        "maximum_adverse_excursion_bps": _hold_summary(
            trades, "maximum_adverse_excursion_bps"
        ),
        "peak_giveback_bps": _hold_summary(trades, "peak_giveback_bps"),
    }


def _combined_economics(current: Record, prior: Record) -> JsonObject:
    exact = _mapping(prior.get("exact_live", {}), "prior exact live evidence")
    fields = ("closed_trades", "wins", "losses", "breakeven")
    counts = {
        field: _optional_integer(exact.get(field), 0)
        + _optional_integer(current.get(field), 0)
        for field in fields
    }
    values = {}
    for field in ("net_pnl_usd", "fees_usd", "funding_usd"):
        values[field] = _optional_number(exact.get(field), 0.0) + _optional_number(
            current.get(field), 0.0
        )
    values["gross_pnl_usd"] = (
        values["net_pnl_usd"] + values["fees_usd"] - values["funding_usd"]
    )
    return counts | values


def _technical_findings(
    route: str, audit: Record, closed_trades: Sequence[Record]
) -> list[str]:
    findings: list[str] = []
    execution = _mapping(audit.get("execution"), "execution")
    parity = _mapping(execution.get("friction_parity"), "friction parity")
    rows = _mapping(parity.get("by_provider_symbol"), "friction parity routes")
    route_parity = _mapping(rows.get(route), f"friction parity {route}")
    mismatches = _texts(route_parity.get("mismatches", []), "friction mismatches")
    findings.extend(f"friction_contract_mismatch:{field}" for field in mismatches)
    for row in _open_trades(route, audit):
        if not isinstance(row.get("protective_stop"), Mapping):
            findings.append("open_lifecycle_missing_protective_stop")
    for row in closed_trades:
        missing = closed_lifecycle_missing_fields(row)
        if missing:
            lifecycle = str(row.get("lifecycle_id", "unknown"))
            findings.append(
                f"closed_lifecycle_incomplete:{lifecycle}:{','.join(missing)}"
            )
        elif not lifecycle_size_matches(row):
            lifecycle = str(row.get("lifecycle_id", "unknown"))
            findings.append(f"closed_lifecycle_size_mismatch:{lifecycle}")
    return sorted(set(findings))


def _has_exit_leakage(trades: Sequence[Record], hurdle_bps: float) -> bool:
    for row in trades:
        hold = row.get("completed_hold_capture")
        if not isinstance(hold, Mapping):
            continue
        mfe = hold.get("maximum_favorable_excursion_bps")
        if _is_number(mfe) and float(mfe) >= hurdle_bps:
            if _number(row.get("net_pnl_usd"), "trade net PnL") < 0.0:
                return True
    return False


def _classifications(
    *, technical: bool, negative: bool, leakage: bool, drag: bool, robust_positive: bool
) -> list[str]:
    if technical:
        return ["technical_fault"]
    values = []
    if negative:
        values.append("negative_signal")
    if leakage:
        values.append("exit_leakage")
    if drag:
        values.append("execution_drag")
    if not values:
        values.append(
            "no_observed_issue" if robust_positive else "insufficient_evidence"
        )
    return [name for name in _CLASSIFICATION_ORDER if name in values]


def _successor_disposition(
    routes: Mapping[str, Record], contracts: Mapping[str, Record]
) -> JsonObject:
    removed = sorted(
        route
        for route, report in routes.items()
        if contracts[route].get("execution_authority_in_v85") is True
        and any(
            item in {"technical_fault", "negative_signal"}
            for item in _texts(report.get("classifications"), "classifications")
        )
    )
    remaining_symbols = {
        route.rpartition("|")[2]
        for route, contract in contracts.items()
        if contract.get("execution_authority_in_v85") is True and route not in removed
    }
    required = sorted(
        {route.rpartition("|")[2] for route in removed} - remaining_symbols
    )
    return {
        "remove_execution_routes": removed,
        "required_same_asset_replacements": required,
        "v86_complete": not required,
        "automatic_live_transition": False,
    }


def _summary(
    routes: Mapping[str, Record], contracts: Mapping[str, Record]
) -> JsonObject:
    def count(label: str) -> int:
        return sum(
            label in _texts(row.get("classifications"), "classifications")
            for row in routes.values()
        )

    return {
        "monitored_routes": len(routes),
        "executable_routes": sum(
            contract.get("execution_authority_in_v85") is True
            for contract in contracts.values()
        ),
        "technical_fault_routes": count("technical_fault"),
        "negative_signal_routes": count("negative_signal"),
        "exit_leakage_routes": count("exit_leakage"),
        "execution_drag_routes": count("execution_drag"),
        "insufficient_evidence_routes": count("insufficient_evidence"),
        "no_observed_issue_routes": count("no_observed_issue"),
    }


def _lifecycle_diagnostic(row: Record) -> JsonObject:
    hold = _mapping(row.get("completed_hold_capture"), "completed hold capture")
    return {
        "lifecycle_id": _text(row.get("lifecycle_id"), "lifecycle id"),
        "side": _text(row.get("side"), "trade side"),
        "exit_reason": _text(row.get("exit_reason"), "exit reason"),
        "net_pnl_usd": _number(row.get("net_pnl_usd"), "trade net PnL"),
        "maximum_favorable_excursion_bps": hold.get("maximum_favorable_excursion_bps"),
        "maximum_adverse_excursion_bps": hold.get("maximum_adverse_excursion_bps"),
        "peak_giveback_bps": hold.get("peak_giveback_bps"),
        "holding_time_ms": row.get("holding_time_ms"),
    }


def _maximum_drawdown(values: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _cadence(trades: Sequence[Record]) -> float | None:
    timestamps = sorted(_nested_numbers(trades, "entry", "venue_timestamp_ms"))
    if len(timestamps) < 2 or timestamps[-1] <= timestamps[0]:
        return None
    span_days = (timestamps[-1] - timestamps[0]) / 86_400_000.0
    return (len(timestamps) - 1) / span_days


def _nested_numbers(rows: Sequence[Record], section: str, field: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        nested = row.get(section)
        if isinstance(nested, Mapping) and _is_number(nested.get(field)):
            values.append(float(nested[field]))
    return values


def _hold_summary(rows: Sequence[Record], field: str) -> JsonObject:
    return _numeric_summary(_nested_numbers(rows, "completed_hold_capture", field))


def _numeric_summary(values: Sequence[float]) -> JsonObject:
    if not values:
        return {"count": 0, "minimum": None, "mean": None, "maximum": None}
    return {
        "count": len(values),
        "minimum": min(values),
        "mean": sum(values) / len(values),
        "maximum": max(values),
    }


def _classification_confidence(classifications: Sequence[str], combined: Record) -> str:
    if "technical_fault" in classifications:
        return "high"
    if "negative_signal" in classifications:
        return (
            "medium"
            if _optional_integer(combined.get("closed_trades"), 0) < 5
            else "high"
        )
    return "low"


def _report_contract() -> JsonObject:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_strategy_mutation": False,
        "runtime_strategy_changed": False,
    }


def _limitations() -> list[str]:
    return [
        "Sparse exact-live samples do not establish future expectancy.",
        "A route-level diagnosis is not a profitability guarantee for a replacement.",
        "Excursion paths use completed candles and cannot recover private queue state.",
        "The report cannot place, cancel, or modify orders or restart the live cohort.",
    ]


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _records(value: object, label: str) -> list[Record]:
    if not isinstance(value, list) or not all(
        isinstance(row, Mapping) for row in value
    ):
        raise ValueError(f"{label} must be a list of objects")
    return value


def _texts(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ValueError(f"{label} must be a list of non-empty strings")
    return tuple(value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _route(value: object) -> str:
    route = _text(value, "route")
    strategy, separator, symbol = route.rpartition("|")
    if not separator or not strategy or not symbol:
        raise ValueError("route must use strategy|symbol identity")
    return route


def _optional_integer(value: object, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("optional count must be a non-negative integer")
    return value


def _number(value: object, label: str) -> float:
    if not _is_number(value):
        raise ValueError(f"{label} must be finite numeric")
    return float(value)


def _optional_number(value: object, default: float) -> float:
    return default if value is None else _number(value, "optional numeric value")


def _is_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    result = float(value)
    return result == result and result not in {float("inf"), float("-inf")}
