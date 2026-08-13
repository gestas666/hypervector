#!/usr/bin/env python3
"""Publish a bounded post-cutoff asymmetric portfolio evidence checkpoint."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import UTC, datetime
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.cohort_asymmetric_forward_observer import (
    asymmetric_forward_declaration,
    build_asymmetric_forward_observer,
)
from hypervector.research.cohort_live_audit_values import (
    mapping,
    mapping_list,
    text,
)

_CHECKPOINT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")
_JOURNAL = Path("docs/research-journal/cohort-asymmetric-shared-portfolio-v1.json")
_OUTPUT = Path(
    "data/runtime/bidirectional_cohort/latest_asymmetric_forward_observer.json"
)
_SUMMARY_FIELDS = (
    "closed_trades",
    "wins",
    "losses",
    "breakeven",
    "net_pnl_usd",
    "fees_usd",
    "funding_usd",
    "profit_factor",
    "mean_return_on_margin_pct",
    "median_return_on_margin_pct",
    "largest_winner_usd",
    "net_pnl_excluding_largest_winner_usd",
)


def build_parser() -> argparse.ArgumentParser:
    """Build the read-only forward-observer command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=_CHECKPOINT)
    parser.add_argument("--journal", type=Path, default=_JOURNAL)
    parser.add_argument("--out", type=Path, default=_OUTPUT)
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    """Build one report-only snapshot from strict checkpoint and journal inputs."""
    checkpoint = _load_json(args.checkpoint, "checkpoint")
    journal = _load_json(args.journal, "journal")
    audit = _checkpoint_audit(checkpoint)
    declaration, cutoff = _journal_cutoff(journal)
    run_identity = mapping(audit.get("run"), "checkpoint run")
    reflections = mapping(audit.get("trade_reflections"), "trade reflections")
    report = build_asymmetric_forward_observer(
        mapping_list(reflections.get("trades"), "reflected trades"),
        current_profile_fingerprint=text(
            run_identity.get("profile_fingerprint"), "profile fingerprint"
        ),
        current_run_id=text(run_identity.get("run_id"), "run id"),
        predeclared_at_utc=declaration,
        entry_cutoff_timestamp_ms=cutoff,
    )
    report["generated_at_utc"] = datetime.now(UTC).isoformat()
    report["evidence"] = {
        "checkpoint": _path_evidence(args.checkpoint),
        "journal": _path_evidence(args.journal),
    }
    return report


def command_summary(report: Mapping[str, object]) -> dict[str, object]:
    """Return compact decision telemetry without route-level detail."""
    return {
        "evidence_state": text(report.get("evidence_state"), "evidence state"),
        "source_counts": dict(mapping(report.get("source_counts"), "source counts")),
        "candidate": _economics_summary(report.get("candidate"), "candidate"),
        "excluded_symmetric_sides": _economics_summary(
            report.get("excluded_symmetric_sides"), "excluded symmetric sides"
        ),
    }


def _checkpoint_audit(checkpoint: Mapping[str, object]) -> Mapping[str, object]:
    contract = mapping(checkpoint.get("checkpoint_contract"), "checkpoint contract")
    if contract.get("report_only") is not True:
        raise ValueError("checkpoint must be report-only")
    if contract.get("execution_authority") != "none":
        raise ValueError("checkpoint execution authority must be none")
    if contract.get("runtime_strategy_changed") is not False:
        raise ValueError("checkpoint must not report a runtime strategy change")
    return mapping(checkpoint.get("audit"), "checkpoint audit")


def _journal_cutoff(journal: Mapping[str, object]) -> tuple[str, int]:
    declaration = asymmetric_forward_declaration(journal)
    return declaration.predeclared_at_utc, declaration.entry_cutoff_timestamp_ms


def _economics_summary(value: object, label: str) -> dict[str, object]:
    economics = mapping(value, label)
    missing = tuple(field for field in _SUMMARY_FIELDS if field not in economics)
    if missing:
        raise ValueError(f"{label} is missing fields: {', '.join(missing)}")
    return {field: economics[field] for field in _SUMMARY_FIELDS}


def _load_json(path: Path, label: str) -> Mapping[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"asymmetric observer {label} is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"asymmetric observer {label} must be an object")
    return value


def _path_evidence(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def main() -> None:
    """Refresh the bounded observer without touching the execution backend."""
    args = build_parser().parse_args()
    report = run(args)
    write_atomic_json(args.out, report)
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "execution_authority": "none",
                **command_summary(report),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
