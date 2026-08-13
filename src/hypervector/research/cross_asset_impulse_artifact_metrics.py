"""Independent metric reconciliation for impulse artifact validation."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping
import math

import numpy as np
import pandas as pd

Cell = dict[str, object]
_TOLERANCE = 1e-8


def validate_impulse_fold_aggregates(
    cells: list[Cell], rows: pd.DataFrame, artifact: Mapping[str, object]
) -> None:
    """Recompute core fold metrics from the immutable event sidecar."""
    development_end = pd.Timestamp(_text(artifact.get("end_utc"), "development end"))
    decisions = pd.to_datetime(rows["decision_time_utc"], utc=True)
    for cell in cells:
        selected = _cell_rows(rows, cell)
        selected_decisions = decisions.loc[selected.index]
        folds = cell.get("folds")
        if not isinstance(folds, list) or len(folds) != 3:
            raise ValueError("impulse cell folds differ from contract")
        for fold in folds:
            mapping = _mapping(fold, "impulse fold")
            start = pd.Timestamp(_text(mapping.get("start_utc"), "fold start"))
            end = pd.Timestamp(_text(mapping.get("end_utc"), "fold end"))
            mask = (selected_decisions >= start) & (selected_decisions < end)
            fold_rows = selected.loc[mask]
            for anchor in ("base", "delayed"):
                reported = _mapping(mapping.get(anchor), f"fold {anchor}")
                _validate_one_fold(reported, fold_rows, anchor, end, development_end)


def validate_impulse_collision_diagnostics(
    artifact: Mapping[str, object], rows: pd.DataFrame
) -> None:
    """Recompute follower-time dependence diagnostics from event rows."""
    selected = rows.loc[
        rows["signal_variant"].eq("primary") & rows["anchor"].eq("base")
    ]
    events = set(
        zip(
            selected["leader_symbol"],
            selected["follower_symbol"],
            selected["decision_time_utc"],
            strict=True,
        )
    )
    groups: dict[tuple[object, object], set[object]] = defaultdict(set)
    for leader, follower, decision in events:
        groups[(follower, decision)].add(leader)
    distribution = Counter(len(leaders) for leaders in groups.values())
    reported = _mapping(artifact.get("collision_diagnostics"), "collision diagnostics")
    expected: dict[str, object] = {
        "nominal_unique_pair_events": len(events),
        "cluster_size_distribution": {
            str(size): count for size, count in sorted(distribution.items())
        },
        "uniqueness_weighted_effective_count": float(len(groups)),
        "portfolio_unique_follower_times": len(groups),
    }
    for key, value in expected.items():
        if not _same_value(reported.get(key), value):
            raise ValueError(f"impulse collision diagnostic differs for {key}")


def _validate_one_fold(
    reported: Mapping[str, object],
    rows: pd.DataFrame,
    anchor: str,
    fold_end: pd.Timestamp,
    development_end: pd.Timestamp,
) -> None:
    selected = rows.loc[rows["anchor"].eq(anchor)].copy()
    statuses = _effective_statuses(selected, fold_end, development_end)
    resolved = selected.loc[statuses.eq("resolved")]
    values = resolved["directional_gross_return_bps"].astype(float).tolist()
    expected = _fold_metrics(values, resolved)
    excluded = Counter(statuses.loc[~statuses.eq("resolved")])
    expected["excluded"] = {
        key: int(excluded.get(key, 0))
        for key in ("technical_gap", "fold_boundary_purged", "right_censored")
    }
    for key, value in expected.items():
        if not _same_value(reported.get(key), value):
            raise ValueError(f"impulse fold {key} differs from event rows")


def _effective_statuses(
    rows: pd.DataFrame, fold_end: pd.Timestamp, development_end: pd.Timestamp
) -> pd.Series:
    statuses = rows["status"].astype(str).copy()
    if rows.empty:
        return statuses
    exits = pd.to_datetime(rows["exit_time_utc"], utc=True)
    resolved = statuses.eq("resolved")
    statuses.loc[resolved & exits.ge(development_end)] = "right_censored"
    statuses.loc[resolved & exits.ge(fold_end) & exits.lt(development_end)] = (
        "fold_boundary_purged"
    )
    return statuses


def _fold_metrics(values: list[float], rows: pd.DataFrame) -> dict[str, object]:
    mean = float(np.mean(values)) if values else None
    trim = math.floor(len(values) * 0.1)
    ordered = sorted(values)
    trimmed = ordered[trim : len(ordered) - trim] if trim else ordered
    payload: dict[str, object] = {
        "resolved_events": len(values),
        "long_events": int(rows["direction"].eq("long").sum()),
        "short_events": int(rows["direction"].eq("short").sum()),
        "mean_gross_bps": mean,
        "median_gross_bps": float(np.median(values)) if values else None,
        "trimmed_mean_gross_bps": float(np.mean(trimmed)) if trimmed else None,
        "std_gross_bps": float(np.std(values, ddof=1)) if len(values) > 1 else None,
        "mean_minus_nominal_bps": mean - 13.0 if mean is not None else None,
        "mean_minus_stress_bps": mean - 20.0 if mean is not None else None,
    }
    for name, quantile in (("p10", 0.1), ("p25", 0.25), ("p75", 0.75), ("p90", 0.9)):
        payload[f"{name}_gross_bps"] = (
            float(np.quantile(values, quantile, method="linear")) if values else None
        )
    for threshold in (0, 13, 20, 26):
        payload[f"fraction_above_{threshold}_bps"] = (
            sum(value > threshold for value in values) / len(values) if values else None
        )
    return payload


def _cell_rows(rows: pd.DataFrame, cell: Mapping[str, object]) -> pd.DataFrame:
    mask = (
        rows["signal_variant"].eq(cell["signal_variant"])
        & rows["leader_symbol"].eq(cell["leader_symbol"])
        & rows["follower_symbol"].eq(cell["follower_symbol"])
        & rows["horizon_minutes"].eq(cell["horizon_minutes"])
    )
    return rows.loc[mask]


def _same_value(left: object, right: object) -> bool:
    if left is None or right is None:
        return left is right
    if isinstance(right, dict):
        return left == right
    if isinstance(right, (int, float)) and not isinstance(right, bool):
        try:
            return math.isclose(float(left), float(right), abs_tol=_TOLERANCE)
        except (TypeError, ValueError):
            return False
    return left == right


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value
