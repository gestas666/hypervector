#!/usr/bin/env python3
"""Run the frozen report-only BTC/SOL flow-exhaustion development screen."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    write_immutable_json,
    write_immutable_parquet,
)
from hypervector.research.flow_exhaustion_data import (
    assemble_flow_exhaustion_rows,
    load_flow_exhaustion_minute_path,
)
from hypervector.research.flow_exhaustion_replay import (
    FlowExhaustionReplayConfig,
    replay_flow_exhaustion_signals,
)
from hypervector.research.flow_exhaustion_replay_models import (
    FlowExhaustionRejection,
    FlowExhaustionReplayReport,
    FlowExhaustionTrade,
)
from hypervector.research.flow_exhaustion_reporting import (
    assess_flow_exhaustion_development,
)
from hypervector.research.flow_exhaustion_signals import (
    FlowExhaustionSignalConfig,
    FlowExhaustionSignalReport,
    build_segmented_flow_exhaustion_signals,
)
from hypervector.research.low_tf_duckdb import (
    LowTimeframeInputFrames,
    load_low_timeframe_inputs,
)


_SCHEMA_VERSION = "flow_exhaustion_development_v1"
_DEVELOPMENT_START = datetime(2025, 8, 4, tzinfo=UTC)
_DEVELOPMENT_END = datetime(2026, 1, 28, tzinfo=UTC)
_HISTORY_BARS = 2_016
_HORIZON_BARS = 6


@dataclass(frozen=True)
class _ScreenResult:
    """All in-memory evidence for one frozen development run."""

    signal_config: FlowExhaustionSignalConfig
    nominal_config: FlowExhaustionReplayConfig
    stress_config: FlowExhaustionReplayConfig
    funding_paths: dict[str, tuple[Path, ...]]
    inputs: dict[str, LowTimeframeInputFrames]
    signal_reports: dict[str, FlowExhaustionSignalReport]
    signals: pd.DataFrame
    nominal: FlowExhaustionReplayReport
    stress: FlowExhaustionReplayReport
    assessment: dict[str, object]


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit report-only research command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--segment", required=True, choices=("development",))
    parser.add_argument("--btc-funding", required=True, type=Path, action="append")
    parser.add_argument("--sol-funding", required=True, type=Path, action="append")
    parser.add_argument("--out", required=True, type=Path)
    return parser


def validated_window(args: argparse.Namespace) -> tuple[datetime, datetime]:
    """Require the data-boundary-amended preregistered development window."""
    start, end = _timestamp(str(args.start)), _timestamp(str(args.end))
    if start != _DEVELOPMENT_START or end != _DEVELOPMENT_END:
        raise ValueError(
            "flow-exhaustion screen requires the frozen development window "
            f"{_DEVELOPMENT_START.isoformat()} to {_DEVELOPMENT_END.isoformat()}"
        )
    return start, end


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the frozen development screen and publish immutable evidence."""
    args = build_parser().parse_args(argv)
    start, end = validated_window(args)
    output = Path(args.out)
    sidecars = _sidecar_paths(output)
    _ensure_outputs_available(output, tuple(sidecars.values()))
    result = _execute_screen(args, start, end)
    frames = _sidecar_frames(result.signals, result.nominal, result.stress)
    for name, path in sidecars.items():
        write_immutable_parquet(path, frames[name])
    write_immutable_json(output, _report(args, start, end, result, sidecars))
    print(
        "wrote report-only flow-exhaustion development artifact: "
        f"{output} passed={result.assessment['passed']} "
        f"trades={result.nominal.completed_trades}"
    )
    return 0


def _execute_screen(
    args: argparse.Namespace,
    start: datetime,
    end: datetime,
) -> _ScreenResult:
    signal_config = FlowExhaustionSignalConfig()
    funding_paths = {
        "BTC": tuple(Path(path) for path in args.btc_funding),
        "SOL": tuple(Path(path) for path in args.sol_funding),
    }
    inputs, signal_reports = _load_signals(
        Path(args.database), start, end, signal_config
    )
    signals = _combined_signals(signal_reports)
    minute_paths = {
        symbol: load_flow_exhaustion_minute_path(
            Path(args.database),
            symbol,
            start,
            end + timedelta(minutes=31),
            list(funding_paths[symbol]),
        )
        for symbol in ("BTC", "SOL")
    }
    nominal_config = FlowExhaustionReplayConfig(round_trip_cost_bps=13.0)
    stress_config = FlowExhaustionReplayConfig(round_trip_cost_bps=20.0)
    nominal = replay_flow_exhaustion_signals(minute_paths, signals, nominal_config)
    stress = replay_flow_exhaustion_signals(minute_paths, signals, stress_config)
    assessment = assess_flow_exhaustion_development(nominal, stress, start, end)
    return _ScreenResult(
        signal_config,
        nominal_config,
        stress_config,
        funding_paths,
        inputs,
        signal_reports,
        signals,
        nominal,
        stress,
        assessment,
    )


def _load_signals(
    database: Path,
    start: datetime,
    end: datetime,
    config: FlowExhaustionSignalConfig,
) -> tuple[
    dict[str, LowTimeframeInputFrames],
    dict[str, FlowExhaustionSignalReport],
]:
    inputs: dict[str, LowTimeframeInputFrames] = {}
    reports: dict[str, FlowExhaustionSignalReport] = {}
    for symbol in ("BTC", "SOL"):
        loaded = load_low_timeframe_inputs(
            database,
            symbol,
            start,
            end,
            history_bars=_HISTORY_BARS,
            horizon_bars=_HORIZON_BARS,
        )
        rows = assemble_flow_exhaustion_rows(loaded)
        decision_rows = rows.loc[rows["bar_open_at"].lt(end)].copy()
        report = build_segmented_flow_exhaustion_signals(decision_rows, symbol, config)
        reports[symbol] = _trim_signal_report(report, start, end)
        inputs[symbol] = loaded
    return inputs, reports


def _trim_signal_report(
    report: FlowExhaustionSignalReport,
    start: datetime,
    end: datetime,
) -> FlowExhaustionSignalReport:
    signals = report.signals
    selected = signals.loc[
        signals["bar_open_at"].ge(start) & signals["bar_open_at"].lt(end)
    ].copy()
    return FlowExhaustionSignalReport(
        selected.reset_index(drop=True), report.evaluated_bars, report.blockers
    )


def _combined_signals(
    reports: dict[str, FlowExhaustionSignalReport],
) -> pd.DataFrame:
    combined = pd.concat(
        [reports[symbol].signals for symbol in ("BTC", "SOL")],
        ignore_index=True,
    )
    return combined.sort_values(
        ["available_at_utc", "rank_score", "symbol"],
        ascending=[True, False, True],
    ).reset_index(drop=True)


def _sidecar_paths(output: Path) -> dict[str, Path]:
    parent, stem = output.parent, output.stem
    return {
        "signals": parent / f"{stem}_signals.parquet",
        "nominal_trades": parent / f"{stem}_nominal_trades.parquet",
        "nominal_rejections": parent / f"{stem}_nominal_rejections.parquet",
        "stress_trades": parent / f"{stem}_stress_trades.parquet",
        "stress_rejections": parent / f"{stem}_stress_rejections.parquet",
    }


def _ensure_outputs_available(output: Path, sidecars: tuple[Path, ...]) -> None:
    existing = [path for path in (output, *sidecars) if path.exists()]
    if existing:
        paths = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"flow-exhaustion output exists: {paths}")


def _sidecar_frames(
    signals: pd.DataFrame,
    nominal: FlowExhaustionReplayReport,
    stress: FlowExhaustionReplayReport,
) -> dict[str, pd.DataFrame]:
    return {
        "signals": signals,
        "nominal_trades": _dataclass_frame(nominal.trades, FlowExhaustionTrade),
        "nominal_rejections": _dataclass_frame(
            nominal.rejections, FlowExhaustionRejection
        ),
        "stress_trades": _dataclass_frame(stress.trades, FlowExhaustionTrade),
        "stress_rejections": _dataclass_frame(
            stress.rejections, FlowExhaustionRejection
        ),
    }


def _dataclass_frame(records: tuple[object, ...], kind: type[object]) -> pd.DataFrame:
    columns = [item.name for item in fields(kind)]
    return pd.DataFrame([asdict(record) for record in records], columns=columns)


def _report(
    args: argparse.Namespace,
    start: datetime,
    end: datetime,
    result: _ScreenResult,
    sidecars: dict[str, Path],
) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "segment": str(args.segment),
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "report_only": True,
        "execution_authority": "none",
        "place_attempted": False,
        "selection_status": "frozen_development_contract",
        "data_boundary_amendment": {
            "original_start_utc": "2025-07-28T00:00:00+00:00",
            "reason": "BTC archive resumes at original boundary without seven-day warmup",
            "gap_policy": "reset rolling history; never bridge missing bars",
        },
        "signal_config": asdict(result.signal_config),
        "nominal_replay_config": asdict(result.nominal_config),
        "stress_replay_config": asdict(result.stress_config),
        "inputs": _input_report(result.inputs, result.funding_paths),
        "signals": {
            symbol: {
                "eligible": len(report.signals),
                "evaluated_bars": report.evaluated_bars,
                "blockers": report.blockers,
            }
            for symbol, report in result.signal_reports.items()
        },
        "nominal": _replay_summary(result.nominal),
        "stress": _replay_summary(result.stress),
        "development_assessment": result.assessment,
        "sidecars": {
            name: {"path": str(path), **file_evidence(path)}
            for name, path in sidecars.items()
        },
        "limitations": [
            "Historical OI and explicit liquidation-event labels are unavailable.",
            "ETH and HYPE lack matching historical L2 in this database.",
            "Passing development would still require untouched validation and forward shadow evidence.",
        ],
    }


def _input_report(
    inputs: dict[str, LowTimeframeInputFrames],
    funding_paths: dict[str, tuple[Path, ...]],
) -> dict[str, object]:
    return {
        symbol: {
            "bars": len(loaded.bars),
            "trade_bars": len(loaded.trades),
            "book_bars": len(loaded.books),
            "missing_book_bars": loaded.missing_book_bars,
            "orphan_book_bars": loaded.orphan_book_bars,
            "five_minute_gaps": _gap_records(loaded.bars),
            "bars_sha256": _frame_sha256(loaded.bars),
            "trades_sha256": _frame_sha256(loaded.trades),
            "books_sha256": _frame_sha256(loaded.books),
            "funding_files": [
                {"path": str(path), **file_evidence(path)}
                for path in funding_paths[symbol]
            ],
        }
        for symbol, loaded in inputs.items()
    }


def _gap_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    times = pd.DatetimeIndex(frame["bar_open_at"])
    output: list[dict[str, object]] = []
    for previous, current in zip(times[:-1], times[1:], strict=False):
        delta = current - previous
        if delta <= pd.Timedelta(minutes=5):
            continue
        output.append(
            {
                "previous_bar_utc": previous.isoformat(),
                "next_bar_utc": current.isoformat(),
                "missing_five_minute_bars": int(delta / pd.Timedelta(minutes=5)) - 1,
            }
        )
    return output


def _replay_summary(report: FlowExhaustionReplayReport) -> dict[str, object]:
    return {
        key: value
        for key, value in report.to_dict().items()
        if key not in {"trades", "rejections"}
    }


def _frame_sha256(frame: pd.DataFrame) -> str:
    digest = sha256()
    digest.update("\x1f".join(map(str, frame.columns)).encode())
    digest.update(
        pd.util.hash_pandas_object(frame, index=False, categorize=True)
        .to_numpy()
        .tobytes()
    )
    return digest.hexdigest()


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("flow-exhaustion timestamps must include a timezone")
    return parsed.astimezone(UTC)


if __name__ == "__main__":
    raise SystemExit(main())
