"""Point-in-time dataset construction for observe-only Hypervelocity models."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

import numpy as np
import pandas as pd

_RECOVERY_CANDIDATE = "5m_bbwp_hard_range_25_recovery_6_cooldown_300s"
_RESOLVED_STATUSES = ("target_completed", "liquidated")
_STOP_RESOLVED_STATUSES = ("target_completed", "stopped", "liquidated")

BASE_FEATURE_NAMES: tuple[str, ...] = (
    "direction_sign",
    "directional_ema_gap_bps_1m",
    "directional_rsi_gap_1m",
    "bbwp_1m_percentile",
    "bbwp_1m_compression_age_bars",
    "regime_age_5m_bars",
    "regime_strength_score",
    "regime_strength_percentile",
    "breakout_volume_ratio",
    "context_15m_alignment",
    "bbwp_5m_percentile",
    "directional_ema_gap_bps_5m",
    "directional_structure_distance_bps",
)

BOOK_FEATURE_NAMES: tuple[str, ...] = (
    "book_snapshot_age_ms",
    "directional_obi_5",
    "directional_obi_20",
    "directional_obi_5_trailing_median",
    "directional_obi_20_trailing_median",
    "spread_bps",
    "directional_micro_price_delta_bps",
    "directional_ofi_top_5s_normalized",
    "book_window_snapshots",
)

SEQUENCE_BOOK_FEATURE_NAMES: tuple[str, ...] = (
    "book_sequence_snapshots_15s",
    "directional_obi_5_mean_15s",
    "directional_obi_5_delta_15s",
    "directional_ofi_top_15s_normalized",
    "book_sequence_snapshots_60s",
    "directional_obi_5_mean_60s",
    "directional_obi_5_delta_60s",
    "directional_obi_5_sign_mean_60s",
    "directional_ofi_top_60s_normalized",
    "directional_micro_price_delta_bps_mean_60s",
    "spread_bps_median_60s",
)


def feature_coverage(rows: pd.DataFrame) -> dict[str, int]:
    """Count available values for each declared model feature."""
    names = BASE_FEATURE_NAMES + BOOK_FEATURE_NAMES + SEQUENCE_BOOK_FEATURE_NAMES
    return {name: int(rows[name].notna().sum()) for name in names}


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} contains a non-string key")
    return value


def assert_observe_only_policy(policy: Mapping[str, object]) -> None:
    """Fail unless a model policy is strictly annotation-only."""
    observed = {
        "mode": policy.get("mode"),
        "may_filter": policy.get("may_filter"),
        "may_scale": policy.get("may_scale"),
    }
    expected = {"mode": "observe", "may_filter": False, "may_scale": False}
    if observed != expected:
        raise ValueError(f"metalabel policy is not observe-only: {observed}")


def _lifecycle_rows(
    payload: Mapping[str, object],
    *,
    identity_field: str,
    expected_identity: str,
) -> list[dict[str, object]]:
    if payload.get("ok") is not True or payload.get("report_only") is not True:
        raise ValueError("model evidence must be a successful report-only artifact")
    if payload.get(identity_field) != expected_identity:
        raise ValueError(
            "model evidence candidate identity differs from frozen contract"
        )
    assert_observe_only_policy(
        _mapping(payload.get("metalabel_policy"), "model metalabel policy")
    )
    replay = _mapping(payload.get("event_replay"), "model event replay")
    values = replay.get("lifecycles")
    if not isinstance(values, list):
        raise ValueError("model event replay lifecycles must be an array")
    return [dict(_mapping(value, "model lifecycle")) for value in values]


def resolved_candidate_lifecycles(
    payload: Mapping[str, object],
    *,
    identity_field: str,
    expected_identity: str,
) -> pd.DataFrame:
    """Return resolved binary outcomes for one immutable replay identity."""
    frame = pd.DataFrame(
        _lifecycle_rows(
            payload,
            identity_field=identity_field,
            expected_identity=expected_identity,
        )
    )
    return _resolved_lifecycle_frame(frame)


def resolved_recovery_lifecycles(payload: Mapping[str, object]) -> pd.DataFrame:
    """Return only filled target/liquidation outcomes with causal timestamps."""
    return resolved_candidate_lifecycles(
        payload,
        identity_field="event_candidate",
        expected_identity=_RECOVERY_CANDIDATE,
    )


def resolved_margin_stop_lifecycles(
    payload: Mapping[str, object],
) -> pd.DataFrame:
    """Return target-versus-loss outcomes from the frozen 14% stop replay."""
    if (
        payload.get("ok") is not True
        or payload.get("report_only") is not True
        or payload.get("runtime_strategy_changed") is not False
    ):
        raise ValueError("margin-stop evidence must be report-only and unchanged")
    assert_observe_only_policy(
        _mapping(payload.get("metalabel_policy"), "margin-stop metalabel policy")
    )
    comparison = _mapping(payload.get("comparison"), "margin-stop comparison")
    candidates = _mapping(comparison.get("candidates"), "margin-stop candidates")
    candidate = _mapping(
        candidates.get("stop_14pct_margin"), "14% margin-stop candidate"
    )
    if candidate.get("fixed_margin_stop_pct") != 14.0:
        raise ValueError("14% margin-stop candidate has a different stop boundary")
    replay = _mapping(candidate.get("replay"), "14% margin-stop replay")
    if replay.get("fill_rule") != "trade-through":
        raise ValueError("14% margin-stop replay must use trade-through fills")
    values = replay.get("lifecycles")
    if not isinstance(values, list):
        raise ValueError("14% margin-stop lifecycles must be an array")
    frame = pd.DataFrame(
        [dict(_mapping(value, "14% margin-stop lifecycle")) for value in values]
    )
    return _resolved_lifecycle_frame(
        frame,
        resolved_statuses=_STOP_RESOLVED_STATUSES,
        label_column="loss_risk",
        positive_statuses=("stopped", "liquidated"),
    )


def resolved_comparison_candidate_lifecycles(
    payload: Mapping[str, object],
    *,
    candidate_name: str,
) -> pd.DataFrame:
    """Return target-versus-liquidation outcomes for a comparison candidate."""
    if (
        payload.get("ok") is not True
        or payload.get("report_only") is not True
        or payload.get("runtime_strategy_changed") is not False
    ):
        raise ValueError("comparison evidence must be report-only and unchanged")
    assert_observe_only_policy(
        _mapping(payload.get("metalabel_policy"), "comparison metalabel policy")
    )
    comparison = _mapping(payload.get("comparison"), "comparison evidence")
    candidates = _mapping(comparison.get("candidates"), "comparison candidates")
    candidate = _mapping(candidates.get(candidate_name), candidate_name)
    replay = _mapping(candidate.get("replay"), f"{candidate_name} replay")
    values = replay.get("lifecycles")
    if not isinstance(values, list):
        raise ValueError(f"{candidate_name} lifecycles must be an array")
    frame = pd.DataFrame(
        [dict(_mapping(value, f"{candidate_name} lifecycle")) for value in values]
    )
    return _resolved_lifecycle_frame(frame)


def _resolved_lifecycle_frame(
    frame: pd.DataFrame,
    *,
    resolved_statuses: tuple[str, ...] = _RESOLVED_STATUSES,
    label_column: str = "liquidation_risk",
    positive_statuses: tuple[str, ...] = ("liquidated",),
) -> pd.DataFrame:
    required = {
        "lifecycle_id",
        "direction",
        "signal_time_utc",
        "entry_time_utc",
        "outcome_time_utc",
        "status",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"recovery lifecycles missing fields: {sorted(missing)}")
    frame = frame.loc[frame["status"].isin(resolved_statuses)].copy()
    if frame.empty:
        raise ValueError("recovery evidence has no resolved filled lifecycles")
    if frame["entry_time_utc"].isna().any():
        raise ValueError("resolved recovery lifecycle is missing its entry time")
    if not frame["direction"].isin(("long", "short")).all():
        raise ValueError("resolved recovery lifecycle has an invalid direction")
    signal = pd.DatetimeIndex(
        pd.to_datetime(frame["signal_time_utc"], utc=True, format="ISO8601")
    )
    outcome = pd.DatetimeIndex(
        pd.to_datetime(frame["outcome_time_utc"], utc=True, format="ISO8601")
    )
    if (outcome <= signal).any():
        raise ValueError("resolved recovery outcome must follow its signal")
    frame["signal_ts_ms"] = signal.as_unit("ms").asi8
    frame["outcome_ts_ms"] = outcome.as_unit("ms").asi8
    frame[label_column] = frame["status"].isin(positive_statuses).astype("int8")
    return frame.sort_values("signal_ts_ms", kind="stable").reset_index(drop=True)


def _required_columns(frame: pd.DataFrame, names: set[str], label: str) -> None:
    missing = names.difference(frame.columns)
    if missing:
        raise ValueError(f"{label} missing columns: {sorted(missing)}")


def signal_times_utc(frame: pd.DataFrame) -> pd.DatetimeIndex:
    """Parse mixed-precision ISO8601 signal timestamps as UTC."""
    _required_columns(frame, {"signal_time_utc"}, "metalabel signal rows")
    return pd.DatetimeIndex(
        pd.to_datetime(frame["signal_time_utc"], utc=True, format="ISO8601")
    )


def _validate_feature_frames(
    decisions: pd.DataFrame,
    context_5m: pd.DataFrame,
    bar_annotations: pd.DataFrame,
    book_annotations: pd.DataFrame,
) -> None:
    decision_fields = {
        "ema_gap_bps_signed",
        "rsi",
        "rsi_ema",
        "bbwp_percentile",
        "bbwp_1m_compression_age_bars",
        "regime_strength_score",
        "regime_strength_percentile",
        "breakout_volume_ratio",
        "context_15m",
    }
    _required_columns(decisions, decision_fields, "metalabel decisions")
    _required_columns(
        context_5m,
        {"bbwp_percentile", "ema_gap_bps_signed"},
        "metalabel 5m context",
    )
    _required_columns(
        bar_annotations,
        {"regime_age_bars", "directional_structure_distance_bps"},
        "metalabel bar annotations",
    )
    book_fields = {
        "book_snapshot_age_ms",
        "obi_5",
        "obi_20",
        "obi_5_trailing_median",
        "obi_20_trailing_median",
        "spread_bps",
        "micro_price_delta_bps",
        "ofi_top_5s_normalized",
        "book_window_snapshots",
    }
    _required_columns(book_annotations, book_fields, "metalabel book annotations")
    if not decisions.index.equals(context_5m.index):
        raise ValueError("metalabel decisions and 5m context indexes differ")
    if not decisions.index.equals(bar_annotations.index):
        raise ValueError("metalabel decisions and bar annotation indexes differ")


def _completed_bar_features(
    decisions: pd.DataFrame,
    context_5m: pd.DataFrame,
    bar_annotations: pd.DataFrame,
) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "ema_gap_bps_signed_1m": decisions["ema_gap_bps_signed"],
            "rsi_gap_1m": decisions["rsi"] - decisions["rsi_ema"],
            "bbwp_1m_percentile": decisions["bbwp_percentile"],
            "bbwp_1m_compression_age_bars": decisions["bbwp_1m_compression_age_bars"],
            "regime_age_5m_bars": bar_annotations["regime_age_bars"],
            "regime_strength_score": decisions["regime_strength_score"],
            "regime_strength_percentile": decisions["regime_strength_percentile"],
            "breakout_volume_ratio": decisions["breakout_volume_ratio"],
            "context_15m": decisions["context_15m"],
            "bbwp_5m_percentile": context_5m["bbwp_percentile"],
            "ema_gap_bps_signed_5m": context_5m["ema_gap_bps_signed"],
            "directional_structure_distance_bps": bar_annotations[
                "directional_structure_distance_bps"
            ],
        },
        index=decisions.index,
    )
    frame.index = frame.index + pd.Timedelta(minutes=1)
    return frame


def _context_alignment(direction: pd.Series, context: pd.Series) -> np.ndarray:
    aligned = ((direction == "long") & (context == "TREND_UP")) | (
        (direction == "short") & (context == "TREND_DOWN")
    )
    opposed = ((direction == "long") & (context == "TREND_DOWN")) | (
        (direction == "short") & (context == "TREND_UP")
    )
    return np.select((aligned, opposed), (1.0, -1.0), default=0.0)


def _align_completed_bars(
    bars: pd.DataFrame,
    signals: pd.DatetimeIndex,
    bar_alignment: Literal["exact", "backward"],
) -> pd.DataFrame:
    if bar_alignment == "exact":
        return bars.reindex(signals)
    if bar_alignment == "backward":
        return bars.reindex(signals, method="ffill")
    raise ValueError(f"unknown metalabel bar alignment: {bar_alignment}")


def _directionalize_features(output: pd.DataFrame) -> pd.DataFrame:
    sign = np.where(output["direction"].eq("long"), 1.0, -1.0)
    output["direction_sign"] = sign
    output["directional_ema_gap_bps_1m"] = sign * output["ema_gap_bps_signed_1m"]
    output["directional_rsi_gap_1m"] = sign * output["rsi_gap_1m"]
    output["context_15m_alignment"] = _context_alignment(
        output["direction"], output["context_15m"]
    )
    output["directional_ema_gap_bps_5m"] = sign * output["ema_gap_bps_signed_5m"]
    for source, target in (
        ("obi_5", "directional_obi_5"),
        ("obi_20", "directional_obi_20"),
        ("obi_5_trailing_median", "directional_obi_5_trailing_median"),
        ("obi_20_trailing_median", "directional_obi_20_trailing_median"),
        ("micro_price_delta_bps", "directional_micro_price_delta_bps"),
        ("ofi_top_5s_normalized", "directional_ofi_top_5s_normalized"),
    ):
        output[target] = sign * output[source]
    for source, target in (
        ("obi_5_mean_15s", "directional_obi_5_mean_15s"),
        ("obi_5_delta_15s", "directional_obi_5_delta_15s"),
        ("ofi_top_15s_normalized", "directional_ofi_top_15s_normalized"),
        ("obi_5_mean_60s", "directional_obi_5_mean_60s"),
        ("obi_5_delta_60s", "directional_obi_5_delta_60s"),
        ("obi_5_sign_mean_60s", "directional_obi_5_sign_mean_60s"),
        ("ofi_top_60s_normalized", "directional_ofi_top_60s_normalized"),
        (
            "micro_price_delta_bps_mean_60s",
            "directional_micro_price_delta_bps_mean_60s",
        ),
    ):
        if source in output:
            output[target] = sign * output[source]
    return output


def build_metalabel_rows(
    lifecycles: pd.DataFrame,
    decisions: pd.DataFrame,
    context_5m: pd.DataFrame,
    bar_annotations: pd.DataFrame,
    book_annotations: pd.DataFrame,
    *,
    bar_alignment: Literal["exact", "backward"] = "exact",
    label_column: str = "liquidation_risk",
) -> pd.DataFrame:
    """Join resolved outcomes to causal completed-bar and signal-time L2 features."""
    _validate_feature_frames(decisions, context_5m, bar_annotations, book_annotations)
    _required_columns(
        lifecycles,
        {"direction", "signal_time_utc", label_column},
        "metalabel lifecycles",
    )
    output = lifecycles.reset_index(drop=True).copy()
    signals = signal_times_utc(output)
    bars = _completed_bar_features(decisions, context_5m, bar_annotations)
    aligned_bars = _align_completed_bars(bars, signals, bar_alignment)
    output = pd.concat(
        [
            output,
            aligned_bars.reset_index(drop=True),
            book_annotations.reindex(signals).reset_index(drop=True),
        ],
        axis=1,
    )
    return _directionalize_features(output)
