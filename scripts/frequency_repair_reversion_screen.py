"""Evaluate the frozen band-recovery hypothesis with the prior screen's costs."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

import frequency_repair_screen as baseline
from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hip3_transfer_sources import attach_official_funding
from hypervector.research.hourly_band_reentry import (
    STRATEGY,
    build_hourly_band_reentry_signals,
)


def evaluate(directory: Path, symbol: str) -> list[dict[str, object]]:
    """Reuse the identical native inputs and execution/cost comparison."""
    source = directory / symbol.replace(":", "_")
    bars, funding_evidence = attach_official_funding(
        pd.read_parquet(source / "bars.parquet"),
        pd.read_parquet(source / "funding.parquet"),
    )
    if funding_evidence.unassigned_event_count or funding_evidence.delayed_event_count:
        raise ValueError(f"{symbol}: incomplete native funding assignment")
    signals = build_hourly_band_reentry_signals(bars)
    output = [
        baseline.run_case(
            bars,
            signals,
            baseline.execution_config(symbol, slip, fee),
            window,
            STRATEGY,
            cost,
        )
        for cost, slip, fee in baseline.COSTS
        for window in baseline.WINDOWS
    ]
    for row in output:
        if row["window"] == "continuous":
            print({key: row[key] for key in ("symbol", "cost", "activity")}, flush=True)
    return output


def main() -> None:
    """Write all outcomes without parameter selection or execution authority."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    cases = [
        row for symbol in baseline.SYMBOLS for row in evaluate(args.input_dir, symbol)
    ]
    paths = [
        Path(__file__),
        Path(baseline.__file__),
        args.input_dir / "manifest.json",
        Path("docs/research/frequency-noncrypto-reversion-protocol-20260907.md"),
        Path("src/hypervector/research/hourly_band_reentry.py"),
    ]
    paths.extend(sorted(args.input_dir.rglob("*.parquet")))
    write_immutable_json(
        args.out,
        {
            "schema_version": 1,
            "execution_authority": "none",
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
            "cases": cases,
            "evidence": {str(path.resolve()): file_evidence(path) for path in paths},
            "limitations": [
                "Exploratory second mechanism after inspecting first-screen aggregate results.",
                "Native candle OHLC conditional fills; no receipt, depth or private fill reconstruction.",
                "Chronological extension has prior research exposure, not pristine OOS.",
                "Independent asset screens; shared capital and native liquidation marks remain unvalidated.",
            ],
        },
    )


if __name__ == "__main__":
    main()
