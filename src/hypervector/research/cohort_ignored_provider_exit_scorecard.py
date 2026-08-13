"""Portfolio scorecard for provider exits ignored by immutable live policy."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import fmean, median

from hypervector.research.cohort_live_audit_values import (
    mapping,
    nonnegative_int,
    number,
    text,
)

Record = Mapping[str, object]
_MINIMUM_RESOLVED_POLICY_SAMPLE = 5
_EXIT_MODE_OBSERVED = "observed"
_EXIT_MODE_UNAVAILABLE = "unavailable_in_recorded_readiness_metrics"


@dataclass(frozen=True)
class _ExitObservation:
    strategy_id: str
    symbol: str
    exit_mode: str
    exit_mode_status: str
    exit_reason: str
    continuation_bps: float
    ignored_signal_count: int
    maximum_favorable_excursion_bps: float | None
    maximum_adverse_excursion_bps: float | None
    peak_giveback_bps: float | None


def build_ignored_provider_exit_policy_scorecard(
    *,
    closed_trades: Sequence[Record],
    open_trades: Sequence[Record],
) -> dict[str, object]:
    """Summarize resolved and provisional ignored exits without pooling them."""
    resolved = _section(
        closed_trades,
        evidence_key="ignored_provider_exit_outcome",
        path_key="gross_continuation_from_signal_bps",
        trajectory_key="path_from_first_signal_to_actual_exit",
    )
    provisional = _section(
        open_trades,
        evidence_key="ignored_provider_exit_observer",
        path_key="path_since_first_signal",
        trajectory_key="path_since_first_signal",
    )
    resolved_count = int(resolved["observed_ignored_exit_lifecycles"])
    decision = (
        "resolved_exit_evidence_requires_policy_analysis"
        if resolved_count >= _MINIMUM_RESOLVED_POLICY_SAMPLE
        else "insufficient_resolved_exit_evidence"
    )
    return {
        "schema_version": 2,
        "mode": "ignored_provider_exit_policy_scorecard_v2",
        "contract": _contract(),
        "resolved": resolved,
        "provisional_open": provisional,
        "decision": decision,
        "minimum_resolved_lifecycles_for_policy_analysis": (
            _MINIMUM_RESOLVED_POLICY_SAMPLE
        ),
        "limitations": _limitations(),
    }


def _section(
    trades: Sequence[Record],
    *,
    evidence_key: str,
    path_key: str,
    trajectory_key: str,
) -> dict[str, object]:
    rows = tuple(trades)
    observations = tuple(
        observation
        for trade in rows
        if (
            observation := _observation(
                trade,
                evidence_key=evidence_key,
                path_key=path_key,
                trajectory_key=trajectory_key,
            )
        )
        is not None
    )
    return {
        "total_lifecycles": len(rows),
        "observed_ignored_exit_lifecycles": len(observations),
        "without_observed_ignored_exit_lifecycles": len(rows) - len(observations),
        "exit_mode_unavailable_lifecycles": sum(
            row.exit_mode_status == _EXIT_MODE_UNAVAILABLE for row in observations
        ),
        "continuation_bps": _statistics(observations),
        "path_trajectory_bps": _trajectory_statistics(observations),
        "by_provider_exit_mode": _grouped(observations),
    }


def _observation(
    trade: Record,
    *,
    evidence_key: str,
    path_key: str,
    trajectory_key: str,
) -> _ExitObservation | None:
    text(trade.get("lifecycle_id"), "ignored exit lifecycle id")
    symbol = text(trade.get("symbol"), "ignored exit symbol")
    strategy = text(trade.get("strategy_id"), "ignored exit strategy")
    evidence = mapping(trade.get(evidence_key), "ignored exit evidence")
    status = text(evidence.get("status"), "ignored exit status")
    if status != "observed":
        return None
    count = nonnegative_int(evidence.get("ignored_signal_count"), "ignored signals")
    if count < 1:
        raise ValueError("observed ignored exit requires at least one signal")
    signal = mapping(evidence.get("first_signal"), "ignored exit first signal")
    readiness = mapping(signal.get("readiness"), "ignored exit readiness")
    metrics = mapping(readiness.get("metrics"), "ignored exit metrics")
    exit_mode, exit_mode_status = _exit_mode(metrics)
    favorable, adverse, giveback = _trajectory(evidence, trajectory_key)
    return _ExitObservation(
        strategy_id=strategy,
        symbol=symbol,
        exit_mode=exit_mode,
        exit_mode_status=exit_mode_status,
        exit_reason=text(signal.get("exit_reason"), "ignored exit reason"),
        continuation_bps=_continuation(evidence, path_key),
        ignored_signal_count=count,
        maximum_favorable_excursion_bps=favorable,
        maximum_adverse_excursion_bps=adverse,
        peak_giveback_bps=giveback,
    )


def _exit_mode(metrics: Record) -> tuple[str, str]:
    raw = metrics.get("exit_mode")
    if raw is None:
        return "unavailable", _EXIT_MODE_UNAVAILABLE
    return text(raw, "ignored exit mode"), _EXIT_MODE_OBSERVED


def _continuation(evidence: Record, path_key: str) -> float:
    raw = evidence.get(path_key)
    if path_key == "path_since_first_signal":
        raw = mapping(raw, "ignored exit path").get("current_directional_return_bps")
    return number(raw, "ignored exit continuation bps")


def _trajectory(
    evidence: Record,
    trajectory_key: str,
) -> tuple[float | None, float | None, float | None]:
    path = mapping(evidence.get(trajectory_key), "ignored exit trajectory")
    if text(path.get("status"), "ignored exit trajectory status") != "observed":
        return None, None, None
    values = (
        number(
            path.get("maximum_favorable_excursion_bps"),
            "ignored exit maximum favorable excursion",
        ),
        number(
            path.get("maximum_adverse_excursion_bps"),
            "ignored exit maximum adverse excursion",
        ),
        number(path.get("peak_giveback_bps"), "ignored exit peak giveback"),
    )
    if any(value < 0.0 for value in values):
        raise ValueError("ignored exit excursion values must be nonnegative")
    return values


def _statistics(observations: Sequence[_ExitObservation]) -> dict[str, object]:
    return _value_statistics(tuple(row.continuation_bps for row in observations))


def _value_statistics(values: Sequence[float]) -> dict[str, object]:
    return {
        "count": len(values),
        "favorable_count": sum(value > 0.0 for value in values),
        "nonpositive_count": sum(value <= 0.0 for value in values),
        "mean": fmean(values) if values else None,
        "median": median(values) if values else None,
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
        "mean_excluding_largest": (
            fmean(sorted(values)[:-1]) if len(values) > 1 else None
        ),
    }


def _trajectory_statistics(
    observations: Sequence[_ExitObservation],
) -> dict[str, object]:
    observed = tuple(
        row for row in observations if row.maximum_favorable_excursion_bps is not None
    )
    return {
        "observed_lifecycles": len(observed),
        "unavailable_lifecycles": len(observations) - len(observed),
        "maximum_favorable_excursion": _value_statistics(
            tuple(float(row.maximum_favorable_excursion_bps) for row in observed)
        ),
        "maximum_adverse_excursion": _value_statistics(
            tuple(float(row.maximum_adverse_excursion_bps) for row in observed)
        ),
        "peak_giveback": _value_statistics(
            tuple(float(row.peak_giveback_bps) for row in observed)
        ),
    }


def _grouped(observations: Sequence[_ExitObservation]) -> list[dict[str, object]]:
    groups: dict[tuple[str, str, str, str], list[_ExitObservation]] = defaultdict(list)
    for row in observations:
        groups[
            (row.strategy_id, row.exit_mode, row.exit_mode_status, row.exit_reason)
        ].append(row)
    return [
        {
            "strategy_id": key[0],
            "exit_mode": key[1],
            "exit_mode_status": key[2],
            "exit_reason": key[3],
            "lifecycles": len(rows),
            "symbols": sorted({row.symbol for row in rows}),
            "ignored_signal_count": sum(row.ignored_signal_count for row in rows),
            "continuation_bps": _statistics(rows),
            "path_trajectory_bps": _trajectory_statistics(rows),
        }
        for key, rows in sorted(groups.items())
    ]


def _contract() -> dict[str, object]:
    return {
        "automatic_promotion": False,
        "execution_authority": "none",
        "report_only": True,
        "runtime_strategy_changed": False,
    }


def _limitations() -> list[str]:
    return [
        "open paths are provisional and are never pooled with resolved exits",
        "signal prices are not counterfactual venue fills",
        "gross continuation excludes counterfactual fees, funding, and slippage",
        "endpoint continuation cannot represent path excursion or peak giveback",
        "the sample threshold labels research maturity and cannot gate execution",
        "the scorecard cannot honor, ignore, route, close, or promote an exit",
    ]
