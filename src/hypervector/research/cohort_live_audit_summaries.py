"""Validated run, runtime, portfolio, and readiness summaries for live audits."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from itertools import pairwise

from hypervector.live.cohort_backup_evidence import validated_prestart_backup_payload
from hypervector.research.cohort_live_audit_execution import numeric_summary
from hypervector.research.cohort_live_audit_values import (
    event_rows,
    executable_provider_pairs,
    expected_provider_pairs,
    fraction,
    mapping,
    nonnegative_int,
    number,
    object_list,
    payload,
    positive_int,
    run_id,
    text,
    text_list,
    timestamp,
)

Record = Mapping[str, object]


def scorecard_pairs(identity: Record) -> frozenset[tuple[str, str]]:
    """Project validated live provider keys into scorecard pair identities."""
    pairs: set[tuple[str, str]] = set()
    for key in expected_provider_pairs(identity):
        strategy_id, separator, symbol = key.rpartition("|")
        if not separator or not strategy_id or not symbol:
            raise ValueError("live provider identity must be strategy|symbol")
        pairs.add((strategy_id, symbol))
    return frozenset(pairs)


def validated_records(records: Sequence[Record], label: str) -> tuple[Record, ...]:
    """Validate a complete, contiguous ledger prefix before audit projection."""
    if not records:
        raise ValueError(f"{label} live audit requires at least one record")
    validated = tuple(records)
    for expected, row in enumerate(validated, start=1):
        if not isinstance(row, Mapping):
            raise ValueError(f"{label} ledger row {expected} must be an object")
        if row.get("sequence") != expected:
            raise ValueError(
                f"{label} ledger sequence must be contiguous at {expected}"
            )
        payload(row)
    return validated


def rebased(records: Sequence[Record]) -> tuple[dict[str, object], ...]:
    """Rebase a selected ledger prefix for the existing journal projector."""
    return tuple(
        {**row, "sequence": sequence} for sequence, row in enumerate(records, 1)
    )


def experiment_contract() -> dict[str, object]:
    """Declare the live audit's immutable report-only authority contract."""
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "performance_gate": False,
        "balance_gate": False,
    }


def run_summary(
    records: Sequence[Record], identity: Record, symbols: tuple[str, ...]
) -> dict[str, object]:
    """Summarize the selected armed run and its executable provider scope."""
    policy = mapping(payload(identity).get("position_policy"), "position policy")
    expected = expected_provider_pairs(identity)
    executable = executable_provider_pairs(identity)
    return {
        "run_id": run_id(identity),
        "profile_id": identity.get("profile_id"),
        "profile_fingerprint": identity.get("profile_fingerprint"),
        "run_fingerprint": identity.get("run_fingerprint"),
        "prestart_backup": validated_prestart_backup_payload(
            payload(identity).get("prestart_backup")
        ),
        "symbols": list(symbols),
        "executable_provider_symbols": sorted(executable),
        "observe_only_provider_symbols": sorted(expected.difference(executable)),
        "maximum_concurrent_positions": positive_int(
            policy.get("maximum_concurrent_positions"), "maximum positions"
        ),
        "row_count": len(records),
        "first_observed_at_utc": records[0].get("observed_at_utc"),
        "last_observed_at_utc": records[-1].get("observed_at_utc"),
    }


def runtime_summary(
    records: Sequence[Record], assets: Mapping[str, Sequence[Record]]
) -> dict[str, object]:
    """Summarize heartbeat cadence and terminal asset stop reasons."""
    heartbeats = event_rows(records, "heartbeat")
    times = [timestamp(row) for row in heartbeats]
    intervals = [(right - left).total_seconds() for left, right in pairwise(times)]
    stops = Counter(
        str(payload(row).get("stop_reason"))
        for rows in assets.values()
        for row in rows
        if row.get("event_type") == "state_transition"
        and payload(row).get("state") == "STOPPED"
    )
    return {
        "poll_cycles": len(heartbeats),
        "duration_seconds": (
            timestamp(records[-1]) - timestamp(records[0])
        ).total_seconds(),
        "poll_interval_seconds": numeric_summary(intervals),
        "stop_reasons": dict(sorted(stops.items())),
    }


def portfolio_summary(records: Sequence[Record]) -> dict[str, object]:
    """Summarize authoritative cohort snapshots without filling absent values."""
    snapshots = [payload(row) for row in event_rows(records, "cohort_snapshot")]
    if not snapshots:
        return {"status": "not_observed"}
    equities = [
        number(row.get("account_value_usd"), "account value") for row in snapshots
    ]
    opens = [
        nonnegative_int(row.get("open_position_count"), "open positions")
        for row in snapshots
    ]
    margins = [
        number(row.get("total_margin_used_usd"), "margin used") for row in snapshots
    ]
    notionals = [
        number(row.get("total_notional_position_usd"), "notional") for row in snapshots
    ]
    return {
        "status": "observed",
        "snapshot_count": len(snapshots),
        "initial_equity_usd": equities[0],
        "final_equity_usd": equities[-1],
        "equity_change_usd": equities[-1] - equities[0],
        "minimum_equity_usd": min(equities),
        "maximum_equity_usd": max(equities),
        "maximum_drawdown_pct": _maximum_drawdown_pct(equities),
        "maximum_open_positions": max(opens),
        "maximum_margin_used_usd": max(margins),
        "maximum_notional_usd": max(notionals),
    }


def readiness_summary(records: Sequence[Record], identity: Record) -> dict[str, object]:
    """Aggregate provider setup diagnostics without interpreting them as probability."""
    evaluations = [
        item
        for row in event_rows(records, "intent_routing")
        for item in object_list(payload(row), "evaluations", required=False)
    ]
    grouped: dict[str, list[Record]] = defaultdict(list)
    for evaluation in evaluations:
        strategy = text(evaluation.get("strategy_id"), "evaluation strategy")
        symbol = text(evaluation.get("symbol"), "evaluation symbol")
        grouped[f"{strategy}|{symbol}"].append(evaluation)
    expected = expected_provider_pairs(identity)
    summaries = {
        key: _provider_summary(values) for key, values in sorted(grouped.items())
    }
    return {
        "evaluations": len(evaluations),
        "expected_provider_symbols": len(expected),
        "observed_provider_symbols": len(grouped),
        "missing_provider_symbols": sorted(expected.difference(grouped)),
        "by_provider_symbol": summaries,
    }


def limitations() -> list[str]:
    """List the audit's non-negotiable interpretation limits."""
    return [
        "setup readiness is prerequisite completion, not win probability",
        "sampled markouts cannot reveal private queue position",
        "one run supplies descriptive evidence rather than a durable edge estimate",
        "the audit cannot mutate strategy state or submit orders",
    ]


def _provider_summary(evaluations: Sequence[Record]) -> dict[str, object]:
    fractions = []
    blockers: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    for evaluation in evaluations:
        readiness = mapping(evaluation.get("readiness"), "readiness")
        fractions.append(fraction(readiness.get("readiness_fraction")))
        blockers.update(text_list(readiness.get("blockers"), "readiness blockers"))
        reasons.update([text(evaluation.get("reason"), "evaluation reason")])
    latest = evaluations[-1]
    latest_readiness = mapping(latest.get("readiness"), "latest readiness")
    backend_reason = latest.get("backend_non_action_reason")
    return {
        "count": len(evaluations),
        "eligible": sum(
            evaluation.get("eligible") is True for evaluation in evaluations
        ),
        "latest_fraction": fractions[-1],
        "maximum_fraction": max(fractions),
        "mean_fraction": sum(fractions) / len(fractions),
        "latest_side": latest_readiness.get("side"),
        "latest_reason": text(latest.get("reason"), "latest evaluation reason"),
        "latest_backend_non_action_reason": (
            None if backend_reason is None else text(backend_reason, "backend reason")
        ),
        "latest_metrics": dict(
            mapping(latest_readiness.get("metrics", {}), "latest readiness metrics")
        ),
        "latest_blockers": text_list(
            latest_readiness.get("blockers"), "latest readiness blockers"
        ),
        "latest_indicators": text_list(
            latest_readiness.get("indicators"), "readiness indicators"
        ),
        "readiness_sampling_basis": "backend_poll_evaluations",
        "blockers": dict(sorted(blockers.items())),
        "blocker_combinations": _blocker_combinations(evaluations),
        "blocker_episode_basis": "maximal_consecutive_identical_blocker_sets",
        "blocker_episode_combinations": _blocker_episode_combinations(evaluations),
        "reasons": dict(sorted(reasons.items())),
    }


def _blocker_combinations(evaluations: Sequence[Record]) -> list[dict[str, object]]:
    """Count canonical simultaneous blocker sets across readiness evaluations."""
    counts: Counter[tuple[str, ...]] = Counter()
    for evaluation in evaluations:
        readiness = mapping(evaluation.get("readiness"), "readiness")
        blockers = text_list(readiness.get("blockers"), "readiness blockers")
        if len(set(blockers)) != len(blockers):
            raise ValueError("readiness blockers must be unique per evaluation")
        counts[tuple(sorted(blockers))] += 1
    return [
        {"blockers": list(blockers), "evaluations": count}
        for blockers, count in sorted(counts.items())
    ]


def _blocker_episode_combinations(
    evaluations: Sequence[Record],
) -> list[dict[str, object]]:
    """Count maximal consecutive blocker states without hiding raw poll rows."""
    rows: Counter[tuple[str, ...]] = Counter()
    episodes: Counter[tuple[str, ...]] = Counter()
    prior: tuple[str, ...] | None = None
    for evaluation in evaluations:
        readiness = mapping(evaluation.get("readiness"), "readiness")
        blockers = tuple(sorted(text_list(readiness.get("blockers"), "blockers")))
        rows[blockers] += 1
        if blockers != prior:
            episodes[blockers] += 1
        prior = blockers
    return [
        {
            "blockers": list(blockers),
            "episodes": episodes[blockers],
            "evaluations": count,
        }
        for blockers, count in sorted(rows.items())
    ]


def _maximum_drawdown_pct(values: Sequence[float]) -> float:
    peak = values[0]
    maximum = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0.0:
            maximum = max(maximum, (peak - value) / peak * 100.0)
    return maximum
