"""Point-in-time Hyperliquid L2 features for HYPE breakout entries."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Literal, Sequence

import numpy as np
import pandas as pd

from hypervector.data.hl_events import L2SnapshotEvent
from hypervector.data.hl_rest_l2_recorder import REST_L2_SOURCE
from hypervector.data.oxa_storage import open_text_reader, verify_file_evidence

HYPE_ENTRY_L2_FEATURES: tuple[str, ...] = (
    "l2_spread_latest_bps",
    "l2_spread_mean_60s_bps",
    "l2_spread_p90_60s_bps",
    "l2_spread_max_60s_bps",
    "l2_aligned_microprice_latest_bps",
    "l2_aligned_imbalance_top1_latest",
    "l2_aligned_imbalance_top5_latest",
    "l2_aligned_imbalance_top20_latest",
    "l2_aligned_imbalance_top5_mean_5s",
    "l2_aligned_imbalance_top5_mean_15s",
    "l2_aligned_imbalance_top5_mean_30s",
    "l2_aligned_imbalance_top5_mean_60s",
    "l2_imbalance_top5_std_60s",
    "l2_aligned_imbalance_top5_change_5s",
    "l2_aligned_imbalance_top5_change_15s",
    "l2_aligned_imbalance_top5_change_30s",
    "l2_aligned_mid_return_5s_bps",
    "l2_aligned_mid_return_15s_bps",
    "l2_aligned_mid_return_30s_bps",
    "l2_aligned_mid_return_60s_bps",
    "l2_mid_range_60s_bps",
    "l2_mid_realized_vol_60s_bps",
    "l2_aligned_depth_log_ratio_latest",
    "l2_aligned_top1_concentration_diff_latest",
    "l2_snapshot_rate_60s",
)

_IDENTITY_COLUMNS = ("side", "signal_time_utc", "entry_time_utc")
_AUDIT_COLUMNS = (
    "window_id",
    *_IDENTITY_COLUMNS,
    "bundle_path",
    "status",
    "manifest_complete",
    "row_count",
    "pre_entry_rows",
    "post_entry_rows",
    "last_pre_entry_age_ms",
    "first_post_entry_delay_ms",
    "causal_covered",
    "execution_covered",
)


@dataclass(frozen=True)
class HypeL2EntryDataset:
    """Covered entry rows, full coverage index, and report-only evidence."""

    rows: pd.DataFrame
    coverage: pd.DataFrame
    report: dict[str, object]


@dataclass(frozen=True)
class _BookSnapshot:
    timestamp_ms: int
    midpoint: float
    spread_bps: float
    microprice_bps: float
    imbalance_top1: float
    imbalance_top5: float
    imbalance_top20: float
    depth_log_ratio: float
    top1_concentration_diff: float


def hype_l2_features_at_decision(
    events: Sequence[L2SnapshotEvent],
    *,
    decision_time_ms: int,
    side: Literal["long", "short"],
    sampling_interval_ms: int = 1_000,
) -> dict[str, float]:
    """Derive the frozen L2 inputs available before one live decision."""
    if decision_time_ms <= 0:
        raise ValueError("HYPE L2 decision timestamp must be positive")
    if side not in {"long", "short"}:
        raise ValueError("HYPE L2 decision side must be long or short")
    if sampling_interval_ms <= 0:
        raise ValueError("HYPE L2 sampling interval must be positive")
    _validate_live_events(events)
    start_ms = decision_time_ms - 60_000
    selected = tuple(
        event for event in events if start_ms <= event.exchange_ts_ms < decision_time_ms
    )
    if not selected:
        raise ValueError("HYPE L2 decision window contains no pre-decision books")
    snapshots = tuple(_snapshot_from_event(event) for event in selected)
    sampled = _sample_pre(snapshots, decision_time_ms, sampling_interval_ms)
    direction = 1.0 if side == "long" else -1.0
    values = _causal_features(sampled, decision_time_ms, direction)
    return {name: values[name] for name in HYPE_ENTRY_L2_FEATURES}


def _validate_live_events(events: Sequence[L2SnapshotEvent]) -> None:
    if not events:
        raise ValueError("HYPE L2 live event sequence must be non-empty")
    timestamps: list[int] = []
    for event in events:
        if event.symbol != "HYPE":
            raise ValueError(f"HYPE L2 live event has symbol {event.symbol!r}")
        if event.source != REST_L2_SOURCE:
            raise ValueError(f"HYPE L2 live event has source {event.source!r}")
        timestamps.append(event.exchange_ts_ms)
    if timestamps != sorted(set(timestamps)):
        raise ValueError("HYPE L2 live events are duplicated or out of order")


def build_hype_entry_l2_dataset(
    raw: pd.DataFrame,
    audit: pd.DataFrame,
    *,
    sampling_interval_ms: int | None = None,
) -> HypeL2EntryDataset:
    """Join frozen entries to audited bundles and derive pre-entry features."""
    if sampling_interval_ms is not None and sampling_interval_ms <= 0:
        raise ValueError("HYPE L2 sampling interval must be positive")
    joined = _join_coverage(raw, audit)
    covered = joined["status"].eq("covered")
    _validate_covered_contract(joined.loc[covered])
    feature_rows = [
        _window_features(row, sampling_interval_ms)
        for _, row in joined.loc[covered].sort_values("_row_order").iterrows()
    ]
    model_rows = joined.loc[covered].sort_values("_row_order").copy()
    if model_rows.empty:
        raise ValueError("HYPE L2 dataset contains no causally covered rows")
    features = pd.DataFrame(feature_rows, index=model_rows.index)
    model_rows = pd.concat([model_rows, features], axis=1)
    _validate_features(model_rows)
    output = model_rows.drop(columns=["_row_order"]).reset_index(drop=True)
    coverage = joined.drop(columns=["_row_order"]).reset_index(drop=True)
    report = _build_report(joined, output, sampling_interval_ms)
    return HypeL2EntryDataset(output, coverage, report)


def _join_coverage(raw: pd.DataFrame, audit: pd.DataFrame) -> pd.DataFrame:
    _validate_frame(raw, _IDENTITY_COLUMNS, "frozen HYPE feature")
    _validate_frame(audit, _AUDIT_COLUMNS, "HYPE L2 audit")
    left = raw.copy()
    left["_row_order"] = np.arange(len(left), dtype=int)
    right = audit.loc[:, _AUDIT_COLUMNS].copy()
    for name in ("signal_time_utc", "entry_time_utc"):
        left[name] = pd.to_datetime(left[name], utc=True, errors="raise")
        right[name] = pd.to_datetime(right[name], utc=True, errors="raise")
    joined = left.merge(
        right,
        how="left",
        on=list(_IDENTITY_COLUMNS),
        validate="one_to_one",
        suffixes=("", "_audit"),
    )
    if joined["window_id"].isna().any() or len(joined) != len(raw):
        raise ValueError("HYPE L2 audit identity does not exactly match frozen entries")
    if len(audit) != len(raw):
        raise ValueError("HYPE L2 audit identity contains unmatched rows")
    return joined.sort_values("_row_order")


def _validate_frame(frame: pd.DataFrame, columns: tuple[str, ...], label: str) -> None:
    missing = sorted(set(columns).difference(frame.columns))
    if missing:
        raise ValueError(f"{label} rows missing columns: {missing}")
    if frame.empty:
        raise ValueError(f"{label} rows must be non-empty")
    identity = frame.loc[:, _IDENTITY_COLUMNS].astype(str)
    if identity.duplicated().any():
        raise ValueError(f"{label} identity rows must be unique")
    if not set(frame["side"].astype(str)).issubset({"long", "short"}):
        raise ValueError(f"{label} side must be long or short")


def _validate_covered_contract(rows: pd.DataFrame) -> None:
    if rows.empty:
        return
    flags = (
        rows["manifest_complete"].eq(True)
        & rows["causal_covered"].eq(True)
        & rows["execution_covered"].eq(True)
    )
    if not flags.all():
        raise ValueError("covered HYPE L2 audit row violates coverage contract")
    numeric = rows[["row_count", "pre_entry_rows", "post_entry_rows"]].astype(int)
    if (numeric <= 0).any().any():
        raise ValueError("covered HYPE L2 audit row must contain pre/post snapshots")


def _window_features(
    row: pd.Series,
    sampling_interval_ms: int | None,
) -> dict[str, float | int | str]:
    directory = Path(str(row["bundle_path"]))
    snapshots = _load_bundle(directory)
    entry_ms = int(pd.Timestamp(row["entry_time_utc"]).timestamp() * 1_000)
    pre = tuple(value for value in snapshots if value.timestamp_ms < entry_ms)
    post = tuple(value for value in snapshots if value.timestamp_ms >= entry_ms)
    _validate_window_counts(row, pre, post, len(snapshots), entry_ms)
    pre = _sample_pre(pre, entry_ms, sampling_interval_ms)
    side = 1.0 if row["side"] == "long" else -1.0
    values: dict[str, float | int | str] = dict(_causal_features(pre, entry_ms, side))
    values.update(_execution_diagnostics(pre[-1], post[0], entry_ms, side))
    values["l2_window_id"] = str(row["window_id"])
    return values


def _sample_pre(
    snapshots: tuple[_BookSnapshot, ...],
    entry_ms: int,
    interval_ms: int | None,
) -> tuple[_BookSnapshot, ...]:
    if interval_ms is None:
        return snapshots
    buckets: dict[int, _BookSnapshot] = {}
    boundary = entry_ms - 1
    for snapshot in snapshots:
        bucket = (boundary - snapshot.timestamp_ms) // interval_ms
        buckets[bucket] = snapshot
    return tuple(sorted(buckets.values(), key=lambda value: value.timestamp_ms))


def _load_bundle(directory: Path) -> tuple[_BookSnapshot, ...]:
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"HYPE L2 bundle manifest is missing: {directory}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"HYPE L2 bundle manifest must be an object: {directory}")
    if not _valid_manifest_identity(payload):
        raise ValueError(f"HYPE L2 bundle manifest identity is invalid: {directory}")
    verify_file_evidence(directory, payload.get("files"))
    snapshots = _read_snapshots(directory / "books.jsonl.gz")
    if payload.get("row_count") != len(snapshots):
        raise ValueError(f"HYPE L2 bundle row count mismatch: {directory}")
    return snapshots


def _valid_manifest_identity(payload: dict[str, object]) -> bool:
    return bool(
        payload.get("source") == "0xarchive_hyperliquid_native_l2"
        and payload.get("symbol") == "HYPE"
        and payload.get("complete") is True
        and payload.get("continuation_cursor") is None
    )


def _read_snapshots(path: Path) -> tuple[_BookSnapshot, ...]:
    snapshots: list[_BookSnapshot] = []
    with open_text_reader(path) as handle:
        for line in handle:
            payload = json.loads(line)
            snapshots.append(_parse_snapshot(payload))
    timestamps = [value.timestamp_ms for value in snapshots]
    if timestamps != sorted(set(timestamps)):
        raise ValueError("HYPE L2 book timestamps are duplicated or out of order")
    return tuple(snapshots)


def _parse_snapshot(value: object) -> _BookSnapshot:
    if not isinstance(value, dict):
        raise ValueError("HYPE L2 book row must be an object")
    timestamp = value.get("ts_exchange_ms")
    if not isinstance(timestamp, int):
        raise ValueError("HYPE L2 book row requires an integer exchange timestamp")
    bids = _parse_levels(value.get("bids"), descending=True)
    asks = _parse_levels(value.get("asks"), descending=False)
    return _book_snapshot(timestamp, bids, asks)


def _snapshot_from_event(event: L2SnapshotEvent) -> _BookSnapshot:
    bids = tuple((level.price, level.size) for level in event.bids)
    asks = tuple((level.price, level.size) for level in event.asks)
    return _book_snapshot(event.exchange_ts_ms, bids, asks)


def _book_snapshot(
    timestamp: int,
    bids: tuple[tuple[float, float], ...],
    asks: tuple[tuple[float, float], ...],
) -> _BookSnapshot:
    best_bid, best_ask = bids[0][0], asks[0][0]
    if best_bid >= best_ask:
        raise ValueError("HYPE L2 book is crossed or locked")
    midpoint = (best_bid + best_ask) / 2.0
    bid1, ask1 = bids[0][1], asks[0][1]
    microprice = (best_bid * ask1 + best_ask * bid1) / (bid1 + ask1)
    bid20, ask20 = _depth(bids, 20), _depth(asks, 20)
    return _BookSnapshot(
        timestamp,
        midpoint,
        (best_ask - best_bid) / midpoint * 10_000.0,
        (microprice / midpoint - 1.0) * 10_000.0,
        _imbalance(bid1, ask1),
        _imbalance(_depth(bids, 5), _depth(asks, 5)),
        _imbalance(bid20, ask20),
        math.log(bid20 / ask20),
        bid1 / bid20 - ask1 / ask20,
    )


def _parse_levels(
    value: object, *, descending: bool
) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("HYPE L2 book side must contain levels")
    levels: list[tuple[float, float]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("HYPE L2 book level must be an object")
        price, size = float(item.get("px", 0.0)), float(item.get("sz", 0.0))
        if not math.isfinite(price) or not math.isfinite(size) or min(price, size) <= 0:
            raise ValueError("HYPE L2 book level price and size must be positive")
        levels.append((price, size))
    prices = [item[0] for item in levels]
    expected = sorted(set(prices), reverse=descending)
    if prices != expected:
        raise ValueError("HYPE L2 book levels are duplicated or out of order")
    return tuple(levels)


def _depth(levels: tuple[tuple[float, float], ...], count: int) -> float:
    return sum(size for _, size in levels[:count])


def _imbalance(bid_size: float, ask_size: float) -> float:
    return (bid_size - ask_size) / (bid_size + ask_size)


def _validate_window_counts(
    row: pd.Series,
    pre: tuple[_BookSnapshot, ...],
    post: tuple[_BookSnapshot, ...],
    total: int,
    entry_ms: int,
) -> None:
    expected = (
        int(row["pre_entry_rows"]),
        int(row["post_entry_rows"]),
        int(row["row_count"]),
    )
    if (len(pre), len(post), total) != expected:
        raise ValueError("HYPE L2 bundle counts differ from audited identity")
    pre_age = entry_ms - pre[-1].timestamp_ms
    post_delay = post[0].timestamp_ms - entry_ms
    if pre_age != int(row["last_pre_entry_age_ms"]):
        raise ValueError("HYPE L2 pre-entry timing differs from audit")
    if post_delay != int(row["first_post_entry_delay_ms"]):
        raise ValueError("HYPE L2 post-entry timing differs from audit")


def _causal_features(
    pre: tuple[_BookSnapshot, ...],
    entry_ms: int,
    side: float,
) -> dict[str, float]:
    latest = pre[-1]
    spreads = np.asarray([value.spread_bps for value in pre], dtype=float)
    imbalance = np.asarray([value.imbalance_top5 for value in pre], dtype=float)
    output = {
        "l2_spread_latest_bps": latest.spread_bps,
        "l2_spread_mean_60s_bps": float(spreads.mean()),
        "l2_spread_p90_60s_bps": float(np.quantile(spreads, 0.9)),
        "l2_spread_max_60s_bps": float(spreads.max()),
        "l2_aligned_microprice_latest_bps": side * latest.microprice_bps,
        "l2_aligned_imbalance_top1_latest": side * latest.imbalance_top1,
        "l2_aligned_imbalance_top5_latest": side * latest.imbalance_top5,
        "l2_aligned_imbalance_top20_latest": side * latest.imbalance_top20,
        "l2_imbalance_top5_std_60s": float(imbalance.std(ddof=0)),
        "l2_mid_range_60s_bps": _mid_range(pre),
        "l2_mid_realized_vol_60s_bps": _realized_vol(pre),
        "l2_aligned_depth_log_ratio_latest": side * latest.depth_log_ratio,
        "l2_aligned_top1_concentration_diff_latest": side
        * latest.top1_concentration_diff,
        "l2_snapshot_rate_60s": len(pre) / 60.0,
    }
    _attach_horizon_features(output, pre, entry_ms, side)
    return output


def _attach_horizon_features(
    output: dict[str, float],
    pre: tuple[_BookSnapshot, ...],
    entry_ms: int,
    side: float,
) -> None:
    latest = pre[-1]
    for seconds in (5, 15, 30, 60):
        recent = [
            value.imbalance_top5
            for value in pre
            if value.timestamp_ms >= entry_ms - seconds * 1_000
        ]
        output[f"l2_aligned_imbalance_top5_mean_{seconds}s"] = side * float(
            np.mean(recent)
        )
        reference = _reference_snapshot(pre, entry_ms - seconds * 1_000)
        output[f"l2_aligned_mid_return_{seconds}s_bps"] = (
            side * (latest.midpoint / reference.midpoint - 1.0) * 10_000.0
        )
        if seconds < 60:
            output[f"l2_aligned_imbalance_top5_change_{seconds}s"] = side * (
                latest.imbalance_top5 - reference.imbalance_top5
            )


def _reference_snapshot(
    pre: tuple[_BookSnapshot, ...], target_ms: int
) -> _BookSnapshot:
    eligible = [value for value in pre if value.timestamp_ms <= target_ms]
    return eligible[-1] if eligible else pre[0]


def _mid_range(pre: tuple[_BookSnapshot, ...]) -> float:
    values = np.asarray([value.midpoint for value in pre], dtype=float)
    return float((values.max() / values.min() - 1.0) * 10_000.0)


def _realized_vol(pre: tuple[_BookSnapshot, ...]) -> float:
    values = np.asarray([value.midpoint for value in pre], dtype=float)
    if len(values) < 2:
        return 0.0
    returns = np.diff(np.log(values))
    return float(np.sqrt(np.square(returns).sum()) * 10_000.0)


def _execution_diagnostics(
    latest: _BookSnapshot,
    first_post: _BookSnapshot,
    entry_ms: int,
    side: float,
) -> dict[str, float | int]:
    return {
        "l2_last_pre_entry_age_ms": entry_ms - latest.timestamp_ms,
        "l2_first_post_entry_delay_ms": first_post.timestamp_ms - entry_ms,
        "l2_first_post_spread_bps": first_post.spread_bps,
        "l2_post_mid_move_bps": side
        * (first_post.midpoint / latest.midpoint - 1.0)
        * 10_000.0,
    }


def _validate_features(rows: pd.DataFrame) -> None:
    values = rows.loc[:, HYPE_ENTRY_L2_FEATURES].astype(float)
    if not np.isfinite(values.to_numpy()).all():
        raise ValueError("HYPE entry L2 model features must be finite")
    if rows["l2_window_id"].duplicated().any():
        raise ValueError("HYPE entry L2 window identity must be unique")


def _build_report(
    joined: pd.DataFrame,
    output: pd.DataFrame,
    sampling_interval_ms: int | None,
) -> dict[str, object]:
    covered = joined["status"].eq("covered")
    counts = joined["status"].value_counts().sort_index().to_dict()
    return {
        "schema_version": 1,
        "mode": "hype_entry_l2_features_development_v1",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
            "post_entry_fields_excluded_from_model": True,
        },
        "coverage": {
            "source_rows": len(joined),
            "covered_rows": int(covered.sum()),
            "excluded_rows": int((~covered).sum()),
            "status_counts": {str(key): int(value) for key, value in counts.items()},
        },
        "features": list(HYPE_ENTRY_L2_FEATURES),
        "feature_count": len(HYPE_ENTRY_L2_FEATURES),
        "sampling": {
            "mode": (
                "native_all_snapshots"
                if sampling_interval_ms is None
                else "causal_last_snapshot_per_bucket"
            ),
            "interval_ms": sampling_interval_ms,
        },
        "selection_bias": {
            "covered": _outcome_slice(joined.loc[covered]),
            "excluded": _outcome_slice(joined.loc[~covered]),
        },
        "output_rows": len(output),
    }


def _outcome_slice(rows: pd.DataFrame) -> dict[str, object]:
    output: dict[str, object] = {"rows": len(rows)}
    if rows.empty or "net_return_bps" not in rows:
        return output
    net = pd.to_numeric(rows["net_return_bps"], errors="coerce").dropna()
    gross = pd.to_numeric(rows["gross_return_bps"], errors="coerce").dropna()
    output.update(
        {
            "mean_gross_return_bps": float(gross.mean()) if not gross.empty else None,
            "mean_net_return_bps": float(net.mean()) if not net.empty else None,
            "positive_net_rate": float(net.gt(0.0).mean()) if not net.empty else None,
            "long_rows": int(rows["side"].eq("long").sum()),
            "short_rows": int(rows["side"].eq("short").sum()),
        }
    )
    return output
