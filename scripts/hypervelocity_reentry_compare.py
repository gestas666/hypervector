"""Retain a bounded Hypervelocity same-direction re-entry screen."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_json
from hypervector.regime.composite import classify_multitimeframe
from hypervector.research.hypervelocity_reentry_compare import (
    screen_target_continuation_candidates,
    screen_target_rsi_candidates,
)
from hypervector.strategies.hypervelocity_profile import (
    load_hypervelocity_profile,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--positions", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--experiment",
        choices=("target-continuation", "target-rsi"),
        default="target-continuation",
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _bars(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"re-entry bars are missing: {path}")
    frame = pd.read_parquet(path)
    if "timestamp" not in frame:
        raise ValueError("re-entry bars require timestamp")
    index = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True))
    frame = frame.set_axis(index)
    if frame.empty or not index.is_monotonic_increasing or index.has_duplicates:
        raise ValueError("re-entry bars must be non-empty, unique, and increasing")
    return frame


def _positions(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"original positions are missing: {path}")
    return pd.read_csv(path)


def _survivors(rows: tuple[dict[str, object], ...]) -> list[str]:
    control = rows[0]["serial"]
    alignment = rows[0]["original_alignment"]
    if not isinstance(control, dict) or not isinstance(alignment, dict):
        raise ValueError("re-entry results have invalid summaries")
    control_equity = float(control["final_marked_equity"])
    source_cadence = float(alignment["source_logical_positions_per_day"])
    survivors: list[str] = []
    for row in rows[1:]:
        candidate, serial = row["candidate"], row["serial"]
        if not isinstance(candidate, dict) or not isinstance(serial, dict):
            raise ValueError("re-entry candidate result is invalid")
        cadence = float(serial["completed_trades_per_day"])
        if (
            float(serial["final_marked_equity"]) > control_equity
            and 0.5 * source_cadence <= cadence <= 2.0 * source_cadence
        ):
            survivors.append(str(candidate["candidate_id"]))
    return survivors


def _screen(
    experiment: str,
    bars: pd.DataFrame,
    decisions: pd.DataFrame,
    positions: pd.DataFrame,
) -> tuple[str, tuple[dict[str, object], ...]]:
    if experiment == "target-continuation":
        return (
            "target_continuation_reentry_v1",
            screen_target_continuation_candidates(bars, decisions, positions),
        )
    return (
        "target_rsi_reconfirmation_v1",
        screen_target_rsi_candidates(bars, decisions, positions),
    )


def _report(args: argparse.Namespace) -> dict[str, object]:
    profile = load_hypervelocity_profile(args.config)
    bars = _bars(args.bars)
    positions = _positions(args.positions)
    decisions = classify_multitimeframe(bars, config=profile.regime_config)
    experiment, results = _screen(args.experiment, bars, decisions, positions)
    survivors = _survivors(results)
    return {
        "ok": True,
        "report_only": True,
        "experiment": experiment,
        "source_evidence": {
            "bars": file_evidence(args.bars),
            "positions": file_evidence(args.positions),
            "runtime_config": file_evidence(args.config),
        },
        "metalabel_policy": {
            "mode": profile.metalabel_mode,
            "may_filter": False,
            "may_scale": False,
        },
        "acceptance": {
            "equity_must_exceed_control": True,
            "source_cadence_multiple_minimum": 0.5,
            "source_cadence_multiple_maximum": 2.0,
            "event_replay_profit_threshold_usd": 10_000.0,
        },
        "results": list(results),
        "serial_survivors": survivors,
        "event_replay_required": bool(survivors),
        "runtime_strategy_changed": False,
        "limitations": [
            "Serial screening approximates fills at next-bar open, not public L2.",
            "Historical funding is not applied in serial screening.",
            "The source log does not identify which closes reached an 8% target.",
        ],
    }


def main() -> int:
    """Write one new, report-only comparison artifact."""
    args = _parser().parse_args()
    try:
        if args.out.exists():
            raise FileExistsError(f"re-entry output already exists: {args.out}")
        report = _report(args)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.out, report)
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
