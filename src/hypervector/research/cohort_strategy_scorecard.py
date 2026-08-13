"""Non-gating historical and forward evidence scorecard for the cohort."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping

from hypervector.live.multi_asset_strategy_evidence import (
    StrategyResearchEvidence,
    strategy_research_evidence,
)

Pair = tuple[str, str]
_HORIZONS = (5, 15, 30, 60)


def build_strategy_scorecard(
    expected: frozenset[Pair],
    readiness_by_pair: Mapping[str, object],
    signal_outcomes: Mapping[str, object],
    *,
    execution_by_pair: Mapping[str, object] | None = None,
    repeatability_by_pair: Mapping[str, object] | None = None,
    execution_scope: str | None = None,
) -> dict[str, object]:
    """Combine bounded research facts without filtering or sizing authority."""
    outcomes = _mapping(
        signal_outcomes.get("by_provider_symbol", {}),
        "scorecard outcomes",
    )
    execution = execution_by_pair or {}
    repeatability = repeatability_by_pair or {}
    scope = _execution_scope(execution, execution_scope)
    expected_keys = {f"{strategy_id}|{symbol}" for strategy_id, symbol in expected}
    unexpected = (set(execution) | set(repeatability)) - expected_keys
    if unexpected:
        raise ValueError(
            "scorecard execution outcomes exceed expected provider coverage"
        )
    records = {
        f"{strategy_id}|{symbol}": _provider_record(
            strategy_id,
            symbol,
            _optional_mapping(readiness_by_pair.get(f"{strategy_id}|{symbol}")),
            _optional_mapping(outcomes.get(f"{strategy_id}|{symbol}")),
            _optional_mapping(execution.get(f"{strategy_id}|{symbol}")),
            _optional_mapping(repeatability.get(f"{strategy_id}|{symbol}")),
            scope,
        )
        for strategy_id, symbol in sorted(expected)
    }
    return {
        "contract": _scorecard_contract(),
        "summary": _scorecard_summary(records),
        "by_provider_symbol": records,
    }


def _scorecard_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "performance_gate": False,
        "balance_gate": False,
        "trade_count_gate": False,
        "automatic_pause": False,
        "automatic_retuning": False,
        "execution_authority": "none",
    }


def _scorecard_summary(
    records: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    assessments = Counter(
        str(record["forward_assessment"]) for record in records.values()
    )
    return {
        "mappings": len(records),
        "mappings_with_live_outcomes": sum(
            bool(record["execution_outcomes_identifiable"])
            for record in records.values()
        ),
        **dict(sorted(assessments.items())),
    }


def _provider_record(
    strategy_id: str,
    symbol: str,
    readiness: Mapping[str, object],
    outcome: Mapping[str, object],
    execution: Mapping[str, object],
    repeatability: Mapping[str, object],
    execution_scope: str | None,
) -> dict[str, object]:
    evidence = strategy_research_evidence(strategy_id, symbol)
    eligible = _optional_integer(
        outcome.get("eligible_evaluations"),
        _optional_integer(readiness.get("eligible"), 0),
    )
    evaluations = _optional_integer(
        outcome.get("evaluations"),
        _optional_integer(readiness.get("count"), 0),
    )
    horizons = _eligible_horizons(outcome)
    assessment = _forward_assessment(eligible, horizons)
    return {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "research_state": evidence.research_state,
        "confidence": evidence.confidence,
        "historical_cadence": evidence.cadence,
        "historical_summary": evidence.summary,
        "evidence_source": evidence.evidence_source,
        "directional_research": _directional_research(evidence),
        "forward_evaluations": evaluations,
        "eligible_signals": eligible,
        "resolved_signal_horizons": len(horizons),
        "forward_assessment": assessment,
        "eligible_signal_horizons": horizons,
        "strategy_edge_identifiable": False,
        **_execution_evidence(execution, execution_scope),
        **_repeatability_evidence(
            repeatability,
            strategy_id=strategy_id,
            symbol=symbol,
            execution=execution,
        ),
        "performance_gate": False,
        "execution_effect": "report_only",
    }


def _repeatability_evidence(
    value: Mapping[str, object],
    *,
    strategy_id: str,
    symbol: str,
    execution: Mapping[str, object],
) -> dict[str, object]:
    if not value:
        return {}
    if not execution:
        raise ValueError("repeatability evidence requires execution outcomes")
    closed = _optional_integer(value.get("closed_trades"), 0)
    execution_closed = _optional_integer(execution.get("closed_trades"), 0)
    net_pnl = _number(value.get("net_pnl_usd"), "repeatability net PnL")
    execution_net = _number(execution.get("net_pnl_usd"), "execution net PnL")
    if (
        value.get("strategy_id") != strategy_id
        or value.get("symbol") != symbol
        or closed != execution_closed
        or abs(net_pnl - execution_net) > 1e-9
        or value.get("profit_forecast") is not None
    ):
        raise ValueError("repeatability evidence disagrees with execution outcomes")
    return {"repeatability_evidence": dict(value)}


def _execution_evidence(
    value: Mapping[str, object], scope: str | None
) -> dict[str, object]:
    if not value:
        return {"execution_outcomes_identifiable": False}
    closed = _optional_integer(value.get("closed_trades"), 0)
    wins = _optional_integer(value.get("wins"), 0)
    losses = _optional_integer(value.get("losses"), 0)
    breakeven = _optional_integer(value.get("breakeven"), 0)
    if closed < 1 or wins + losses + breakeven != closed:
        raise ValueError("scorecard execution outcome counts are inconsistent")
    performance = {
        "closed_trades": closed,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "win_rate_pct": _bounded_percent(value.get("win_rate_pct"), "win rate"),
        "net_pnl_usd": _number(value.get("net_pnl_usd"), "execution net PnL"),
        "entry_margin_used_usd": _positive_number(
            value.get("entry_margin_used_usd"), "execution entry margin"
        ),
        "net_return_on_margin_pct": _number(
            value.get("net_return_on_margin_pct"), "execution net return"
        ),
        "mean_trade_return_on_margin_pct": _number(
            value.get("mean_trade_return_on_margin_pct"), "execution mean return"
        ),
        "profit_factor": _optional_nonnegative_number(value.get("profit_factor")),
        "fees_usd": _nonnegative_number(value.get("fees_usd"), "execution fees"),
        "funding_usd": _number(value.get("funding_usd"), "execution funding"),
    }
    sides = _execution_side_summaries(value, performance)
    return {
        "execution_outcomes_identifiable": True,
        "execution_performance_scope": scope,
        "execution_performance": performance,
        **({"execution_performance_by_side": sides} if sides else {}),
    }


def _execution_side_summaries(
    value: Mapping[str, object],
    total: Mapping[str, object],
) -> dict[str, object]:
    raw = _optional_mapping(value.get("by_side"))
    if not raw:
        return {}
    if not set(raw).issubset({"long", "short"}):
        raise ValueError("scorecard execution sides must be long or short")
    sides = {
        side: _mapping(
            _execution_evidence(_mapping(summary, "execution side summary"), None).get(
                "execution_performance"
            ),
            "projected execution side summary",
        )
        for side, summary in sorted(raw.items())
    }
    _validate_side_aggregate(total, sides)
    return sides


def _validate_side_aggregate(
    total: Mapping[str, object],
    sides: Mapping[str, object],
) -> None:
    count_fields = ("closed_trades", "wins", "losses", "breakeven")
    sum_fields = (
        "net_pnl_usd",
        "entry_margin_used_usd",
        "fees_usd",
        "funding_usd",
    )
    rows = tuple(_mapping(value, "execution side") for value in sides.values())
    counts_match = all(
        sum(_optional_integer(row.get(field), 0) for row in rows)
        == _optional_integer(total.get(field), 0)
        for field in count_fields
    )
    sums_match = all(
        abs(
            sum(_number(row.get(field), field) for row in rows)
            - _number(total.get(field), field)
        )
        <= 1e-9
        for field in sum_fields
    )
    if not counts_match or not sums_match:
        raise ValueError("scorecard side execution outcomes do not sum to pair total")


def _execution_scope(execution: Mapping[str, object], value: str | None) -> str | None:
    if not execution:
        return None
    scope = value or "compatible_profile_history"
    if scope not in {
        "compatible_profile_history",
        "provider_execution_contract_history",
    }:
        raise ValueError("scorecard execution performance scope is unsupported")
    return scope


def _directional_research(
    evidence: StrategyResearchEvidence,
) -> dict[str, object]:
    records = {item.side: item.as_payload() for item in evidence.directional_evidence}
    if len(records) != len(evidence.directional_evidence) or not set(records).issubset(
        {"long", "short"}
    ):
        raise ValueError("directional research must contain unique long/short records")
    return records


def _eligible_horizons(outcome: Mapping[str, object]) -> dict[str, object]:
    classes = _optional_mapping(outcome.get("by_evidence_class"))
    eligible = _optional_mapping(classes.get("eligible_signal"))
    values = _optional_mapping(eligible.get("horizons"))
    return {
        str(minutes): _horizon_record(
            _mapping(values[str(minutes)], "scorecard horizon")
        )
        for minutes in _HORIZONS
        if str(minutes) in values
        and _optional_integer(
            _mapping(values[str(minutes)], "scorecard horizon").get("resolved"),
            0,
        )
        > 0
    }


def _horizon_record(value: Mapping[str, object]) -> dict[str, object]:
    mean = value.get("mean_directional_close_return_bps")
    return {
        "resolved": _optional_integer(value.get("resolved"), 0),
        "independent": _optional_integer(value.get("non_overlapping_resolved"), 0),
        "mean_directional_return_bps": (
            _number(mean, "scorecard mean directional return")
            if mean is not None
            else None
        ),
        "positive_directional_rate": value.get("positive_directional_rate"),
    }


def _forward_assessment(eligible: int, horizons: Mapping[str, object]) -> str:
    if eligible == 0:
        return "no_eligible_signal_evidence"
    means = [
        _number(
            _mapping(value, "scorecard horizon record").get(
                "mean_directional_return_bps"
            ),
            "scorecard mean directional return",
        )
        for value in horizons.values()
        if _mapping(value, "scorecard horizon record").get(
            "mean_directional_return_bps"
        )
        is not None
    ]
    if not means:
        return "eligible_signals_unresolved"
    if all(value <= 0.0 for value in means):
        return "descriptive_adverse_paths"
    if all(value > 0.0 for value in means):
        return "descriptive_favorable_paths"
    return "descriptive_mixed_paths"


def _optional_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _optional_integer(value: object, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("scorecard count must be a non-negative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not result == result or result in {float("inf"), float("-inf")}:
        raise ValueError(f"{label} must be finite")
    return result


def _positive_number(value: object, label: str) -> float:
    result = _number(value, label)
    if result <= 0.0:
        raise ValueError(f"{label} must be positive")
    return result


def _nonnegative_number(value: object, label: str) -> float:
    result = _number(value, label)
    if result < 0.0:
        raise ValueError(f"{label} must be non-negative")
    return result


def _optional_nonnegative_number(value: object) -> float | None:
    if value is None:
        return None
    return _nonnegative_number(value, "execution profit factor")


def _bounded_percent(value: object, label: str) -> float:
    result = _number(value, label)
    if not 0.0 <= result <= 100.0:
        raise ValueError(f"{label} must be in [0, 100]")
    return result
