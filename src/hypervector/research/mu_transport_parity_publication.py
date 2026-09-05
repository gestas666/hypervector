"""Immutable publication orchestration for the frozen MU parity window."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.mu_transport_parity_finalizer import (
    MuTransportWindowSpec,
    ObserverWindowProgress,
    assess_decision_parity,
    read_observer_progress,
    validate_frozen_generators,
)

Record = Mapping[str, object]
CommandRunner = Callable[[tuple[str, ...]], None]


@dataclass(frozen=True)
class MuFinalizationInputs:
    """Explicit files and roots used by one finalization attempt."""

    prereg: Path
    observer_journal: Path
    development_diagnostic: Path
    data_root: Path
    out_dir: Path
    root: Path
    source_hash_correction: Path | None = None


def manifest_path(inputs: MuFinalizationInputs, spec: MuTransportWindowSpec) -> Path:
    """Return the deterministic one-result publication path."""
    return _chain_paths(inputs, spec)["manifest"]


def load_existing_manifest(
    inputs: MuFinalizationInputs, spec: MuTransportWindowSpec
) -> dict[str, object] | None:
    """Load and validate a prior immutable result when present."""
    path = manifest_path(inputs, spec)
    if not path.is_file():
        return None
    report = _load_json(path, "manifest")
    _validate_existing_manifest(inputs, spec, report)
    return report


def publish_missing_failure(
    inputs: MuFinalizationInputs,
    spec: MuTransportWindowSpec,
    progress: ObserverWindowProgress,
) -> Path:
    """Publish the frozen result when observer coverage is incomplete."""
    path = manifest_path(inputs, spec)
    path.parent.mkdir(parents=True, exist_ok=True)
    reasons: list[str] = []
    if progress.missing_decisions:
        reasons.append("missing_observer_decisions")
    if progress.unresolved_decisions:
        reasons.append("unresolved_observer_decisions")
    report = _manifest_base(inputs, spec, progress)
    report.update({"verdict": "FAIL", "failure_reasons": reasons})
    write_immutable_json(path, report)
    return path


def publish_complete(
    inputs: MuFinalizationInputs,
    spec: MuTransportWindowSpec,
    progress: ObserverWindowProgress,
    command_runner: CommandRunner,
) -> tuple[Path, str]:
    """Run the frozen evidence chain and publish its immutable verdict."""
    paths = _chain_paths(inputs, spec)
    paths["manifest"].parent.mkdir(parents=True, exist_ok=True)
    for command in _chain_commands(inputs, spec, paths):
        command_runner(command)
    validate_frozen_generators(
        spec, inputs.root, correction_path=inputs.source_hash_correction
    )
    current = read_observer_progress(inputs.observer_journal, spec)
    _require_same_progress(progress, current)
    reports = _load_chain_reports(paths)
    verdict, reasons = assess_decision_parity(reports["decision_parity"], spec)
    report = _manifest_base(inputs, spec, current)
    report.update(_complete_fields(paths, reports, verdict, reasons))
    write_immutable_json(paths["manifest"], report)
    return paths["manifest"], verdict


def publish_chain_failure(
    inputs: MuFinalizationInputs,
    spec: MuTransportWindowSpec,
    progress: ObserverWindowProgress,
    error: Exception,
) -> Path:
    """Publish one immutable failure after a child evidence command fails."""
    paths = _chain_paths(inputs, spec)
    paths["manifest"].parent.mkdir(parents=True, exist_ok=True)
    report = _manifest_base(inputs, spec, progress)
    existing = {
        key: _path_evidence(path)
        for key, path in paths.items()
        if key != "manifest" and path.is_file()
    }
    report.update(
        {
            "verdict": "FAIL",
            "failure_reasons": ["evidence_chain_failed"],
            "failure_detail": str(error),
            "chain_evidence": existing,
        }
    )
    write_immutable_json(paths["manifest"], report)
    return paths["manifest"]


def publish_source_failure(
    inputs: MuFinalizationInputs,
    spec: MuTransportWindowSpec,
    progress: ObserverWindowProgress,
    error: Exception,
) -> Path:
    """Publish the fixed-window failure for a changed frozen generator."""
    path = manifest_path(inputs, spec)
    path.parent.mkdir(parents=True, exist_ok=True)
    report = _manifest_base(inputs, spec, progress)
    report.update(
        {
            "verdict": "FAIL",
            "failure_reasons": ["frozen_generator_changed"],
            "failure_detail": str(error),
            "chain_evidence": {},
        }
    )
    write_immutable_json(path, report)
    return path


def _complete_fields(
    paths: Mapping[str, Path],
    reports: Mapping[str, Record],
    verdict: str,
    reasons: tuple[str, ...],
) -> dict[str, object]:
    return {
        "verdict": verdict,
        "failure_reasons": list(reasons),
        "chain_evidence": {
            key: _path_evidence(path)
            for key, path in paths.items()
            if key != "manifest"
        },
        "decision_parity_assessment": reports["decision_parity"].get(
            "technical_assessment"
        ),
    }


def _chain_paths(
    inputs: MuFinalizationInputs, spec: MuTransportWindowSpec
) -> dict[str, Path]:
    directory = inputs.out_dir / f"xyz_mu_{spec.start_ms}_{spec.end_exclusive_ms}"
    return {
        "path_audit": directory / "path_audit.json",
        "candle_parity": directory / "candle_parity.json",
        "signal_parity": directory / "signal_parity.json",
        "decision_parity": directory / "decision_parity.json",
        "manifest": directory / "manifest.json",
    }


def _chain_commands(
    inputs: MuFinalizationInputs,
    spec: MuTransportWindowSpec,
    paths: Mapping[str, Path],
) -> tuple[tuple[str, ...], ...]:
    scripts = inputs.root / "scripts"
    shared = ("--symbol", spec.symbol, "--data-root", str(inputs.data_root))
    path = _command(
        scripts / "hip3_prospective_path_audit.py",
        (*shared, "--output", str(paths["path_audit"]), "--timeframe-minutes", "15"),
    )
    candle = _command(
        scripts / "hip3_prospective_candle_parity.py",
        (
            *shared,
            "--path-audit",
            str(paths["path_audit"]),
            "--output",
            str(paths["candle_parity"]),
        ),
    )
    return (
        path,
        candle,
        _signal_command(inputs, spec, paths),
        _decision_command(inputs, spec, paths),
    )


def _signal_command(
    inputs: MuFinalizationInputs,
    spec: MuTransportWindowSpec,
    paths: Mapping[str, Path],
) -> tuple[str, ...]:
    return _command(
        inputs.root / "scripts/hip3_prospective_signal_parity.py",
        (
            "--symbol",
            spec.symbol,
            "--data-root",
            str(inputs.data_root),
            "--path-audit",
            str(paths["path_audit"]),
            "--candle-parity",
            str(paths["candle_parity"]),
            "--development-diagnostic",
            str(inputs.development_diagnostic),
            "--output",
            str(paths["signal_parity"]),
        ),
    )


def _decision_command(
    inputs: MuFinalizationInputs,
    spec: MuTransportWindowSpec,
    paths: Mapping[str, Path],
) -> tuple[str, ...]:
    return _command(
        inputs.root / "scripts/hip3_shadow_observer_decision_parity.py",
        (
            "--signal-parity",
            str(paths["signal_parity"]),
            "--observer-journal",
            str(inputs.observer_journal),
            "--output",
            str(paths["decision_parity"]),
            "--start-ms",
            str(spec.start_ms),
            "--end-ms",
            str(spec.last_ms),
        ),
    )


def _command(script: Path, args: tuple[str, ...]) -> tuple[str, ...]:
    return (sys.executable, str(script), *args)


def _load_chain_reports(paths: Mapping[str, Path]) -> dict[str, dict[str, object]]:
    schemas = {
        "path_audit": "hip3_prospective_path_audit_v1",
        "candle_parity": "hip3_prospective_candle_parity_v1",
        "signal_parity": "hip3_prospective_signal_parity_v1",
        "decision_parity": "hip3_shadow_observer_decision_parity_v2",
    }
    reports: dict[str, dict[str, object]] = {}
    for key, schema in schemas.items():
        report = _load_json(paths[key], key)
        if report.get("schema_version") != schema:
            raise ValueError(f"MU finalization {key} schema is invalid")
        _require_report_only(report, key)
        reports[key] = report
    signal = _mapping(reports["signal_parity"], "technical_assessment")
    if signal.get("prospective_signal_source_parity_resolved") is not True:
        raise ValueError("MU finalization signal-source parity is unresolved")
    return reports


def _require_same_progress(
    before: ObserverWindowProgress, after: ObserverWindowProgress
) -> None:
    fields = (
        "observed_decisions",
        "resolved_decisions",
        "eligible_decisions",
        "long_decisions",
        "short_decisions",
        "missing_decisions",
        "unresolved_decisions",
    )
    if any(getattr(before, field) != getattr(after, field) for field in fields):
        raise RuntimeError("MU observer window changed during finalization")


def _validate_existing_manifest(
    inputs: MuFinalizationInputs,
    spec: MuTransportWindowSpec,
    report: Record,
) -> None:
    if report.get("schema_version") != "v52_mu_transport_parity_finalization_v1":
        raise ValueError("MU finalization manifest schema is invalid")
    if report.get("hypothesis_id") != spec.hypothesis_id:
        raise ValueError("MU finalization manifest hypothesis is inconsistent")
    _require_report_only(report, "manifest")
    if _mapping(report, "scope") != _scope_record(spec):
        raise ValueError("MU finalization manifest scope is inconsistent")
    if report.get("verdict") not in {"PASS", "FAIL"}:
        raise ValueError("MU finalization manifest verdict is invalid")
    evidence = _mapping(report, "source_evidence")
    _require_path_evidence(evidence.get("preregistration"), inputs.prereg)
    _require_path_evidence(evidence.get("source_journal"), spec.source_journal)
    _require_path_evidence(
        evidence.get("development_diagnostic"), inputs.development_diagnostic
    )
    _validate_correction_evidence(evidence, inputs.source_hash_correction)
    chain = report.get("chain_evidence")
    if chain is not None:
        for value in _mapping(report, "chain_evidence").values():
            _require_declared_evidence(value)


def _manifest_base(
    inputs: MuFinalizationInputs,
    spec: MuTransportWindowSpec,
    progress: ObserverWindowProgress,
) -> dict[str, object]:
    return {
        "schema_version": "v52_mu_transport_parity_finalization_v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "hypothesis_id": spec.hypothesis_id,
        "contract": _contract(),
        "scope": _scope_record(spec),
        "observer_progress": _progress_record(progress),
        "source_evidence": _source_evidence(inputs, spec),
    }


def _source_evidence(
    inputs: MuFinalizationInputs, spec: MuTransportWindowSpec
) -> dict[str, object]:
    evidence = {
        "preregistration": _path_evidence(inputs.prereg),
        "source_journal": _path_evidence(spec.source_journal),
        "development_diagnostic": _path_evidence(inputs.development_diagnostic),
    }
    if inputs.source_hash_correction is not None:
        evidence["source_hash_correction"] = _path_evidence(
            inputs.source_hash_correction
        )
    return evidence


def _validate_correction_evidence(
    evidence: Record, correction_path: Path | None
) -> None:
    declared = evidence.get("source_hash_correction")
    if correction_path is None:
        if declared is not None:
            raise ValueError("MU finalization has unexpected hash correction evidence")
        return
    _require_path_evidence(declared, correction_path)


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "promotion_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }


def _require_report_only(report: Record, label: str) -> None:
    contract = _mapping(report, "contract")
    if any(
        contract.get(key) != value
        for key, value in _contract().items()
        if key != "automatic_live_change"
    ):
        raise ValueError(f"MU finalization {label} authority contract is invalid")


def _scope_record(spec: MuTransportWindowSpec) -> dict[str, object]:
    return {
        "symbol": spec.symbol,
        "provider_id": spec.provider_id,
        "profile_id": spec.profile_id,
        "timeframe": "15m",
        "first_decision_ms": spec.start_ms,
        "last_decision_ms": spec.last_ms,
        "end_exclusive_ms": spec.end_exclusive_ms,
        "expected_decisions": spec.expected_decisions,
    }


def _progress_record(progress: ObserverWindowProgress) -> dict[str, object]:
    return {
        "observed_decisions": progress.observed_decisions,
        "resolved_decisions": progress.resolved_decisions,
        "eligible_decisions": progress.eligible_decisions,
        "long_decisions": progress.long_decisions,
        "short_decisions": progress.short_decisions,
        "missing_decisions": list(progress.missing_decisions),
        "unresolved_decisions": list(progress.unresolved_decisions),
        "journal_snapshot_sha256": progress.journal_snapshot_sha256,
        "journal_snapshot_bytes": progress.journal_snapshot_bytes,
        "stable_bytes": progress.stable_bytes,
        "dropped_tail_bytes": progress.dropped_tail_bytes,
    }


def _path_evidence(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"MU finalization evidence is missing: {path}")
    return {"path": str(path.resolve()), **file_evidence(path)}


def _require_path_evidence(value: object, path: Path) -> None:
    evidence = _object(value, "evidence")
    if evidence.get("path") != str(path.resolve()):
        raise ValueError("MU finalization evidence path is inconsistent")
    _require_declared_evidence(evidence)


def _require_declared_evidence(value: object) -> None:
    evidence = _object(value, "evidence")
    path = Path(str(evidence.get("path")))
    observed = file_evidence(path)
    if observed.get("sha256") != evidence.get("sha256"):
        raise ValueError("MU finalization evidence checksum mismatch")
    if observed.get("bytes") != evidence.get("bytes"):
        raise ValueError("MU finalization evidence byte count mismatch")


def _load_json(path: Path, label: str) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"MU finalization {label} is missing: {path}")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"MU finalization {label} must be an object")
    return value


def _mapping(parent: Record, key: str) -> Record:
    return _object(parent.get(key), key)


def _object(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"MU finalization {label} must be an object")
    return value
