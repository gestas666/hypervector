"""Hash-chained material-change history for cohort improvement research."""

from __future__ import annotations

from collections.abc import Mapping
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import TextIO

from hypervector.research.cohort_active_route_lifecycle_status import (
    normalize_active_route_lifecycle_statuses,
)

Record = Mapping[str, object]


def material_state_payload(report: Record) -> dict[str, object]:
    """Return the canonical material report state used for durable hashing."""
    material = json.loads(json.dumps(report))
    if not isinstance(material, dict):
        raise ValueError("material report must serialize to an object")
    for field in (
        "generated_at_utc",
        "source_checkpoint_generated_at_utc",
        "material_state_sha256",
        "evidence",
    ):
        material.pop(field, None)
    _normalize_ephemeral_state(material)
    return material


def material_state_sha256(report: Record) -> str:
    """Hash the canonical material report state."""
    return _hash_payload(material_state_payload(report))


def append_material_report(path: Path, report: Record) -> bool:
    """Append one new report state; return false when material state is unchanged."""
    material_hash = _digest_text(
        report.get("material_state_sha256"), "material state hash"
    )
    payload = material_state_payload(report)
    if _hash_payload(payload) != material_hash:
        raise ValueError("report material payload hash does not match declared state")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            prior = _read_events(stream)
            if prior and _is_same_reconstructible_state(prior[-1], material_hash):
                return False
            event = _event(report, payload, material_hash, prior)
            stream.seek(0, 2)
            stream.write(
                json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
            )
            stream.flush()
            os.fsync(stream.fileno())
            return True
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _is_same_reconstructible_state(event: Record, material_hash: str) -> bool:
    return (
        event.get("schema_version") == 2
        and event.get("material_state_sha256") == material_hash
        and isinstance(event.get("material_payload"), Mapping)
    )


def _read_events(stream: TextIO) -> list[dict[str, object]]:
    stream.seek(0)
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(stream, 1):
        if not line.strip():
            raise ValueError(f"history event {line_number} is blank")
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"history event {line_number} is invalid JSON") from exc
        if not isinstance(value, dict):
            raise ValueError(f"history event {line_number} must be an object")
        try:
            _validate_event(value, line_number, rows)
        except ValueError as exc:
            raise ValueError(f"history event {line_number} is invalid: {exc}") from exc
        rows.append(value)
    return rows


def _validate_event(
    event: dict[str, object],
    line_number: int,
    prior: list[dict[str, object]],
) -> None:
    if event.get("sequence") != line_number:
        raise ValueError(f"history event {line_number} sequence is invalid")
    previous = prior[-1]["event_sha256"] if prior else None
    if event.get("previous_event_sha256") != previous:
        raise ValueError(f"history event {line_number} chain is invalid")
    _digest_text(event.get("material_state_sha256"), "material state hash")
    if event.get("schema_version") == 2:
        _validate_material_payload(event, prior)
    elif event.get("schema_version") != 1:
        raise ValueError(f"history event {line_number} schema is invalid")
    expected = _event_hash(event)
    if event.get("event_sha256") != expected:
        raise ValueError(f"history event {line_number} hash is invalid")


def _event(
    report: Record,
    payload: dict[str, object],
    material_hash: str,
    prior: list[dict[str, object]],
) -> dict[str, object]:
    event = {
        "schema_version": 2,
        "sequence": len(prior) + 1,
        "recorded_at_utc": _text(report.get("generated_at_utc"), "report time"),
        "previous_event_sha256": prior[-1]["event_sha256"] if prior else None,
        "material_state_sha256": material_hash,
        "material_payload": payload,
        "changed_paths": _changed_paths(_prior_payload(prior), payload),
        "source": _mapping(report.get("source"), "report source"),
        "operational_assessment": _mapping(
            report.get("operational_assessment"), "operational assessment"
        ),
        "highest_value_next_investigation": report.get(
            "highest_value_next_investigation"
        ),
        "hypothesis_ledger": _list(
            report.get("hypothesis_ledger"), "hypothesis ledger"
        ),
        "change_proposals": _list(report.get("change_proposals"), "change proposals"),
        "contract": _mapping(report.get("contract"), "report contract"),
    }
    event["event_sha256"] = _event_hash(event)
    return event


def _validate_material_payload(
    event: dict[str, object], prior: list[dict[str, object]]
) -> None:
    payload = _mapping(event.get("material_payload"), "material payload")
    actual = _hash_payload(payload)
    if event.get("material_state_sha256") != actual:
        raise ValueError("material payload hash is invalid")
    changed = _string_list(event.get("changed_paths"), "changed paths")
    expected = _changed_paths(_prior_payload(prior), payload)
    if changed != expected:
        raise ValueError("material changed paths are invalid")


def _prior_payload(prior: list[dict[str, object]]) -> Record | None:
    if not prior or prior[-1].get("schema_version") != 2:
        return None
    return _mapping(prior[-1].get("material_payload"), "prior material payload")


def _changed_paths(previous: Record | None, current: Record) -> list[str]:
    if previous is None:
        return ["$"]
    output: list[str] = []
    _collect_changed_paths(previous, current, "$", output)
    return output


def _collect_changed_paths(
    previous: object,
    current: object,
    path: str,
    output: list[str],
) -> None:
    if isinstance(previous, Mapping) and isinstance(current, Mapping):
        for key in sorted(set(previous) | set(current)):
            child = f"{path}.{key}"
            if key not in previous or key not in current:
                output.append(child)
            else:
                _collect_changed_paths(previous[key], current[key], child, output)
        return
    if isinstance(previous, list) and isinstance(current, list):
        if len(previous) != len(current):
            output.append(path)
            return
        for index, (left, right) in enumerate(zip(previous, current, strict=True)):
            _collect_changed_paths(left, right, f"{path}[{index}]", output)
        return
    if previous != current:
        output.append(path)


def _normalize_ephemeral_state(material: dict[str, object]) -> None:
    source = material.get("source")
    if isinstance(source, dict):
        source.pop("last_observed_at_utc", None)
    operational = material.get("operational_assessment")
    if isinstance(operational, dict):
        operational.pop("heartbeat_age_seconds", None)
    evidence_health = material.get("evidence_health")
    if isinstance(evidence_health, dict):
        evidence_health.pop("right_censored_observations", None)
        evidence_health.pop("metric_value_gaps", None)
    _normalize_live_diagnostics(material.get("live_opportunity_diagnostics"))
    _normalize_execution_diagnostics(material.get("execution_diagnostics"))
    _normalize_external_asset_pipeline(material.get("external_asset_pipeline"))
    _normalize_hype_native(material.get("hype_native_prospective_lifecycle"))
    normalize_active_route_lifecycle_statuses(
        material.get("active_hypothesis_lifecycle_statuses")
    )
    _normalize_cadence_review_clock(material.get("cadence_review_clock"))
    _normalize_route_cadence_review_clocks(material.get("route_cadence_review_clocks"))
    _normalize_mandate_evidence(material.get("mandate_evidence"))
    _normalize_performance(material.get("performance"))
    _normalize_index_signal_capture(material.get("index_signal_capture"))
    _normalize_prospective_rows(material.get("prospective_experiment_evidence"))
    _normalize_queue_observers(material.get("experiment_queue"))
    _normalize_queue_observers(material.get("hypothesis_ledger"))


def _normalize_cadence_review_clock(value: object) -> None:
    _pop_fields(value, ("elapsed_seconds", "remaining_seconds"))


def _normalize_route_cadence_review_clocks(value: object) -> None:
    if not isinstance(value, dict):
        return
    for clock in value.values():
        _normalize_cadence_review_clock(clock)


def _normalize_index_signal_capture(value: object) -> None:
    if not isinstance(value, dict):
        return
    for field in (
        "common_watermark_ms",
        "expected_decisions_total",
        "observed_decisions_total",
        "age_seconds_by_symbol",
        "cursor_skew_boundaries",
    ):
        value.pop(field, None)


def _normalize_execution_diagnostics(value: object) -> None:
    if not isinstance(value, dict):
        return
    entry = value.get("entry_age")
    if not isinstance(entry, dict):
        return
    for field in ("paired_cycles", "evaluations"):
        entry.pop(field, None)
    routes = entry.get("by_provider_symbol")
    if isinstance(routes, dict):
        for route in routes.values():
            if isinstance(route, dict):
                route.pop("evaluations", None)


def _normalize_external_asset_pipeline(value: object) -> None:
    if not isinstance(value, dict):
        return
    value.pop("observed_at_utc", None)
    candidates = value.get("candidates")
    if not isinstance(candidates, list):
        return
    for candidate in candidates:
        if isinstance(candidate, dict):
            _normalize_external_observer(candidate.get("observer"))


def _normalize_external_observer(value: object) -> None:
    if not isinstance(value, dict):
        return
    for field in (
        "observed_at_utc",
        "age_seconds",
        "decisions_published",
        "decision_rows_total",
        "non_action_decisions_total",
        "prospective_candle_rows_total",
        "latest_trailing_return_bps",
        "latest_shock_threshold_bps",
        "latest_threshold_fraction",
    ):
        value.pop(field, None)


def _normalize_hype_native(value: object) -> None:
    if not isinstance(value, dict):
        return
    for field in ("observed_at_utc", "age_seconds"):
        value.pop(field, None)
    current = value.get("current_open_lifecycle")
    if not isinstance(current, dict):
        return
    for field in (
        "current_book_time_ms",
        "current_exit_price",
        "current_gross_return_bps",
        "current_modeled_net_usd_excluding_funding",
        "maximum_favorable_excursion_bps",
        "maximum_adverse_excursion_bps",
        "maximum_book_gap_ms",
        "peak_giveback_bps",
    ):
        current.pop(field, None)


def _normalize_mandate_evidence(value: object) -> None:
    if not isinstance(value, dict):
        return
    _pop_fields(value.get("execution"), ("cycles",))
    _pop_fields(
        value.get("opportunities"),
        (
            "provider_evaluations",
            "directional_evaluations",
            "right_censored_observations",
            "exact_one_blocker_candidates",
            "book_matched_candidates",
            "book_missing_candidates",
            "book_stale_candidates",
        ),
    )
    _pop_fields(value.get("regimes"), ("evaluations",))
    portfolio = value.get("portfolio_interactions")
    if isinstance(portfolio, dict):
        _pop_fields(portfolio.get("realized"), ("snapshot_count",))
        _pop_fields(
            portfolio.get("planned"),
            (
                "planned_margin_usd",
                "planned_notional_usd",
                "maximum_simultaneous_effective_margin_fraction",
                "largest_margin_share",
            ),
        )


def _normalize_performance(value: object) -> None:
    _pop_fields(value, ("equity_usd",))


def _pop_fields(value: object, fields: tuple[str, ...]) -> None:
    if isinstance(value, dict):
        for field in fields:
            value.pop(field, None)


def _normalize_queue_observers(value: object) -> None:
    if not isinstance(value, list):
        return
    for row in value:
        if isinstance(row, dict):
            _normalize_prospective(row.get("prospective_observation"))


def _normalize_prospective_rows(value: object) -> None:
    if not isinstance(value, list):
        return
    for row in value:
        _normalize_prospective(row)


def _normalize_prospective(value: object) -> None:
    if isinstance(value, dict):
        value.pop("observed_at_utc", None)
        value.pop("raw_exact_evaluations", None)


def _normalize_live_diagnostics(value: object) -> None:
    if not isinstance(value, dict):
        return
    _remove_window_progress(value.get("observation_window"))
    _remove_total_progress(value.get("totals"))
    routes = value.get("routes")
    if isinstance(routes, list):
        for route in routes:
            _normalize_live_route(route)
    leads = value.get("robust_report_only_leads")
    if isinstance(leads, list):
        for lead in leads:
            _normalize_path_material(lead)


def _remove_window_progress(value: object) -> None:
    if isinstance(value, dict):
        value.pop("end_utc", None)
        value.pop("duration_seconds", None)


def _remove_total_progress(value: object) -> None:
    if isinstance(value, dict):
        value.pop("evaluations", None)
        value.pop("directional_evaluations", None)
        value.pop("right_censored_observations", None)


def _normalize_live_route(value: object) -> None:
    if not isinstance(value, dict):
        return
    _normalize_decision_side_coverage(value.get("decision_side_coverage"))
    for field in (
        "outcome_evaluations",
        "readiness_evaluations",
        "latest_readiness_fraction",
        "latest_blockers",
        "blocker_counts",
    ):
        value.pop(field, None)
    paths = value.get("one_blocker_paths")
    if isinstance(paths, list):
        for path in paths:
            _normalize_path_material(path)
    combinations = value.get("blocker_combinations")
    if isinstance(combinations, list):
        for combination in combinations:
            _pop_fields(combination, ("evaluations",))
    episodes = value.get("blocker_episode_combinations")
    if isinstance(episodes, list):
        for episode in episodes:
            _pop_fields(episode, ("evaluations",))


def _normalize_decision_side_coverage(value: object) -> None:
    if not isinstance(value, dict):
        return
    for field in ("directional_evaluations", "nondirectional_evaluations"):
        value.pop(field, None)
    by_side = value.get("by_side")
    if not isinstance(by_side, dict):
        return
    for row in by_side.values():
        _pop_fields(row, ("evaluations", "eligible_evaluations"))


def _normalize_path_material(value: object) -> None:
    if isinstance(value, dict):
        value.pop("blocker_evaluations", None)
        value.pop("censored", None)


def _hash_payload(payload: Record) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


def _event_hash(event: Record) -> str:
    payload = {key: value for key, value in event.items() if key != "event_sha256"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


def _digest_text(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise ValueError(f"{label} must be lowercase SHA-256")
    return text


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return list(value)


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a text array")
    return list(value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()
