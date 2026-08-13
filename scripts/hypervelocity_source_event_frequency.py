#!/usr/bin/env python3
"""Publish causal event cadence for one frozen source-follow profile."""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Sequence
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hypertrader_label_evidence import load_label_evidence
from hypervector.research.hypertrader_source_adapter import (
    load_hyperliquid_candles,
    resample_hyperliquid_5m,
)
from hypervector.research.source_follow_event_frequency import (
    SourceFollowFrequencyPolicy,
    audit_source_follow_event_frequency,
)
from hypervector.strategies.source_follow_profile import load_source_follow_profile


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--labels-metadata", type=Path, required=True)
    parser.add_argument("--candles", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _report(args: argparse.Namespace) -> dict[str, object]:
    profile = load_source_follow_profile(args.profile)
    label_evidence = load_label_evidence(args.labels, args.labels_metadata)
    if label_evidence.revision != profile.source_revision:
        raise ValueError("frequency labels do not match the profile source revision")
    labels = pd.read_parquet(args.labels)
    labels.index = pd.DatetimeIndex(pd.to_datetime(labels.index, utc=True))
    candle_sources = _candle_source_counts(args.candles)
    candles = load_hyperliquid_candles(args.candles)
    report = audit_source_follow_event_frequency(
        labels,
        resample_hyperliquid_5m(candles),
        SourceFollowFrequencyPolicy(
            minimum_confidence=profile.minimum_confidence,
            minimum_range_bps=profile.minimum_range_bps,
            maximum_range_bps=profile.maximum_range_bps,
        ),
    )
    report["profile_id"] = profile.profile_id
    report["source_revision"] = label_evidence.revision
    report["candle_sources"] = candle_sources
    report["evidence"] = {
        **label_evidence.files,
        "profile": file_evidence(args.profile),
        "candles": [file_evidence(path) for path in args.candles],
    }
    return report


def _candle_source_counts(paths: Sequence[Path]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for path in paths:
        source = pd.read_parquet(path, columns=["source"])["source"].astype(str)
        counts.update(source)
    unexpected = sorted(set(counts).difference({"hl", "hl_gap_fill"}))
    if unexpected:
        raise ValueError(
            f"frequency candles contain non-Hyperliquid sources: {unexpected}"
        )
    return dict(sorted(counts.items()))


def _publish(args: argparse.Namespace) -> dict[str, object]:
    if args.out.exists():
        raise FileExistsError(f"immutable frequency output exists: {args.out}")
    report = _report(args)
    write_immutable_json(args.out, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Publish a no-execution source-event frequency audit."""
    args = _parser().parse_args(argv)
    report = _publish(args)
    print(
        json.dumps(
            {
                "out": str(args.out),
                "eligible_events": report["eligible_events"],
                "report_only": report["report_only"],
                "execution_authority": report["execution_authority"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
