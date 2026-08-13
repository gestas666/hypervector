#!/usr/bin/env python3
"""Publish a fixed executable near-miss matrix from live cohort evidence."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from contextlib import ExitStack
import json
from pathlib import Path

from hypervector.data.hl import hl_coin
from hypervector.data.hl_funding_evidence import (
    HlFundingEvidence,
    read_complete_hl_funding_evidence,
)
from hypervector.data.oxa_storage import write_immutable_json
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.research.cohort_execution_opportunity_matrix import (
    build_execution_opportunity_matrix,
    provider_replay_settings,
)
from hypervector.research.cohort_live_audit_values import run_id
from hypervector.research.cohort_live_run_selection import select_armed_live_run
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--funding",
        action="append",
        required=True,
        help="repeat SYMBOL=/absolute/or/relative/funding.parquet",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--horizon-minutes", type=int, default=60)
    parser.add_argument("--taker-fee-rate", type=float, default=0.000432)
    return parser


def _publish(args: argparse.Namespace) -> tuple[dict[str, object], Path]:
    config = load_multi_asset_live_config(args.config, mode="observe")
    funding_paths = _funding_paths(args.funding)
    with ExitStack() as stack:
        cohort_path = args.ledger_root / "decisions.jsonl"
        cohort, cohort_evidence = stack.enter_context(
            snapshot_decision_ledger(cohort_path)
        )
        selected, identity = select_armed_live_run(cohort, args.run_id)
        assets, asset_evidence = _asset_snapshots(stack, args.ledger_root, config)
        funding = _funding_evidence(funding_paths, config.symbols)
        report = build_execution_opportunity_matrix(
            selected,
            assets,
            {symbol: evidence.rows for symbol, evidence in funding.items()},
            settings_by_pair=provider_replay_settings(config),
            horizon_minutes=args.horizon_minutes,
            taker_fee_rate=args.taker_fee_rate,
        )
        _validate_funding_bounds(report, funding)
    report["evidence"] = {
        "run_id": run_id(identity),
        "config": str(args.config),
        "cohort": {"path": str(cohort_path), **cohort_evidence},
        "assets": asset_evidence,
        "funding": {symbol: evidence.evidence for symbol, evidence in funding.items()},
    }
    if args.out.exists():
        raise FileExistsError(f"immutable opportunity matrix exists: {args.out}")
    write_immutable_json(args.out, report)
    return report, args.out


def _asset_snapshots(
    stack: ExitStack,
    ledger_root: Path,
    config: MultiAssetLiveConfig,
) -> tuple[dict[str, list[dict[str, object]]], dict[str, dict[str, object]]]:
    rows: dict[str, list[dict[str, object]]] = {}
    evidence: dict[str, dict[str, object]] = {}
    for symbol in config.symbols:
        path = ledger_root / f"{symbol.lower()}.jsonl"
        asset_rows, facts = stack.enter_context(snapshot_decision_ledger(path))
        rows[symbol] = asset_rows
        evidence[symbol] = {"path": str(path), **facts}
    return rows, evidence


def _funding_paths(values: Sequence[str]) -> dict[str, Path]:
    output: dict[str, Path] = {}
    for value in values:
        symbol, separator, raw_path = value.partition("=")
        if not separator or not symbol.strip() or not raw_path.strip():
            raise ValueError("funding arguments require SYMBOL=PATH")
        normalized = hl_coin(symbol)
        if normalized in output:
            raise ValueError(f"duplicate funding path for {normalized}")
        output[normalized] = Path(raw_path)
    return output


def _funding_evidence(
    paths: Mapping[str, Path], symbols: Sequence[str]
) -> dict[str, HlFundingEvidence]:
    missing = sorted(set(symbols).difference(paths))
    if missing:
        raise ValueError(f"missing funding evidence for symbols: {missing}")
    return {
        symbol: read_complete_hl_funding_evidence(paths[symbol], symbol)
        for symbol in symbols
    }


def _validate_funding_bounds(
    report: Mapping[str, object], funding: Mapping[str, HlFundingEvidence]
) -> None:
    results = report.get("results")
    if not isinstance(results, list):
        raise ValueError("opportunity matrix results must be a list")
    for result in results:
        if not isinstance(result, dict):
            raise ValueError("opportunity matrix result must be an object")
        first = result.get("first_entry_time_ms")
        last = result.get("last_exit_time_ms")
        symbol = result.get("symbol")
        if first is None and last is None:
            continue
        if (
            not isinstance(first, int)
            or not isinstance(last, int)
            or not isinstance(symbol, str)
        ):
            raise ValueError("opportunity matrix interval is invalid")
        funding[symbol].require_covers(first, last)


def main(argv: Sequence[str] | None = None) -> int:
    """Publish all sparse, unfavorable, one-sided, and favorable rows unchanged."""
    report, output = _publish(_parser().parse_args(argv))
    results = report.get("results")
    if not isinstance(results, list):
        raise RuntimeError("opportunity matrix results are invalid")
    print(
        json.dumps(
            {
                "out": str(output),
                "hypotheses": report["hypotheses"],
                "comparisons": report["comparisons"],
                "resolved_comparisons": sum(
                    isinstance(row, dict) and int(row.get("resolved", 0)) > 0
                    for row in results
                ),
                "report_only": True,
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
