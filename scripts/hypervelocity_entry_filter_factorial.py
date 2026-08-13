"""Replay the canonical, hard-BBWP, and recovery entry-filter factorial."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

import pandas as pd

from hypervector.data.oxa_archive_audit import (
    OxaArchiveAuditConfig,
    verified_archive_bundles,
)
from hypervector.data.oxa_storage import (
    file_evidence,
    write_immutable_json,
)
from hypervector.regime.composite import _completed_context, classify_multitimeframe
from hypervector.research.hypervelocity_entry_filter_factorial import (
    ENTRY_FILTER_CANDIDATES,
    STRENGTH_FOLLOWUP_CANDIDATES,
    apply_minimum_entry_strength,
    entry_filter_candidate_configs,
    entry_filter_decision_grid,
    source_entry_attribution,
    source_fill_proximity,
    strength_followup_candidate_configs,
)
from hypervector.research.hypervelocity_margin_stop_compare import (
    summarize_margin_stop_grid,
)
from hypervector.research.maker_replay_models import (
    MakerReplayConfig,
    MakerReplayReport,
)
from hypervector.research.hypervelocity_metalabel_features import load_model_bars
from hypervector.research.hypervelocity_metalabel_report import runtime_observe_contract
from hypervector.research.hypervelocity_replay_evidence import (
    decision_identity,
    replay_archive_summary,
)
from hypervector.research.hypervelocity_source_inputs import source_positions
from hypervector.research.maker_replay_context_io import load_verified_replay_context
from hypervector.research.maker_replay_stream import (
    archive_evidence_chunks,
    replay_maker_order_decision_grid_chunks,
)
from hypervector.strategies.hypervelocity_profile import load_hypervelocity_profile

_FAITHFUL_CONFIG_SHA256 = (
    "801d2c7af3c1211c13fea49dda673fdb8ed40ff0909692e9cebad070c0e3246f"
)
_FILTER_FLAGS = {
    "canonical_control": {"hard_bbwp": False, "recovery6": False},
    "hard_bbwp_only": {"hard_bbwp": True, "recovery6": False},
    "recovery6_only": {"hard_bbwp": False, "recovery6": True},
    "hard_bbwp_recovery6": {"hard_bbwp": True, "recovery6": True},
    "hard_bbwp_recovery6_control": {
        "hard_bbwp": True,
        "recovery6": True,
        "minimum_entry_strength": None,
    },
    "hard_bbwp_recovery6_strength50": {
        "hard_bbwp": True,
        "recovery6": True,
        "minimum_entry_strength": 50.0,
    },
}


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--positions", type=Path, required=True)
    parser.add_argument("--supplemental-positions", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--start", type=_utc, required=True)
    parser.add_argument("--end", type=_utc, required=True)
    parser.add_argument("--price-context", type=Path, required=True)
    parser.add_argument("--funding-context", type=Path, required=True)
    parser.add_argument("--segment-days", type=int, default=30)
    parser.add_argument("--minimum-entry-strength", type=float, choices=(50.0,))
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _metalabel_policy(config: Path) -> dict[str, object]:
    policy = runtime_observe_contract(config)
    return {name: policy[name] for name in ("mode", "may_filter", "may_scale")}


def _experiment_contract(
    args: argparse.Namespace,
    candidate_order: tuple[str, ...] = ENTRY_FILTER_CANDIDATES,
) -> dict[str, object]:
    return {
        "report_only": True,
        "runtime_strategy_changed": False,
        "candidate_order": list(candidate_order),
        "window_start_utc": args.start.isoformat(),
        "window_end_utc": args.end.isoformat(),
        "allocation_fraction": 0.70,
        "leverage": 40.0,
        "gross_margin_target_pct": 8.0,
        "minimum_entry_strength": args.minimum_entry_strength,
    }


def _verify_config(path: Path) -> dict[str, object]:
    evidence = file_evidence(path)
    if evidence["sha256"] != _FAITHFUL_CONFIG_SHA256:
        raise ValueError("faithful config checksum mismatch")
    return evidence


def _source_evidence(args: argparse.Namespace) -> dict[str, object]:
    return {
        "bars": file_evidence(args.bars),
        "positions": file_evidence(args.positions),
        "supplemental_positions": file_evidence(args.supplemental_positions),
        "runtime_config": _verify_config(args.config),
        "price_context": file_evidence(args.price_context),
        "funding_context": file_evidence(args.funding_context),
    }


def _decision_grid(
    bars: pd.DataFrame,
    config_path: Path,
) -> dict[str, pd.DataFrame]:
    profile = load_hypervelocity_profile(config_path)
    canonical = classify_multitimeframe(bars, config=profile.regime_config)
    context_5m = _completed_context(
        bars,
        bars.index,
        5,
        profile.regime_config,
    )
    return entry_filter_decision_grid(
        canonical,
        context_5m,
        compression_threshold=profile.regime_config.bbwp_compression_threshold,
        recovery_age_bars=6,
    )


def _candidate_inputs(
    bars: pd.DataFrame,
    args: argparse.Namespace,
) -> tuple[
    dict[str, pd.DataFrame],
    dict[str, MakerReplayConfig],
    dict[str, dict[str, object]],
]:
    grid = _decision_grid(bars, args.config)
    if args.minimum_entry_strength is None:
        return grid, entry_filter_candidate_configs(), _FILTER_FLAGS
    control = grid["hard_bbwp_recovery6"]
    candidate = apply_minimum_entry_strength(
        control,
        minimum=args.minimum_entry_strength,
    )
    decisions = dict(zip(STRENGTH_FOLLOWUP_CANDIDATES, (control, candidate)))
    return decisions, strength_followup_candidate_configs(), _FILTER_FLAGS


def _enrich_comparison(
    comparison: dict[str, object],
    decisions: dict[str, pd.DataFrame],
    reports: Mapping[str, MakerReplayReport],
    positions: pd.DataFrame,
    filter_flags: Mapping[str, dict[str, object]],
) -> None:
    candidates = comparison.get("candidates")
    if not isinstance(candidates, dict):
        raise RuntimeError("entry-filter comparison candidates are invalid")
    attribution = source_entry_attribution(positions, decisions)
    for name in decisions:
        candidate = candidates.get(name)
        report = reports.get(name)
        if not isinstance(candidate, dict) or report is None:
            raise RuntimeError(f"entry-filter comparison is incomplete for {name}")
        candidate["filter_flags"] = filter_flags[name]
        candidate["decision_identity_sha256"] = decision_identity(decisions[name])
        candidate["directional_decision_bars"] = int(
            decisions[name]["entry_direction"].notna().sum()
        )
        candidate["source_entry_attribution"] = attribution[name]
        candidate["source_fill_proximity"] = source_fill_proximity(
            positions,
            report,
        )


def _report(args: argparse.Namespace) -> dict[str, object]:
    if args.end <= args.start:
        raise ValueError("entry-filter replay end must follow start")
    _verify_config(args.config)
    bars = load_model_bars(args.bars, args.start, args.end)
    decisions, configs, filter_flags = _candidate_inputs(bars, args)
    candidate_order = tuple(decisions)
    expected_order = (
        ENTRY_FILTER_CANDIDATES
        if args.minimum_entry_strength is None
        else STRENGTH_FOLLOWUP_CANDIDATES
    )
    if candidate_order != expected_order or tuple(configs) != candidate_order:
        raise RuntimeError("entry-filter candidate identity changed")
    audit = OxaArchiveAuditConfig("BTC", args.start, args.end, args.data_root)
    bundles = verified_archive_bundles(audit)
    context = load_verified_replay_context(args.price_context, args.funding_context)
    reports = replay_maker_order_decision_grid_chunks(
        archive_evidence_chunks(bundles, include_trades=True),
        decisions,
        configs,
        context=context,
    )
    comparison = summarize_margin_stop_grid(
        reports,
        configs,
        start=pd.Timestamp(args.start),
        end=pd.Timestamp(args.end),
        segment_days=args.segment_days,
    )
    positions = source_positions(args.positions, args.supplemental_positions)
    _enrich_comparison(comparison, decisions, reports, positions, filter_flags)
    experiment = (
        "entry_filter_2x2_factorial_v1"
        if args.minimum_entry_strength is None
        else "hard_recovery_minimum_strength_followup_v1"
    )
    return {
        "ok": True,
        "experiment": experiment,
        **_experiment_contract(args, candidate_order),
        "source_evidence": _source_evidence(args),
        "candidate_configs": {name: asdict(value) for name, value in configs.items()},
        "metalabel_policy": _metalabel_policy(args.config),
        "archive": replay_archive_summary(bundles, context),
        "comparison": comparison,
        "limitations": [
            "All 90 days are development evidence; no sealed holdout is claimed.",
            "Creator screenshots are selected and omit losing trade details.",
            "Public trade-through cannot reveal private queue rank or cancellation.",
            "Authentic mark liquidation still executes at visible BBO without hidden depth.",
        ],
    }


def main() -> int:
    """Write one immutable four-candidate entry-filter report."""
    args = _parser().parse_args()
    try:
        write_immutable_json(args.out, _report(args))
    except (OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
