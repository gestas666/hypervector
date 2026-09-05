"""Cutoff-bound signal evidence from a technically audited observer run."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
import math

Record = Mapping[str, object]
Evaluation = tuple[int, Record]


def build_observer_prospective_window(
    records: Sequence[Record],
    full_audit: Record,
    *,
    start_ms: int,
) -> dict[str, object]:
    """Summarize only decisions at or after an immutable prospective cutoff."""
    _nonnegative_integer(start_ms, "prospective start")
    identity = _audit_identity(full_audit)
    selected = tuple(row for row in records if row.get("run_id") == identity["run_id"])
    evaluations, pre_cutoff, action_count, withheld_count = _window_rows(
        selected, start_ms
    )
    technical = _technical(full_audit, selected, evaluations, identity, action_count)
    signals = _signals(evaluations, action_count, withheld_count)
    return {
        "schema_version": 1,
        "mode": "cohort_observer_prospective_window",
        "contract": _contract(),
        "identity": identity,
        "window": _window(selected, start_ms, pre_cutoff),
        "technical": technical,
        "signals": signals,
        "latest_evaluation": dict(evaluations[-1][1]) if evaluations else None,
        "status": _status(technical, signals),
        "limitations": _limitations(),
    }


def _audit_identity(audit: Record) -> dict[str, str]:
    contract = _mapping(audit.get("observer_contract"), "observer contract")
    required = {
        "report_only": True,
        "execution_authority": "none",
        "orders_observed": False,
        "fills_observed": False,
        "profitability_measured": False,
        "runtime_strategy_changed": False,
    }
    for key, expected in required.items():
        if contract.get(key) != expected:
            raise ValueError(f"observer contract has invalid {key}")
    run = _mapping(audit.get("run"), "observer run")
    return {
        "run_id": _text(run.get("run_id"), "run id"),
        "profile_id": _text(run.get("profile_id"), "profile id"),
        "profile_fingerprint": _text(
            run.get("profile_fingerprint"), "profile fingerprint"
        ),
    }


def _window_rows(
    records: Sequence[Record], start_ms: int
) -> tuple[list[Evaluation], int, int, int]:
    output: list[Evaluation] = []
    pre_cutoff = action_count = withheld_count = 0
    for row in records:
        if row.get("event_type") != "intent_routing":
            continue
        arrival_ms = _timestamp_ms(row.get("observed_at_utc"))
        payload = _mapping(row.get("payload"), "routing payload")
        values = _object_list(payload.get("evaluations"), "routing evaluations")
        for evaluation in values:
            decision_ms = _nonnegative_integer(
                evaluation.get("decision_time_ms"), "decision time"
            )
            if decision_ms < start_ms:
                pre_cutoff += 1
            else:
                output.append((arrival_ms, evaluation))
        if any(_decision_in_window(value, start_ms) for value in values):
            action_count += len(_object_list(payload.get("actions"), "routing actions"))
            withheld_count += len(
                _object_list(payload.get("withheld"), "routing withheld")
            )
    return output, pre_cutoff, action_count, withheld_count


def _technical(
    audit: Record,
    records: Sequence[Record],
    evaluations: Sequence[Evaluation],
    identity: Record,
    action_count: int,
) -> dict[str, object]:
    gaps = _full_run_gaps(audit)
    keys = [_evaluation_key(value) for _, value in evaluations]
    duplicates = len(keys) - len(set(keys))
    future = sum(_decision_ms(value) > arrival for arrival, value in evaluations)
    if duplicates:
        gaps.append("duplicate_evaluation_identity")
    if future:
        gaps.append("future_decision_timestamp")
    if action_count:
        gaps.append("observer_routed_action_present")
    gaps.extend(_identity_gaps(records, identity))
    gaps = sorted(set(gaps))
    return {
        "complete": not gaps,
        "full_run_complete": not _full_run_gaps(audit),
        "technical_gaps": gaps,
        "duplicate_evaluations": duplicates,
        "future_decisions": future,
    }


def _full_run_gaps(audit: Record) -> list[str]:
    technical = _mapping(audit.get("technical"), "full-run technical audit")
    gaps = _text_list(technical.get("technical_gaps"), "full-run technical gaps")
    if technical.get("complete") is not (not gaps):
        raise ValueError("full-run technical completeness contradicts its gaps")
    return [f"full_run:{value}" for value in gaps]


def _identity_gaps(records: Sequence[Record], identity: Record) -> list[str]:
    gaps: list[str] = []
    for row in records:
        if (
            row.get("profile_id") != identity["profile_id"]
            or row.get("profile_fingerprint") != identity["profile_fingerprint"]
        ):
            gaps.append("window_identity_mismatch")
        if (
            row.get("execution_mode") != "observe"
            or row.get("live_armed") is not False
            or row.get("execution_authority") != "none"
        ):
            gaps.append("window_execution_authority_mismatch")
    return gaps


def _signals(
    evaluations: Sequence[Evaluation], action_count: int, withheld_count: int
) -> dict[str, object]:
    values = [value for _, value in evaluations]
    blockers = Counter(
        blocker for value in values for blocker in _evaluation_blockers(value)
    )
    return {
        "evaluations": len(values),
        "eligible_evaluations": sum(value.get("eligible") is True for value in values),
        "routed_actions": action_count,
        "withheld_intents": withheld_count,
        "by_side": _by_side(values),
        "blocker_counts": dict(sorted(blockers.items())),
        "readiness": _readiness_summary(values),
    }


def _readiness_summary(evaluations: Sequence[Record]) -> dict[str, object]:
    """Summarize evaluation proximity without treating polls as setups."""
    if not evaluations:
        return {
            "sampling_basis": "completed_minute_evaluations",
            "independent_setup_count_claimed": False,
            "maximum_fraction": None,
            "evaluations_at_maximum": 0,
            "fraction_distribution": [],
            "latest_at_maximum": None,
        }
    measured = [(value, _readiness_metrics(value)) for value in evaluations]
    maximum = max(metrics[2] for _, metrics in measured)
    maxima = [(value, metrics) for value, metrics in measured if metrics[2] == maximum]
    distribution = Counter(metrics[2] for _, metrics in measured)
    return {
        "sampling_basis": "completed_minute_evaluations",
        "independent_setup_count_claimed": False,
        "maximum_fraction": maximum,
        "evaluations_at_maximum": len(maxima),
        "fraction_distribution": [
            {"readiness_fraction": fraction, "evaluations": count}
            for fraction, count in sorted(distribution.items())
        ],
        "latest_at_maximum": _readiness_record(*maxima[-1]),
    }


def _readiness_metrics(value: Record) -> tuple[int, int, float]:
    readiness = _mapping(value.get("readiness"), "evaluation readiness")
    met = _nonnegative_integer(readiness.get("conditions_met"), "conditions met")
    required = _nonnegative_integer(
        readiness.get("conditions_required"), "conditions required"
    )
    if required == 0 or met > required:
        raise ValueError("readiness condition counts are invalid")
    fraction = readiness.get("readiness_fraction")
    if isinstance(fraction, bool) or not isinstance(fraction, (int, float)):
        raise ValueError("readiness fraction must be numeric")
    measured = float(fraction)
    if not math.isfinite(measured) or abs(measured - met / required) > 1e-9:
        raise ValueError("readiness fraction contradicts condition counts")
    return met, required, measured


def _readiness_record(
    value: Record, metrics: tuple[int, int, float]
) -> dict[str, object]:
    met, required, _ = metrics
    return {
        "decision_time_ms": _decision_ms(value),
        "side": _text(value.get("side"), "evaluation side"),
        "conditions_met": met,
        "conditions_required": required,
        "blockers": list(_evaluation_blockers(value)),
        "reason": _text(value.get("reason"), "evaluation reason"),
    }


def _by_side(evaluations: Sequence[Record]) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = {}
    for value in evaluations:
        side = _text(value.get("side"), "evaluation side")
        counts = output.setdefault(side, {"eligible_evaluations": 0, "evaluations": 0})
        counts["evaluations"] += 1
        counts["eligible_evaluations"] += value.get("eligible") is True
    return dict(sorted(output.items()))


def _window(
    records: Sequence[Record], start_ms: int, pre_cutoff: int
) -> dict[str, object]:
    return {
        "start_ms": start_ms,
        "decision_policy": "decision_time_ms_greater_than_or_equal_to_start_ms",
        "pre_cutoff_evaluations_excluded": pre_cutoff,
        "last_observed_at_utc": records[-1].get("observed_at_utc") if records else None,
    }


def _status(technical: Record, signals: Record) -> str:
    if technical.get("complete") is not True:
        return "technical_evidence_incomplete"
    if signals.get("eligible_evaluations"):
        return "prospective_eligible_signal_observed"
    if signals.get("evaluations"):
        return "prospective_collecting_no_eligible_signal"
    return "prospective_collecting_no_evaluations"


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "orders_supported": False,
        "profitability_measured": False,
        "runtime_strategy_changed": False,
    }


def _limitations() -> list[str]:
    return [
        "pre-cutoff rows establish run health but cannot support forward conclusions",
        "observer evaluations are not orders, fills, or executable PnL",
        "an eligible signal remains diagnostic until a causal costed path resolves",
        "this report cannot route, size, retune, pause, or promote a live strategy",
    ]


def _evaluation_key(value: Record) -> tuple[str, str, int]:
    return (
        _text(value.get("strategy_id"), "evaluation strategy"),
        _text(value.get("symbol"), "evaluation symbol"),
        _decision_ms(value),
    )


def _evaluation_blockers(value: Record) -> tuple[str, ...]:
    readiness = _mapping(value.get("readiness"), "evaluation readiness")
    return tuple(_text_list(readiness.get("blockers"), "readiness blockers"))


def _decision_ms(value: Record) -> int:
    return _nonnegative_integer(value.get("decision_time_ms"), "decision time")


def _decision_in_window(value: Record, start_ms: int) -> bool:
    return _decision_ms(value) >= start_ms


def _timestamp_ms(value: object) -> int:
    text = _text(value, "observed timestamp").replace("Z", "+00:00")
    timestamp = datetime.fromisoformat(text)
    if timestamp.tzinfo is None:
        raise ValueError("observed timestamp must include a timezone")
    return int(timestamp.timestamp() * 1_000)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _object_list(value: object, label: str) -> list[Record]:
    if not isinstance(value, list) or not all(
        isinstance(item, Mapping) for item in value
    ):
        raise ValueError(f"{label} must be a list of objects")
    return list(value)


def _text_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a list of strings")
    return list(value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value
