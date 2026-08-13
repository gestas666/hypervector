"""Replay strict-source target-only and opposite-entry close/reverse candidates."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.regime.composite import classify_multitimeframe
from hypervector.research.hypertrader_label_evidence import load_label_evidence
from hypervector.research.hypertrader_source_adapter import (
    PINNED_HYPERTRADER_REVISION,
)
from hypervector.research.hypervelocity_close_reverse_compare import (
    aggregate_close_reverse_blocks,
    close_reverse_candidate_configs,
    summarize_close_reverse_grid,
)
from hypervector.research.hypervelocity_metalabel_features import load_model_bars
from hypervector.research.hypervelocity_metalabel_report import (
    runtime_observe_contract,
)
from hypervector.research.hypervelocity_replay_evidence import decision_identity
from hypervector.research.hypervelocity_source_regime_gate import (
    apply_source_regime_agreement,
    bound_decision_grid,
)
from hypervector.research.maker_replay_context_io import (
    context_coverage_report,
    load_verified_replay_context,
)
from hypervector.research.maker_replay_stream import (
    replay_maker_order_decision_grid_chunks,
)
from hypervector.research.research_evidence_source import maker_replay_evidence
from hypervector.strategies.hypervelocity_profile import load_hypervelocity_profile


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--strict-labels", type=Path, required=True)
    parser.add_argument("--strict-metadata", type=Path, required=True)
    parser.add_argument("--price-context", type=Path, required=True)
    parser.add_argument("--funding-context", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--creator-evidence", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument(
        "--window",
        nargs=2,
        action="append",
        type=_utc,
        metavar=("START", "END"),
        required=True,
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _experiment_contract(args: argparse.Namespace) -> dict[str, object]:
    return {
        "report_only": True,
        "runtime_strategy_changed": False,
        "model_authority": "observe_only",
        "portfolio_paths_stitched_across_gaps": False,
        "allocation_fraction": 0.70,
        "leverage": 40.0,
        "gross_margin_target_pct": 8.0,
        "normal_reentry_cooldown_seconds": 60.0,
        "atomic_reversal_bypasses_normal_cooldown": True,
        "requested_windows": len(args.window),
    }


def _validated_windows(
    values: Sequence[Sequence[datetime]],
) -> list[tuple[datetime, datetime]]:
    windows: list[tuple[datetime, datetime]] = []
    previous_end: datetime | None = None
    for value in values:
        start, end = value
        if end <= start:
            raise ValueError("close/reverse window end must follow start")
        if previous_end is not None and start < previous_end:
            raise ValueError(
                "close/reverse windows must be ordered and non-overlapping"
            )
        windows.append((start, end))
        previous_end = end
    return windows


def _strict_labels(args: argparse.Namespace) -> tuple[pd.DataFrame, dict[str, object]]:
    evidence = load_label_evidence(args.strict_labels, args.strict_metadata)
    valid = evidence.metadata_verified
    valid &= evidence.revision == PINNED_HYPERTRADER_REVISION
    if not valid:
        raise ValueError("strict Hypertrader label revision or metadata is invalid")
    labels = pd.read_parquet(args.strict_labels)
    if labels.empty:
        raise ValueError("strict Hypertrader label file is empty")
    return labels, {
        "revision": evidence.revision,
        "metadata_verified": evidence.metadata_verified,
        "files": evidence.files,
    }


def _decisions(
    bars: pd.DataFrame,
    labels: pd.DataFrame,
    config_path: Path,
    *,
    start: datetime,
    end: datetime,
) -> dict[str, pd.DataFrame]:
    profile = load_hypervelocity_profile(config_path)
    canonical = classify_multitimeframe(bars, config=profile.regime_config)
    strict = apply_source_regime_agreement(
        canonical,
        labels,
        revision="strict",
    )
    names = close_reverse_candidate_configs()
    return bound_decision_grid(
        {name: strict.copy() for name in names},
        start=start,
        end=end,
    )


def _warmup(
    bars: pd.DataFrame,
    start: datetime,
    end: datetime,
) -> dict[str, object]:
    return {
        "history_start_utc": bars.index[0].isoformat(),
        "history_end_utc_exclusive": (
            bars.index[-1] + pd.Timedelta(minutes=1)
        ).isoformat(),
        "prior_causal_bars": int((bars.index < start).sum()),
        "evaluated_bars": int(((bars.index >= start) & (bars.index < end)).sum()),
        "future_bars_loaded": 0,
    }


def _window_report(
    args: argparse.Namespace,
    labels: pd.DataFrame,
    context: object,
    start: datetime,
    end: datetime,
) -> dict[str, object]:
    bars = load_model_bars(args.bars, start, end, include_prior=True)
    decisions = _decisions(bars, labels, args.config, start=start, end=end)
    configs = close_reverse_candidate_configs()
    replay = maker_replay_evidence(
        args.data_root,
        "BTC",
        start,
        end,
        include_trades=True,
        database_path=args.database,
    )
    reports = replay_maker_order_decision_grid_chunks(
        replay.chunks,
        decisions,
        configs,
        context=context,
    )
    inconclusive = [
        name
        for name, report in reports.items()
        if not report.execution_economics_conclusive
    ]
    if inconclusive:
        raise ValueError(
            f"close/reverse replay has incomplete L2 evidence: {inconclusive}"
        )
    comparison = summarize_close_reverse_grid(
        reports,
        configs,
        start=pd.Timestamp(start),
        end=pd.Timestamp(end),
    )
    return {
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "causal_warmup": _warmup(bars, start, end),
        "decision_identity_sha256": decision_identity(next(iter(decisions.values()))),
        "archive": replay.summary,
        "comparison": comparison,
    }


def _source_evidence(
    args: argparse.Namespace,
    labels: dict[str, object],
) -> dict[str, object]:
    return {
        "bars": file_evidence(args.bars),
        "config": file_evidence(args.config),
        "strict_labels": labels,
        "price_context": file_evidence(args.price_context),
        "funding_context": file_evidence(args.funding_context),
        "database": file_evidence(args.database),
        "creator_close_reverse": file_evidence(args.creator_evidence),
    }


def _report(args: argparse.Namespace) -> dict[str, object]:
    windows = _validated_windows(args.window)
    labels, label_evidence = _strict_labels(args)
    context = load_verified_replay_context(args.price_context, args.funding_context)
    blocks = [
        _window_report(args, labels, context, start, end) for start, end in windows
    ]
    comparisons = [block["comparison"] for block in blocks]
    return {
        "ok": True,
        "experiment": "strict_source_opposite_entry_close_reverse_v1",
        **_experiment_contract(args),
        "candidate_configs": {
            name: asdict(config)
            for name, config in close_reverse_candidate_configs().items()
        },
        "runtime_policy": runtime_observe_contract(args.config),
        "source_evidence": _source_evidence(args, label_evidence),
        "context": context_coverage_report(context),
        "blocks": blocks,
        "aggregate": aggregate_close_reverse_blocks(comparisons),
        "limitations": [
            "Public trade-through cannot observe private queue rank or cancellation.",
            "Authentic mark liquidation exits at visible BBO without hidden depth.",
            "Creator close minutes lack exact fills and causal exit reasons.",
            "Each gap-free block resets equity; paths are not stitched across gaps.",
        ],
    }


def main() -> int:
    """Write one immutable close/reverse comparison over explicit windows."""
    args = _parser().parse_args()
    try:
        write_immutable_json(args.out, _report(args))
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
