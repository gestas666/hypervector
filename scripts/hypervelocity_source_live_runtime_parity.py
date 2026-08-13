#!/usr/bin/env python3
"""Audit source-follow shadow telemetry against causal offline evidence."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.paper.report import load_decision_rows
from hypervector.research.hypertrader_label_evidence import load_label_evidence
from hypervector.research.hypertrader_source_adapter import (
    load_hyperliquid_candles,
    resample_hyperliquid_5m,
)
from hypervector.research.research_database_replay import canonical_trade_bars
from hypervector.research.source_follow_live_parity import (
    SourceFollowParityPolicy,
    audit_source_follow_live_rows,
)
from hypervector.strategies.source_follow_profile import load_source_follow_profile


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--labels-metadata", type=Path, required=True)
    market = parser.add_mutually_exclusive_group(required=True)
    market.add_argument("--database", type=Path)
    market.add_argument("--bars", type=Path, action="append")
    parser.add_argument("--start", type=_utc_datetime)
    parser.add_argument("--end", type=_utc_datetime)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _experiment_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "runtime_strategy_changed": False,
        "execution_authority": "none",
    }


def _report(args: argparse.Namespace) -> dict[str, object]:
    _validate_window(args.start, args.end)
    profile = load_source_follow_profile(args.profile)
    evidence = load_label_evidence(args.labels, args.labels_metadata)
    if evidence.revision != profile.source_revision:
        raise ValueError("live parity labels do not match the profile source revision")
    all_rows = load_decision_rows(args.decisions)
    rows = _selected_rows(all_rows, profile.profile_id, args.start, args.end)
    labels = pd.read_parquet(args.labels)
    bars, market_evidence = _market_bars(args, rows)
    policy = SourceFollowParityPolicy(
        profile_id=profile.profile_id,
        minimum_confidence=profile.minimum_confidence,
        minimum_range_bps=profile.minimum_range_bps,
        maximum_range_bps=profile.maximum_range_bps,
        decision_delay_seconds=profile.decision_delay_seconds,
        entry_pulse_seconds=profile.entry_pulse_seconds,
    )
    parity = audit_source_follow_live_rows(rows, labels, bars, policy)
    return {
        **_experiment_contract(),
        "source_revision": evidence.revision,
        "window": _window_summary(rows),
        "evidence": {
            **evidence.files,
            "profile": file_evidence(args.profile),
            "decisions": file_evidence(args.decisions),
            **market_evidence,
        },
        "parity": parity,
        "exact": parity["exact"],
        "limitations": [
            "Parity validates implementation consistency, not profitability.",
            "Unflushed recorder data remains uncovered and fails the audit.",
            "Forward promotion still requires resolved shadow trades.",
        ],
    }


def _selected_rows(
    rows: list[dict[str, object]],
    profile_id: str,
    start: datetime | None,
    end: datetime | None,
) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    for row in rows:
        if row.get("action") != "regime_observation":
            continue
        if row.get("profile_id") != profile_id:
            continue
        stamp = _row_timestamp(row)
        if start is not None and stamp < start:
            continue
        if end is not None and stamp >= end:
            continue
        selected.append(row)
    return selected


def _relevant_bars(
    database: Path,
    rows: list[dict[str, object]],
) -> pd.DataFrame:
    if not rows:
        return _empty_bars()
    labels = [
        _value_timestamp(row.get("source_follow_label_time_utc"), "label timestamp")
        for row in rows
    ]
    start = min(labels) - timedelta(minutes=5)
    end = max(labels) + timedelta(minutes=5)
    return canonical_trade_bars(database, "BTC", start, end)


def _market_bars(
    args: argparse.Namespace,
    rows: list[dict[str, object]],
) -> tuple[pd.DataFrame, dict[str, object]]:
    if args.database is not None:
        return _relevant_bars(args.database, rows), {
            "database": file_evidence(args.database)
        }
    paths = list(args.bars)
    candles = load_hyperliquid_candles(paths)
    return resample_hyperliquid_5m(candles), {
        "bars": [file_evidence(path) for path in paths]
    }


def _empty_bars() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["open", "high", "low", "close", "volume", "trade_count"],
        index=pd.DatetimeIndex([], tz="UTC"),
    )


def _window_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    if not rows:
        return {"observations": 0, "start_utc": None, "end_utc": None}
    stamps = [_row_timestamp(row) for row in rows]
    return {
        "observations": len(rows),
        "start_utc": min(stamps).isoformat(),
        "end_utc": max(stamps).isoformat(),
    }


def _row_timestamp(row: dict[str, object]) -> datetime:
    return _value_timestamp(row.get("feed_ts"), "ledger feed_ts")


def _value_timestamp(value: object, label: str) -> datetime:
    if value is None:
        raise ValueError(f"{label} is missing")
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware")
    return stamp.tz_convert("UTC").to_pydatetime().astimezone(UTC)


def _utc_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid UTC timestamp: {value}") from exc
    if parsed.utcoffset() != timedelta(0):
        raise argparse.ArgumentTypeError("timestamp must use UTC offset")
    return parsed.astimezone(UTC)


def _validate_window(start: datetime | None, end: datetime | None) -> None:
    if (start is None) != (end is None):
        raise ValueError("live parity requires both --start and --end")
    if start is not None and end is not None and end <= start:
        raise ValueError("live parity --end must be after --start")


def main(argv: list[str] | None = None) -> int:
    """Write immutable read-only evidence and fail on incomplete parity."""
    args = _parser().parse_args(argv)
    report = _report(args)
    write_immutable_json(args.out, report)
    print(f"wrote {args.out}")
    return 0 if report["exact"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
