"""Causal report-only paths for HYPE fresh onsets rejected by V58."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from math import isfinite
from statistics import mean, median

from hypervector.research.cohort_forward_paths import (
    Candle,
    DirectionalPath,
    build_candle_index,
    non_overlapping_paths,
    resolve_directional_path,
    validated_horizons,
)
from hypervector.research.cohort_signal_candidates import (
    SignalCandidate,
    evaluation_candidates,
)

Record = Mapping[str, object]


def build_hype_rejected_onset_context(
    records: Sequence[Record],
    *,
    strategy_id: str,
    symbol: str,
    prospective_start_ms: int,
    horizons_minutes: Sequence[int] = (5, 15, 30, 60),
    estimated_round_trip_friction_bps: float = 13.0,
) -> dict[str, object]:
    """Summarize rejected fresh-onset paths without claiming fills or PnL."""
    strategy = _text(strategy_id, "HYPE strategy id")
    market = _text(symbol, "HYPE symbol")
    start = _nonnegative_int(prospective_start_ms, "HYPE prospective start")
    friction = _nonnegative_float(
        estimated_round_trip_friction_bps, "estimated round-trip friction"
    )
    horizons = validated_horizons(horizons_minutes)
    candidates, _, _ = evaluation_candidates(records)
    target = _target_candidates(candidates, strategy, market, start)
    fresh = tuple(candidate for candidate in target if _fresh_onset(candidate))
    rejected = tuple(candidate for candidate in fresh if not candidate.eligible)
    _validate_rejected(rejected)
    candles = build_candle_index(records).get(market, {})
    horizon_rows = {
        str(horizon): _horizon_summary(rejected, candles, horizon, friction)
        for horizon in horizons
    }
    return _report(strategy, market, start, friction, fresh, rejected, horizon_rows)


def _target_candidates(
    candidates: Sequence[SignalCandidate], strategy: str, symbol: str, start: int
) -> tuple[SignalCandidate, ...]:
    target = [
        candidate
        for candidate in candidates
        if candidate.strategy_id == strategy
        and candidate.symbol == symbol
        and candidate.decision_time_ms >= start
    ]
    return tuple(sorted(target, key=lambda candidate: candidate.decision_time_ms))


def _fresh_onset(candidate: SignalCandidate) -> bool:
    value = candidate.metrics.get("canonical_breakout_onset_fresh")
    if not isinstance(value, bool):
        raise ValueError("HYPE onset freshness telemetry must be boolean")
    return value


def _validate_rejected(candidates: Sequence[SignalCandidate]) -> None:
    for candidate in candidates:
        relation = candidate.metrics.get("breakout_side_relation")
        breakout_side = candidate.metrics.get("breakout_side")
        if relation not in {"aligned", "opposed"}:
            raise ValueError("HYPE fresh onset relation must be aligned or opposed")
        if breakout_side not in {"long", "short"}:
            raise ValueError("HYPE fresh onset breakout side must be long or short")
        if candidate.side not in {"long", "short"}:
            raise ValueError("HYPE rejected onset requires a structural side")
        if not candidate.blockers:
            raise ValueError("HYPE rejected onset requires an explicit blocker")


def _horizon_summary(
    candidates: Sequence[SignalCandidate],
    candles: Mapping[int, Candle],
    horizon: int,
    friction: float,
) -> dict[str, object]:
    outcomes: list[DirectionalPath] = []
    statuses: Counter[str] = Counter()
    for candidate in candidates:
        status, path = resolve_directional_path(
            decision_time_ms=candidate.decision_time_ms,
            available_time_ms=candidate.available_time_ms,
            reference_price=candidate.reference_price,
            side=candidate.side or "",
            candles=candles,
            horizon_minutes=horizon,
        )
        statuses[status] += 1
        if path is not None:
            outcomes.append(path)
    independent = non_overlapping_paths(outcomes, horizon)
    return {
        "resolved": len(outcomes),
        "censored": statuses["censored"],
        "missing_data": statuses["missing_data"],
        **_return_summary(outcomes, friction),
        "independent": _return_summary(independent, friction),
    }


def _return_summary(
    paths: Sequence[DirectionalPath], friction: float
) -> dict[str, object]:
    returns = [path.directional_close_return_bps for path in paths]
    adjusted = [value - friction for value in returns]
    if not returns:
        return _empty_return_summary()
    largest_index = max(range(len(adjusted)), key=adjusted.__getitem__)
    excluding = [
        value for index, value in enumerate(adjusted) if index != largest_index
    ]
    return {
        "observations": len(returns),
        "mean_directional_close_return_bps": mean(returns),
        "median_directional_close_return_bps": median(returns),
        "positive_directional_rate": _rate(value > 0.0 for value in returns),
        "mean_after_estimated_friction_bps": mean(adjusted),
        "median_after_estimated_friction_bps": median(adjusted),
        "cost_clearing_close_rate": _rate(value > 0.0 for value in adjusted),
        "mean_excluding_largest_after_friction_bps": (
            mean(excluding) if excluding else None
        ),
        "mean_favorable_excursion_bps": mean(
            path.favorable_excursion_bps for path in paths
        ),
        "mean_adverse_excursion_bps": mean(
            path.adverse_excursion_bps for path in paths
        ),
    }


def _empty_return_summary() -> dict[str, object]:
    return {
        "observations": 0,
        "mean_directional_close_return_bps": None,
        "median_directional_close_return_bps": None,
        "positive_directional_rate": None,
        "mean_after_estimated_friction_bps": None,
        "median_after_estimated_friction_bps": None,
        "cost_clearing_close_rate": None,
        "mean_excluding_largest_after_friction_bps": None,
        "mean_favorable_excursion_bps": None,
        "mean_adverse_excursion_bps": None,
    }


def _report(
    strategy: str,
    symbol: str,
    start: int,
    friction: float,
    fresh: Sequence[SignalCandidate],
    rejected: Sequence[SignalCandidate],
    horizons: Mapping[str, object],
) -> dict[str, object]:
    relations = Counter(str(row.metrics["breakout_side_relation"]) for row in rejected)
    blockers = Counter(blocker for row in rejected for blocker in row.blockers)
    technical_complete = all(
        isinstance(value, Mapping) and value.get("missing_data") == 0
        for value in horizons.values()
    )
    return {
        "schema_version": 1,
        "mode": "v58_hype_rejected_onset_context",
        "contract": _contract(friction),
        "identity": {
            "strategy_id": strategy,
            "symbol": symbol,
            "prospective_start_ms": start,
        },
        "fresh_onsets": len(fresh),
        "eligible_fresh_onsets": sum(row.eligible for row in fresh),
        "rejected_fresh_onsets": len(rejected),
        "first_decision_time_ms": rejected[0].decision_time_ms if rejected else None,
        "last_decision_time_ms": rejected[-1].decision_time_ms if rejected else None,
        "breakout_side_relations": dict(sorted(relations.items())),
        "blocker_counts": dict(sorted(blockers.items())),
        "horizons": dict(horizons),
        "technical_complete": technical_complete,
        "strategy_change_supported": False,
        "interpretation": "counterfactual_rejected_paths_not_live_fills_or_pnl",
        "limitations": _limitations(),
    }


def _contract(friction: float) -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "orders_supported": False,
        "fills_assumed": False,
        "pnl_claimed": False,
        "runtime_strategy_changed": False,
        "thresholds_selected": False,
        "estimated_round_trip_friction_bps": friction,
    }


def _limitations() -> list[str]:
    return [
        "completed candles cannot establish exact intrabar stop ordering",
        "fixed friction is an estimate rather than exact entry and exit fills",
        "rejected paths do not include exact funding or portfolio occupancy",
        "small correlated onset samples cannot establish a durable edge",
    ]


def _rate(values: Iterable[bool]) -> float:
    observations = tuple(values)
    return sum(observations) / len(observations)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _nonnegative_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not isfinite(result) or result < 0.0:
        raise ValueError(f"{label} must be finite and nonnegative")
    return result
