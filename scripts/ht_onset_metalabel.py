#!/usr/bin/env python3
"""Publish purged report-only HT onset return-ranking evidence."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.ml.ht_onset_metalabel import evaluate_ht_onset_metalabel
from hypervector.research.hype_breakout_exit_market import build_hype_exit_market
from hypervector.research.mu_hip3_archive_provenance import (
    require_unchanged_generator,
    source_tree_identity,
)

MarketLoader = Callable[[Path, Path], tuple[pd.DataFrame, object]]


def build_parser() -> argparse.ArgumentParser:
    """Build explicit local-input and immutable-output arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", choices=("BTC", "ETH", "SOL"), required=True)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--funding", type=Path, required=True)
    parser.add_argument("--holdout-days", type=int, default=60)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def run_report(
    args: argparse.Namespace,
    *,
    market_loader: MarketLoader | None = None,
) -> dict[str, object]:
    """Build and immutably publish one source-stable HT ranker artifact."""
    bars = Path(args.bars)
    funding = Path(args.funding)
    _require_file(bars, "HT ranker bars")
    _require_file(funding, "HT ranker funding")
    expected = {"bars": file_evidence(bars), "funding": file_evidence(funding)}
    root = Path(__file__).resolve().parents[1]
    generator = source_tree_identity(root, Path(__file__).resolve())
    market, market_evidence = (market_loader or _load_market)(bars, funding)
    result = evaluate_ht_onset_metalabel(
        market,
        symbol=str(args.symbol),
        holdout_days=int(args.holdout_days),
    )
    report = dict(result.report)
    report["generated_at_utc"] = datetime.now(UTC).isoformat()
    report["evidence"] = {
        "bars": expected["bars"],
        "bars_path": str(bars.resolve()),
        "funding": expected["funding"],
        "funding_path": str(funding.resolve()),
        "market": _evidence_payload(market_evidence),
    }
    report["generator_identity"] = generator
    report = _json_safe(report)
    _require_unchanged_inputs(expected, bars, funding)
    require_unchanged_generator(generator, root, Path(__file__).resolve())
    write_immutable_json(Path(args.out), report)
    return report


def _load_market(bars: Path, funding: Path) -> tuple[pd.DataFrame, object]:
    raw_bars = pd.read_parquet(bars)
    funding_rows = pd.read_parquet(funding)
    return build_hype_exit_market(raw_bars, funding_rows)


def _evidence_payload(value: object) -> object:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)  # type: ignore[arg-type]
    return value


def _json_safe(report: dict[str, object]) -> dict[str, object]:
    encoded = json.dumps(report, allow_nan=False, sort_keys=True)
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise RuntimeError("HT ranker report did not encode as an object")
    return decoded


def _require_unchanged_inputs(
    expected: dict[str, dict[str, object]],
    bars: Path,
    funding: Path,
) -> None:
    observed = {"bars": file_evidence(bars), "funding": file_evidence(funding)}
    if observed != expected:
        raise ValueError("HT ranker input evidence changed during evaluation")


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} does not exist: {path}")


def main() -> int:
    """Publish one immutable report-only artifact."""
    args = build_parser().parse_args()
    report = run_report(args)
    later = report["later_already_opened"]
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(Path(args.out).resolve()),
                "execution_authority": "none",
                "later_already_opened": later,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
