"""Shared execution-incapable command for exact candidate acceptance."""

from __future__ import annotations

import argparse
from collections.abc import Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, ExitStack, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Protocol

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.cohort_live_audit_values import mapping, text
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger

Record = Mapping[str, object]
SnapshotBundle = tuple[
    list[dict[str, object]],
    dict[str, list[dict[str, object]]],
    dict[str, object],
]


class AcceptanceSnapshotBuilder(Protocol):
    """Build one exact aggregate-input snapshot."""

    def __call__(
        self, checkpoint: Record, journal: Record, candidate_path: Path
    ) -> dict[str, object]: ...


class PoststartAcceptanceBuilder(Protocol):
    """Build aggregate acceptance from checkpoint and candidate snapshot."""

    def __call__(
        self,
        checkpoint: Record,
        route_snapshot: Record,
        *,
        maximum_pressure_age_seconds: float,
    ) -> dict[str, object]: ...


class RawAcceptanceBuilder(Protocol):
    """Build raw-ledger acceptance from frozen prefixes."""

    def __call__(
        self,
        checkpoint: Record,
        aggregate_acceptance: Record,
        cohort_records: Sequence[Record],
        asset_records: Mapping[str, Sequence[Record]],
        *,
        maximum_pressure_age_seconds: float,
    ) -> dict[str, object]: ...


class SnapshotInputProvider(Protocol):
    """Return a frozen ledger-prefix context for one run."""

    def __call__(
        self, root: Path, run_id: str
    ) -> AbstractContextManager[SnapshotBundle]: ...


@dataclass(frozen=True)
class CandidateAcceptanceCommandSpec:
    """Bind exact paths and hashes for one candidate acceptance command."""

    version_label: str
    bundle_schema: str
    checkpoint: Path
    journal: Path
    candidate_config: Path
    ledger_root: Path
    output_dir: Path
    output_prefix: str
    journal_sha256: str
    symbols: tuple[str, ...]


@dataclass(frozen=True)
class CandidateAcceptanceCommand:
    """Provide one exact report-only candidate verifier command."""

    spec: CandidateAcceptanceCommandSpec
    snapshot_builder: AcceptanceSnapshotBuilder
    poststart_builder: PoststartAcceptanceBuilder
    raw_builder: RawAcceptanceBuilder
    snapshot_inputs: SnapshotInputProvider

    def build_parser(self) -> argparse.ArgumentParser:
        """Build the exact versioned verifier parser."""
        parser = argparse.ArgumentParser(
            description=f"Publish immutable {self.spec.version_label} acceptance"
        )
        parser.add_argument("--checkpoint", type=Path, default=self.spec.checkpoint)
        parser.add_argument("--journal", type=Path, default=self.spec.journal)
        parser.add_argument(
            "--candidate-config", type=Path, default=self.spec.candidate_config
        )
        parser.add_argument("--ledger-root", type=Path, default=self.spec.ledger_root)
        parser.add_argument("--out", type=Path)
        parser.add_argument("--maximum-pressure-age-seconds", type=float, default=30.0)
        return parser

    def run(self, args: argparse.Namespace) -> dict[str, object]:
        """Snapshot exact ledgers and persist one technical decision."""
        generated = datetime.now(UTC)
        output = args.out or _timestamped_output(generated, self.spec)
        if output.exists():
            raise FileExistsError(
                f"{self.spec.version_label} acceptance output already exists: {output}"
            )
        checkpoint = _load_json(args.checkpoint, "checkpoint", self.spec)
        journal = _load_bound_journal(args.journal, self.spec)
        snapshot = self.snapshot_builder(checkpoint, journal, args.candidate_config)
        aggregate = self.poststart_builder(
            checkpoint,
            snapshot,
            maximum_pressure_age_seconds=args.maximum_pressure_age_seconds,
        )
        raw, ledger_evidence = self._raw_acceptance(args, checkpoint, aggregate)
        report = _bundle(generated, aggregate, raw, self.spec)
        report["evidence"] = _evidence(args, output, ledger_evidence)
        write_atomic_json(output, report)
        return report

    def exit_code(self, report: Record) -> int:
        """Return zero only when both exact technical checks accept."""
        accepted = report.get("accepted")
        if not isinstance(accepted, bool):
            raise ValueError(
                f"{self.spec.version_label} acceptance state must be boolean"
            )
        return 0 if accepted else 2

    def command_summary(self, report: Record) -> dict[str, object]:
        """Return bounded operator output without raw-ledger expansion."""
        evidence = mapping(
            report.get("evidence"),
            f"{self.spec.version_label} acceptance evidence",
        )
        return {
            "accepted": report.get("accepted"),
            "decision": report.get("decision"),
            "reasons": report.get("reasons"),
            "out": evidence.get("output_path"),
            "execution_authority": "none",
        }

    def main(self, argv: Sequence[str] | None = None) -> int:
        """Persist evidence without importing a venue order client."""
        report = self.run(self.build_parser().parse_args(argv))
        print(json.dumps(self.command_summary(report), sort_keys=True))
        return self.exit_code(report)

    def _raw_acceptance(
        self,
        args: argparse.Namespace,
        checkpoint: Record,
        aggregate: Record,
    ) -> tuple[dict[str, object], dict[str, object]]:
        run_id = text(
            mapping(aggregate.get("run"), "aggregate run").get("run_id"),
            "run ID",
        )
        context = self.snapshot_inputs(args.ledger_root, run_id)
        if not isinstance(context, AbstractContextManager):
            raise TypeError("snapshot input provider must return a context manager")
        with context as inputs:
            cohort, assets, evidence = inputs
            raw = self.raw_builder(
                checkpoint,
                aggregate,
                cohort,
                assets,
                maximum_pressure_age_seconds=args.maximum_pressure_age_seconds,
            )
        return raw, evidence


@contextmanager
def snapshot_acceptance_inputs(
    root: Path,
    run_id: str,
    *,
    symbols: tuple[str, ...],
) -> Iterator[SnapshotBundle]:
    """Freeze one cohort prefix and each exact asset prefix."""
    with ExitStack() as stack:
        cohort_path = root / "decisions.jsonl"
        cohort, cohort_evidence = stack.enter_context(
            snapshot_decision_ledger(
                cohort_path, run_id=run_id, allow_incomplete_tail=True
            )
        )
        assets, evidence = _snapshot_assets(stack, root, run_id, symbols)
        yield (
            cohort,
            assets,
            {
                "cohort_ledger_prefix": {
                    "source_path": str(cohort_path.resolve()),
                    **cohort_evidence,
                },
                "asset_ledger_prefixes": evidence,
            },
        )


def _snapshot_assets(
    stack: ExitStack,
    root: Path,
    run_id: str,
    symbols: tuple[str, ...],
) -> tuple[dict[str, list[dict[str, object]]], dict[str, object]]:
    assets: dict[str, list[dict[str, object]]] = {}
    evidence: dict[str, object] = {}
    for symbol in symbols:
        path = root / f"{symbol.lower()}.jsonl"
        rows, prefix = stack.enter_context(
            snapshot_decision_ledger(path, run_id=run_id, allow_incomplete_tail=True)
        )
        assets[symbol] = rows
        evidence[symbol] = {"source_path": str(path.resolve()), **prefix}
    return assets, evidence


def _bundle(
    generated: datetime,
    aggregate: Record,
    raw: Record,
    spec: CandidateAcceptanceCommandSpec,
) -> dict[str, object]:
    reasons = [
        f"{label}:{reason}"
        for label, report in (("poststart", aggregate), ("raw", raw))
        for reason in _reasons(report, spec)
    ]
    accepted = aggregate.get("accepted") is True and raw.get("accepted") is True
    return {
        "schema_version": spec.bundle_schema,
        "generated_at_utc": generated.isoformat(),
        "execution_authority": "none",
        "accepted": accepted,
        "decision": "accepted" if accepted else "rejected",
        "reasons": reasons,
        "poststart": dict(aggregate),
        "raw_ledger": dict(raw),
    }


def _reasons(report: Record, spec: CandidateAcceptanceCommandSpec) -> list[str]:
    raw = report.get("reasons")
    if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
        raise ValueError(
            f"{spec.version_label} component reasons must be a string list"
        )
    return list(raw)


def _load_bound_journal(path: Path, spec: CandidateAcceptanceCommandSpec) -> Record:
    evidence = file_evidence(path)
    if evidence["sha256"] != spec.journal_sha256:
        raise ValueError(
            f"{spec.version_label} journal SHA-256 does not match transition contract"
        )
    return _load_json(path, "journal", spec)


def _load_json(path: Path, label: str, spec: CandidateAcceptanceCommandSpec) -> Record:
    if not path.is_file():
        raise FileNotFoundError(
            f"{spec.version_label} acceptance {label} is missing: {path}"
        )
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"{spec.version_label} acceptance {label} must be an object")
    return value


def _evidence(
    args: argparse.Namespace,
    output: Path,
    ledger_evidence: Record,
) -> dict[str, object]:
    return {
        "checkpoint": _path_evidence(args.checkpoint),
        "journal": _path_evidence(args.journal),
        "candidate_config": _path_evidence(args.candidate_config),
        **ledger_evidence,
        "output_path": str(output.resolve()),
    }


def _path_evidence(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _timestamped_output(
    generated: datetime, spec: CandidateAcceptanceCommandSpec
) -> Path:
    stamp = generated.strftime("%Y%m%dT%H%M%SZ")
    return spec.output_dir / f"{spec.output_prefix}_{stamp}.json"
