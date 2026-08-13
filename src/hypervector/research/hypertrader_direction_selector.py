"""Paired, annotation-only direction evidence for pinned Recipe C events."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

_CONTRACT_FIELDS = (
    "fill_rule",
    "initial_equity",
    "allocation_fraction",
    "leverage",
    "gross_margin_target_pct",
    "entry_ttl_seconds",
)
_OUTCOME_SCORES = {
    "target_completed": 1,
    "canceled": 0,
    "expired": 0,
    "liquidated": -1,
    "stopped": -1,
}


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object with string keys")
    return value


def _utc(value: object, label: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a timestamp") from exc
    if timestamp.tz is None:
        raise ValueError(f"{label} must be timezone-aware")
    return timestamp.tz_convert("UTC")


def _labels_hash(payload: Mapping[str, object]) -> object:
    evidence = _mapping(payload.get("source_evidence"), "source evidence")
    labels = _mapping(evidence.get("labels"), "labels evidence")
    return labels.get("sha256")


def _validate_artifact(payload: Mapping[str, object], family: str) -> None:
    observed = {
        "report_only": payload.get("report_only"),
        "runtime_strategy_changed": payload.get("runtime_strategy_changed"),
        "model_authority": payload.get("model_authority"),
        "candidate_family": payload.get("candidate_family"),
    }
    expected = {
        "report_only": True,
        "runtime_strategy_changed": False,
        "model_authority": "observe",
        "candidate_family": family,
    }
    if observed != expected:
        raise ValueError(f"direction artifact violates research contract: {observed}")


def _event_outcomes(payload: Mapping[str, object]) -> list[Mapping[str, object]]:
    development = _mapping(payload.get("development"), "development evidence")
    values = development.get("event_outcomes")
    if not isinstance(values, list):
        raise ValueError("development event outcomes must be an array")
    rows = [_mapping(value, "event outcome") for value in values]
    if development.get("events") != len(rows):
        raise ValueError("development event count differs from outcome rows")
    return rows


def _status(event: Mapping[str, object]) -> str:
    lifecycle = event.get("lifecycle")
    if lifecycle is None:
        return str(event.get("admission"))
    return str(_mapping(lifecycle, "event lifecycle").get("status"))


def _outcome_time(event: Mapping[str, object], signal: pd.Timestamp) -> pd.Timestamp:
    lifecycle = event.get("lifecycle")
    if lifecycle is None:
        return signal
    value = _mapping(lifecycle, "event lifecycle").get("outcome_time_utc")
    return _utc(value, "event outcome time")


def _preference(fade_status: str, follow_status: str) -> str:
    if "not_submitted" in {fade_status, follow_status}:
        return "path_dependent"
    fade_score = _OUTCOME_SCORES.get(fade_status)
    follow_score = _OUTCOME_SCORES.get(follow_status)
    if fade_score is None or follow_score is None or fade_score == follow_score:
        return "ambiguous"
    return "fade" if fade_score > follow_score else "follow"


def _validate_pair(
    fade: Mapping[str, object], follow: Mapping[str, object]
) -> tuple[list[Mapping[str, object]], list[Mapping[str, object]]]:
    _validate_artifact(fade, "source-fade-only")
    _validate_artifact(follow, "source-follow-only")
    if any(fade.get(field) != follow.get(field) for field in _CONTRACT_FIELDS):
        raise ValueError("fade and follow execution contracts differ")
    if _labels_hash(fade) != _labels_hash(follow):
        raise ValueError("fade and follow labels evidence differs")
    fade_rows = _event_outcomes(fade)
    follow_rows = _event_outcomes(follow)
    fade_times = [row.get("decision_time_utc") for row in fade_rows]
    follow_times = [row.get("decision_time_utc") for row in follow_rows]
    if fade_times != follow_times:
        raise ValueError("fade and follow decision timestamps differ")
    return fade_rows, follow_rows


def pair_direction_outcomes(
    fade_payload: Mapping[str, object],
    follow_payload: Mapping[str, object],
) -> pd.DataFrame:
    """Pair exact event times and label only unequal, path-independent outcomes."""
    fade_rows, follow_rows = _validate_pair(fade_payload, follow_payload)
    rows: list[dict[str, object]] = []
    for fade, follow in zip(fade_rows, follow_rows, strict=True):
        signal = _utc(fade.get("decision_time_utc"), "event decision time")
        fade_status, follow_status = _status(fade), _status(follow)
        preference = _preference(fade_status, follow_status)
        outcome = max(
            _outcome_time(fade, signal),
            _outcome_time(follow, signal),
        )
        rows.append(
            {
                "decision_time_utc": signal,
                "signal_ts_ms": signal.as_unit("ms").value,
                "outcome_ts_ms": outcome.as_unit("ms").value,
                "fade_status": fade_status,
                "follow_status": follow_status,
                "preference": preference,
                "trainable": preference in {"fade", "follow"},
            }
        )
    return pd.DataFrame(rows)


def _interval_weight(
    position: int,
    starts: np.ndarray,
    ends: np.ndarray,
    boundaries: np.ndarray,
) -> float:
    start, end = starts[position], ends[position]
    segments = boundaries[(boundaries >= start) & (boundaries <= end)]
    weighted = 0.0
    for left, right in zip(segments[:-1], segments[1:], strict=True):
        concurrent = int(np.sum((starts <= left) & (ends > left)))
        if concurrent < 1:
            raise RuntimeError("label interval has zero measured concurrency")
        weighted += float(right - left) / concurrent
    return weighted / float(end - start)


def add_interval_uniqueness(
    rows: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, float | int | None]]:
    """Add duration-weighted uniqueness and report effective sample size."""
    required = {"signal_ts_ms", "outcome_ts_ms", "trainable"}
    missing = required.difference(rows.columns)
    if missing:
        raise ValueError(f"direction rows missing: {sorted(missing)}")
    output = rows.copy(deep=True)
    output["average_uniqueness"] = float("nan")
    positions = np.flatnonzero(output["trainable"].astype(bool).to_numpy())
    if not len(positions):
        return output, {
            "nominal_trainable": 0,
            "effective_sample_size": 0.0,
            "mean_uniqueness": None,
        }
    starts = output.iloc[positions]["signal_ts_ms"].to_numpy(dtype=np.int64)
    ends = output.iloc[positions]["outcome_ts_ms"].to_numpy(dtype=np.int64)
    if np.any(ends <= starts):
        raise ValueError("trainable direction outcomes must resolve after decision")
    boundaries = np.unique(np.concatenate((starts, ends)))
    weights = np.asarray(
        [_interval_weight(i, starts, ends, boundaries) for i in range(len(starts))]
    )
    output.loc[output.index[positions], "average_uniqueness"] = weights
    return output, {
        "nominal_trainable": int(len(weights)),
        "effective_sample_size": float(weights.sum()),
        "mean_uniqueness": float(weights.mean()),
    }


def consensus_direction_labels(
    paired_by_fill: Mapping[str, pd.DataFrame],
) -> pd.DataFrame:
    """Require every fill model to resolve the same preferred direction."""
    if not paired_by_fill:
        raise ValueError("at least one paired fill model is required")
    names = sorted(paired_by_fill)
    first = paired_by_fill[names[0]].reset_index(drop=True)
    required = {
        "decision_time_utc",
        "signal_ts_ms",
        "outcome_ts_ms",
        "preference",
    }
    if missing := required.difference(first.columns):
        raise ValueError(f"paired direction rows missing: {sorted(missing)}")
    output = first[["decision_time_utc", "signal_ts_ms"]].copy()
    preference_columns: list[str] = []
    outcome_columns: list[str] = []
    for name in names:
        frame = paired_by_fill[name].reset_index(drop=True)
        if not frame["decision_time_utc"].equals(first["decision_time_utc"]):
            raise ValueError("paired fill decision timestamps differ")
        column = f"preference_{name}"
        output[column] = frame["preference"]
        preference_columns.append(column)
        outcome_column = f"outcome_ts_ms_{name}"
        output[outcome_column] = frame["outcome_ts_ms"]
        outcome_columns.append(outcome_column)
    preferences = output[preference_columns]
    unanimous = preferences.nunique(axis=1).eq(1)
    direction = preferences.iloc[:, 0].where(unanimous, "unresolved")
    output["consensus_direction"] = direction.where(
        direction.isin(("fade", "follow")), "unresolved"
    )
    output["outcome_ts_ms"] = output[outcome_columns].max(axis=1).astype("int64")
    output["trainable"] = output["consensus_direction"].isin(("fade", "follow"))
    output["direction_label"] = pd.Series(pd.NA, index=output.index, dtype="Int8")
    output.loc[output["consensus_direction"].eq("fade"), "direction_label"] = 0
    output.loc[output["consensus_direction"].eq("follow"), "direction_label"] = 1
    return output
