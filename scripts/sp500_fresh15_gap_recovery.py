#!/usr/bin/env python3
"""Publish an immutable report-only SP500 outage mark recovery audit."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
from pathlib import Path
import sys
from typing import cast

import pandas as pd

from hypervector.data.jsonl_prefix import (
    read_jsonl_prefix,
    require_jsonl_prefix_unchanged,
)
from hypervector.data.oxa_storage import (
    file_evidence,
    verify_file_evidence,
    write_immutable_json,
)
from hypervector.research.sp500_fresh15_gap_recovery import (
    Sp500Fresh15GapRecoveryConfig,
    build_sp500_fresh15_gap_recovery,
)

Record = dict[str, object]


def build_parser() -> argparse.ArgumentParser:
    """Build the no-authority SP500 outage recovery command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--watcher-status", type=Path, required=True)
    parser.add_argument("--decision-journal", type=Path, required=True)
    parser.add_argument("--candle-journal", type=Path, required=True)
    parser.add_argument("--price-archive", type=Path, required=True)
    parser.add_argument("--maximum-mark-gap-ms", type=int, default=5_000)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def run_command(args: argparse.Namespace) -> Record:
    """Verify bounded evidence and publish one immutable recovery report."""
    output = Path(args.output)
    _require_new_output(output)
    paths = _paths(args)
    _require_distinct((*paths.values(), output))
    fixed = _fixed_inputs(paths)
    decisions, decision_evidence = read_jsonl_prefix(
        paths["decision_journal"], "SP500 decision journal"
    )
    candles, candle_evidence = read_jsonl_prefix(
        paths["candle_journal"], "SP500 candle journal"
    )
    generator = _generator_identity()
    report = _build(args, fixed, decisions, candles)
    _require_unchanged(paths, fixed, decision_evidence, candle_evidence, generator)
    report["input_evidence"] = _input_evidence(
        paths, fixed, decision_evidence, candle_evidence
    )
    report["generator_identity"] = generator
    write_immutable_json(output, report)
    return report


def _paths(args: argparse.Namespace) -> dict[str, Path]:
    archive = Path(args.price_archive)
    return {
        "preregistration": Path(args.preregistration),
        "watcher_status": Path(args.watcher_status),
        "decision_journal": Path(args.decision_journal),
        "candle_journal": Path(args.candle_journal),
        "price_manifest": archive / "manifest.json",
        "prices": archive / "prices.parquet",
    }


def _fixed_inputs(paths: Mapping[str, Path]) -> dict[str, object]:
    manifest = _json_object(paths["price_manifest"], "price manifest")
    verify_file_evidence(paths["price_manifest"].parent, manifest.get("files"))
    return {
        "preregistration": _json_object(paths["preregistration"], "preregistration"),
        "watcher_status": _json_object(paths["watcher_status"], "watcher status"),
        "price_manifest": manifest,
        "prices": pd.read_parquet(paths["prices"]),
        "evidence": {
            key: _path_evidence(paths[key])
            for key in ("preregistration", "watcher_status", "price_manifest", "prices")
        },
    }


def _build(
    args: argparse.Namespace,
    fixed: Mapping[str, object],
    decisions: Sequence[Mapping[str, object]],
    candles: Sequence[Mapping[str, object]],
) -> Record:
    return build_sp500_fresh15_gap_recovery(
        preregistration=_mapping(fixed.get("preregistration"), "preregistration"),
        watcher_status=_mapping(fixed.get("watcher_status"), "watcher status"),
        decisions=decisions,
        candles=candles,
        price_manifest=_mapping(fixed.get("price_manifest"), "price manifest"),
        prices=_frame(fixed.get("prices")),
        config=Sp500Fresh15GapRecoveryConfig(
            int(getattr(args, "maximum_mark_gap_ms", 5_000))
        ),
    )


def _require_unchanged(
    paths: Mapping[str, Path],
    fixed: Mapping[str, object],
    decision_evidence: Mapping[str, object],
    candle_evidence: Mapping[str, object],
    generator: Mapping[str, object],
) -> None:
    expected = _mapping(fixed.get("evidence"), "fixed evidence")
    for key, evidence in expected.items():
        if _path_evidence(paths[key]) != evidence:
            raise ValueError(f"SP500 recovery input changed: {paths[key]}")
    require_jsonl_prefix_unchanged(
        paths["decision_journal"], decision_evidence, "SP500 decision journal"
    )
    require_jsonl_prefix_unchanged(
        paths["candle_journal"], candle_evidence, "SP500 candle journal"
    )
    if _generator_identity() != dict(generator):
        raise ValueError("SP500 recovery generator changed during evaluation")


def _input_evidence(
    paths: Mapping[str, Path],
    fixed: Mapping[str, object],
    decisions: Mapping[str, object],
    candles: Mapping[str, object],
) -> Record:
    output = dict(_mapping(fixed.get("evidence"), "fixed evidence"))
    output["decision_journal_prefix"] = dict(decisions)
    output["candle_journal_prefix"] = dict(candles)
    output["price_archive"] = str(paths["price_manifest"].parent.resolve())
    return output


def _generator_identity() -> Record:
    root = Path(__file__).resolve().parents[1]
    paths = (
        Path(__file__).resolve(),
        root / "src/hypervector/research/sp500_fresh15_gap_recovery.py",
        root / "src/hypervector/research/hip3_prospective_path_audit.py",
        root / "src/hypervector/cohort_profit_lock_policy.py",
        root / "src/hypervector/data/jsonl_prefix.py",
        root / "src/hypervector/data/oxa_storage.py",
    )
    return {
        str(path.relative_to(root)): {"path": str(path), **file_evidence(path)}
        for path in paths
    }


def _json_object(path: Path, label: str) -> Record:
    if not path.is_file():
        raise FileNotFoundError(f"SP500 recovery {label} is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"SP500 recovery {label} must be an object")
    return cast(Record, value)


def _path_evidence(path: Path) -> Record:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"SP500 recovery {label} must be an object")
    return value


def _frame(value: object) -> pd.DataFrame:
    if not isinstance(value, pd.DataFrame):
        raise ValueError("SP500 recovery prices must be a data frame")
    return value


def _require_distinct(paths: Sequence[Path]) -> None:
    resolved = tuple(path.resolve() for path in paths)
    if len(set(resolved)) != len(resolved):
        raise ValueError("SP500 recovery paths must be distinct")


def _require_new_output(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"SP500 recovery output already exists: {path}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the report-only audit and print a compact technical result."""
    args = build_parser().parse_args(argv)
    try:
        report = run_command(args)
    except (FileExistsError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(Path(args.output).resolve()),
                "disposition": report["disposition"],
                "technical_assessment": report["technical_assessment"],
                "execution_authority": "none",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
