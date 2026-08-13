"""Rank creator-selected Hypervelocity entry minutes without runtime authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_json
from hypervector.regime.composite import _completed_context, classify_multitimeframe
from hypervector.research.hypervelocity_attribution import build_bar_annotations
from hypervector.research.hypervelocity_bbwp_precedence import (
    apply_1m_bbwp_recovery_delay,
    apply_5m_bbwp_range_precedence,
)
from hypervector.research.hypervelocity_entry_ranking import (
    EntryRankingDataset,
    EntryRankingResult,
    build_entry_ranking_dataset,
    evaluate_entry_ranking,
)
from hypervector.research.hypervelocity_metalabel import (
    BASE_FEATURE_NAMES,
    build_metalabel_rows,
)
from hypervector.research.hypervelocity_metalabel_report import (
    runtime_observe_contract,
)
from hypervector.research.hypervelocity_source_inputs import source_positions
from hypervector.strategies.hypervelocity_profile import load_hypervelocity_profile

_EXPECTED_SOURCE_ENTRIES = 35
_CANDIDATE_ID = "5m_bbwp_hard_range_25_recovery_6_entry_minutes"
_BOOK_COLUMNS = (
    "book_snapshot_age_ms",
    "obi_5",
    "obi_20",
    "obi_5_trailing_median",
    "obi_20_trailing_median",
    "spread_bps",
    "micro_price_delta_bps",
    "ofi_top_5s_normalized",
    "book_window_snapshots",
)


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
    parser.add_argument("--start", type=_utc, required=True)
    parser.add_argument("--end", type=_utc, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _bars(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"entry-ranking bars are missing: {path}")
    frame = pd.read_parquet(path)
    if "timestamp" not in frame:
        raise ValueError("entry-ranking bars require timestamp")
    frame.index = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True))
    if frame.empty or frame.index.has_duplicates:
        raise ValueError("entry-ranking bars must be non-empty and unique")
    if not frame.index.is_monotonic_increasing:
        raise ValueError("entry-ranking bars must be ordered")
    cadence = frame.index.to_series().diff().iloc[1:]
    if not cadence.eq(pd.Timedelta(minutes=1)).all():
        raise ValueError("entry-ranking bars require uninterrupted 1m cadence")
    return frame


def _candidate_decisions(
    bars: pd.DataFrame,
    config_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, int, float]:
    profile = load_hypervelocity_profile(config_path)
    config = profile.regime_config
    decisions = classify_multitimeframe(bars, config=config)
    context_5m = _completed_context(bars, bars.index, 5, config)
    decisions = apply_5m_bbwp_range_precedence(
        decisions,
        context_5m,
        threshold=config.bbwp_compression_threshold,
    )
    decisions = apply_1m_bbwp_recovery_delay(
        decisions,
        threshold=config.bbwp_compression_threshold,
        minimum_age_bars=6,
    )
    return (
        decisions,
        context_5m,
        config.structure_lookback,
        config.bbwp_compression_threshold,
    )


def _empty_book_features(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {name: np.full(len(index), np.nan) for name in _BOOK_COLUMNS},
        index=index,
    )


def _candidate_feature_rows(
    bars: pd.DataFrame,
    config_path: Path,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    decisions, context_5m, lookback, compression = _candidate_decisions(
        bars, config_path
    )
    annotations = build_bar_annotations(
        bars,
        decisions,
        structure_lookback=lookback,
        compression_threshold=compression,
    )
    eligible = decisions["entry_direction"].notna()
    signal_times = decisions.index[eligible] + pd.Timedelta(minutes=1)
    lifecycle = pd.DataFrame(
        {
            "direction": decisions.loc[eligible, "entry_direction"].to_numpy(),
            "signal_time_utc": [value.isoformat() for value in signal_times],
            "placeholder": np.zeros(len(signal_times), dtype="int8"),
        }
    )
    rows = build_metalabel_rows(
        lifecycle,
        decisions,
        context_5m,
        annotations,
        _empty_book_features(signal_times),
        label_column="placeholder",
    )
    rows.index = signal_times
    in_window = (rows.index >= start) & (rows.index < end)
    return rows.loc[in_window, ["direction", *BASE_FEATURE_NAMES]].copy()


def _source_entries(positions_path: Path, supplemental_path: Path) -> pd.DataFrame:
    positions = source_positions(positions_path, supplemental_path)
    if len(positions) != _EXPECTED_SOURCE_ENTRIES:
        raise ValueError(
            f"frozen source population changed: {len(positions)} "
            f"!= {_EXPECTED_SOURCE_ENTRIES}"
        )
    ordered = positions.sort_values("open_time_utc", kind="stable").reset_index(
        drop=True
    )
    return pd.DataFrame(
        {
            "source_id": [f"creator_{number:03d}" for number in range(len(ordered))],
            "event_time": ordered["open_time_utc"].astype(str),
            "side": ordered["side"].astype(str),
        }
    )


def _frame_identity(frame: pd.DataFrame) -> str:
    values = pd.util.hash_pandas_object(
        frame.reset_index(names="candidate_time_utc"), index=False
    )
    return hashlib.sha256(values.to_numpy(dtype="uint64").tobytes()).hexdigest()


def _json_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in frame.to_dict("records"):
        row: dict[str, object] = {}
        for key, value in record.items():
            if pd.isna(value):
                row[str(key)] = None
            elif isinstance(value, np.generic):
                row[str(key)] = value.item()
            else:
                row[str(key)] = value
        rows.append(row)
    return rows


def _wins_against(
    metrics: pd.DataFrame,
    model: str,
    baseline: str,
) -> tuple[int, int]:
    evaluable = metrics.loc[metrics["test_positives"].gt(0)]
    pivot = evaluable.pivot(
        index="test_day_utc", columns="model", values="positive_percentile_mean"
    )
    comparable = pivot[[model, baseline]].dropna()
    return int(comparable[model].gt(comparable[baseline]).sum()), len(comparable)


def _majority(wins: int, total: int) -> bool:
    return total >= 3 and wins > total / 2


def _model_shape_days(
    evaluable: pd.DataFrame,
    model: str,
    source_days: int,
) -> tuple[int, int]:
    recalls = evaluable.loc[evaluable["model"].eq(model), "top_10pct_recall"]
    return int(recalls.gt(0.15).sum()), source_days


def _assessment(
    metrics: pd.DataFrame,
    *,
    source_accounting_complete: bool = True,
) -> dict[str, object]:
    evaluable = metrics.loc[metrics["test_positives"].gt(0)]
    source_days = int(evaluable["test_day_utc"].nunique())
    correctness = source_accounting_complete and source_days >= 3
    learned = ("logistic", "lightgbm")
    uniform_wins = {
        model: _wins_against(metrics, model, "uniform") for model in learned
    }
    strength_wins = {
        model: _wins_against(metrics, model, "strength_only") for model in learned
    }
    no_collapse = {
        model: bool(
            evaluable.loc[evaluable["model"].eq(model), "positive_percentile_mean"]
            .dropna()
            .ge(0.25)
            .all()
        )
        for model in learned
    }
    association = correctness and all(
        _majority(*uniform_wins[model]) and no_collapse[model] for model in learned
    )
    association &= any(_majority(*strength_wins[model]) for model in learned)
    shape_days = {
        model: _model_shape_days(evaluable, model, source_days) for model in learned
    }
    shape = correctness and any(_majority(*shape_days[model]) for model in learned)
    return {
        "correctness_screen_passed": bool(correctness),
        "association_screen_passed": bool(association),
        "shape_screen_passed": bool(shape),
        "advanced_to_l2_trial": bool(correctness and association and shape),
        "evaluable_heldout_source_days": source_days,
        "uniform_day_wins": uniform_wins,
        "strength_day_wins": strength_wins,
        "bottom_quartile_collapse_absent": no_collapse,
        "top_decile_recall_above_15pct_days": shape_days,
    }


def _source_evidence(args: argparse.Namespace) -> dict[str, object]:
    return {
        "bars": file_evidence(args.bars),
        "positions": file_evidence(args.positions),
        "supplemental_positions": file_evidence(args.supplemental_positions),
        "runtime_config": file_evidence(args.config),
    }


def _report(args: argparse.Namespace) -> dict[str, object]:
    if args.end <= args.start:
        raise ValueError("entry-ranking end must follow start")
    runtime_policy = runtime_observe_contract(args.config)
    candidates = _candidate_feature_rows(
        _bars(args.bars), args.config, args.start, args.end
    )
    source = _source_entries(args.positions, args.supplemental_positions)
    dataset = build_entry_ranking_dataset(
        candidates,
        source,
        evidence_start=pd.Timestamp(args.start),
        evidence_end=pd.Timestamp(args.end),
    )
    result = evaluate_entry_ranking(dataset)
    matched = int(dataset.source_alignment["matched_direction"].sum())
    all_accounted = len(dataset.source_alignment) == _EXPECTED_SOURCE_ENTRIES
    assessment = _assessment(
        result.fold_metrics,
        source_accounting_complete=all_accounted,
    )
    return _report_payload(args, dataset, result, runtime_policy, matched, assessment)


def _dataset_summary(
    candidates: pd.DataFrame,
    source_count: int,
    matched: int,
) -> dict[str, object]:
    return {
        "identity_sha256": _frame_identity(candidates),
        "candidate_minutes": len(candidates),
        "source_entries": source_count,
        "matched_direction_entries": matched,
        "unmatched_source_entries": source_count - matched,
        "feature_coverage": {
            name: int(candidates[name].notna().sum()) for name in BASE_FEATURE_NAMES
        },
        "non_entry_label": "unlabeled_not_negative",
    }


def _experiment_contracts(result: EntryRankingResult) -> dict[str, object]:
    return {
        "feature_contract": {
            "id": "causal_bar_regime_13_v1",
            "names": list(BASE_FEATURE_NAMES),
        },
        "model_contract": {
            "id": "fixed_logistic_shallow_lightgbm_v1",
            "searched_set": list(result.searched_set),
            "hyperparameter_search": False,
            "scores_are_probabilities": False,
        },
        "split_contract": {
            "id": "expanding_utc_day_forward_v1",
            "fold_local_fit": True,
        },
    }


def _report_payload(
    args: argparse.Namespace,
    dataset: EntryRankingDataset,
    result: EntryRankingResult,
    runtime_policy: dict[str, object],
    matched: int,
    assessment: dict[str, object],
) -> dict[str, object]:
    candidates = dataset.candidates
    payload = {
        "ok": True,
        "report_only": True,
        "runtime_strategy_changed": False,
        "experiment": "creator_entry_time_positive_unlabeled_ranking_v1",
        "candidate_identity": _CANDIDATE_ID,
        "evidence_window": {
            "start": args.start.isoformat(),
            "end": args.end.isoformat(),
        },
        "source_evidence": _source_evidence(args),
        "runtime_policy": runtime_policy,
        "dataset": _dataset_summary(candidates, len(dataset.source_alignment), matched),
        "source_alignment": _json_records(dataset.source_alignment),
        "fold_audit": _json_records(result.fold_audit),
        "fold_metrics": _json_records(result.fold_metrics),
        "metrics": result.summary,
        "assessment": assessment,
        "limitations": [
            "Creator screenshots are sparse and may omit losing or unremarkable trades.",
            "Unlabeled candidate minutes are not known bad entries.",
            "Scores are ranking annotations, not calibrated entry probabilities.",
            "No orderbook feature, threshold, strategy gate, or runtime model is installed.",
        ],
    }
    payload.update(_experiment_contracts(result))
    return payload


def main() -> int:
    """Write one immutable annotation-only creator entry ranking report."""
    args = _parser().parse_args()
    try:
        if args.out.exists():
            raise FileExistsError(f"entry-ranking output exists: {args.out}")
        report = _report(args)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.out, report)
    except (OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
