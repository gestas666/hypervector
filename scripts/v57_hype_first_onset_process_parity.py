#!/usr/bin/env python3
"""Freeze exact V57 first-HYPE-onset parity across three running processes."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.cohort_provider_evaluation_parity import (
    build_cohort_provider_evaluation_parity,
)
from hypervector.research.selected_ledger_evaluation import (
    SelectedLedgerEvaluation,
    read_exact_provider_evaluation,
    require_selected_evaluation_unchanged,
)

Record = Mapping[str, object]
_PROVIDER_ID = "hype_breakout_compression_alignment_bidirectional_v2"
_SYMBOL = "HYPE"
_DECISION_TIME_MS = 1787070000000
_LIVE_RUN_ID = "bidirectional-live-1787065473571"
_RELATED = Path(
    "data/logs/research/bidirectional_cohort/"
    "v57_hype_first_true_onset_stop_path_20260818_v2.json"
)


@dataclass(frozen=True)
class SourceSpec:
    """Frozen identity for one exact process ledger."""

    name: str
    kind: str
    path: Path
    run_id: str
    profile_id: str
    profile_fingerprint: str
    run_fingerprint: str


def source_specs(root: Path = Path(".")) -> tuple[SourceSpec, ...]:
    """Return the exact live and observer process identities."""
    return (
        SourceSpec(
            "v57_live",
            "live",
            root / "data/live/bidirectional_cohort/decisions.jsonl",
            _LIVE_RUN_ID,
            "multi_asset_growth_first_5000_spcx_short_containment_v57",
            "724c259bd94be60d80ffc2e6b9a760412b9729ab1f8fea403e61d266f0d9cb8d",
            "5394821e43ebe21126ef7352b190ac921caa3cdcc6ccf22e3f9dc3cdf5bc843c",
        ),
        SourceSpec(
            "native_long_observer",
            "observer",
            root
            / "data/observe/v54_hype_native_long_challenger_continuous_20260818/decisions.jsonl",
            "bidirectional-observe-1787029740833",
            "multi_asset_growth_first_5000_hype_native_long_challenger_v54",
            "1c0beafb19ef1b8c5594d3bf1aa6a23eeff12f28f540d958953cc25e8bff1643",
            "09a64ad206d33ac6644400bd21e3d5128c4b98c457f99662c40721cb02b7869d",
        ),
        SourceSpec(
            "native_fixed8_observer",
            "observer",
            root
            / "data/observe/v54_hype_native_fixed8_continuous_20260818/decisions.jsonl",
            "bidirectional-observe-1787028309077",
            "multi_asset_growth_first_5000_hype_native_reconstruction_candidate_v54",
            "adeacd3fc6eab07f1214043921712e64e9b1c6ea7664a8111e6f419cd8f5bddb",
            "b19cea622e79e29d47c95abfb441d734fcb41e3f524c1cd7b902b87e9b9dce69",
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the immutable report command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def validate_related_event(path: Path) -> dict[str, object]:
    """Require the linked stop-path evidence to identify the same exact event."""
    value: object = json.loads(path.read_text())
    report = _object(value, "related stop-path report")
    contract = _object(report.get("contract"), "related report contract")
    identity = _object(report.get("identity"), "related report identity")
    expected = (_LIVE_RUN_ID, _PROVIDER_ID, _SYMBOL, _DECISION_TIME_MS)
    observed = tuple(
        identity.get(key)
        for key in ("run_id", "strategy_id", "symbol", "decision_time_ms")
    )
    if observed != expected:
        raise ValueError("related event identity does not match parity target")
    if (
        contract.get("report_only") is not True
        or contract.get("execution_authority") != "none"
    ):
        raise ValueError("related event is not report-only evidence")
    return dict(report)


def build_report(specs: Sequence[SourceSpec], related_path: Path) -> dict[str, object]:
    """Read, compare, and revalidate one exact event across all sources."""
    generator = _generator_identity()
    related = validate_related_event(related_path)
    related_evidence = file_evidence(related_path)
    selected = {spec.name: _read_source(spec) for spec in specs}
    report = build_cohort_provider_evaluation_parity(
        rows_by_source={name: value.row for name, value in selected.items()},
        source_kinds={spec.name: spec.kind for spec in specs},
        provider_id=_PROVIDER_ID,
        symbol=_SYMBOL,
        decision_time_ms=_DECISION_TIME_MS,
    )
    _revalidate_inputs(selected, related_path, related_evidence, generator)
    report.update(
        {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "input_evidence": {
                **{name: value.evidence for name, value in selected.items()},
                "related_stop_path": _path_evidence(related_path, related_evidence),
            },
            "related_stop_path_status": related.get("status"),
            "generator_identity": {"files": generator},
        }
    )
    report["material_state_sha256"] = _digest(report)
    return report


def _read_source(spec: SourceSpec) -> SelectedLedgerEvaluation:
    value = read_exact_provider_evaluation(
        spec.path,
        run_id=spec.run_id,
        provider_id=_PROVIDER_ID,
        symbol=_SYMBOL,
        decision_time_ms=_DECISION_TIME_MS,
    )
    _require_source_identity(spec, value.row)
    return value


def _require_source_identity(spec: SourceSpec, row: Record) -> None:
    expected = (
        spec.run_id,
        spec.profile_id,
        spec.profile_fingerprint,
        spec.run_fingerprint,
    )
    observed = tuple(
        row.get(key)
        for key in ("run_id", "profile_id", "profile_fingerprint", "run_fingerprint")
    )
    if observed != expected:
        raise ValueError(f"{spec.name} ledger identity changed")


def _revalidate_inputs(
    selected: Mapping[str, SelectedLedgerEvaluation],
    related_path: Path,
    related_evidence: Record,
    generator: Sequence[Record],
) -> None:
    for value in selected.values():
        require_selected_evaluation_unchanged(value)
    if file_evidence(related_path) != related_evidence:
        raise RuntimeError("related stop-path evidence changed during evaluation")
    if list(generator) != _generator_identity():
        raise RuntimeError("process-parity generator changed during evaluation")


def _generator_identity() -> list[dict[str, object]]:
    paths = (
        Path(__file__).resolve(),
        Path("src/hypervector/research/cohort_provider_evaluation_parity.py").resolve(),
        Path("src/hypervector/research/selected_ledger_evaluation.py").resolve(),
        Path("src/hypervector/data/oxa_storage.py").resolve(),
    )
    return [_file_record(path) for path in paths]


def _file_record(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {"path": str(path), "sha256": sha256(raw).hexdigest(), "bytes": len(raw)}


def _path_evidence(path: Path, evidence: Record) -> dict[str, object]:
    return {**evidence, "path": str(path.resolve())}


def _digest(value: Record) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return sha256(raw.encode()).hexdigest()


def _object(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    """Publish one immutable report-only parity artifact."""
    args = build_parser().parse_args(argv)
    output = Path(args.out)
    inputs = [spec.path.resolve() for spec in source_specs()]
    if output.resolve() in {*inputs, _RELATED.resolve()}:
        raise ValueError("parity output must differ from every input")
    report = build_report(source_specs(), _RELATED)
    write_immutable_json(output, report)
    assessment = _object(report["technical_assessment"], "technical assessment")
    print(
        json.dumps(
            {
                "event": "v57_hype_first_onset_process_parity",
                "output": str(output),
                "semantic_parity_resolved": assessment["semantic_parity_resolved"],
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
