"""Source-bound, authority-none context for the V58 SP500 outage recovery."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.hip3_development_provenance import require_unchanged_file
from hypervector.research.v58_sp500_source_history_context import (
    load_v58_sp500_source_history,
)

Record = Mapping[str, object]

_DISPOSITION = "OPEN_LIFECYCLE_CENSORED_DECISION_GAP"
_ROUTE = "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3|xyz:SP500"
_PROVIDER = "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3"
_SOURCE_HISTORY = Path(
    "docs/research-journal/v51-sp500-fresh15-v3-live-lifecycle-v2.json"
)
_SOURCE_HISTORY_SHA256 = (
    "0164723389bbeb56d993b33505c0068661acb41d3cdd5a02d44f49ab311715b6"
)


@dataclass(frozen=True)
class Sp500GapRecoveryContext:
    """Immutable recovered-path facts that retain the decision-path censor."""

    payload: dict[str, object]
    evidence: dict[str, object]
    execution_authority: str = "none"


def load_v58_sp500_gap_recovery_context(
    report_path: Path,
    journal_path: Path,
    *,
    source_history_journal: Path | None = None,
    expected_history_journal_sha256: str | None = None,
) -> Sp500GapRecoveryContext:
    """Load and reconcile the immutable recovery report and disposition journal."""
    report_evidence = file_evidence(report_path)
    journal_evidence = file_evidence(journal_path)
    report = _load_mapping(report_path, "SP500 recovery report")
    journal = _load_mapping(journal_path, "SP500 recovery journal")
    _require_report_contract(report)
    _require_journal_contract(journal, report_evidence)
    _require_reconciliation(report, journal)
    payload = _payload(report, journal)
    history_evidence = _source_history(
        payload,
        report,
        source_history_journal,
        expected_history_journal_sha256,
    )
    context = Sp500GapRecoveryContext(
        payload,
        {
            "recovery_report": {"path": str(report_path.resolve()), **report_evidence},
            "disposition_journal": {
                "path": str(journal_path.resolve()),
                **journal_evidence,
            },
            **history_evidence,
        },
    )
    require_unchanged_file(report_path, report_evidence)
    require_unchanged_file(journal_path, journal_evidence)
    return context


def load_v58_sp500_gap_context_with_history(
    report_path: Path,
    journal_path: Path,
) -> Sp500GapRecoveryContext:
    """Load V58 recovery plus pinned prior mechanism-compatible evidence."""
    return load_v58_sp500_gap_recovery_context(
        report_path,
        journal_path,
        source_history_journal=_SOURCE_HISTORY,
        expected_history_journal_sha256=_SOURCE_HISTORY_SHA256,
    )


def sp500_gap_recovery_context_payload(
    context: Sp500GapRecoveryContext,
) -> dict[str, object]:
    """Serialize recovery facts without execution or strategy-change authority."""
    return {
        **context.payload,
        "counterfactual_fill_claim": False,
        "pnl_claimed": False,
        "performance_gate": False,
        "strategy_change_supported": False,
        "automatic_live_change": False,
        "execution_authority": context.execution_authority,
    }


def _require_report_contract(report: Record) -> None:
    expected = {
        "schema_version": "sp500_fresh15_gap_recovery_v1",
        "symbol": "xyz:SP500",
        "disposition": _DISPOSITION,
        "execution_authority": "none",
        "report_only": True,
        "orders_supported": False,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }
    if any(report.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 SP500 recovery report contract is invalid")
    technical = _mapping(report.get("technical_assessment"), "technical assessment")
    required = {
        "mark_risk_path_resolved": True,
        "historical_candle_path_resolved": True,
        "prospective_decision_path_resolved": False,
        "full_lifecycle_path_resolved": False,
        "live_change_supported": False,
    }
    if any(technical.get(field) != value for field, value in required.items()):
        raise ValueError("V58 SP500 recovery technical disposition is invalid")
    _require_mark_and_decision_paths(report)


def _require_mark_and_decision_paths(report: Record) -> None:
    marks = _mapping(report.get("mark_recovery"), "mark recovery")
    if (
        marks.get("complete") is not True
        or marks.get("stop_crossed") is not False
        or _positive_integer(marks.get("observations"), "mark observations") < 1
        or _nonnegative_integer(marks.get("maximum_gap_ms"), "maximum mark gap") > 5_000
    ):
        raise ValueError("V58 SP500 recovered mark path is invalid")
    decision = _mapping(report.get("decision_recovery"), "decision recovery")
    expected = _integer_list(
        decision.get("expected_boundaries_ms"), "expected boundaries"
    )
    missing = _integer_list(decision.get("missing_boundaries_ms"), "missing boundaries")
    if decision.get("prospective_complete") is not False or not set(missing) <= set(
        expected
    ):
        raise ValueError("V58 SP500 recovered decision path is invalid")


def _require_journal_contract(journal: Record, report_evidence: Record) -> None:
    expected = {
        "schema_version": (
            "hypervector.v58_sp500_outage_mark_gap_recovery_disposition.v2"
        ),
        "hypothesis_id": "v57-sp500-fresh15-v3-source-native-lifecycle-v1",
        "status": _DISPOSITION,
    }
    if any(journal.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 SP500 recovery journal contract is invalid")
    authority = _mapping(journal.get("authority"), "journal authority")
    required_authority = {
        "report_only": True,
        "execution_authority": "none",
        "orders_supported": False,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "live_configuration_changed": False,
    }
    if any(
        authority.get(field) != value for field, value in required_authority.items()
    ):
        raise ValueError("V58 SP500 recovery journal authority is invalid")
    _require_report_reference(journal, report_evidence)


def _require_report_reference(journal: Record, report_evidence: Record) -> None:
    sources = _records(journal.get("source_evidence"), "journal source evidence")
    report_sha = _text(report_evidence.get("sha256"), "recovery report SHA-256")
    matches = tuple(row for row in sources if row.get("sha256") == report_sha)
    if len(matches) != 1:
        raise ValueError("V58 SP500 recovery report is not source-bound by journal")


def _require_reconciliation(report: Record, journal: Record) -> None:
    lifecycle = _mapping(report.get("lifecycle"), "report lifecycle")
    frozen = _mapping(journal.get("frozen_lifecycle"), "frozen lifecycle")
    expected = {
        "symbol": "xyz:SP500",
        "provider_id": _PROVIDER,
        "decision_time_ms": lifecycle.get("decision_time_ms"),
        "entry_time_ms": lifecycle.get("entry_time_ms"),
        "side": lifecycle.get("side"),
    }
    if any(frozen.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 SP500 recovery lifecycle identity is inconsistent")
    remaining = _mapping(journal.get("remaining_censoring"), "remaining censoring")
    decision = _mapping(report.get("decision_recovery"), "decision recovery")
    if remaining.get("missing_prospective_decision_boundaries_ms") != decision.get(
        "missing_boundaries_ms"
    ):
        raise ValueError("V58 SP500 recovery decision censor is inconsistent")
    _require_ledger_update(journal)


def _require_ledger_update(journal: Record) -> None:
    update = _mapping(journal.get("hypothesis_ledger_update"), "ledger update")
    expected = {
        "route": _ROUTE,
        "experiment": "first_exact_source_native_lifecycle_per_side",
        "status": "being_tested",
        "automatic_live_change": False,
    }
    if any(update.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 SP500 recovery hypothesis ledger update is invalid")
    _text(update.get("minimum_additional_evidence"), "minimum additional evidence")


def _payload(report: Record, journal: Record) -> dict[str, object]:
    technical = _mapping(report.get("technical_assessment"), "technical assessment")
    decision = _mapping(report.get("decision_recovery"), "decision recovery")
    marks = _mapping(report.get("mark_recovery"), "mark recovery")
    update = _mapping(journal.get("hypothesis_ledger_update"), "ledger update")
    return {
        "route": _ROUTE,
        "disposition": _DISPOSITION,
        "hypothesis_status": "being_tested",
        "mark_risk_path_resolved": technical["mark_risk_path_resolved"],
        "historical_candle_path_resolved": technical["historical_candle_path_resolved"],
        "prospective_decision_path_resolved": technical[
            "prospective_decision_path_resolved"
        ],
        "full_lifecycle_path_resolved": technical["full_lifecycle_path_resolved"],
        "missing_prospective_decision_boundaries_ms": list(
            _integer_list(decision.get("missing_boundaries_ms"), "missing boundaries")
        ),
        "recovered_mark_observations": marks["observations"],
        "maximum_recovered_mark_gap_ms": marks["maximum_gap_ms"],
        "minimum_additional_evidence": update["minimum_additional_evidence"],
    }


def _source_history(
    payload: dict[str, object],
    report: Record,
    journal_path: Path | None,
    expected_sha256: str | None,
) -> dict[str, object]:
    if journal_path is None and expected_sha256 is None:
        return {}
    if journal_path is None or expected_sha256 is None:
        raise ValueError("V58 SP500 source history identity is incomplete")
    lifecycle = _mapping(report.get("lifecycle"), "report lifecycle")
    summary, evidence = load_v58_sp500_source_history(
        journal_path,
        expected_sha256,
        current_decision_time_ms=_positive_integer(
            lifecycle.get("decision_time_ms"), "decision time"
        ),
        current_side=_text(lifecycle.get("side"), "lifecycle side"),
    )
    payload["mechanism_compatible_lifecycle_summary"] = summary
    return {"mechanism_compatible_history": evidence}


def _load_mapping(path: Path, label: str) -> Record:
    value = json.loads(path.read_bytes())
    return _mapping(value, label)


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, list):
        raise ValueError(f"V58 {label} must be an array")
    return tuple(_mapping(row, label) for row in value)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"V58 {label} must be an object")
    return value


def _integer_list(value: object, label: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"V58 {label} must be a non-empty array")
    output = tuple(_nonnegative_integer(row, label) for row in value)
    if len(output) != len(set(output)):
        raise ValueError(f"V58 {label} must contain unique values")
    return output


def _positive_integer(value: object, label: str) -> int:
    output = _nonnegative_integer(value, label)
    if output == 0:
        raise ValueError(f"V58 {label} must be positive")
    return output


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"V58 {label} must be a nonnegative integer")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"V58 {label} must be non-empty text")
    return value.strip()
