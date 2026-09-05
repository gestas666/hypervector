#!/usr/bin/env python3
"""Run the preregistered report-only OI deleveraging feasibility screen."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NamedTuple

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.oi_deleveraging_feasibility import (
    OiDeleveragingConfig,
    OiDeleveragingReplay,
    assess_development,
    build_signals,
    replay_signals,
)
from hypervector.research.oi_deleveraging_inputs import (
    load_oi_deleveraging_minutes,
)


_DATABASE_SHA256 = "844c90d94cbb51210bb4281a3a805a001a7ff1c74c3ddc27f830ab348d925637"
_PREREGISTRATION = Path(
    "docs/research-journal/oi-forced-deleveraging-exhaustion-v1.json"
)
_DEVELOPMENT = (
    datetime(2026, 8, 4, 1, 5, tzinfo=UTC),
    datetime(2026, 8, 8, 8, 35, tzinfo=UTC),
)
_CONFIRMATION = (
    datetime(2026, 8, 8, 8, 38, tzinfo=UTC),
    datetime(2026, 8, 9, 15, 39, tzinfo=UTC),
)
_SYMBOLS = ("BTC", "SOL")
_Loader = Callable[[Path, str, datetime, datetime], pd.DataFrame]


class _WindowEvaluation(NamedTuple):
    """One bounded, frozen event evaluation."""

    start: datetime
    end: datetime
    input_rows: dict[str, int]
    signals: pd.DataFrame
    nominal: OiDeleveragingReplay
    stress: OiDeleveragingReplay
    assessment: dict[str, object]


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit report-only command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Evaluate development, conditionally open confirmation, and publish."""
    args = build_parser().parse_args(argv)
    if args.out.exists():
        raise FileExistsError(f"OI deleveraging output exists: {args.out}")
    before = _require_database_identity(args.database)
    preregistration = _evidence_with_path(_PREREGISTRATION)
    evaluations = _run_evaluations(args.database)
    after = _evidence_with_path(args.database)
    if before != after:
        raise RuntimeError("OI deleveraging database changed during evaluation")
    payload = _report(args.database, preregistration, before, evaluations)
    write_immutable_json(args.out, payload)
    development = evaluations["development"]
    print(
        "wrote report-only OI deleveraging feasibility: "
        f"{args.out} passed={development.assessment['passed']} "
        f"events={len(development.nominal.trades)}"
    )
    return 0


def _run_evaluations(
    database: Path,
    *,
    loader: _Loader = load_oi_deleveraging_minutes,
) -> dict[str, object]:
    development = _evaluate_window(database, *_DEVELOPMENT, loader=loader)
    if not bool(development.assessment["passed"]):
        return {
            "development": development,
            "confirmation": None,
            "confirmation_status": "withheld_not_evaluated",
        }
    confirmation = _evaluate_window(database, *_CONFIRMATION, loader=loader)
    return {
        "development": development,
        "confirmation": confirmation,
        "confirmation_status": "evaluated_after_development_pass",
    }


def _evaluate_window(
    database: Path,
    start: datetime,
    end: datetime,
    *,
    loader: _Loader,
) -> _WindowEvaluation:
    config = OiDeleveragingConfig()
    signal_frames: list[pd.DataFrame] = []
    nominal_parts: list[OiDeleveragingReplay] = []
    stress_parts: list[OiDeleveragingReplay] = []
    counts: dict[str, int] = {}
    for symbol in _SYMBOLS:
        path = loader(
            database,
            symbol,
            start,
            end + timedelta(minutes=config.primary_horizon_minutes),
        )
        decision_rows = path.loc[path["minute"].lt(end)].copy()
        signals = build_signals(decision_rows, symbol, config)
        signal_frames.append(signals)
        nominal_parts.append(replay_signals(path, signals, round_trip_cost_bps=13.0))
        stress_parts.append(replay_signals(path, signals, round_trip_cost_bps=20.0))
        counts[symbol] = len(path)
    combined = _combined_signals(signal_frames)
    nominal = _combined_replay(nominal_parts)
    stress = _combined_replay(stress_parts)
    assessment = assess_development(nominal, symbols=_SYMBOLS)
    return _WindowEvaluation(start, end, counts, combined, nominal, stress, assessment)


def _combined_signals(frames: list[pd.DataFrame]) -> pd.DataFrame:
    nonempty = [frame for frame in frames if not frame.empty]
    if not nonempty:
        return pd.DataFrame()
    return (
        pd.concat(nonempty, ignore_index=True)
        .sort_values(["decision_at", "symbol"])
        .reset_index(drop=True)
    )


def _combined_replay(parts: list[OiDeleveragingReplay]) -> OiDeleveragingReplay:
    trades = tuple(trade for part in parts for trade in part.trades)
    rejections = tuple(rejection for part in parts for rejection in part.rejections)
    return OiDeleveragingReplay(trades, rejections)


def _require_database_identity(database: Path) -> dict[str, object]:
    evidence = _evidence_with_path(database)
    if evidence["sha256"] != _DATABASE_SHA256:
        raise ValueError(
            "OI deleveraging database identity differs from preregistration"
        )
    return evidence


def _evidence_with_path(path: Path) -> dict[str, object]:
    evidence = file_evidence(path)
    return {"path": str(path), **evidence}


def _report(
    database: Path,
    preregistration: dict[str, object],
    database_evidence: dict[str, object],
    evaluations: dict[str, object],
) -> dict[str, object]:
    development = evaluations["development"]
    assert isinstance(development, _WindowEvaluation)
    confirmation = evaluations["confirmation"]
    return {
        "schema_version": "oi_deleveraging_feasibility_v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "authority": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
            "place_attempted": False,
        },
        "database": {"requested_path": str(database), **database_evidence},
        "preregistration": preregistration,
        "generator": _generator_evidence(),
        "config": asdict(OiDeleveragingConfig()),
        "development": _window_report(development),
        "confirmation_status": evaluations["confirmation_status"],
        "confirmation": (
            _window_report(confirmation)
            if isinstance(confirmation, _WindowEvaluation)
            else None
        ),
        "live_recommendation": "none",
    }


def _window_report(evaluation: _WindowEvaluation) -> dict[str, object]:
    return {
        "start_utc": evaluation.start.isoformat(),
        "end_utc": evaluation.end.isoformat(),
        "input_rows": evaluation.input_rows,
        "signal_count": len(evaluation.signals),
        "signals": _frame_records(evaluation.signals),
        "nominal": _replay_report(evaluation.nominal),
        "stress": _replay_report(evaluation.stress),
        "assessment": evaluation.assessment,
    }


def _replay_report(replay: OiDeleveragingReplay) -> dict[str, object]:
    trades = [_serializable(asdict(trade)) for trade in replay.trades]
    rejections = [asdict(rejection) for rejection in replay.rejections]
    return {
        "trade_count": len(trades),
        "rejection_count": len(rejections),
        "trades": trades,
        "rejections": [_serializable(item) for item in rejections],
        "summary": _trade_summary(trades),
    }


def _trade_summary(trades: list[dict[str, object]]) -> dict[str, object]:
    if not trades:
        return {"mean_gross_bps": None, "median_gross_bps": None, "mean_net_bps": None}
    frame = pd.DataFrame(trades)
    return {
        "mean_gross_bps": float(frame["gross_bps"].mean()),
        "median_gross_bps": float(frame["gross_bps"].median()),
        "mean_net_bps": float(frame["net_bps"].mean()),
        "by_symbol": frame.groupby("symbol")["net_bps"]
        .agg(["count", "mean"])
        .to_dict("index"),
        "by_exhaustion": frame.groupby("exhausted")["net_bps"]
        .agg(["count", "mean"])
        .to_dict("index"),
    }


def _frame_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return [_serializable(record) for record in frame.to_dict("records")]


def _serializable(record: dict[str, object]) -> dict[str, object]:
    return {
        key: value.isoformat() if isinstance(value, pd.Timestamp) else value
        for key, value in record.items()
    }


def _generator_evidence() -> dict[str, dict[str, object]]:
    paths = (
        Path(__file__),
        Path("src/hypervector/research/oi_deleveraging_feasibility.py"),
        Path("src/hypervector/research/oi_deleveraging_inputs.py"),
        Path("src/hypervector/data/live_event_research_sql.py"),
    )
    return {str(path): file_evidence(path) for path in paths}


if __name__ == "__main__":
    raise SystemExit(main())
