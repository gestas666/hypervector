"""Report-only selective allocation comparison from exact live evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

from hypervector.research.cohort_allocation_capacity import (
    allocation_capacity_available,
    build_allocation_capacity,
)

Record = Mapping[str, object]

_TARGET = "hype_breakout_onset_bidirectional_v1|HYPE"
_PINNED = (
    "hulk_expansion_bidirectional_tuned_v2|HYPE",
    "range_onset_bidirectional_v1|HYPE",
)
_CANDIDATE_CAP_USD = 75.0


def allocation_challenger_applicable(risk_utilization: Record) -> bool:
    """Return whether the selective HYPE experiment would change sizing."""
    providers = _mapping(risk_utilization.get("by_provider_symbol"), "provider sizing")
    required = {_TARGET, *_PINNED}
    if not required.issubset(providers):
        return False
    account = _positive(risk_utilization.get("account_value_usd"), "account value")
    target = _mapping(providers.get(_TARGET), "target provider sizing")
    candidate = _candidate_projection(target, account)
    return not _near(
        candidate["planned_notional_usd"],
        target.get("planned_notional_usd"),
    )


def build_allocation_challenger(
    risk_utilization: Record,
    strategy_scorecard: Record,
    *,
    hype_records: Sequence[Record] = (),
    run_id: str | None = None,
) -> dict[str, object]:
    """Compare one selective cap lift without changing runtime authority."""
    _validate_contract(risk_utilization, "risk")
    _validate_contract(strategy_scorecard, "scorecard")
    account = _positive(risk_utilization.get("account_value_usd"), "account value")
    assets = _mapping(risk_utilization.get("by_asset"), "risk assets")
    providers = _mapping(risk_utilization.get("by_provider_symbol"), "provider sizing")
    target = _mapping(providers.get(_TARGET), "target provider sizing")
    for key in _PINNED:
        _mapping(providers.get(key), f"pinned provider sizing {key}")
    candidate = _candidate_projection(target, account)
    current_max = _current_maximum(risk_utilization, assets, providers, account)
    candidate_max = _candidate_maximum(
        risk_utilization, assets, providers, candidate, account
    )
    current = _projection_view(target)
    result: dict[str, object] = {
        "schema_version": 1,
        "mode": "cohort_selective_allocation_challenger_v1",
        "status": "candidate_not_active",
        "contract": _output_contract(),
        "target_provider_symbol": _TARGET,
        "account_value_usd": account,
        "current": current,
        "candidate": {
            **candidate,
            "effective_change": not _near(
                candidate["planned_notional_usd"], current["planned_notional_usd"]
            ),
        },
        "portfolio": _portfolio_view(current_max, candidate_max),
        "required_profile_changes": _profile_changes(providers),
        "execution_sample": _execution_sample(strategy_scorecard),
        "profit_forecast": None,
        "limitations": _limitations(),
    }
    _append_visible_depth_capacity(result, hype_records, run_id, current, candidate)
    return result


def _append_visible_depth_capacity(
    result: dict[str, object],
    hype_records: Sequence[Record],
    run_id: str | None,
    current: Record,
    candidate: Record,
) -> None:
    if run_id is None or not allocation_capacity_available(hype_records, run_id=run_id):
        return
    result["visible_depth_capacity"] = build_allocation_capacity(
        hype_records,
        run_id=run_id,
        current_notional_usd=_positive(
            current.get("planned_notional_usd"), "current planned notional"
        ),
        candidate_notional_usd=_positive(
            candidate.get("planned_notional_usd"), "candidate planned notional"
        ),
    )


def _validate_contract(evidence: Record, label: str) -> None:
    contract = _mapping(evidence.get("contract"), f"{label} contract")
    invalid = (
        contract.get("report_only") is not True
        or contract.get("execution_authority") != "none"
        or contract.get("performance_gate") is not False
        or contract.get("balance_gate") is not False
    )
    if invalid:
        raise ValueError(f"{label} contract is not report-only and ungated")
    for key in ("automatic_sizing_change", "automatic_pause", "automatic_retuning"):
        if contract.get(key) is True:
            raise ValueError(f"{label} contract is not report-only and ungated")


def _candidate_projection(current: Record, account: float) -> dict[str, object]:
    leverage = _positive(current.get("configured_leverage"), "target leverage")
    margin = _fraction(current.get("configured_margin_fraction"), "target margin")
    uncapped = account * margin * leverage
    planned = min(uncapped, _CANDIDATE_CAP_USD)
    return {
        "configured_leverage": leverage,
        "configured_margin_fraction": margin,
        "configured_max_notional_usd": _CANDIDATE_CAP_USD,
        "uncapped_notional_usd": uncapped,
        "planned_notional_usd": planned,
        "planned_margin_usd": planned / leverage,
        "effective_margin_fraction": planned / leverage / account,
        "cap_binding": uncapped > _CANDIDATE_CAP_USD,
    }


def _projection_view(value: Record) -> dict[str, object]:
    keys = (
        "configured_leverage",
        "configured_margin_fraction",
        "configured_max_notional_usd",
        "uncapped_notional_usd",
        "planned_notional_usd",
        "planned_margin_usd",
        "effective_margin_fraction",
        "cap_binding",
    )
    result = {key: value.get(key) for key in keys}
    for key in keys[:-1]:
        _positive(result[key], f"current {key}")
    if not isinstance(result["cap_binding"], bool):
        raise ValueError("current cap_binding must be boolean")
    return result


def _current_maximum(
    risk: Record,
    assets: Record,
    providers: Record,
    account: float,
) -> float:
    calculated = _maximum_margin(risk, assets, providers, None, account)
    summary = _mapping(risk.get("summary"), "risk summary")
    reported = _positive(
        summary.get("maximum_simultaneous_effective_margin_fraction"),
        "reported maximum margin fraction",
    )
    if not _near(calculated, reported):
        raise ValueError("risk maximum margin summary is inconsistent")
    return reported


def _candidate_maximum(
    risk: Record,
    assets: Record,
    providers: Record,
    candidate: Record,
    account: float,
) -> float:
    return _maximum_margin(risk, assets, providers, candidate, account)


def _maximum_margin(
    risk: Record,
    assets: Record,
    providers: Record,
    candidate: Record | None,
    account: float,
) -> float:
    execution_symbols = _execution_symbols(risk, assets, providers)
    margins = {
        symbol: _positive(
            _mapping(row, f"asset {symbol}").get("planned_margin_usd"),
            f"{symbol} margin",
        )
        for symbol, row in assets.items()
        if symbol in execution_symbols
    }
    for provider_rows in _provider_rows(risk, providers):
        for key, raw in provider_rows.items():
            symbol = _provider_symbol(key)
            row = (
                candidate
                if key == _TARGET and candidate is not None
                else _mapping(raw, key)
            )
            margin = _positive(row.get("planned_margin_usd"), f"{key} planned margin")
            margins[symbol] = max(margins.get(symbol, 0.0), margin)
    count = _maximum_positions(risk)
    return sum(sorted(margins.values(), reverse=True)[:count]) / account


def _execution_symbols(
    risk: Record,
    assets: Record,
    providers: Record,
) -> frozenset[str]:
    summary = _mapping(risk.get("summary"), "risk summary")
    explicit_count = summary.get("executable_assets")
    if explicit_count is None:
        return frozenset(str(symbol) for symbol in assets)
    symbols = frozenset(
        _provider_symbol(key)
        for rows in _provider_rows(risk, providers)
        for key in rows
    )
    if isinstance(explicit_count, bool) or not isinstance(explicit_count, int):
        raise ValueError("executable asset count is invalid")
    if explicit_count != len(symbols) or not symbols.issubset(assets):
        raise ValueError("executable asset count is inconsistent")
    return symbols


def _provider_rows(risk: Record, providers: Record) -> tuple[Record, Record]:
    directional = risk.get("by_provider_symbol_side")
    if directional is None:
        return providers, {}
    return providers, _mapping(directional, "provider side sizing")


def _maximum_positions(risk: Record) -> int:
    summary = _mapping(risk.get("summary"), "risk summary")
    value = summary.get("configured_maximum_positions")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("configured maximum positions is invalid")
    return value


def _profile_changes(providers: Record) -> dict[str, object]:
    pins = []
    for key in _PINNED:
        row = _mapping(providers.get(key), f"pinned provider sizing {key}")
        pins.append(
            {
                "provider_symbol": key,
                "margin_fraction": _fraction(
                    row.get("configured_margin_fraction"), key
                ),
                "max_notional_usd": _positive(
                    row.get("configured_max_notional_usd"), key
                ),
            }
        )
    return {
        "asset": "HYPE",
        "candidate_asset_ceiling_usd": _CANDIDATE_CAP_USD,
        "candidate_target_cap_usd": _CANDIDATE_CAP_USD,
        "pinned_provider_symbols": list(_PINNED),
        "pinned_provider_policies": pins,
        "restart_required": True,
    }


def _execution_sample(scorecard: Record) -> dict[str, object]:
    rows = _mapping(scorecard.get("by_provider_symbol"), "scorecard mappings")
    target = _mapping(rows.get(_TARGET), "target scorecard mapping")
    performance = target.get("execution_performance")
    if performance is None:
        return {"status": "no_resolved_execution_sample"}
    result = dict(_mapping(performance, "target execution performance"))
    result["status"] = "resolved_live_sample"
    result["by_side"] = dict(
        _mapping(target.get("execution_performance_by_side"), "target side sample")
    )
    return result


def _portfolio_view(current: float, candidate: float) -> dict[str, float]:
    return {
        "current_maximum_margin_fraction": current,
        "candidate_maximum_margin_fraction": candidate,
        "change_percentage_points": (candidate - current) * 100.0,
    }


def _output_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_sizing_change": False,
        "automatic_promotion": False,
        "performance_gate": False,
        "balance_gate": False,
    }


def _limitations() -> list[str]:
    return [
        "resolved live sample is descriptive and too small for an edge claim",
        "candidate changes exposure only and cannot rescue a weak signal",
        "account value changes effective sizing but never candidate eligibility",
        "activation requires an explicit future configuration change",
    ]


def _provider_symbol(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("provider-symbol key must be text")
    parts = value.split("|")
    if len(parts) not in {2, 3} or not all(part.strip() for part in parts):
        raise ValueError("provider-symbol key is invalid")
    return parts[1]


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _fraction(value: object, label: str) -> float:
    number = _positive(value, label)
    if number > 1.0:
        raise ValueError(f"{label} must not exceed one")
    return number


def _positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{label} must be finite and positive")
    return number


def _near(left: object, right: object) -> bool:
    left_number = _positive(left, "comparison left")
    right_number = _positive(right, "comparison right")
    return math.isclose(left_number, right_number, rel_tol=1e-9, abs_tol=1e-9)
