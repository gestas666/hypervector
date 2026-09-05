"""Validated HYPE-native prospective lifecycle status for improvement telemetry."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
import math
from pathlib import Path

from hypervector.research.hype_native_baseline_comparison import (
    HYPE_COMPRESSION_BASELINE_STRATEGY_ID,
)

Record = Mapping[str, object]

_MODE = "hype_native_v54_prospective_lifecycle_report_only"
_PROFILE = "multi_asset_growth_first_5000_hype_native_long_challenger_v54"
_PROFILE_FINGERPRINT = (
    "1c0beafb19ef1b8c5594d3bf1aa6a23eeff12f28f540d958953cc25e8bff1643"
)
_STRATEGY = "hype_native_breakout_onset_long_v3"
_WATCH_STATES = {
    "waiting_for_first_eligible_long",
    "eligible_entry_without_executable_depth",
    "technical_evidence_unresolved",
    "tracking_open_lifecycle",
    "resolved_proxy_lifecycle_evidence_available",
}

_ACTIVE_BASELINE_ROUTE = f"{HYPE_COMPRESSION_BASELINE_STRATEGY_ID}|HYPE"


@dataclass(frozen=True)
class HypeNativeLifecycleEvidence:
    """Validated native-HYPE status and exact source-file evidence."""

    status: dict[str, object]
    evidence: dict[str, object]


def load_hype_native_lifecycle_status(
    path: Path,
    *,
    observed_at: datetime,
    maximum_age_seconds: float,
) -> tuple[dict[str, object], dict[str, object]]:
    """Load one exact, report-only native-HYPE lifecycle projection."""
    _require_positive(maximum_age_seconds, "maximum HYPE lifecycle age")
    raw = path.read_bytes()
    payload = _mapping(json.loads(raw), "HYPE lifecycle status")
    _require_contract(payload)
    timestamp, age = _freshness(payload, observed_at)
    status = _project_status(payload, age, maximum_age_seconds)
    status["observed_at_utc"] = timestamp.isoformat()
    return status, _evidence(path, raw)


def load_hype_native_for_profile(
    path: Path,
    audit: Record,
    *,
    observed_at: datetime,
    maximum_age_seconds: float,
) -> HypeNativeLifecycleEvidence | None:
    """Load native-HYPE evidence when its exact baseline route is executable."""
    run = _mapping(audit.get("run"), "improvement audit run")
    routes_value = run.get("executable_provider_symbols")
    if routes_value is None:
        return None
    routes = _text_array(routes_value, "executable provider symbols")
    if _ACTIVE_BASELINE_ROUTE not in routes:
        return None
    status, evidence = load_hype_native_lifecycle_status(
        path,
        observed_at=observed_at,
        maximum_age_seconds=maximum_age_seconds,
    )
    return HypeNativeLifecycleEvidence(status, evidence)


def _require_contract(payload: Record) -> None:
    if payload.get("schema_version") != 1 or payload.get("mode") != _MODE:
        raise ValueError("HYPE lifecycle source contract is invalid")
    state = _text(payload.get("watch_state"), "HYPE lifecycle watch state")
    if state not in _WATCH_STATES or payload.get("status") != state:
        raise ValueError("HYPE lifecycle watch state is invalid")
    contract = _mapping(payload.get("contract"), "HYPE lifecycle contract")
    expected = {
        "execution_authority": "none",
        "report_only": True,
        "orders_or_fills_assumed": False,
        "realized_pnl_claimed": False,
        "funding_included": False,
        "mark_stop_truth_included": False,
    }
    if any(contract.get(field) != value for field, value in expected.items()):
        raise ValueError("HYPE lifecycle authority contract is invalid")
    _require_identity(_mapping(payload.get("identity"), "HYPE lifecycle identity"))


def _require_identity(identity: Record) -> None:
    expected = {
        "profile_id": _PROFILE,
        "profile_fingerprint": _PROFILE_FINGERPRINT,
        "strategy_id": _STRATEGY,
        "symbol": "HYPE",
    }
    if any(identity.get(field) != value for field, value in expected.items()):
        raise ValueError("HYPE lifecycle identity is invalid")
    _text(identity.get("run_id"), "HYPE lifecycle run id")
    if len(_text(identity.get("run_fingerprint"), "HYPE run fingerprint")) != 64:
        raise ValueError("HYPE lifecycle run fingerprint is invalid")


def _freshness(payload: Record, observed_at: datetime) -> tuple[datetime, float]:
    if observed_at.tzinfo is None:
        raise ValueError("HYPE lifecycle observation time needs a timezone")
    observed_ms = _integer(payload.get("observed_at_ms"), "HYPE observed at")
    timestamp = datetime.fromtimestamp(observed_ms / 1_000.0, tz=UTC)
    age = (observed_at.astimezone(UTC) - timestamp).total_seconds()
    if age < 0.0:
        raise ValueError("HYPE lifecycle status is from the future")
    return timestamp, age


def _project_status(
    payload: Record, age: float, maximum_age_seconds: float
) -> dict[str, object]:
    counts = _signal_counts(payload)
    attempts = _object_list(payload.get("attempts"), "HYPE lifecycle attempts")
    lifecycles = _object_list(payload.get("lifecycles"), "HYPE lifecycles")
    if len(attempts) != counts["eligible_long_entries"]:
        raise ValueError("HYPE lifecycle attempt count is inconsistent")
    projected = [_project_lifecycle(row) for row in lifecycles]
    open_rows = [row for row in projected if row["status"] == "open_pending_exit"]
    if len(open_rows) > 1:
        raise ValueError("HYPE lifecycle has multiple simultaneous open paths")
    resolved = sum(
        row["exit_reason"] is not None and row["technical_path_resolved"] is True
        for row in projected
    )
    unresolved = sum(row["technical_path_resolved"] is not True for row in projected)
    summary = _resolved_summary(payload, resolved)
    comparisons = _baseline_comparisons(payload, counts["eligible_long_entries"])
    return {
        "watch_state": payload["watch_state"],
        "freshness_status": "fresh" if age <= maximum_age_seconds else "stale",
        "age_seconds": age,
        **_identity_status(payload),
        **counts,
        "attempted_entries": len(attempts),
        "occupied_entries": _attempt_count(attempts, "occupied_by_prior_lifecycle"),
        "lifecycles": len(projected),
        "open_lifecycles": len(open_rows),
        "resolved_lifecycles": resolved,
        "technically_unresolved_lifecycles": unresolved,
        "current_open_lifecycle": open_rows[0] if open_rows else None,
        "resolved_proxy_summary": summary,
        "baseline_comparisons": comparisons,
        "native_only_opportunities": sum(
            row["baseline_eligible"] is False for row in comparisons
        ),
        "execution_authority": "none",
        "report_only": True,
        "live_change_supported": False,
    }


def _baseline_comparisons(payload: Record, eligible: int) -> list[dict[str, object]]:
    rows = _object_list(payload.get("baseline_comparisons"), "HYPE comparisons")
    if len(rows) != eligible:
        raise ValueError("HYPE comparison count differs from eligible entries")
    output: list[dict[str, object]] = []
    decisions: set[int] = set()
    for row in rows:
        projected = _project_comparison(row)
        decision = int(projected["decision_time_ms"])
        if decision in decisions:
            raise ValueError("HYPE comparison decision times must be unique")
        decisions.add(decision)
        output.append(projected)
    return output


def _project_comparison(row: Record) -> dict[str, object]:
    _require_comparison_identity(row)
    baseline_eligible = _boolean(row.get("baseline_eligible"), "baseline eligibility")
    common_parity = _boolean(row.get("common_feature_parity"), "feature parity")
    if not common_parity:
        raise ValueError("HYPE comparison requires exact common-feature parity")
    conditions_met = _integer(row.get("baseline_conditions_met"), "conditions met")
    conditions_required = _integer(
        row.get("baseline_conditions_required"), "conditions required"
    )
    if conditions_required <= 0 or conditions_met > conditions_required:
        raise ValueError("HYPE baseline condition counts are invalid")
    blockers = _text_array(row.get("baseline_blockers"), "HYPE baseline blockers")
    if not baseline_eligible and not blockers:
        raise ValueError("ineligible HYPE baseline requires blockers")
    expected_class = (
        "native_breakout_and_compression_pullback_both_admitted"
        if baseline_eligible
        else "native_breakout_admitted_compression_pullback_rejected"
    )
    if row.get("opportunity_class") != expected_class:
        raise ValueError("HYPE comparison opportunity class is inconsistent")
    reference = _number(row.get("reference_price"), "comparison reference price")
    if reference <= 0.0:
        raise ValueError("HYPE comparison reference price must be positive")
    return {
        "symbol": "HYPE",
        "decision_time_ms": _integer(row.get("decision_time_ms"), "decision time"),
        "reference_price": reference,
        "native_strategy_id": _STRATEGY,
        "native_eligible": True,
        "baseline_strategy_id": HYPE_COMPRESSION_BASELINE_STRATEGY_ID,
        "baseline_eligible": baseline_eligible,
        "baseline_reason": _text(row.get("baseline_reason"), "baseline reason"),
        "baseline_blockers": blockers,
        "baseline_conditions_met": conditions_met,
        "baseline_conditions_required": conditions_required,
        "common_feature_parity": True,
        "opportunity_class": expected_class,
    }


def _require_comparison_identity(row: Record) -> None:
    expected = {
        "symbol": "HYPE",
        "native_strategy_id": _STRATEGY,
        "native_eligible": True,
        "baseline_strategy_id": HYPE_COMPRESSION_BASELINE_STRATEGY_ID,
    }
    if any(row.get(field) != value for field, value in expected.items()):
        raise ValueError("HYPE comparison identity is invalid")


def _text_array(value: object, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    result = [_text(item, label) for item in value]
    if len(result) != len(set(result)):
        raise ValueError(f"{label} must be unique")
    return result


def _signal_counts(payload: Record) -> dict[str, int]:
    counts = _mapping(payload.get("signal_counts"), "HYPE signal counts")
    return {
        "eligible_long_entries": _integer(
            counts.get("eligible_long_entries"), "eligible HYPE long entries"
        ),
        "exit_only_short_onsets": _integer(
            counts.get("exit_only_short_onsets"), "HYPE exit-only onsets"
        ),
    }


def _project_lifecycle(row: Record) -> dict[str, object]:
    outcome = _mapping(row.get("current_outcome"), "HYPE current outcome")
    gross = _number(outcome.get("gross_return_bps"), "HYPE gross return")
    favorable = _number(
        row.get("maximum_favorable_excursion_bps"), "HYPE favorable excursion"
    )
    technical = _boolean(row.get("technical_path_resolved"), "HYPE path status")
    return {
        "decision_time_ms": _integer(row.get("decision_time_ms"), "decision time"),
        "side": _text(row.get("side"), "HYPE lifecycle side"),
        "status": _text(row.get("status"), "HYPE lifecycle status"),
        "entry_price": _number(row.get("entry_price"), "HYPE entry price"),
        "stop_price": _number(row.get("stop_price"), "HYPE stop price"),
        "current_book_time_ms": _integer(row.get("current_book_time_ms"), "book time"),
        "occupancy_end_time_ms": _integer(row.get("occupancy_end_time_ms"), "deadline"),
        "exit_reason": row.get("exit_reason"),
        "technical_path_resolved": technical,
        "maximum_book_gap_ms": _integer(row.get("maximum_book_gap_ms"), "book gap"),
        "maximum_favorable_excursion_bps": favorable,
        "maximum_adverse_excursion_bps": _number(
            row.get("maximum_adverse_excursion_bps"), "HYPE adverse excursion"
        ),
        "current_exit_price": _number(outcome.get("exit_price"), "HYPE exit price"),
        "current_gross_return_bps": gross,
        "current_modeled_net_usd_excluding_funding": _number(
            outcome.get("net_pnl_usd"), "HYPE modeled net"
        ),
        "peak_giveback_bps": max(favorable - gross, 0.0),
    }


def _resolved_summary(payload: Record, resolved: int) -> dict[str, object]:
    summary = _mapping(payload.get("resolved_proxy_summary"), "HYPE proxy summary")
    trades = _integer(summary.get("trades"), "HYPE resolved trades")
    wins = _integer(summary.get("wins"), "HYPE resolved wins")
    losses = _integer(summary.get("losses"), "HYPE resolved losses")
    if trades != resolved or wins + losses != trades:
        raise ValueError("HYPE resolved lifecycle summary is inconsistent")
    return dict(summary)


def _identity_status(payload: Record) -> dict[str, str]:
    identity = _mapping(payload.get("identity"), "HYPE lifecycle identity")
    return {
        field: _text(identity.get(field), f"HYPE {field}")
        for field in (
            "run_id",
            "profile_id",
            "profile_fingerprint",
            "run_fingerprint",
            "strategy_id",
            "symbol",
        )
    }


def _attempt_count(rows: list[Record], status: str) -> int:
    return sum(row.get("status") == status for row in rows)


def _evidence(path: Path, raw: bytes) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _object_list(value: object, label: str) -> list[Record]:
    if not isinstance(value, list) or any(
        not isinstance(row, Mapping) for row in value
    ):
        raise ValueError(f"{label} must be an object array")
    return list(value)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _require_positive(value: float, label: str) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} must be positive and finite")
