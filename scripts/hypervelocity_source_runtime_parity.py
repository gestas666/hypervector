#!/usr/bin/env python3
"""Verify pinned source runtime labels and events against immutable evidence."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
import math
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.regime.pinned_hypertrader import PinnedHypertraderClassifier
from hypervector.regime.source_follow_runtime import (
    FiveMinuteBar,
    SourceFollowDecision,
    SourceFollowRuntime,
)
from hypervector.research.hypertrader_label_evidence import load_label_evidence
from hypervector.research.hypertrader_source_adapter import (
    PINNED_HYPERTRADER_REVISION,
    annotate_signal_range_eligibility,
    load_hyperliquid_candles,
    resample_hyperliquid_5m,
)
from hypervector.research.hypertrader_source_confidence import (
    extract_source_follow_all_day_confidence_70_events,
)

_MISMATCH_LIMIT = 20


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-backend", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--labels-metadata", type=Path, required=True)
    parser.add_argument("--candles", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _experiment_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "runtime_strategy_changed": False,
        "execution_authority": "none",
        "entry_family": "source-follow-all-day-confidence-70",
        "decision_delay_seconds": 300,
        "entry_pulse_seconds": 60,
    }


def _compare_labels(
    labels: pd.DataFrame,
    decisions: Sequence[SourceFollowDecision],
) -> dict[str, object]:
    expected = {_utc_timestamp(stamp): row for stamp, row in labels.iterrows()}
    actual = {decision.label_time_utc: decision for decision in decisions}
    mismatches: list[dict[str, object]] = []
    mismatch_count = 0
    for stamp in sorted(set(expected) | set(actual)):
        row = expected.get(stamp)
        decision = actual.get(stamp)
        mismatch = _label_mismatch(stamp, row, decision)
        if mismatch is None:
            continue
        mismatch_count += 1
        if len(mismatches) < _MISMATCH_LIMIT:
            mismatches.append(mismatch)
    return {
        "exact": mismatch_count == 0,
        "expected_label_count": len(expected),
        "actual_label_count": len(actual),
        "mismatch_count": mismatch_count,
        "mismatches": mismatches,
    }


def _label_mismatch(
    stamp: datetime,
    row: pd.Series | None,
    decision: SourceFollowDecision | None,
) -> dict[str, object] | None:
    if row is None or decision is None:
        return {
            "label_time_utc": stamp.isoformat(),
            "expected_present": row is not None,
            "actual_present": decision is not None,
        }
    expected_primary = str(row["primary_code"])
    expected_secondary = _optional_text(row["secondary_code"])
    expected_confidence = float(row["confidence"])
    expected_available = _expected_available_at(stamp, row)
    equal = (
        decision.primary == expected_primary
        and decision.secondary == expected_secondary
        and decision.confidence == expected_confidence
        and decision.available_at_utc == expected_available
    )
    if equal:
        return None
    return {
        "label_time_utc": stamp.isoformat(),
        "expected_primary": expected_primary,
        "actual_primary": decision.primary,
        "expected_secondary": expected_secondary,
        "actual_secondary": decision.secondary,
        "expected_confidence": expected_confidence,
        "actual_confidence": decision.confidence,
        "expected_available_at": expected_available.isoformat(),
        "actual_available_at": decision.available_at_utc.isoformat(),
    }


def _compare_events(
    expected_events: pd.DataFrame,
    decisions: Sequence[SourceFollowDecision],
) -> dict[str, object]:
    expected = {
        _utc_timestamp(row["label_time_utc"]): row
        for _, row in expected_events.iterrows()
    }
    actual = {
        decision.label_time_utc: decision
        for decision in decisions
        if decision.source_event
    }
    mismatches: list[dict[str, object]] = []
    mismatch_count = 0
    for stamp in sorted(set(expected) | set(actual)):
        row = expected.get(stamp)
        decision = actual.get(stamp)
        mismatch = _event_mismatch(stamp, row, decision)
        if mismatch is None:
            continue
        mismatch_count += 1
        if len(mismatches) < _MISMATCH_LIMIT:
            mismatches.append(mismatch)
    return {
        "exact": mismatch_count == 0,
        "expected_event_count": len(expected),
        "actual_event_count": len(actual),
        "eligible_entry_count": sum(
            decision.entry_eligible for decision in actual.values()
        ),
        "mismatch_count": mismatch_count,
        "mismatches": mismatches,
    }


def _event_mismatch(
    stamp: datetime,
    row: pd.Series | None,
    decision: SourceFollowDecision | None,
) -> dict[str, object] | None:
    if row is None or decision is None:
        return {
            "label_time_utc": stamp.isoformat(),
            "expected_present": row is not None,
            "actual_present": decision is not None,
        }
    expected_available = _utc_timestamp(row["decision_time_utc"])
    expected_confidence = float(row["confidence"])
    expected_range = float(row["signal_range_bps"])
    expected_eligible = bool(row["entry_eligible"])
    equal = (
        decision.available_at_utc == expected_available
        and decision.confidence == expected_confidence
        and math.isclose(
            decision.signal_range_bps,
            expected_range,
            rel_tol=0.0,
            abs_tol=1e-10,
        )
        and decision.entry_eligible == expected_eligible
    )
    if equal:
        return None
    return {
        "label_time_utc": stamp.isoformat(),
        "expected_available_at": expected_available.isoformat(),
        "actual_available_at": decision.available_at_utc.isoformat(),
        "expected_confidence": expected_confidence,
        "actual_confidence": decision.confidence,
        "expected_range_bps": expected_range,
        "actual_range_bps": decision.signal_range_bps,
        "expected_entry_eligible": expected_eligible,
        "actual_entry_eligible": decision.entry_eligible,
    }


def _report(args: argparse.Namespace) -> dict[str, object]:
    label_evidence = load_label_evidence(args.labels, args.labels_metadata)
    if label_evidence.revision != PINNED_HYPERTRADER_REVISION:
        raise ValueError(
            "source runtime parity requires the exact pinned Hypertrader revision"
        )
    labels = _load_labels(args.labels)
    candles = load_hyperliquid_candles(args.candles)
    bars = resample_hyperliquid_5m(candles)
    if not bars.index.equals(labels.index):
        raise ValueError("source labels and five-minute bars require identical indexes")
    classifier = PinnedHypertraderClassifier(args.upstream_backend)
    runtime = SourceFollowRuntime(classifier)
    decisions = [
        runtime.update(_source_bar(stamp, row)) for stamp, row in bars.iterrows()
    ]
    expected_events = annotate_signal_range_eligibility(
        extract_source_follow_all_day_confidence_70_events(labels),
        bars,
        maximum_range_bps=100.0,
    )
    label_parity = _compare_labels(labels, decisions)
    event_parity = _compare_events(expected_events, decisions)
    return {
        **_experiment_contract(),
        "source_revision": label_evidence.revision,
        "source_identity": classifier.source_identity,
        "evidence": {
            **label_evidence.files,
            "candles": [file_evidence(path) for path in args.candles],
        },
        "bars": len(bars),
        "label_parity": label_parity,
        "event_parity": event_parity,
        "exact": bool(label_parity["exact"] and event_parity["exact"]),
        "limitations": [
            "Parity proves local reproduction of one pinned revision, not edge.",
            "The source confidence is rule agreement, not calibrated probability.",
            "Execution remains disabled until a separate shadow profile is verified.",
        ],
    }


def _load_labels(path: Path) -> pd.DataFrame:
    labels = pd.read_parquet(path)
    if not isinstance(labels.index, pd.DatetimeIndex):
        raise ValueError("source labels require a DatetimeIndex")
    labels.index = pd.DatetimeIndex(pd.to_datetime(labels.index, utc=True))
    required = {"primary_code", "secondary_code", "confidence"}
    missing = required.difference(labels.columns)
    if missing:
        raise ValueError(f"source labels missing columns: {sorted(missing)}")
    if not labels.index.is_monotonic_increasing or not labels.index.is_unique:
        raise ValueError("source label timestamps must be ordered and unique")
    return labels


def _source_bar(stamp: object, row: pd.Series) -> FiveMinuteBar:
    return FiveMinuteBar(
        timestamp_utc=_utc_timestamp(stamp),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]),
    )


def _expected_available_at(stamp: datetime, row: pd.Series) -> datetime:
    available = row.get("available_at")
    return (
        stamp + timedelta(minutes=5)
        if available is None or pd.isna(available)
        else _utc_timestamp(available)
    )


def _optional_text(value: object) -> str | None:
    return None if value is None or pd.isna(value) else str(value)


def _utc_timestamp(value: object) -> datetime:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("source timestamp must be timezone-aware")
    return timestamp.tz_convert("UTC").to_pydatetime().astimezone(UTC)


def main(argv: list[str] | None = None) -> int:
    """Write an immutable parity report and fail on any disagreement."""
    args = _parser().parse_args(argv)
    report = _report(args)
    write_immutable_json(args.out, report)
    print(f"wrote {args.out}")
    return 0 if report["exact"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
