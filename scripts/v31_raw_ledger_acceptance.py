#!/usr/bin/env python3
"""Publish immutable raw-ledger acceptance for an exact v31 checkpoint."""

from __future__ import annotations

import argparse
from collections.abc import Iterator, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.cohort_live_audit_values import mapping, text
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger
from hypervector.research.v31_poststart_acceptance import (
    build_v31_poststart_acceptance,
)
from hypervector.research.v31_raw_identity import V31_SYMBOLS
from hypervector.research.v31_raw_ledger_acceptance import (
    build_v31_raw_ledger_acceptance,
)
from hypervector.research.v31_route_forward import (
    build_v31_route_forward_snapshot,
)

_CHECKPOINT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")
_JOURNAL = Path("docs/research-journal/hip3-route-authority-pruning-v1.json")
_SOURCE = Path("configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml")
_CANDIDATE = Path("configs/multi_asset_bidirectional_swing_pruned_candidate_v31.toml")
_LEDGER_ROOT = Path("data/live/bidirectional_cohort")
_OUTPUT_DIR = Path("data/logs/research/bidirectional_cohort")


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable raw-ledger verifier parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=_CHECKPOINT)
    parser.add_argument("--journal", type=Path, default=_JOURNAL)
    parser.add_argument("--source-config", type=Path, default=_SOURCE)
    parser.add_argument("--candidate-config", type=Path, default=_CANDIDATE)
    parser.add_argument("--ledger-root", type=Path, default=_LEDGER_ROOT)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--maximum-pressure-age-seconds", type=float, default=30.0)
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    """Snapshot raw ledgers and persist one immutable technical decision."""
    generated = datetime.now(UTC)
    output = args.out or _timestamped_output(generated)
    if output.exists():
        raise FileExistsError(
            f"v31 raw-ledger acceptance output already exists: {output}"
        )
    checkpoint = _load_json(args.checkpoint, "checkpoint")
    journal = _load_json(args.journal, "journal")
    route_snapshot = build_v31_route_forward_snapshot(
        checkpoint, journal, args.source_config, args.candidate_config
    )
    aggregate = build_v31_poststart_acceptance(
        checkpoint,
        route_snapshot,
        maximum_pressure_age_seconds=args.maximum_pressure_age_seconds,
    )
    run_id = text(
        mapping(aggregate.get("run"), "aggregate run").get("run_id"), "run ID"
    )
    with _snapshot_inputs(args, run_id) as (cohort, assets, ledger_evidence):
        report = build_v31_raw_ledger_acceptance(
            checkpoint,
            aggregate,
            cohort,
            assets,
            maximum_pressure_age_seconds=args.maximum_pressure_age_seconds,
        )
    report["generated_at_utc"] = generated.isoformat()
    report["evidence"] = _evidence(args, output, ledger_evidence)
    write_atomic_json(output, report)
    return report


def exit_code(report: Mapping[str, object]) -> int:
    """Return zero only for persisted raw-ledger acceptance."""
    accepted = report.get("accepted")
    if not isinstance(accepted, bool):
        raise ValueError("v31 raw-ledger accepted state must be boolean")
    return 0 if accepted else 2


@contextmanager
def _snapshot_inputs(
    args: argparse.Namespace,
    run_id: str,
) -> Iterator[
    tuple[
        list[dict[str, object]],
        dict[str, list[dict[str, object]]],
        dict[str, object],
    ]
]:
    with ExitStack() as stack:
        cohort_path = args.ledger_root / "decisions.jsonl"
        cohort, cohort_evidence = stack.enter_context(
            snapshot_decision_ledger(
                cohort_path, run_id=run_id, allow_incomplete_tail=True
            )
        )
        assets: dict[str, list[dict[str, object]]] = {}
        asset_evidence: dict[str, object] = {}
        for symbol in V31_SYMBOLS:
            path = _asset_path(args.ledger_root, symbol)
            rows, evidence = stack.enter_context(
                snapshot_decision_ledger(
                    path, run_id=run_id, allow_incomplete_tail=True
                )
            )
            assets[symbol] = rows
            asset_evidence[symbol] = {"source_path": str(path.resolve()), **evidence}
        yield (
            cohort,
            assets,
            {
                "cohort_ledger_prefix": {
                    "source_path": str(cohort_path.resolve()),
                    **cohort_evidence,
                },
                "asset_ledger_prefixes": asset_evidence,
            },
        )


def _evidence(
    args: argparse.Namespace,
    output: Path,
    ledger_evidence: Mapping[str, object],
) -> dict[str, object]:
    return {
        "checkpoint": _path_evidence(args.checkpoint),
        "journal": _path_evidence(args.journal),
        "source_config": _path_evidence(args.source_config),
        "candidate_config": _path_evidence(args.candidate_config),
        **ledger_evidence,
        "output_path": str(output.resolve()),
    }


def _load_json(path: Path, label: str) -> Mapping[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"v31 raw-ledger {label} is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"v31 raw-ledger {label} must be an object")
    return value


def _path_evidence(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _asset_path(root: Path, symbol: str) -> Path:
    return root / f"{symbol.lower()}.jsonl"


def _timestamped_output(generated: datetime) -> Path:
    stamp = generated.strftime("%Y%m%dT%H%M%SZ")
    return _OUTPUT_DIR / f"v31_raw_ledger_acceptance_{stamp}.json"


def command_summary(report: Mapping[str, object]) -> dict[str, object]:
    """Return bounded operator output without raw metric expansion."""
    evidence = mapping(report.get("evidence"), "raw-ledger evidence")
    return {
        "accepted": report.get("accepted"),
        "decision": report.get("decision"),
        "reasons": report.get("reasons"),
        "out": evidence.get("output_path"),
        "execution_authority": "none",
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Persist raw-ledger evidence without importing a venue order client."""
    report = run(build_parser().parse_args(argv))
    print(json.dumps(command_summary(report), sort_keys=True))
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
