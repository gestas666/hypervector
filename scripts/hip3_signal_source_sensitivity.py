#!/usr/bin/env python3
"""Compare one frozen HIP-3 route across two development signal sources."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import UTC, datetime
import hashlib
from pathlib import Path

import pandas as pd

import hip3_development_diagnostic as development
import mu_hip3_archive_research as archive
from hypervector.data.hip3_public_candles import Hip3PublicCandleSource
from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)
from hypervector.research.hip3_development_provenance import (
    loaded_project_source_paths,
    require_unchanged_dependencies,
    require_unchanged_file,
    source_dependency_identity,
)
from hypervector.research.hip3_midpoint_bars import Hip3MidpointBars
from hypervector.research.hip3_signal_source_sensitivity import (
    build_hip3_signal_source_sensitivity,
)
from hypervector.research.hip3_transfer_sources import (
    FundingAttachmentEvidence,
    attach_official_funding,
)
from hypervector.research.mu_hip3_archive_candidate import MuArchiveExecution

_HOLD_BARS = 96


def build_parser() -> argparse.ArgumentParser:
    """Return the report-only source-sensitivity parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True, type=archive._hip3_symbol_argument)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--funding", required=True, type=Path)
    parser.add_argument("--start", required=True, type=archive._utc_argument)
    parser.add_argument("--end", required=True, type=archive._utc_argument)
    parser.add_argument("--qualification-report", required=True, type=Path)
    parser.add_argument("--liquidity-report", required=True, type=Path)
    parser.add_argument("--archive-audit-report", required=True, type=Path)
    parser.add_argument("--development-report", required=True, type=Path)
    parser.add_argument("--observed-at", required=True, type=archive._utc_argument)
    parser.add_argument("--nominal-latency-bps-per-side", type=float, default=1.0)
    parser.add_argument("--stress-latency-bps-per-side", type=float, default=2.0)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def run_command(args: argparse.Namespace) -> dict[str, object]:
    """Build and immutably publish one fixed-config development comparison."""
    archive.require_new_outputs(args.output)
    generator = _generator_identity()
    qualification, liquidity, audit = development._load_inputs(args)
    start, end = development._validated_scope(args, audit)
    database_evidence = development._file_reference(args.database)
    midpoint = _load_midpoint(args, audit, start, end)
    funding, funding_input = archive._load_funding_input(
        args, str(args.symbol), start.floor("h"), end.ceil("h"), _forbidden_fetch
    )
    bars, attachment = attach_official_funding(midpoint.bars, funding)
    execution = replace(
        archive._execution(args, qualification, liquidity, str(args.symbol)),
        maximum_hold_bars=_HOLD_BARS,
        **archive._risk_path_columns(bars),
    )
    selected, development_end = _selected_contract(args)
    venue, source = _venue_candles(args, selected, development_end)
    comparison_start = max(development_end - pd.Timedelta(days=90), venue.index[0])
    comparison_start = max(comparison_start, pd.Timestamp(selected["start_utc"]))
    sensitivity = build_hip3_signal_source_sensitivity(
        bars=bars,
        venue_ohlc=venue,
        config=selected["config"],
        execution=execution,
        start_utc=comparison_start,
        end_utc=development_end,
    )
    report = _report(
        args,
        sensitivity,
        source,
        attachment,
        funding_input,
        execution,
        generator,
        database_evidence,
    )
    _require_unchanged(args, generator, database_evidence, funding_input)
    write_immutable_json(args.output, report)
    return report


def _load_midpoint(
    args: argparse.Namespace,
    audit: dict[str, object],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> Hip3MidpointBars:
    return development._load_midpoints(args, audit, start, end)["15m"]


def _selected_contract(
    args: argparse.Namespace,
) -> tuple[dict[str, object], pd.Timestamp]:
    report = archive._load_json(args.development_report)
    selected = archive._mapping(
        report.get("development_selected_track"), "development selected track"
    )
    expected = (str(args.symbol), "15m", "breakout_pressure")
    observed = (
        selected.get("symbol"),
        selected.get("timeframe"),
        selected.get("family"),
    )
    if observed != expected:
        raise ValueError("development report is not the requested frozen route")
    config = archive._mapping(selected.get("config"), "selected config")
    window = archive._mapping(report.get("development_window"), "development window")
    return {
        "start_utc": window["start_utc"],
        "identity": selected,
        "config": Hip3BreakoutPressureConfig(**config),
    }, pd.Timestamp(window["end_utc"])


def _venue_candles(
    args: argparse.Namespace,
    selected: dict[str, object],
    development_end: pd.Timestamp,
) -> tuple[pd.DataFrame, dict[str, object]]:
    observed = pd.Timestamp(args.observed_at)
    frame = Hip3PublicCandleSource().completed_candles(
        symbol=str(args.symbol),
        start_ms=_epoch_ms(pd.Timestamp(selected["start_utc"])),
        end_ms=_epoch_ms(development_end),
        observed_at_ms=_epoch_ms(observed),
    )
    candles = _normalized_candles(frame, development_end)
    source = {
        "source": "hyperliquid_info_candleSnapshot_15m",
        "observed_at_utc": observed.isoformat(),
        "returned_rows": len(frame),
        "comparison_rows": len(candles),
        "comparison_start_utc": candles.index[0].isoformat(),
        "comparison_end_exclusive_utc": development_end.isoformat(),
        "comparison_sha256": _frame_sha256(candles),
    }
    return candles, source


def _normalized_candles(
    frame: pd.DataFrame, development_end: pd.Timestamp
) -> pd.DataFrame:
    required = ["timestamp", "open", "high", "low", "close"]
    missing = sorted(set(required).difference(frame.columns))
    if missing:
        raise ValueError(f"public candle source missing columns: {missing}")
    candles = frame.loc[:, required].copy()
    candles["timestamp"] = pd.to_datetime(candles["timestamp"], utc=True)
    candles = candles.loc[candles["timestamp"] < development_end]
    candles = candles.set_index("timestamp").sort_index()
    if candles.empty or candles.index.duplicated().any():
        raise ValueError("public candle source is empty or duplicated")
    return candles.loc[:, ["open", "high", "low", "close"]].astype(float)


def _report(
    args: argparse.Namespace,
    sensitivity: dict[str, object],
    source: dict[str, object],
    attachment: FundingAttachmentEvidence,
    funding_input: dict[str, object],
    execution: MuArchiveExecution,
    generator: dict[str, object],
    database_evidence: dict[str, object],
) -> dict[str, object]:
    return {
        **sensitivity,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "venue_candle_evidence": source,
        "funding_input": funding_input,
        "funding_attachment": asdict(attachment),
        "execution_friction": asdict(execution),
        "source_evidence": {
            "database": {"path": str(args.database.resolve()), **database_evidence},
            "development_report": development._file_reference(args.development_report),
            "archive_audit": development._file_reference(args.archive_audit_report),
            "qualification": development._file_reference(args.qualification_report),
            "liquidity": development._file_reference(args.liquidity_report),
        },
        "generator_identity": generator,
        "limitations": [
            "the common window is development data and is not out-of-sample",
            "this fixed-route comparison cannot retune or authorize a strategy",
            "risk and fills use archived exact venue paths, not live execution",
        ],
    }


def _require_unchanged(
    args: argparse.Namespace,
    generator: dict[str, object],
    database: dict[str, object],
    funding: dict[str, object],
) -> None:
    root = Path(__file__).resolve().parents[1]
    require_unchanged_dependencies(generator, root)
    require_unchanged_file(args.database, database)
    archive._require_funding_input_unchanged(args, str(args.symbol), funding)


def _generator_identity() -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    paths = loaded_project_source_paths(root, Path(__file__).resolve())
    return source_dependency_identity(root, paths)


def _frame_sha256(frame: pd.DataFrame) -> str:
    encoded = frame.to_csv(index=True, float_format="%.12g").encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _epoch_ms(value: pd.Timestamp) -> int:
    if value.tzinfo is None:
        raise ValueError("source timestamp must include timezone")
    return int(value.timestamp() * 1_000)


def _forbidden_fetch(*_args: object, **_kwargs: object) -> pd.DataFrame:
    raise RuntimeError("signal-source sensitivity forbids network funding fetches")


def main() -> int:
    """Run the immutable report-only comparison."""
    args = build_parser().parse_args()
    run_command(args)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
