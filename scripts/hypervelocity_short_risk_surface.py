#!/usr/bin/env python3
"""Replay a bounded short allocation/leverage surface on exact venue tape."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import importlib.util
import json
import math
from pathlib import Path
import sys
from types import ModuleType

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.maker_replay_context_io import (
    context_coverage_report,
    load_verified_replay_context_parts,
)
from hypervector.research.maker_replay_context import MakerReplayContext
from hypervector.research.maker_replay_models import (
    FillRule,
    MakerReplayConfig,
    MakerReplayReport,
)
from hypervector.research.maker_replay_stream import (
    replay_maker_order_decision_grid_chunks,
)
from hypervector.research.measured_hypervelocity_risk import (
    measured_hypervelocity_candidate_configs,
)
from hypervector.research.research_evidence_source import maker_replay_evidence


def _load_shared_replay() -> ModuleType:
    path = Path(__file__).with_name("hypervelocity_shared_direction_replay.py")
    spec = importlib.util.spec_from_file_location("shared_replay_helpers", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"shared replay helpers could not be loaded: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


shared_replay = _load_shared_replay()

_PARITY_REL_TOLERANCE = 1e-12
_PARITY_ABS_TOLERANCE = 1e-12


def _parser() -> argparse.ArgumentParser:
    parser = shared_replay._parser()
    parser.description = __doc__
    parser.add_argument("--control-artifact", type=Path, required=True)
    parser.add_argument(
        "--surface-mode",
        choices=("tail-risk", "measured"),
        default="tail-risk",
    )
    return parser


def _config(
    initial_equity: float,
    fill_rule: FillRule,
    margin_fraction: float,
    leverage: float,
) -> MakerReplayConfig:
    return MakerReplayConfig(
        initial_equity=initial_equity,
        margin_fraction=margin_fraction,
        leverage=leverage,
        target_margin_pct=8.0,
        fill_rule=fill_rule,
        entry_ttl_seconds=60.0,
        reentry_cooldown_seconds=60.0,
        same_direction_reentry_policy="regime_reset",
        maximum_hold_seconds=86_400.0,
        occupied_signal_policy="ignore",
    )


def _configs(
    initial_equity: float,
    fill_rule: FillRule,
    surface_mode: str = "tail-risk",
) -> dict[str, MakerReplayConfig]:
    """Return the predeclared current-control risk surface."""
    if surface_mode == "measured":
        return measured_hypervelocity_candidate_configs(
            initial_equity=initial_equity,
            fill_rule=fill_rule,
        )
    if surface_mode != "tail-risk":
        raise ValueError(f"unsupported short risk surface mode: {surface_mode}")
    candidates = (
        ("alloc35_lev30_control", 0.35, 30.0),
        ("alloc25_lev30", 0.25, 30.0),
        ("alloc35_lev25", 0.35, 25.0),
        ("alloc35_lev20", 0.35, 20.0),
    )
    return {
        name: _config(initial_equity, fill_rule, allocation, leverage)
        for name, allocation, leverage in candidates
    }


def _contract(
    initial_equity: float,
    fill_rule: FillRule,
    surface_mode: str = "tail-risk",
) -> dict[str, object]:
    """Return the immutable report-only experiment contract."""
    measured = surface_mode == "measured"
    if surface_mode not in {"tail-risk", "measured"}:
        raise ValueError(f"unsupported short risk surface mode: {surface_mode}")
    return {
        "candidate": (
            "source_follow_measured_exposure_v1"
            if measured
            else "source_follow_short_tail_risk_surface_v1"
        ),
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "model_authority": "observe",
        "signal_changed": False,
        "candidate_count": 5 if measured else 4,
        "initial_equity": initial_equity,
        "gross_margin_target_pct": 8.0,
        "maximum_hold_seconds": 86_400.0,
        "entry_ttl_seconds": 60.0,
        "fill_rule": fill_rule,
    }


def _control_replay(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"control artifact is missing: {path}")
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("control artifact must contain a JSON object")
    event_replays = payload.get("event_replays")
    if not isinstance(event_replays, dict):
        raise ValueError("control artifact is missing event_replays")
    control = event_replays.get("strict_tuned")
    if control is None:
        control = event_replays.get("short_control")
    if not isinstance(control, dict):
        raise ValueError(
            "control artifact is missing strict_tuned or short_control replay"
        )
    return control


def _verify_control_parity(
    actual: dict[str, object],
    expected: dict[str, object],
) -> None:
    """Fail if the surface does not reproduce the frozen short control."""
    normalized_actual: object = json.loads(
        json.dumps(actual, allow_nan=False, sort_keys=True)
    )
    normalized_expected: object = json.loads(
        json.dumps(expected, allow_nan=False, sort_keys=True)
    )
    mismatch = _first_mismatch(normalized_actual, normalized_expected)
    if mismatch is not None:
        path, actual_value, expected_value = mismatch
        raise ValueError(
            "control replay mismatch against frozen shared artifact: "
            f"{path} actual={actual_value!r} expected={expected_value!r}"
        )


def _first_mismatch(
    actual: object,
    expected: object,
    path: str = "$",
) -> tuple[str, object, object] | None:
    """Return the first deterministic difference between JSON-shaped values."""
    if isinstance(actual, dict) and isinstance(expected, dict):
        keys = sorted(set(actual).union(expected))
        for key in keys:
            if key not in actual or key not in expected:
                return f"{path}.{key}", actual.get(key), expected.get(key)
            mismatch = _first_mismatch(actual[key], expected[key], f"{path}.{key}")
            if mismatch is not None:
                return mismatch
        return None
    if isinstance(actual, list) and isinstance(expected, list):
        if len(actual) != len(expected):
            return f"{path}.length", len(actual), len(expected)
        for index, (actual_item, expected_item) in enumerate(zip(actual, expected)):
            mismatch = _first_mismatch(
                actual_item,
                expected_item,
                f"{path}[{index}]",
            )
            if mismatch is not None:
                return mismatch
        return None
    if isinstance(actual, float) and isinstance(expected, float):
        if math.isclose(
            actual,
            expected,
            rel_tol=_PARITY_REL_TOLERANCE,
            abs_tol=_PARITY_ABS_TOLERANCE,
        ):
            return None
    if actual != expected:
        return path, actual, expected
    return None


def _comparison(
    reports: dict[str, MakerReplayReport],
) -> dict[str, dict[str, float]]:
    control = reports["alloc35_lev30_control"]
    return {
        name: {
            "final_equity_delta": report.final_equity - control.final_equity,
            "maximum_drawdown_pct_delta": (
                report.maximum_drawdown_pct - control.maximum_drawdown_pct
            ),
        }
        for name, report in reports.items()
    }


def _report(args: argparse.Namespace) -> dict[str, object]:
    bars = shared_replay.load_minute_bars(args.bars)
    shared_replay._validate_inputs(args, bars)
    labels = shared_replay._load_labels(args)
    short_decisions = shared_replay._decision_grid(args, bars, labels).short_control
    context_parts = shared_replay._context_parts(args)
    context = load_verified_replay_context_parts(context_parts)
    configs = _configs(args.initial_equity, args.fill_rule, args.surface_mode)
    evidence = maker_replay_evidence(
        args.data_root,
        "BTC",
        args.start,
        args.end,
        include_trades=args.fill_rule == "trade-through",
        database_path=args.research_database,
    )
    reports = replay_maker_order_decision_grid_chunks(
        evidence.chunks,
        {name: short_decisions for name in configs},
        configs,
        context=context,
    )
    control = reports["alloc35_lev30_control"].to_dict()
    _verify_control_parity(control, _control_replay(args.control_artifact))
    return _payload(args, configs, reports, evidence.summary, context, context_parts)


def _payload(
    args: argparse.Namespace,
    configs: dict[str, MakerReplayConfig],
    reports: dict[str, MakerReplayReport],
    market_evidence: dict[str, object],
    context: MakerReplayContext,
    context_parts: list[tuple[Path, Path]],
) -> dict[str, object]:
    return {
        "schema": (
            "hypervelocity_measured_exposure_v1"
            if args.surface_mode == "measured"
            else "hypervelocity_short_risk_surface_v1"
        ),
        "report_only": True,
        "experiment_contract": _contract(
            args.initial_equity,
            args.fill_rule,
            args.surface_mode,
        ),
        "candidate_configs": {name: asdict(config) for name, config in configs.items()},
        "summaries": {
            name: shared_replay._summary(report) for name, report in reports.items()
        },
        "comparison": _comparison(reports),
        "event_replays": {name: report.to_dict() for name, report in reports.items()},
        "market_evidence": market_evidence,
        "context_evidence": context_coverage_report(context),
        "source_evidence": {
            "bars": shared_replay._path_evidence(args.bars),
            "labels": shared_replay._path_evidence(args.labels),
            "labels_metadata": shared_replay._path_evidence(args.labels_metadata),
            "control_artifact": {
                "path": str(args.control_artifact.resolve()),
                **file_evidence(args.control_artifact),
            },
            "price_context": [
                shared_replay._path_evidence(path) for path, _ in context_parts
            ],
            "funding_context": [
                shared_replay._path_evidence(path) for _, path in context_parts
            ],
        },
        "limitations": [
            "This risk surface was motivated by losses in this same interval.",
            "Public trade-through cannot identify private maker queue rank.",
            "A profitable candidate requires independent validation.",
            "No candidate changes runtime or ML execution authority.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Write one immutable report-only current short risk surface."""
    args = _parser().parse_args(argv)
    try:
        write_immutable_json(args.out, _report(args))
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "out": str(args.out.resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
