#!/usr/bin/env python3
"""Replay pinned Hypertrader BTC B/C events with the source close-only method."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hypertrader_recipe_eval import (
    evaluate_close_recipe,
    summarize_close_recipe,
)
from hypervector.research.hypertrader_label_evidence import load_label_evidence
from hypervector.research.hypertrader_source_adapter import (
    PINNED_HYPERTRADER_REVISION,
    SOURCE_HASHES_BY_REVISION,
    annotate_signal_range_eligibility,
    extract_selective_recipe_events,
    extract_source_follow_all_day_events,
    load_hyperliquid_candles,
    resample_hyperliquid_5m,
    trend_aligned_selective_recipe_events,
)

_FRESH_START = pd.Timestamp("2026-07-27T00:00:00Z")
_FIXED_SLICE = pd.Timedelta(days=90)


def _positive_bps(value: str) -> float:
    bps = float(value)
    if not math.isfinite(bps) or bps <= 0.0:
        raise argparse.ArgumentTypeError("basis points must be finite and positive")
    return bps


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--labels-metadata", type=Path, required=True)
    parser.add_argument("--bars", type=Path, action="append", required=True)
    parser.add_argument("--creator-rows", type=Path, required=True)
    parser.add_argument(
        "--candidate-family",
        choices=("source-fade", "trend-aligned", "source-follow-all-day"),
        default="source-fade",
    )
    parser.add_argument("--maximum-signal-range-bps", type=_positive_bps)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _experiment_contract(
    candidate_family: str = "source-fade",
    *,
    upstream_revision: str = PINNED_HYPERTRADER_REVISION,
    maximum_signal_range_bps: float | None = None,
) -> dict[str, object]:
    return {
        "upstream_revision": upstream_revision,
        "report_only": True,
        "runtime_strategy_changed": False,
        "variants": ["source_independent", "one_position_serialized"],
        "target": "first close at 20bps OR 130 BTC points",
        "fee_bps_round_trip": 8.0,
        "stop_policy": "none",
        "candidate_family": candidate_family,
        "maximum_signal_range_bps": maximum_signal_range_bps,
        "model_authority": "observe",
    }


def _load_labels(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"pinned Hypertrader labels are missing: {path}")
    labels = pd.read_parquet(path)
    if not isinstance(labels.index, pd.DatetimeIndex):
        raise ValueError("pinned Hypertrader labels require a DatetimeIndex")
    labels.index = pd.DatetimeIndex(pd.to_datetime(labels.index, utc=True))
    return labels.sort_index(kind="stable")


def _candidate_events(labels: pd.DataFrame, candidate_family: str) -> pd.DataFrame:
    """Extract the requested source-faithful diagnostic event population."""
    if candidate_family == "source-follow-all-day":
        return extract_source_follow_all_day_events(labels)
    source_events = extract_selective_recipe_events(labels)
    if candidate_family == "source-fade":
        return source_events
    if candidate_family == "trend-aligned":
        return trend_aligned_selective_recipe_events(source_events)
    raise ValueError(f"unsupported close replay candidate: {candidate_family}")


def _range_eligible_events(
    events: pd.DataFrame,
    bars: pd.DataFrame,
    *,
    maximum_bps: float,
) -> pd.DataFrame:
    """Apply the maker-replay completed-bar ceiling to close diagnostics."""
    annotated = annotate_signal_range_eligibility(
        events,
        bars,
        maximum_range_bps=maximum_bps,
    )
    return annotated.loc[annotated["entry_eligible"]].reset_index(drop=True)


def _json_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    payload = json.loads(frame.to_json(orient="records", date_format="iso"))
    if not isinstance(payload, list):
        raise RuntimeError("Hypertrader close replay serialization failed")
    return payload


def _fixed_duration_slices(
    trades: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[dict[str, object]]:
    """Summarize consecutive 90-day windows over the complete study period."""
    if start.tz is None or end.tz is None or end <= start:
        raise ValueError("fixed replay slice bounds require increasing UTC timestamps")
    label_time = pd.to_datetime(trades["label_time_utc"], utc=True)
    rows: list[dict[str, object]] = []
    cursor = start.tz_convert("UTC")
    boundary = end.tz_convert("UTC")
    while cursor < boundary:
        stop = min(cursor + _FIXED_SLICE, boundary)
        selected = trades.loc[label_time.ge(cursor) & label_time.lt(stop)]
        rows.append(
            {
                "window_start_utc": cursor.isoformat(),
                "window_end_utc": stop.isoformat(),
                "summary": summarize_close_recipe(selected),
            }
        )
        cursor = stop
    return rows


def _summary_slices(
    trades: pd.DataFrame,
    bars: pd.DataFrame,
) -> dict[str, object]:
    label_time = pd.to_datetime(trades["label_time_utc"], utc=True)
    output: dict[str, object] = {
        "all": summarize_close_recipe(trades),
        "development_pre_20260727": summarize_close_recipe(
            trades.loc[label_time.lt(_FRESH_START)]
        ),
        "fresh_20260727": summarize_close_recipe(
            trades.loc[label_time.ge(_FRESH_START)]
        ),
        "fixed_90d": _fixed_duration_slices(
            trades,
            start=pd.Timestamp(bars.index[0]),
            end=pd.Timestamp(bars.index[-1]) + pd.Timedelta(minutes=5),
        ),
    }
    output["by_recipe"] = {
        recipe: summarize_close_recipe(trades.loc[trades["recipe_id"].eq(recipe)])
        for recipe in sorted(trades["recipe_id"].astype(str).unique())
    }
    return output


def _variant(
    events: pd.DataFrame, bars: pd.DataFrame, *, serialized: bool
) -> dict[str, object]:
    trades = evaluate_close_recipe(events, bars, serialized=serialized)
    return {"summary": _summary_slices(trades, bars), "trades": _json_records(trades)}


def _creator_alignment(path: Path, events: pd.DataFrame) -> list[dict[str, object]]:
    if not path.is_file():
        raise FileNotFoundError(f"creator recipe rows are missing: {path}")
    creator = pd.read_csv(path)
    required = {"evidence_id", "recipe_id", "entry_time_utc_inferred"}
    missing = required.difference(creator.columns)
    if missing:
        raise ValueError(f"creator recipe rows missing: {sorted(missing)}")
    creator["entry_time_utc_inferred"] = pd.to_datetime(
        creator["entry_time_utc_inferred"], utc=True
    )
    rows: list[dict[str, object]] = []
    for source in creator.to_dict(orient="records"):
        entry = pd.Timestamp(source["entry_time_utc_inferred"])
        candidates = events.loc[events["recipe_id"].eq(source["recipe_id"])]
        if candidates.empty:
            rows.append({**source, "closest_event": None})
            continue
        offsets = pd.to_datetime(candidates["label_time_utc"], utc=True) - entry
        closest = candidates.iloc[int(offsets.abs().argmin())]
        offset = pd.Timestamp(closest["label_time_utc"]) - entry
        decision_offset = pd.Timestamp(closest["decision_time_utc"]) - entry
        rows.append(
            {
                **source,
                "closest_event": pd.Timestamp(closest["label_time_utc"]),
                "label_offset_seconds": offset.total_seconds(),
                "decision_offset_seconds": decision_offset.total_seconds(),
                "label_match_within_5m": abs(offset) <= pd.Timedelta(minutes=5),
            }
        )
    return _json_records(pd.DataFrame(rows))


def _input_evidence(args: argparse.Namespace) -> dict[str, object]:
    return {
        "labels": file_evidence(args.labels),
        "labels_metadata": file_evidence(args.labels_metadata),
        "bars": [file_evidence(path) for path in args.bars],
        "creator_rows": file_evidence(args.creator_rows),
    }


def _report(args: argparse.Namespace) -> dict[str, object]:
    label_evidence = load_label_evidence(args.labels, args.labels_metadata)
    if label_evidence.revision not in SOURCE_HASHES_BY_REVISION:
        raise ValueError(
            f"unsupported Hypertrader label revision: {label_evidence.revision}"
        )
    labels = _load_labels(args.labels)
    candles = load_hyperliquid_candles(args.bars)
    bars = resample_hyperliquid_5m(candles)
    source_events = extract_selective_recipe_events(labels)
    candidate_events = _candidate_events(labels, args.candidate_family)
    events = (
        candidate_events
        if args.maximum_signal_range_bps is None
        else _range_eligible_events(
            candidate_events,
            bars,
            maximum_bps=args.maximum_signal_range_bps,
        )
    )
    return {
        **_experiment_contract(
            args.candidate_family,
            upstream_revision=label_evidence.revision,
            maximum_signal_range_bps=args.maximum_signal_range_bps,
        ),
        "inputs": _input_evidence(args),
        "candidate_event_count": len(candidate_events),
        "event_count": len(events),
        "creator_alignment": _creator_alignment(args.creator_rows, source_events),
        "source_independent": _variant(events, bars, serialized=False),
        "one_position_serialized": _variant(events, bars, serialized=True),
        "limitations": [
            "This diagnostic still uses five-minute closes, not maker fills.",
            "The source 26/26 rows were selected in-sample on different price inputs.",
            "Liquidation, funding, and chronological equity are deferred to maker replay.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Write an immutable close-only source replication artifact."""
    args = _parser().parse_args(argv)
    write_immutable_json(args.out, _report(args))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
