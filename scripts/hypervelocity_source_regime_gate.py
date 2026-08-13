"""Replay current Hypervelocity entries under causal Hypertrader regime agreement."""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.regime.composite import _completed_context, classify_multitimeframe
from hypervector.research.hypertrader_label_evidence import load_label_evidence
from hypervector.research.hypertrader_source_adapter import (
    LEGACY_HYPERTRADER_REVISION,
    PINNED_HYPERTRADER_REVISION,
)
from hypervector.research.hypervelocity_entry_filter_factorial import (
    entry_filter_decision_grid,
    source_entry_attribution,
    source_fill_proximity,
)
from hypervector.research.hypervelocity_margin_stop_compare import (
    margin_stop_candidate_configs,
    summarize_margin_stop_grid,
    wide_margin_stop_candidate_configs,
)
from hypervector.research.hypervelocity_metalabel_features import load_model_bars
from hypervector.research.hypervelocity_metalabel_report import runtime_observe_contract
from hypervector.research.hypervelocity_replay_evidence import decision_identity
from hypervector.research.hypervelocity_source_inputs import source_positions
from hypervector.research.hypervelocity_source_regime_gate import (
    apply_source_regime_agreement,
    bound_decision_grid,
    source_regime_agreement_grid,
    source_regime_interaction_grid,
    source_regime_quality_timing_grid,
)
from hypervector.research.hypervelocity_stop_counterfactual import (
    attach_consolidation_wick_stops,
)
from hypervector.research.maker_replay_context_io import (
    context_coverage_report,
    load_verified_replay_context,
)
from hypervector.research.maker_replay_models import (
    MakerReplayConfig,
    MakerReplayReport,
)
from hypervector.research.maker_replay_stream import (
    replay_maker_order_decision_grid_chunks,
)
from hypervector.research.research_evidence_source import maker_replay_evidence
from hypervector.strategies.hypervelocity_profile import load_hypervelocity_profile

_REVISIONS = {
    "strict": PINNED_HYPERTRADER_REVISION,
    "legacy": LEGACY_HYPERTRADER_REVISION,
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
    parser.add_argument("--strict-labels", type=Path, required=True)
    parser.add_argument("--strict-metadata", type=Path, required=True)
    parser.add_argument("--legacy-labels", type=Path, required=True)
    parser.add_argument("--legacy-metadata", type=Path, required=True)
    parser.add_argument("--price-context", type=Path, required=True)
    parser.add_argument("--funding-context", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--start", type=_utc, required=True)
    parser.add_argument("--end", type=_utc, required=True)
    parser.add_argument("--segment-days", type=int, default=30)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--hard-recovery-interaction", action="store_true")
    mode.add_argument("--hard-recovery-wick-stop", action="store_true")
    mode.add_argument("--strict-stop25", action="store_true")
    mode.add_argument("--strict-quality-timing", action="store_true")
    mode.add_argument("--strict-control-only", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _label_pair(
    labels_path: Path,
    metadata_path: Path,
    expected_revision: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    evidence = load_label_evidence(labels_path, metadata_path)
    if not evidence.metadata_verified or evidence.revision != expected_revision:
        raise ValueError("Hypertrader label revision or metadata is invalid")
    labels = pd.read_parquet(labels_path)
    if labels.empty:
        raise ValueError("Hypertrader label file is empty")
    return labels, {
        "revision": evidence.revision,
        "metadata_verified": evidence.metadata_verified,
        "files": evidence.files,
    }


def _label_sources(
    args: argparse.Namespace,
) -> tuple[dict[str, pd.DataFrame], dict[str, object]]:
    frames: dict[str, pd.DataFrame] = {}
    evidence: dict[str, object] = {}
    for name in _REVISIONS:
        frame, item = _label_pair(
            getattr(args, f"{name}_labels"),
            getattr(args, f"{name}_metadata"),
            _REVISIONS[name],
        )
        frames[name] = frame
        evidence[name] = item
    return frames, evidence


def _decisions(
    bars: pd.DataFrame,
    config_path: Path,
    labels: Mapping[str, pd.DataFrame],
    *,
    hard_recovery_interaction: bool,
    hard_recovery_wick_stop: bool,
    strict_stop25: bool,
    strict_quality_timing: bool,
    strict_control_only: bool,
) -> dict[str, pd.DataFrame]:
    profile = load_hypervelocity_profile(config_path)
    canonical = classify_multitimeframe(bars, config=profile.regime_config)
    if strict_control_only:
        strict = apply_source_regime_agreement(
            canonical,
            labels["strict"],
            revision="strict",
        )
        return {"strict_source_control": strict}
    if strict_stop25:
        strict = apply_source_regime_agreement(
            canonical,
            labels["strict"],
            revision="strict",
        )
        return {name: strict.copy() for name in _configs({}, strict_stop25=True)}
    if strict_quality_timing:
        return source_regime_quality_timing_grid(canonical, labels["strict"])
    if hard_recovery_interaction or hard_recovery_wick_stop:
        context_5m = _completed_context(bars, bars.index, 5, profile.regime_config)
        filtered = entry_filter_decision_grid(
            canonical,
            context_5m,
            compression_threshold=(profile.regime_config.bbwp_compression_threshold),
            recovery_age_bars=6,
        )
        hard_recovery = filtered["hard_bbwp_recovery6"]
        if hard_recovery_wick_stop:
            stopped = attach_consolidation_wick_stops(
                bars,
                hard_recovery,
                threshold=profile.regime_config.bbwp_compression_threshold,
            )
            return {
                "hard_bbwp_recovery6_control": hard_recovery,
                "hard_bbwp_recovery6_consolidation_wick_stop": stopped,
            }
        return source_regime_interaction_grid(
            canonical, hard_recovery, labels["strict"]
        )
    return source_regime_agreement_grid(canonical, labels)


def _configs(
    decisions: Mapping[str, pd.DataFrame],
    *,
    strict_stop25: bool = False,
) -> dict[str, MakerReplayConfig]:
    if strict_stop25:
        grid = wide_margin_stop_candidate_configs()
        return {name: grid[name] for name in ("no_stop_control", "stop_25pct_margin")}
    control = margin_stop_candidate_configs()["no_stop_control"]
    return {name: control for name in decisions}


def _candidate_gate_counts(decisions: pd.DataFrame) -> dict[str, int]:
    counts = Counter(decisions["reason"].astype(str))
    return {
        reason: int(counts.get(reason, 0))
        for reason in (
            "source_regime_unavailable",
            "source_regime_not_tradable",
            "source_regime_direction_mismatch",
        )
    }


def _enrich(
    comparison: dict[str, object],
    decisions: Mapping[str, pd.DataFrame],
    reports: Mapping[str, MakerReplayReport],
    positions: pd.DataFrame,
) -> None:
    candidates = comparison.get("candidates")
    if not isinstance(candidates, dict):
        raise RuntimeError("source-regime comparison candidates are invalid")
    attribution = source_entry_attribution(positions, decisions)
    for name, frame in decisions.items():
        candidate = candidates.get(name)
        if not isinstance(candidate, dict):
            raise RuntimeError(f"source-regime candidate is missing: {name}")
        candidate["directional_decision_bars"] = int(
            frame["entry_direction"].notna().sum()
        )
        candidate["decision_identity_sha256"] = decision_identity(frame)
        candidate["source_entry_attribution"] = attribution[name]
        candidate["source_fill_proximity"] = source_fill_proximity(
            positions, reports[name]
        )
        candidate["source_regime_gate_counts"] = _candidate_gate_counts(frame)


def _source_evidence(
    args: argparse.Namespace,
    labels: dict[str, object],
) -> dict[str, object]:
    return {
        "bars": file_evidence(args.bars),
        "positions": file_evidence(args.positions),
        "supplemental_positions": file_evidence(args.supplemental_positions),
        "runtime_config": file_evidence(args.config),
        "price_context": file_evidence(args.price_context),
        "funding_context": file_evidence(args.funding_context),
        "hypertrader_labels": labels,
    }


def _contract(args: argparse.Namespace) -> dict[str, object]:
    return {
        "report_only": True,
        "runtime_strategy_changed": False,
        "causal_label_rule": "label available_at <= decision_time + 1 minute",
        "window_start_utc": args.start.isoformat(),
        "window_end_utc": args.end.isoformat(),
        "allocation_fraction": 0.70,
        "leverage": 40.0,
        "gross_margin_target_pct": 8.0,
        "hard_recovery_interaction": args.hard_recovery_interaction,
        "hard_recovery_wick_stop": args.hard_recovery_wick_stop,
        "strict_stop25": args.strict_stop25,
        "strict_quality_timing": args.strict_quality_timing,
        "strict_control_only": args.strict_control_only,
    }


def _warmup_contract(
    bars: pd.DataFrame,
    *,
    start: datetime,
    end: datetime,
) -> dict[str, object]:
    prior = bars.index < start
    evaluated = (bars.index >= start) & (bars.index < end)
    return {
        "history_start_utc": bars.index[0].isoformat(),
        "history_end_utc_exclusive": (
            bars.index[-1] + pd.Timedelta(minutes=1)
        ).isoformat(),
        "prior_causal_bars": int(prior.sum()),
        "evaluated_bars": int(evaluated.sum()),
        "future_bars_loaded": 0,
    }


def _run_replay(
    args: argparse.Namespace,
    decisions: Mapping[str, pd.DataFrame],
    configs: Mapping[str, MakerReplayConfig],
) -> tuple[dict[str, object], dict[str, object]]:
    context = load_verified_replay_context(args.price_context, args.funding_context)
    replay = maker_replay_evidence(
        args.data_root,
        "BTC",
        args.start,
        args.end,
        include_trades=True,
        database_path=args.database,
    )
    reports = replay_maker_order_decision_grid_chunks(
        replay.chunks, decisions, configs, context=context
    )
    comparison = summarize_margin_stop_grid(
        reports,
        configs,
        start=pd.Timestamp(args.start),
        end=pd.Timestamp(args.end),
        segment_days=args.segment_days,
    )
    positions = source_positions(args.positions, args.supplemental_positions)
    _enrich(comparison, decisions, reports, positions)
    archive = {
        **replay.summary,
        "start": args.start.isoformat(),
        "end": args.end.isoformat(),
        "context": context_coverage_report(context),
    }
    return comparison, archive


def _report(args: argparse.Namespace) -> dict[str, object]:
    if args.end <= args.start:
        raise ValueError("source-regime replay end must follow start")
    labels, label_evidence = _label_sources(args)
    bars = load_model_bars(args.bars, args.start, args.end, include_prior=True)
    decisions = _decisions(
        bars,
        args.config,
        labels,
        hard_recovery_interaction=args.hard_recovery_interaction,
        hard_recovery_wick_stop=args.hard_recovery_wick_stop,
        strict_stop25=args.strict_stop25,
        strict_quality_timing=args.strict_quality_timing,
        strict_control_only=args.strict_control_only,
    )
    decisions = bound_decision_grid(decisions, start=args.start, end=args.end)
    configs = _configs(decisions, strict_stop25=args.strict_stop25)
    comparison, archive = _run_replay(args, decisions, configs)
    return {
        "ok": True,
        "experiment": _experiment_name(args),
        **_contract(args),
        "causal_warmup": _warmup_contract(
            bars,
            start=args.start,
            end=args.end,
        ),
        "candidate_order": list(decisions),
        "candidate_configs": {name: asdict(config) for name, config in configs.items()},
        "metalabel_policy": runtime_observe_contract(args.config),
        "source_evidence": _source_evidence(args, label_evidence),
        "archive": archive,
        "comparison": comparison,
        "limitations": [
            "All replay windows are development evidence; no sealed holdout is claimed.",
            "Creator screenshots are selected and omit losing trade details.",
            "Public trade-through cannot reveal private queue rank or cancellation.",
            "Authentic mark liquidation still exits at visible BBO without hidden depth.",
        ],
    }


def _experiment_name(args: argparse.Namespace) -> str:
    """Return the explicit report identity for one mutually exclusive mode."""
    if args.strict_control_only:
        return "strict_source_control_runtime60_v1"
    if args.strict_quality_timing:
        return "strict_source_quality_timing_v1"
    if args.strict_stop25:
        return "strict_source_agreement_stop25_v1"
    if args.hard_recovery_wick_stop:
        return "hard_recovery_consolidation_wick_stop_v1"
    if args.hard_recovery_interaction:
        return "hard_recovery_strict_source_interaction_v1"
    return "causal_hypertrader_regime_agreement_v1"


def main() -> int:
    """Write one immutable causal source-regime agreement replay report."""
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
