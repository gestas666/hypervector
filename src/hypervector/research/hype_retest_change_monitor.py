"""Report-only contract monitoring for the HYPE breakout retest revision."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

_CONTROL = "hype_breakout_onset_bidirectional_v1"
_RETEST = "hype_breakout_retest_bidirectional_v2"
_TARGETS = frozenset({_CONTROL, _RETEST})


def build_hype_retest_change_monitor(
    rows: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    """Compare v1 onsets with v2 arm/confirm behavior without execution authority."""
    evaluations = _target_evaluations(rows)
    control = _control_onsets(evaluations)
    armed = _retest_by_state(evaluations, "armed")
    violations = _invariant_violations(evaluations)
    return {
        "status": "technical_fault" if violations else "contract_consistent",
        "execution_authority": "none",
        "control_onsets": len(control),
        "retest_armed": len(armed),
        "retest_confirmed": len(_retest_by_state(evaluations, "confirmed")),
        "retest_expired": len(_retest_by_state(evaluations, "expired")),
        "hard_invariant_violations": violations,
        "matched_onsets": _matched_onsets(control, armed),
    }


def _target_evaluations(
    rows: Iterable[Mapping[str, object]],
) -> tuple[Mapping[str, object], ...]:
    evaluations: list[Mapping[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    for row in rows:
        if row.get("event_type") != "intent_routing":
            continue
        payload = _mapping(row.get("payload"), "intent routing payload")
        for raw in _mappings(payload.get("evaluations"), "evaluations"):
            strategy = raw.get("strategy_id")
            if strategy not in _TARGETS or raw.get("symbol") != "HYPE":
                continue
            identity = _evaluation_identity(raw)
            if identity not in seen:
                evaluations.append(raw)
                seen.add(identity)
    return tuple(evaluations)


def _control_onsets(
    evaluations: tuple[Mapping[str, object], ...],
) -> dict[int, Mapping[str, object]]:
    return {
        _integer(row, "decision_time_ms"): row
        for row in evaluations
        if row.get("strategy_id") == _CONTROL and _metric_flag(row, "breakout_onset")
    }


def _retest_by_state(
    evaluations: tuple[Mapping[str, object], ...], state: str
) -> dict[int, Mapping[str, object]]:
    return {
        _integer(row, "decision_time_ms"): row
        for row in evaluations
        if row.get("strategy_id") == _RETEST
        and _metric_text(row, "entry_policy_state") == state
    }


def _invariant_violations(
    evaluations: tuple[Mapping[str, object], ...],
) -> list[dict[str, object]]:
    violations: list[dict[str, object]] = []
    for row in evaluations:
        if row.get("strategy_id") != _RETEST or row.get("eligible") is not True:
            continue
        side = _text(row, "side")
        breakout_side = _metric_text(row, "breakout_side")
        reasons: list[str] = []
        if _metric_text(row, "entry_policy_state") != "confirmed":
            reasons.append("eligible_without_confirmation")
        if _metric_flag(row, "breakout_onset"):
            reasons.append("eligible_on_immediate_onset")
        side_issue = _entry_side_issue(row, side, breakout_side)
        if side_issue is not None:
            reasons.append(side_issue)
        if reasons:
            violations.append(
                {
                    "decision_time_ms": _integer(row, "decision_time_ms"),
                    "reasons": reasons,
                    "side": side,
                    "breakout_side": breakout_side,
                }
            )
    return violations


def _matched_onsets(
    control: Mapping[int, Mapping[str, object]],
    armed: Mapping[int, Mapping[str, object]],
) -> list[dict[str, object]]:
    return [
        {
            "decision_time_ms": decision_time_ms,
            "v1_side": _text(control[decision_time_ms], "side"),
            "v2_side": _text(armed[decision_time_ms], "side"),
            "breakout_side": _metric_text(armed[decision_time_ms], "breakout_side"),
        }
        for decision_time_ms in sorted(control.keys() & armed.keys())
    ]


def _evaluation_identity(row: Mapping[str, object]) -> tuple[object, ...]:
    metrics = _metrics(row)
    return (
        row.get("strategy_id"),
        row.get("decision_time_ms"),
        row.get("eligible"),
        row.get("side"),
        metrics.get("breakout_onset"),
        metrics.get("breakout_side"),
        metrics.get("entry_policy_state"),
        metrics.get("entry_mode"),
        metrics.get("structural_direction"),
    )


def _entry_side_issue(
    row: Mapping[str, object], side: str, breakout_side: str
) -> str | None:
    metrics = _metrics(row)
    mode = metrics.get("entry_mode")
    structural = metrics.get("structural_direction")
    if mode == "fade" and side == structural and side != breakout_side:
        return None
    if mode == "continuation" and side == structural == breakout_side:
        return None
    if mode not in {None, "fade", "continuation"}:
        return "eligible_entry_mode_invalid"
    if mode is None and side == breakout_side:
        return None
    if mode is None:
        return "eligible_side_opposes_breakout"
    return "eligible_side_violates_entry_mode"


def _metrics(row: Mapping[str, object]) -> Mapping[str, object]:
    readiness = _mapping(row.get("readiness"), "evaluation readiness")
    return _mapping(readiness.get("metrics"), "evaluation readiness metrics")


def _metric_text(row: Mapping[str, object], key: str) -> str:
    return _text(_metrics(row), key)


def _metric_flag(row: Mapping[str, object], key: str) -> bool:
    value = _metrics(row).get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be boolean")
    return value


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return value


def _mappings(value: object, label: str) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return tuple(_mapping(item, f"{label} item") for item in value)


def _text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value.strip()


def _integer(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be a nonnegative integer")
    return value
