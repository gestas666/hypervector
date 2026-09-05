"""Contracts for finalizing one predeclared MU transport-parity window."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger

Record = Mapping[str, object]
_CADENCE_MS = 15 * 60_000
_WINDOW_SCHEMAS = frozenset(
    (
        "v52_mu_transport_parity_forward_window_v1",
        "v53_mu_transport_parity_forward_window_v1",
    )
)


@dataclass(frozen=True)
class MuTransportWindowSpec:
    """Validated immutable identity for one MU forward window."""

    hypothesis_id: str
    symbol: str
    provider_id: str
    profile_id: str
    start_ms: int
    last_ms: int
    end_exclusive_ms: int
    expected_decisions: int
    source_journal: Path
    source_journal_sha256: str
    report_module_sha256: str
    report_script_sha256: str
    observer_generator_identity: tuple[tuple[str, str, int], ...]


@dataclass(frozen=True)
class ObserverWindowProgress:
    """Exact prospective observer coverage inside the frozen window."""

    observed_decisions: int
    resolved_decisions: int
    eligible_decisions: int
    long_decisions: int
    short_decisions: int
    missing_decisions: tuple[int, ...]
    unresolved_decisions: tuple[int, ...]
    journal_snapshot_sha256: str
    journal_snapshot_bytes: int
    stable_bytes: int
    dropped_tail_bytes: int

    @property
    def complete(self) -> bool:
        """Return whether every required decision has resolved evidence."""
        return not self.missing_decisions and not self.unresolved_decisions


def load_window_spec(path: Path) -> MuTransportWindowSpec:
    """Load and validate one exact report-only MU preregistration."""
    report = _load_json(path, "MU transport preregistration")
    schema = _text(report, "schema_version")
    if schema not in _WINDOW_SCHEMAS:
        raise ValueError("MU transport preregistration schema is invalid")
    _require_contract(_mapping(report, "contract"))
    scope = _mapping(report, "scope")
    frozen = _mapping(report, "frozen_sources")
    source = _mapping(frozen, "source_journal")
    source_path = path.parent / _text(source, "path")
    spec = MuTransportWindowSpec(
        hypothesis_id=_text(report, "hypothesis_id"),
        symbol=_text(scope, "symbol"),
        provider_id=_text(scope, "provider_id"),
        profile_id=_text(scope, "profile_id"),
        start_ms=_integer(scope, "first_decision_ms"),
        last_ms=_integer(scope, "last_decision_ms"),
        end_exclusive_ms=_integer(scope, "end_exclusive_ms"),
        expected_decisions=_integer(scope, "expected_decisions"),
        source_journal=source_path.resolve(),
        source_journal_sha256=_text(source, "sha256"),
        report_module_sha256=_text(frozen, "bounded_report_module_sha256"),
        report_script_sha256=_text(frozen, "bounded_report_script_sha256"),
        observer_generator_identity=_observer_generators(
            frozen, required=schema.startswith("v53_")
        ),
    )
    _validate_window(spec)
    _require_sha256(spec.source_journal, spec.source_journal_sha256)
    return spec


def read_observer_progress(
    path: Path, spec: MuTransportWindowSpec
) -> ObserverWindowProgress:
    """Snapshot the active observer journal and measure exact window coverage."""
    with snapshot_decision_ledger(path, allow_incomplete_tail=True) as (
        rows,
        evidence,
    ):
        selected = _observer_rows(rows, spec)
    expected = tuple(range(spec.start_ms, spec.last_ms + 1, _CADENCE_MS))
    missing = tuple(timestamp for timestamp in expected if timestamp not in selected)
    unresolved = tuple(
        timestamp for timestamp, row in selected.items() if not _pressure_resolved(row)
    )
    entries = [row for row in selected.values() if _decision(row).get("eligible")]
    return ObserverWindowProgress(
        observed_decisions=len(selected),
        resolved_decisions=len(selected) - len(unresolved),
        eligible_decisions=len(entries),
        long_decisions=sum(_decision(row).get("side") == "long" for row in entries),
        short_decisions=sum(_decision(row).get("side") == "short" for row in entries),
        missing_decisions=missing,
        unresolved_decisions=unresolved,
        journal_snapshot_sha256=_text(evidence, "sha256"),
        journal_snapshot_bytes=_integer(evidence, "bytes"),
        stable_bytes=_integer(evidence, "stable_bytes"),
        dropped_tail_bytes=_integer(evidence, "dropped_tail_bytes"),
    )


def validate_frozen_generators(
    spec: MuTransportWindowSpec,
    root: Path,
    *,
    correction_path: Path | None = None,
) -> None:
    """Require every pre-window decision generator to retain exact bytes."""
    _require_sha256(spec.source_journal, spec.source_journal_sha256)
    journal = _load_json(spec.source_journal, "MU source journal")
    refreshed = _mapping(journal, "refreshed_evidence")
    expected: dict[str, Record] = {}
    for key in ("venue_path", "candle_source", "strategy_signal_source"):
        reference = _mapping(refreshed, key)
        artifact_path = (
            spec.source_journal.parent / _text(reference, "path")
        ).resolve()
        _require_artifact_evidence(
            spec, refreshed, key, artifact_path, reference, correction_path
        )
        artifact = _load_json(artifact_path, f"{key} artifact")
        _merge_generator_identity(expected, _mapping(artifact, "generator_identity"))
    for relative, evidence in expected.items():
        _require_file_evidence(root / relative, evidence, "MU decision generator")
    _require_observer_generators(spec, root)
    _require_sha256(
        root / "src/hypervector/research/hip3_shadow_observer_decision_parity.py",
        spec.report_module_sha256,
    )
    _require_sha256(
        root / "scripts/hip3_shadow_observer_decision_parity.py",
        spec.report_script_sha256,
    )


def _observer_generators(
    frozen: Record, *, required: bool
) -> tuple[tuple[str, str, int], ...]:
    value = frozen.get("observer_generator_identity")
    if value is None and not required:
        return ()
    if not isinstance(value, list) or not value:
        raise ValueError("MU observer generator identity is required")
    records: list[tuple[str, str, int]] = []
    for item in value:
        record = _object(item, "observer generator evidence")
        relative = _text(record, "path")
        path = Path(relative)
        digest = _text(record, "sha256")
        size = _integer(record, "bytes")
        if path.is_absolute() or ".." in path.parts or size < 0 or len(digest) != 64:
            raise ValueError("MU observer generator evidence is invalid")
        records.append((relative, digest, size))
    if len({record[0] for record in records}) != len(records):
        raise ValueError("MU observer generator paths must be unique")
    return tuple(records)


def _require_observer_generators(spec: MuTransportWindowSpec, root: Path) -> None:
    for relative, digest, size in spec.observer_generator_identity:
        _require_file_evidence(
            root / relative,
            {"sha256": digest, "bytes": size},
            "MU observer",
        )


def _require_artifact_evidence(
    spec: MuTransportWindowSpec,
    refreshed: Record,
    key: str,
    artifact_path: Path,
    reference: Record,
    correction_path: Path | None,
) -> None:
    try:
        _require_file_evidence(artifact_path, reference, f"{key} artifact")
    except ValueError:
        if key != "strategy_signal_source" or correction_path is None:
            raise
        _validate_signal_hash_correction(
            spec, refreshed, artifact_path, reference, correction_path
        )


def _validate_signal_hash_correction(
    spec: MuTransportWindowSpec,
    refreshed: Record,
    artifact_path: Path,
    incorrect: Record,
    correction_path: Path,
) -> None:
    correction = _load_json(correction_path, "MU source hash correction")
    _require_correction_contract(correction, spec)
    _require_correction_source(correction, spec)
    if correction.get("field") != "refreshed_evidence.strategy_signal_source.sha256":
        raise ValueError("MU source hash correction field is invalid")
    if correction.get("incorrect_sha256") != incorrect.get("sha256"):
        raise ValueError("MU source hash correction does not bind the incorrect hash")
    correct = _mapping(correction, "correct_artifact")
    _require_exact_path_evidence(correct, artifact_path, "correct signal artifact")
    _require_cross_binding(correction, refreshed, artifact_path, correct, spec)


def _require_correction_contract(
    correction: Record, spec: MuTransportWindowSpec
) -> None:
    if correction.get("schema_version") != "v52_mu_source_hash_correction_v1":
        raise ValueError("MU source hash correction schema is invalid")
    if correction.get("hypothesis_id") != spec.hypothesis_id:
        raise ValueError("MU source hash correction hypothesis is invalid")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
        "corrects_hash_only": True,
    }
    contract = _mapping(correction, "contract")
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("MU source hash correction contract is invalid")


def _require_correction_source(correction: Record, spec: MuTransportWindowSpec) -> None:
    source = _mapping(correction, "source_journal")
    _require_exact_path_evidence(source, spec.source_journal, "source journal")
    if source.get("sha256") != spec.source_journal_sha256:
        raise ValueError("MU source hash correction preregistration binding is invalid")


def _require_cross_binding(
    correction: Record,
    refreshed: Record,
    artifact_path: Path,
    correct: Record,
    spec: MuTransportWindowSpec,
) -> None:
    observer_reference = _mapping(refreshed, "observer_transport")
    observer_path = (
        spec.source_journal.parent / _text(observer_reference, "path")
    ).resolve()
    _require_file_evidence(observer_path, observer_reference, "observer artifact")
    observer = _mapping(correction, "cross_binding_artifact")
    _require_exact_path_evidence(observer, observer_path, "observer artifact")
    if correction.get("cross_binding_field") != "input_evidence.signal_parity":
        raise ValueError("MU source hash correction cross-binding field is invalid")
    report = _load_json(observer_path, "MU observer cross-binding artifact")
    bound = _mapping(_mapping(report, "input_evidence"), "signal_parity")
    if bound.get("sha256") != correct.get("sha256"):
        raise ValueError("MU source hash correction cross-binding checksum is invalid")
    if bound.get("bytes") != correct.get("bytes"):
        raise ValueError(
            "MU source hash correction cross-binding byte count is invalid"
        )
    bound_path = Path(_text(bound, "path")).resolve()
    if bound_path != artifact_path:
        raise ValueError("MU source hash correction cross-binding path is invalid")


def _require_exact_path_evidence(expected: Record, path: Path, label: str) -> None:
    if Path(_text(expected, "path")).resolve() != path.resolve():
        raise ValueError(f"MU source hash correction {label} path is invalid")
    _require_file_evidence(path, expected, f"MU source hash correction {label}")


def assess_decision_parity(
    report: Record, spec: MuTransportWindowSpec
) -> tuple[str, tuple[str, ...]]:
    """Apply only the success metrics frozen by the MU preregistration."""
    if report.get("schema_version") != "hip3_shadow_observer_decision_parity_v2":
        raise ValueError("MU decision parity schema is invalid")
    _require_output_contract(_mapping(report, "contract"))
    scope = _mapping(report, "scope")
    expected_scope = {
        "symbol": spec.symbol,
        "provider_id": spec.provider_id,
        "profile_id": spec.profile_id,
        "timeframe": "15m",
    }
    if any(scope.get(key) != value for key, value in expected_scope.items()):
        raise ValueError("MU decision parity scope is inconsistent")
    coverage = _mapping(report, "coverage")
    if coverage.get("comparison_start_ms") != spec.start_ms:
        raise ValueError("MU decision parity start bound is inconsistent")
    if coverage.get("comparison_end_ms") != spec.last_ms:
        raise ValueError("MU decision parity end bound is inconsistent")
    if coverage.get("comparison_window_policy") != "explicit_requested_bounds":
        raise ValueError("MU decision parity window policy is inconsistent")
    assessment = _mapping(report, "technical_assessment")
    checks = _assessment_checks(assessment, spec)
    failed = tuple(name for name, passed in checks if not passed)
    return ("PASS" if not failed else "FAIL", failed)


def _assessment_checks(
    assessment: Record, spec: MuTransportWindowSpec
) -> tuple[tuple[str, bool], ...]:
    return (
        (
            "comparison_decisions",
            assessment.get("comparison_decisions") == spec.expected_decisions,
        ),
        (
            "missing_observer_decisions",
            assessment.get("missing_observer_decisions") == 0,
        ),
        (
            "entry_decision_mismatches",
            assessment.get("entry_decision_mismatches") == 0,
        ),
        (
            "non_vacuous_entry_comparison",
            assessment.get("non_vacuous_entry_comparison") is True,
        ),
        (
            "observer_archive_pressure_decision_parity_resolved",
            assessment.get("observer_archive_pressure_decision_parity_resolved")
            is True,
        ),
    )


def _require_output_contract(contract: Record) -> None:
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "promotion_authority": "none",
        "runtime_strategy_changed": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("MU decision parity authority contract is invalid")


def _merge_generator_identity(expected: dict[str, Record], observed: Record) -> None:
    for path, evidence in observed.items():
        if not isinstance(path, str) or not path.strip():
            raise ValueError("MU generator path must be non-empty text")
        record = _object(evidence, f"generator evidence {path}")
        prior = expected.get(path)
        if prior is not None and dict(prior) != dict(record):
            raise ValueError("MU pre-window generator identities conflict")
        expected[path] = record


def _require_file_evidence(path: Path, expected: Record, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    actual = file_evidence(path)
    if actual.get("sha256") != expected.get("sha256"):
        raise ValueError(f"{label} generator changed after window start")
    if "bytes" in expected and actual.get("bytes") != expected.get("bytes"):
        raise ValueError(f"{label} byte count changed after window start")


def _observer_rows(
    rows: list[dict[str, object]], spec: MuTransportWindowSpec
) -> dict[int, Record]:
    selected: dict[int, Record] = {}
    for row in rows:
        decision = _decision(row)
        timestamp = _integer(decision, "decision_time_ms")
        if not spec.start_ms <= timestamp <= spec.last_ms:
            continue
        _validate_observer_row(row, decision, spec)
        if timestamp in selected:
            raise ValueError("duplicate observer decision in frozen MU window")
        selected[timestamp] = row
    return selected


def _validate_observer_row(
    row: Record, decision: Record, spec: MuTransportWindowSpec
) -> None:
    expected = {
        "symbol": spec.symbol,
        "provider_id": spec.provider_id,
        "profile_id": spec.profile_id,
        "pressure_source": "hyperliquid_mainnet_l2_rest",
        "execution_authority": "none",
        "prospective": True,
    }
    if any(decision.get(key) != value for key, value in expected.items()):
        raise ValueError("observer decision identity is inconsistent")
    if row.get("report_only") is not True or row.get("execution_authority") != "none":
        raise ValueError("observer decision authority contract is invalid")
    if row.get("runtime_strategy_changed") is not False or row.get("intents") != []:
        raise ValueError("observer decision attempted a strategy or intent mutation")


def _pressure_resolved(row: Record) -> bool:
    decision = _decision(row)
    return all(
        decision.get(key) is True
        for key in (
            "pressure_state_history_complete",
            "pressure_fresh",
            "pressure_scan_complete",
        )
    )


def _decision(row: Record) -> Record:
    if row.get("event_type") != "mu_hip3_breakout_shadow_decision":
        raise ValueError("observer journal contains a non-MU decision event")
    return _mapping(row, "decision")


def _validate_window(spec: MuTransportWindowSpec) -> None:
    expected = (spec.last_ms - spec.start_ms) // _CADENCE_MS + 1
    if spec.start_ms <= 0 or spec.last_ms < spec.start_ms:
        raise ValueError("MU transport window bounds are invalid")
    if (spec.last_ms - spec.start_ms) % _CADENCE_MS:
        raise ValueError("MU transport decisions are not 15m aligned")
    if spec.end_exclusive_ms != spec.last_ms + _CADENCE_MS:
        raise ValueError("MU transport end-exclusive bound is invalid")
    if spec.expected_decisions != expected:
        raise ValueError("MU transport expected decision count is inconsistent")
    if spec.symbol != "xyz:MU" or spec.provider_id == spec.profile_id:
        raise ValueError("MU transport source identity is invalid")


def _require_contract(contract: Record) -> None:
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "promotion_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
        "no_window_shrinkage": True,
        "no_replacement_window_after_failure": True,
        "no_parameter_retuning_during_window": True,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("MU transport preregistration contract is invalid")


def _require_sha256(path: Path, expected: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"MU transport source journal is missing: {path}")
    if file_evidence(path).get("sha256") != expected:
        raise ValueError("MU transport source journal checksum mismatch")


def _load_json(path: Path, label: str) -> Record:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    value = json.loads(path.read_text())
    return _object(value, label)


def _mapping(parent: Record, key: str) -> Record:
    return _object(parent.get(key), key)


def _object(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(parent: Record, key: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value.strip()


def _integer(parent: Record, key: str) -> int:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value
