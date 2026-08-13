"""Reproducible report assembly for Hypervelocity causal attribution."""

from __future__ import annotations

import json
import tomllib
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_archive_audit import (
    OxaArchiveAuditConfig,
    verified_archive_bundles,
)
from hypervector.data.oxa_storage import file_evidence
from hypervector.regime.composite import classify_multitimeframe
from hypervector.regime.hypervelocity_candidates import (
    HypervelocityRegimeCandidate,
    hypervelocity_candidate_matrix,
)
from hypervector.research.hypervelocity_attribution import (
    align_book_pressure,
    attribution_slices,
    build_bar_annotations,
    build_lifecycle_attribution,
)
from hypervector.research.hypervelocity_attribution_io import (
    load_signal_book_pressure,
)

_DIMENSIONS = (
    "direction",
    "regime_age_bucket",
    "structure_distance_bucket",
    "bbwp_recency_bucket",
    "context_15m_alignment",
    "pressure_alignment",
)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} contains a non-string key")
    return value


def _read_json(path: Path) -> Mapping[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"comparison report is missing: {path}")
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"comparison report is invalid JSON: {path}") from exc
    return _mapping(payload, "comparison report")


def _candidate(candidate_id: str) -> HypervelocityRegimeCandidate:
    candidates = {
        candidate.candidate_id: candidate
        for candidate in hypervelocity_candidate_matrix()
    }
    if candidate_id not in candidates:
        raise ValueError(f"unknown Hypervelocity attribution candidate: {candidate_id}")
    return candidates[candidate_id]


def _lifecycle_frame(
    payload: Mapping[str, object],
    candidate: HypervelocityRegimeCandidate,
    fill_rule: str,
) -> pd.DataFrame:
    if payload.get("ok") is not True or payload.get("report_only") is not True:
        raise ValueError("comparison report is not successful report-only evidence")
    replay = _mapping(payload.get("l2_replay"), "comparison l2_replay")
    candidate_replay = _mapping(replay.get(candidate.candidate_id), "candidate replay")
    identity = _mapping(candidate_replay.get("candidate"), "candidate identity")
    if dict(identity) != candidate.to_dict():
        raise ValueError(
            "candidate fingerprint or parameters differ from source report"
        )
    reports = _mapping(candidate_replay.get("reports"), "candidate reports")
    report = _mapping(reports.get(fill_rule), f"{fill_rule} report")
    lifecycles = report.get("lifecycles")
    if not isinstance(lifecycles, list):
        raise ValueError("maker replay lifecycles must be an array")
    rows = [dict(_mapping(row, "maker replay lifecycle")) for row in lifecycles]
    return pd.DataFrame(rows)


def _indexed_bars(path: Path, start: datetime, end: datetime) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Hyperliquid bar evidence is missing: {path}")
    bars = pd.read_parquet(path)
    if "timestamp" not in bars:
        raise ValueError("Hyperliquid bar evidence requires timestamp")
    index = pd.DatetimeIndex(pd.to_datetime(bars["timestamp"], utc=True))
    bars = bars.set_axis(index)
    bars = bars.loc[(bars.index >= start) & (bars.index < end)].copy()
    if bars.empty:
        raise ValueError("Hyperliquid bar evidence does not cover the analysis window")
    if not bars.index.is_monotonic_increasing or bars.index.has_duplicates:
        raise ValueError("Hyperliquid bar timestamps must be unique and increasing")
    cadence = bars.index.to_series().diff().iloc[1:]
    if not cadence.eq(pd.Timedelta(minutes=1)).all():
        raise ValueError(
            "Hyperliquid attribution bars require uninterrupted 1m cadence"
        )
    return bars


def _runtime_contract(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"faithful runtime config is missing: {path}")
    with path.open("rb") as handle:
        payload = tomllib.load(handle)
    model = _mapping(payload.get("model"), "faithful model policy")
    runtime = _mapping(payload.get("runtime"), "faithful runtime policy")
    observed = {
        "mode": model.get("mode"),
        "may_filter": model.get("may_filter"),
        "may_scale": model.get("may_scale"),
        "runtime_mode": runtime.get("metalabel_mode"),
    }
    expected = {
        "mode": "observe",
        "may_filter": False,
        "may_scale": False,
        "runtime_mode": "observe",
    }
    if observed != expected:
        raise ValueError(
            f"metalabel policy violates frozen observe contract: {observed}"
        )
    return {**observed, "config_evidence": file_evidence(path)}


def summarize_attribution(attributed: pd.DataFrame) -> dict[str, object]:
    """Summarize all lifecycles without creating a promotion gate."""
    if "status" not in attributed or "book_snapshot_ts_ms" not in attributed:
        raise ValueError(
            "attributed lifecycles require status and book evidence fields"
        )
    counts = attributed["status"].astype(str).value_counts().sort_index()
    return {
        "report_only": True,
        "runtime_strategy_changed": False,
        "lifecycles": len(attributed),
        "status_counts": {str(key): int(value) for key, value in counts.items()},
        "book_pressure_coverage": int(attributed["book_snapshot_ts_ms"].notna().sum()),
        "book_pressure_missing": int(attributed["book_snapshot_ts_ms"].isna().sum()),
        "slices": attribution_slices(attributed, _DIMENSIONS),
    }


def _json_rows(frame: pd.DataFrame) -> list[dict[str, object]]:
    records = frame.astype(object).where(frame.notna(), None).to_dict("records")
    return [{str(key): value for key, value in row.items()} for row in records]


def _validate_source_archive(
    payload: Mapping[str, object], start: datetime, end: datetime
) -> Mapping[str, object]:
    archive = _mapping(payload.get("archive"), "comparison archive")
    expected = (start.isoformat(), end.isoformat())
    observed = (archive.get("start"), archive.get("end"))
    if observed != expected or archive.get("checksums_verified") is not True:
        raise ValueError("comparison archive bounds or checksum status do not match")
    return archive


def generate_attribution_report(
    *,
    comparison_path: Path,
    bars_path: Path,
    data_root: Path,
    runtime_config_path: Path,
    start: datetime,
    end: datetime,
    candidate_id: str,
    fill_rule: str,
) -> dict[str, object]:
    """Generate a checksum-verified, causal Hypervelocity attribution report."""
    payload = _read_json(comparison_path)
    source_archive = _validate_source_archive(payload, start, end)
    candidate = _candidate(candidate_id)
    lifecycles = _lifecycle_frame(payload, candidate, fill_rule)
    bars = _indexed_bars(bars_path, start, end)
    decisions = classify_multitimeframe(bars, config=candidate.config)
    bar_annotations = build_bar_annotations(
        bars,
        decisions,
        structure_lookback=candidate.config.structure_lookback,
        compression_threshold=candidate.config.bbwp_compression_threshold,
    )
    signal_times = pd.DatetimeIndex(
        pd.to_datetime(lifecycles["signal_time_utc"], utc=True)
    )
    archive_config = OxaArchiveAuditConfig("BTC", start, end, data_root)
    bundles = verified_archive_bundles(archive_config)
    pressure = load_signal_book_pressure(bundles, signal_times)
    book_annotations = align_book_pressure(signal_times, pressure)
    attributed = build_lifecycle_attribution(
        lifecycles, bar_annotations, book_annotations
    )
    return {
        "ok": True,
        "report_only": True,
        "candidate": candidate.to_dict(),
        "fill_rule": fill_rule,
        "analysis_window": {"start": start.isoformat(), "end": end.isoformat()},
        "source_evidence": {
            "comparison": file_evidence(comparison_path),
            "bars": file_evidence(bars_path),
            "archive": dict(source_archive),
        },
        "metalabel_policy": _runtime_contract(runtime_config_path),
        "summary": summarize_attribution(attributed),
        "rows": _json_rows(attributed),
        "limitations": (
            "L2 pressure is public displayed liquidity and can change or be canceled.",
            "Pressure is annotation-only and has not been validated as causal edge.",
            "Five-minute structure uses prior rolling extremes, not discretionary zones.",
            "Historical funding and authentic venue mark price remain unavailable here.",
        ),
    }
