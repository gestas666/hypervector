"""Retain structural stop counterfactuals for exact replay fills."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_json
from hypervector.regime.composite import _completed_context, classify_multitimeframe
from hypervector.research.hypervelocity_bbwp_precedence import (
    apply_1m_bbwp_recovery_delay,
    apply_5m_bbwp_range_precedence,
)
from hypervector.research.hypervelocity_stop_counterfactual import (
    evaluate_confirmed_pivot_stops,
    evaluate_consolidation_wick_stops,
)
from hypervector.strategies.hypervelocity_profile import load_hypervelocity_profile


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--candidate")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--stop-kind",
        choices=("consolidation-wick", "confirmed-pivot"),
        default="consolidation-wick",
    )
    parser.add_argument("--pivot-left-bars", type=int, default=2)
    parser.add_argument("--pivot-right-bars", type=int, default=2)
    parser.add_argument("--pivot-buffer-bps", type=float, default=0.0)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _json(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"stop replay evidence is missing: {path}")
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("stop replay evidence must be a JSON object")
    return payload


def _bars(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    if "timestamp" not in frame:
        raise ValueError("stop bars require timestamp")
    frame.index = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True))
    return frame


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object with string keys")
    return value


def _lifecycle_rows(
    replay: dict[str, object],
    candidate: str | None,
) -> list[object]:
    if candidate is None:
        event = _mapping(replay.get("event_replay"), "event replay")
        rows = event.get("lifecycles")
    else:
        comparison = _mapping(replay.get("comparison"), "comparison")
        candidates = _mapping(comparison.get("candidates"), "comparison candidates")
        if candidate not in candidates:
            raise ValueError(f"stop replay candidate is missing: {candidate}")
        selected = _mapping(candidates[candidate], "stop replay candidate")
        candidate_replay = _mapping(selected.get("replay"), "candidate replay")
        rows = candidate_replay.get("lifecycles")
    if not isinstance(rows, list):
        raise ValueError("stop replay evidence has no event lifecycles")
    return rows


def _decisions(
    bars: pd.DataFrame,
    config_path: Path,
) -> tuple[pd.DataFrame, dict[str, object]]:
    profile = load_hypervelocity_profile(config_path)
    control = classify_multitimeframe(bars, config=profile.regime_config)
    context = _completed_context(bars, bars.index, 5, profile.regime_config)
    hard_range = apply_5m_bbwp_range_precedence(
        control,
        context,
        threshold=profile.regime_config.bbwp_compression_threshold,
    )
    delayed = apply_1m_bbwp_recovery_delay(
        hard_range,
        threshold=profile.regime_config.bbwp_compression_threshold,
        minimum_age_bars=6,
    )
    policy = {
        "mode": profile.metalabel_mode,
        "may_filter": False,
        "may_scale": False,
    }
    return delayed, policy


def _report(args: argparse.Namespace) -> dict[str, object]:
    replay = _json(args.replay)
    bars = _bars(args.bars)
    decisions, model_policy = _decisions(bars, args.config)
    lifecycles = pd.DataFrame(_lifecycle_rows(replay, args.candidate))
    if args.stop_kind == "confirmed-pivot":
        counterfactual = evaluate_confirmed_pivot_stops(
            bars,
            lifecycles,
            left_bars=args.pivot_left_bars,
            right_bars=args.pivot_right_bars,
            buffer_bps=args.pivot_buffer_bps,
        )
        experiment = "confirmed_strict_pivot_stop_v1"
    else:
        counterfactual = evaluate_consolidation_wick_stops(
            bars,
            decisions,
            lifecycles,
        )
        experiment = "last_bbwp_consolidation_wick_stop_v1"
    return {
        "ok": True,
        "report_only": True,
        "experiment": experiment,
        "source_evidence": {
            "bars": file_evidence(args.bars),
            "replay": file_evidence(args.replay),
            "runtime_config": file_evidence(args.config),
        },
        "metalabel_policy": model_policy,
        "stop_contract": {
            "kind": args.stop_kind,
            "source_candidate": args.candidate,
            "pivot_left_bars": args.pivot_left_bars,
            "pivot_right_bars": args.pivot_right_bars,
            "pivot_buffer_bps": args.pivot_buffer_bps,
        },
        "counterfactual": counterfactual.to_dict(),
        "runtime_strategy_changed": False,
        "limitations": [
            "Only full 1m bars strictly between entry and outcome are scanned.",
            "Partial entry and outcome minutes require exact BBO replay.",
            "A fixed-lifecycle result does not model new entries after early exits.",
        ],
    }


def main() -> int:
    """Write one immutable stop-counterfactual artifact."""
    args = _parser().parse_args()
    try:
        if args.out.exists():
            raise FileExistsError(f"stop output already exists: {args.out}")
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
