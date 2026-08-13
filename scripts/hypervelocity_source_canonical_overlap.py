#!/usr/bin/env python3
"""Audit source short-event overlap with causal canonical regime decisions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.regime.composite import classify_multitimeframe
from hypervector.research.hypertrader_source_confidence import (
    extract_source_follow_session_06_15_confidence_70_events,
)
from hypervector.research.hypervelocity_replay_evidence import decision_identity
from hypervector.research.hypervelocity_source_canonical_overlap import (
    align_source_events_to_canonical_decisions,
    summarize_source_canonical_overlap,
)
from hypervector.strategies.hypervelocity_profile import load_hypervelocity_profile


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", required=True, type=Path)
    parser.add_argument("--source-labels", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser


def _load_bars(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"canonical bars are missing: {path}")
    bars = pd.read_parquet(path)
    if "timestamp" not in bars:
        raise ValueError("canonical bars require timestamp")
    bars = bars.set_index(pd.to_datetime(bars.pop("timestamp"), utc=True))
    if not bars.index.is_unique:
        raise ValueError("canonical bar timestamps must be unique")
    return bars.sort_index(kind="stable")


def _load_events(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"source labels are missing: {path}")
    labels = pd.read_parquet(path)
    return extract_source_follow_session_06_15_confidence_70_events(labels)


def _json_rows(frame: pd.DataFrame) -> list[dict[str, object]]:
    encoded = frame.to_json(orient="records", date_format="iso", date_unit="us")
    decoded = json.loads(encoded)
    if not isinstance(decoded, list):
        raise TypeError("aligned overlap rows did not encode as a list")
    return decoded


def _input_evidence(paths: dict[str, Path]) -> dict[str, object]:
    return {
        name: {"path": str(path), **file_evidence(path)} for name, path in paths.items()
    }


def _report(args: argparse.Namespace) -> dict[str, object]:
    profile = load_hypervelocity_profile(args.config)
    bars = _load_bars(args.bars)
    events = _load_events(args.source_labels)
    decisions = classify_multitimeframe(bars, profile.regime_config)
    aligned = align_source_events_to_canonical_decisions(events, decisions)
    return {
        "schema_version": 1,
        "experiment": {
            "report_only": True,
            "runtime_strategy_changed": False,
            "source_event_policy": "trend_down_session_06_15_min_confidence_0_70",
            "canonical_alignment": "decision_time_minus_one_completed_minute_bar",
            "nearest_onset_is_diagnostic_only": True,
            "model_authority": "observe",
        },
        "inputs": _input_evidence(
            {
                "bars": args.bars,
                "source_labels": args.source_labels,
                "config": args.config,
            }
        ),
        "canonical_decision_identity_sha256": decision_identity(decisions),
        "summary": summarize_source_canonical_overlap(aligned),
        "rows": _json_rows(aligned),
    }


def main() -> None:
    """Run the immutable report-only source/canonical overlap audit."""
    args = _parser().parse_args()
    write_immutable_json(args.out, _report(args))
    print(args.out)


if __name__ == "__main__":
    main()
