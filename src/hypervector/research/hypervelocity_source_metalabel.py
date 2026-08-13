"""Assemble gap-separated strict-source replays for causal metalabel research."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.hypervelocity_metalabel import (
    build_metalabel_rows,
    feature_coverage,
    resolved_comparison_candidate_lifecycles,
    signal_times_utc,
)
from hypervector.research.hypervelocity_metalabel_features import (
    candidate_feature_frames,
    load_model_bars,
    signal_book_features,
)
from hypervector.research.hypervelocity_metalabel_report import (
    MetalabelDatasetAssembly,
    MetalabelPopulationContract,
    _archive_contract,
    _read_json,
    _validate_frozen_population,
    runtime_observe_contract,
    verify_recovery_source_files,
)
from hypervector.research.hypervelocity_source_features import (
    source_feature_coverage,
    source_regime_features,
)

_CANDIDATE = "strict_source_control"
_REPLAY_SETTINGS: dict[str, object] = {
    "entry_depth_ticks": 0,
    "entry_ttl_seconds": 300.0,
    "fill_rule": "trade-through",
    "fixed_margin_stop_pct": None,
    "maximum_hold_seconds": None,
    "reentry_cooldown_seconds": 60.0,
    "same_direction_reentry_policy": "regime_reset",
    "target_continuation_limit_per_episode": None,
}


@dataclass(frozen=True)
class VerifiedSourceSegment:
    """One immutable, execution-conclusive, gap-free replay segment."""

    path: Path
    start: datetime
    end: datetime
    lifecycles: pd.DataFrame
    archive: dict[str, object]
    candidate_config: dict[str, object]


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} contains a non-string key")
    return value


def _utc(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO8601 timestamp")
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a UTC offset")
    return parsed.tz_convert("UTC").to_pydatetime()


def _validate_candidate_config(payload: Mapping[str, object]) -> dict[str, object]:
    configs = _mapping(payload.get("candidate_configs"), "candidate configs")
    observed = dict(_mapping(configs.get(_CANDIDATE), _CANDIDATE))
    mismatches = {
        key: (observed.get(key), expected)
        for key, expected in _REPLAY_SETTINGS.items()
        if observed.get(key) != expected
    }
    if mismatches:
        raise ValueError(f"strict-source runtime replay settings differ: {mismatches}")
    expected_top = {
        "allocation_fraction": 0.70,
        "leverage": 40.0,
        "gross_margin_target_pct": 8.0,
    }
    top_mismatches = {
        key: (payload.get(key), expected)
        for key, expected in expected_top.items()
        if payload.get(key) != expected
    }
    if top_mismatches:
        raise ValueError(f"strict-source portfolio settings differ: {top_mismatches}")
    return observed


def _validate_replay(payload: Mapping[str, object]) -> None:
    comparison = _mapping(payload.get("comparison"), "source comparison")
    candidates = _mapping(comparison.get("candidates"), "source candidates")
    candidate = _mapping(candidates.get(_CANDIDATE), _CANDIDATE)
    replay = _mapping(candidate.get("replay"), "strict-source replay")
    required = {
        "fill_rule": "trade-through",
        "liquidation_model": "hyperliquid_mark_bbo_execution_v1",
        "execution_economics_conclusive": True,
        "active_book_gap_windows": 0,
        "empty_book_evidence_windows": 0,
    }
    mismatches = {
        key: (replay.get(key), expected)
        for key, expected in required.items()
        if replay.get(key) != expected
    }
    if mismatches:
        raise ValueError(f"strict-source replay evidence is inconclusive: {mismatches}")


def validate_source_segment(path: Path) -> VerifiedSourceSegment:
    """Validate and extract one corrected strict-source replay artifact."""
    payload = _read_json(path)
    start = _utc(payload.get("window_start_utc"), "source window start")
    end = _utc(payload.get("window_end_utc"), "source window end")
    if end <= start:
        raise ValueError("source replay end must follow start")
    archive = _archive_contract(payload, start, end)
    if (
        archive.get("empty_book_windows") != 0
        or archive.get("empty_trade_windows") != 0
    ):
        raise ValueError("strict-source archive window contains empty evidence")
    candidate_config = _validate_candidate_config(payload)
    _validate_replay(payload)
    lifecycles = resolved_comparison_candidate_lifecycles(
        payload,
        candidate_name=_CANDIDATE,
    )
    return VerifiedSourceSegment(
        path=path,
        start=start,
        end=end,
        lifecycles=lifecycles,
        archive=archive,
        candidate_config=candidate_config,
    )


def _ordered_segments(paths: Sequence[Path]) -> tuple[VerifiedSourceSegment, ...]:
    if not paths:
        raise ValueError("at least one strict-source replay is required")
    segments = tuple(
        sorted((validate_source_segment(path) for path in paths), key=lambda x: x.start)
    )
    for previous, current in zip(segments, segments[1:], strict=False):
        if current.start < previous.end:
            raise ValueError("strict-source replay windows overlap")
        if current.candidate_config != previous.candidate_config:
            raise ValueError("strict-source replay candidate configs differ")
    return segments


def _verify_source_labels(payload: Mapping[str, object], path: Path) -> None:
    sources = _mapping(payload.get("source_evidence"), "source evidence")
    labels = _mapping(sources.get("hypertrader_labels"), "source label evidence")
    strict = _mapping(labels.get("strict"), "strict source label evidence")
    files = _mapping(strict.get("files"), "strict source label files")
    declared = dict(_mapping(files.get("labels"), "strict source labels"))
    if declared != file_evidence(path):
        raise ValueError("strict source label file evidence differs")


def _segment_rows(
    segment: VerifiedSourceSegment,
    *,
    data_root: Path,
    decisions: pd.DataFrame,
    context_5m: pd.DataFrame,
    bar_features: pd.DataFrame,
    source_labels: pd.DataFrame | None,
) -> pd.DataFrame:
    lifecycles = segment.lifecycles.copy()
    segment_id = f"{segment.start.isoformat()}_{segment.end.isoformat()}"
    lifecycles["segment_id"] = segment_id
    signals = signal_times_utc(lifecycles)
    books = signal_book_features(data_root, segment.start, segment.end, signals)
    rows = build_metalabel_rows(
        lifecycles,
        decisions,
        context_5m,
        bar_features,
        books,
        bar_alignment="backward",
    )
    if source_labels is not None:
        source = source_regime_features(source_labels, signals).reset_index(drop=True)
        rows = pd.concat([rows.reset_index(drop=True), source], axis=1)
    return rows


def assemble_source_metalabel_dataset(
    *,
    replay_paths: Sequence[Path],
    bars_path: Path,
    config_path: Path,
    data_root: Path,
    expected_resolved: int,
    expected_liquidations: int,
    source_labels_path: Path | None = None,
) -> MetalabelDatasetAssembly:
    """Assemble exact gap-free replay blocks into one annotation-only dataset."""
    if expected_resolved < 1 or not 0 < expected_liquidations < expected_resolved:
        raise ValueError("source population expectations must contain both classes")
    segments = _ordered_segments(replay_paths)
    sources = verify_recovery_source_files(
        _read_json(segments[0].path), bars_path, config_path
    )
    for segment in segments[1:]:
        verify_recovery_source_files(_read_json(segment.path), bars_path, config_path)
    source_labels = None
    if source_labels_path is not None:
        for segment in segments:
            _verify_source_labels(_read_json(segment.path), source_labels_path)
        source_labels = pd.read_parquet(source_labels_path)
    bars = load_model_bars(
        bars_path,
        segments[0].start,
        segments[-1].end,
        include_prior=True,
    )
    decisions, context_5m, bar_features = candidate_feature_frames(
        bars,
        config_path,
        "faithful",
    )
    rows = pd.concat(
        [
            _segment_rows(
                segment,
                data_root=data_root,
                decisions=decisions,
                context_5m=context_5m,
                bar_features=bar_features,
                source_labels=source_labels,
            )
            for segment in segments
        ],
        ignore_index=True,
    ).sort_values("signal_ts_ms", kind="stable", ignore_index=True)
    contract = MetalabelPopulationContract(
        profile="strict-source-runtime60",
        identity_field="comparison.candidates",
        expected_identity=_CANDIDATE,
        expected_resolved=expected_resolved,
        expected_liquidations=expected_liquidations,
        expected_positives=expected_liquidations,
        label_column="liquidation_risk",
        decision_profile="faithful",
        bar_alignment="backward",
        source_key="strict_source_replays",
    )
    _validate_frozen_population(rows, contract)
    sources[contract.source_key] = [file_evidence(segment.path) for segment in segments]
    if source_labels_path is not None:
        sources["strict_source_labels"] = file_evidence(source_labels_path)
    archive = {
        "checksums_verified": True,
        "gap_separated_segments": [segment.archive for segment in segments],
        "candidate_config": segments[0].candidate_config,
    }
    coverage = feature_coverage(rows)
    if source_labels is not None:
        coverage.update(source_feature_coverage(rows))
    return MetalabelDatasetAssembly(
        rows=rows,
        source_evidence=sources,
        archive_evidence=archive,
        runtime_policy=runtime_observe_contract(config_path),
        feature_coverage=coverage,
        population_contract=contract,
    )
