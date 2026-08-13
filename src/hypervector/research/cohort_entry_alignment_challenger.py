"""Report-only entry-regime threshold comparisons for closed cohort trades."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

from hypervector.research.cohort_live_audit_values import mapping, number, text
from hypervector.research.cohort_trade_performance import build_trade_performance

Record = Mapping[str, object]
_STRUCTURE_THRESHOLDS = (0.0, 0.25, 0.5, 0.75)
_COMPONENT_THRESHOLDS = (-0.5, 0.0, 0.5)


def build_entry_alignment_challenger(
    trades: Sequence[Record],
    thresholds: Sequence[float] = _STRUCTURE_THRESHOLDS,
) -> dict[str, object]:
    """Compare fixed entry-alignment thresholds per provider-symbol mapping."""
    return _build_challenger(
        trades,
        thresholds,
        score_field="structure_support_score",
        threshold_field="minimum_structure_support_score",
        mode="cohort_entry_alignment_threshold_challenger_v1",
        score_label="structure support",
    )


def build_entry_component_alignment_challenger(
    trades: Sequence[Record],
    thresholds: Sequence[float] = _COMPONENT_THRESHOLDS,
) -> dict[str, object]:
    """Compare fixed component-alignment thresholds by exact mapping."""
    return _build_challenger(
        trades,
        thresholds,
        score_field="component_alignment_score",
        threshold_field="minimum_component_alignment_score",
        mode="cohort_entry_component_alignment_threshold_challenger_v1",
        score_label="component alignment",
    )


def _build_challenger(
    trades: Sequence[Record],
    thresholds: Sequence[float],
    *,
    score_field: str,
    threshold_field: str,
    mode: str,
    score_label: str,
) -> dict[str, object]:
    candidates = _validated_thresholds(thresholds)
    grouped: dict[tuple[str, str], list[Record]] = {}
    for trade in trades:
        key = (
            text(trade.get("strategy_id"), "challenger strategy"),
            text(trade.get("symbol"), "challenger symbol"),
        )
        grouped.setdefault(key, []).append(trade)
    return {
        "schema_version": 1,
        "mode": mode,
        "contract": _contract(),
        "thresholds": list(candidates),
        "provider_symbols": [
            _mapping_summary(
                strategy,
                symbol,
                values,
                candidates,
                score_field=score_field,
                threshold_field=threshold_field,
                score_label=score_label,
            )
            for (strategy, symbol), values in sorted(grouped.items())
        ],
        "limitations": _limitations(score_label),
    }


def _validated_thresholds(values: Sequence[float]) -> tuple[float, ...]:
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        for value in values
    ):
        raise ValueError("entry-alignment thresholds must be numeric")
    thresholds = tuple(float(value) for value in values)
    if not thresholds or len(set(thresholds)) != len(thresholds):
        raise ValueError("entry-alignment thresholds must be unique and non-empty")
    if any(
        not math.isfinite(value) or not -1.0 <= value <= 1.0 for value in thresholds
    ):
        raise ValueError("entry-alignment thresholds must be finite within [-1, 1]")
    if tuple(sorted(thresholds)) != thresholds:
        raise ValueError("entry-alignment thresholds must be increasing")
    return thresholds


def _mapping_summary(
    strategy: str,
    symbol: str,
    trades: Sequence[Record],
    thresholds: Sequence[float],
    *,
    score_field: str,
    threshold_field: str,
    score_label: str,
) -> dict[str, object]:
    scored = [
        (trade, _entry_score(trade, score_field, score_label)) for trade in trades
    ]
    observed = [(trade, score) for trade, score in scored if score is not None]
    unavailable = len(scored) - len(observed)
    comparable = [trade for trade, _ in observed]
    return {
        "strategy_id": strategy,
        "symbol": symbol,
        "closed_trades": len(trades),
        "observed_entry_scores": len(observed),
        "unavailable_entry_scores": unavailable,
        "observed_score_minimum": min((score for _, score in observed), default=None),
        "observed_score_maximum": max((score for _, score in observed), default=None),
        "comparable_baseline_performance": _performance(comparable),
        "threshold_results": [
            _threshold_result(observed, threshold, threshold_field)
            for threshold in thresholds
        ],
    }


def _entry_score(trade: Record, score_field: str, score_label: str) -> float | None:
    assessment = mapping(
        trade.get("entry_regime_assessment"), "entry regime assessment"
    )
    value = assessment.get(score_field)
    if value is None:
        return None
    score = number(value, f"entry {score_label} score")
    if not -1.0 <= score <= 1.0:
        raise ValueError(f"entry {score_label} score must be within [-1, 1]")
    return score


def _threshold_result(
    observed: Sequence[tuple[Record, float]],
    threshold: float,
    threshold_field: str,
) -> dict[str, object]:
    admitted = [trade for trade, score in observed if score >= threshold]
    excluded = [trade for trade, score in observed if score < threshold]
    admitted_performance = _performance(admitted)
    excluded_performance = _performance(excluded)
    excluded_pnl = number(excluded_performance.get("net_pnl_usd"), "excluded net PnL")
    return {
        threshold_field: threshold,
        "admitted_performance": admitted_performance,
        "excluded_performance": excluded_performance,
        "net_difference_if_excluded_had_zero_cost_usd": -excluded_pnl,
    }


def _performance(trades: Sequence[Record]) -> dict[str, object]:
    summary = build_trade_performance(trades).get("total")
    return dict(mapping(summary, "entry challenger performance"))


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
    }


def _limitations(score_label: str) -> list[str]:
    limitations = [
        "thresholds compare recorded closed outcomes and are not fitted forecasts",
        "rejected trades are assigned zero hypothetical PnL without portfolio reallocation",
        "overlapping positions and repeated regimes are not statistically independent",
        "small samples cannot establish edge or authorize promotion",
        "the challenger cannot filter, size, route, close, or mutate a live position",
    ]
    if score_label == "component alignment":
        limitations.insert(
            1,
            "historical component direction association was inverse in later windows",
        )
    return limitations
