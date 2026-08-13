"""Causal, report-only attribution for canonical regime components."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from hypervector.regime.component_telemetry import build_regime_component_frame
from hypervector.regime.composite import classify_multitimeframe
from hypervector.research.regime_component_attribution_stats import daily_ic_summary

_BAR_COLUMNS = ("open", "high", "low", "close", "volume")
_SUPPORTED_SOURCES = frozenset({"hl", "hl_gap_fill"})
_ONE_MINUTE = pd.Timedelta(minutes=1)
_CATEGORICAL_COMPONENTS = (
    "ema_21_55_direction",
    "sma_100_200_direction",
    "cipher_a_direction",
    "harsi_direction",
    "mtf_5m_bias",
    "mtf_15m_bias",
)
_NUMERIC_COMPONENTS = (
    "regime_strength_score",
    "ema_21_55_gap_bps",
    "ema_21_55_gap_abs_bps",
    "sma_100_200_gap_bps",
    "sma_100_200_gap_abs_bps",
    "harsi_smoothed_rsi",
    "harsi_smoothed_rsi_abs",
    "choppiness_14",
    "trend_slope_bps",
    "trend_slope_abs_bps",
    "trend_r2",
    "self_aware_tqi",
)
_ABSOLUTE_COMPONENTS = {
    "ema_21_55_gap_abs_bps": "ema_21_55_gap_bps",
    "sma_100_200_gap_abs_bps": "sma_100_200_gap_bps",
    "harsi_smoothed_rsi_abs": "harsi_smoothed_rsi",
    "trend_slope_abs_bps": "trend_slope_bps",
}
_IC_TARGETS = (
    "future_close_return",
    "future_absolute_close_return",
    "future_absolute_excursion",
)


@dataclass(frozen=True)
class AttributionSegment:
    """A half-open chronological attribution segment in UTC."""

    name: str
    start: pd.Timestamp
    end: pd.Timestamp

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("attribution segment name must be non-empty")
        if self.start.tz is None or self.end.tz is None:
            raise ValueError("attribution segment boundaries must be timezone-aware")
        if (
            self.start.tz_convert("UTC") != self.start
            or self.end.tz_convert("UTC") != self.end
        ):
            raise ValueError("attribution segment boundaries must be UTC")
        if self.start >= self.end:
            raise ValueError("attribution segment start must precede end")


def build_component_feature_frame(bars: pd.DataFrame) -> pd.DataFrame:
    """Return causal canonical and component features at each completed minute."""
    frame = _validated_bars(bars)
    regime = classify_multitimeframe(frame.loc[:, list(_BAR_COLUMNS)])
    components = build_regime_component_frame(frame.loc[:, list(_BAR_COLUMNS)])
    canonical_columns = [
        "primary_regime",
        "state_1m",
        "state_5m",
        "context_15m",
        "structural_direction",
        "entry_direction",
        "regime_strength_score",
    ]
    output = regime.loc[:, canonical_columns].join(components)
    for magnitude, signed in _ABSOLUTE_COMPONENTS.items():
        output[magnitude] = output[signed].abs()
    output["source"] = frame["source"]
    return output


def resolve_forward_paths(
    bars: pd.DataFrame,
    features: pd.DataFrame,
    segment: AttributionSegment,
    *,
    horizon_minutes: int,
    gap_quarantine_minutes: int = 0,
) -> pd.DataFrame:
    """Resolve strictly future paths while retaining every exclusion reason."""
    frame = _validated_bars(bars)
    _validate_horizon(horizon_minutes)
    _validate_gap_quarantine(gap_quarantine_minutes)
    if not features.index.equals(frame.index):
        raise ValueError("attribution features must share the bar index")
    in_segment = (frame.index >= segment.start) & (frame.index < segment.end)
    paths = _forward_columns(frame, horizon_minutes, gap_quarantine_minutes).loc[
        in_segment
    ]
    paths = paths.join(features.loc[in_segment])
    paths["future_start"] = paths.index + _ONE_MINUTE
    paths["future_end"] = paths.index + pd.Timedelta(minutes=horizon_minutes)
    paths["exclusion_reason"] = _exclusion_reasons(paths, segment)
    paths["usable"] = paths["exclusion_reason"].eq("usable")
    return paths


def build_component_attribution(
    bars: pd.DataFrame,
    *,
    symbol: str,
    segments: tuple[AttributionSegment, ...],
    horizons_minutes: tuple[int, ...] = (5, 15, 30, 60),
    gap_quarantine_minutes: int = 0,
) -> dict[str, object]:
    """Build an immutable-ready report with no execution or PnL authority."""
    frame = _validated_bars(bars)
    _validate_segments(segments)
    if not symbol.strip():
        raise ValueError("attribution symbol must be non-empty")
    horizons = tuple(_validate_horizon(value) for value in horizons_minutes)
    if len(set(horizons)) != len(horizons):
        raise ValueError("attribution horizons must be unique")
    _validate_gap_quarantine(gap_quarantine_minutes)
    features = build_component_feature_frame(frame)
    segment_reports = {
        segment.name: _segment_report(
            frame, features, segment, horizons, gap_quarantine_minutes
        )
        for segment in segments
    }
    return {
        "schema_version": 1,
        "mode": "regime_component_attribution_report_only",
        "execution_authority": "none",
        "model_authority": "none",
        "thresholds_selected": False,
        "fills_assumed": False,
        "pnl_claimed": False,
        "gap_quarantine_minutes": gap_quarantine_minutes,
        "symbol": symbol.upper(),
        "source_counts": _string_counts(frame["source"]),
        "segments": segment_reports,
    }


def summarize_resolved_paths(
    paths: pd.DataFrame,
    *,
    horizon_minutes: int,
) -> dict[str, object]:
    """Summarize resolved paths without pooled correlations or trade claims."""
    horizon = _validate_horizon(horizon_minutes)
    required = {
        "usable",
        "exclusion_reason",
        "future_close_return",
        "future_high_return",
        "future_low_return",
        "primary_regime",
        "structural_direction",
    }
    missing = sorted(required.difference(paths.columns))
    if missing:
        raise ValueError(f"resolved attribution paths missing columns: {missing}")
    usable = _usable_with_targets(paths)
    counts = _observation_counts(paths)
    counts["non_overlapping"] = _non_overlapping_count(usable.index, horizon)
    return {
        "observations": counts,
        "canonical": _canonical_summary(usable),
        "range_quality": _range_quality(usable),
        "directional_calls": _directional_summary(usable),
        "categorical_components": _categorical_summary(paths, usable),
        "numeric_components": _numeric_summary(usable),
    }


def _validated_bars(bars: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(set(_BAR_COLUMNS + ("source",)).difference(bars.columns))
    if missing:
        raise ValueError(f"attribution bars missing columns: {missing}")
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise ValueError("attribution bars require a DatetimeIndex")
    index = pd.DatetimeIndex(bars.index)
    if index.tz is None or str(index.tz) != "UTC":
        raise ValueError("attribution bars require a UTC index")
    if index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError("attribution bars require unique increasing timestamps")
    if len(index) > 1 and not index.to_series().diff().iloc[1:].eq(_ONE_MINUTE).all():
        raise ValueError("attribution bars require exact one-minute cadence")
    frame = bars.loc[:, list(_BAR_COLUMNS) + ["source"]].copy()
    numeric = frame.loc[:, list(_BAR_COLUMNS)].astype(float)
    if frame.empty or not np.isfinite(numeric.to_numpy()).all():
        raise ValueError("attribution bars must contain finite OHLCV values")
    sources = set(frame["source"].astype(str).unique())
    if not sources.issubset(_SUPPORTED_SOURCES):
        raise ValueError(f"unsupported attribution provenance: {sorted(sources)}")
    frame.loc[:, list(_BAR_COLUMNS)] = numeric
    frame["source"] = frame["source"].astype(str)
    return frame


def _validate_segments(segments: tuple[AttributionSegment, ...]) -> None:
    if not segments:
        raise ValueError("attribution requires at least one segment")
    if len({segment.name for segment in segments}) != len(segments):
        raise ValueError("attribution segment names must be unique")
    for previous, current in zip(segments, segments[1:], strict=False):
        if current.start < previous.end:
            raise ValueError("attribution segments must be ordered and non-overlapping")


def _validate_horizon(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError("attribution horizons must be positive integer minutes")
    return value


def _validate_gap_quarantine(value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("gap quarantine must be nonnegative integer minutes")


def _future_window(series: pd.Series, horizon: int, operation: str) -> pd.Series:
    shifted = series.shift(-1)
    rolling = shifted.rolling(horizon, min_periods=horizon)
    result = rolling.max() if operation == "max" else rolling.min()
    return result.shift(-(horizon - 1))


def _forward_columns(
    frame: pd.DataFrame,
    horizon: int,
    quarantine: int,
) -> pd.DataFrame:
    reference = frame["close"].astype(float)
    future_close = reference.shift(-horizon)
    future_high = _future_window(frame["high"].astype(float), horizon, "max")
    future_low = _future_window(frame["low"].astype(float), horizon, "min")
    gap = frame["source"].eq("hl_gap_fill").astype(int)
    path_gap = _future_window(gap, horizon, "max").fillna(0.0).astype(bool)
    feature_gap = (
        gap.shift(1).rolling(quarantine, min_periods=1).max().fillna(0.0).astype(bool)
        if quarantine
        else False
    )
    return pd.DataFrame(
        {
            "reference_close": reference,
            "future_close_return": future_close / reference - 1.0,
            "future_high_return": future_high / reference - 1.0,
            "future_low_return": future_low / reference - 1.0,
            "decision_gap": gap.astype(bool),
            "label_path_gap": path_gap,
            "feature_gap_quarantine": feature_gap,
        },
        index=frame.index,
    )


def _exclusion_reasons(paths: pd.DataFrame, segment: AttributionSegment) -> pd.Series:
    reason = pd.Series("usable", index=paths.index, dtype=object)
    censored = paths["future_end"].ge(segment.end) | paths["future_close_return"].isna()
    reason = reason.mask(paths["feature_gap_quarantine"], "gap_feature_quarantine")
    reason = reason.mask(paths["label_path_gap"], "gap_label_path")
    reason = reason.mask(censored, "right_censored")
    return reason.mask(paths["decision_gap"], "gap_decision")


def _segment_report(
    bars: pd.DataFrame,
    features: pd.DataFrame,
    segment: AttributionSegment,
    horizons: tuple[int, ...],
    gap_quarantine_minutes: int,
) -> dict[str, object]:
    reports: dict[str, object] = {}
    for horizon in horizons:
        paths = resolve_forward_paths(
            bars,
            features,
            segment,
            horizon_minutes=horizon,
            gap_quarantine_minutes=gap_quarantine_minutes,
        )
        reports[str(horizon)] = summarize_resolved_paths(paths, horizon_minutes=horizon)
    return {
        "start": segment.start.isoformat(),
        "end": segment.end.isoformat(),
        "horizons": reports,
    }


def _observation_counts(paths: pd.DataFrame) -> dict[str, int]:
    reasons = paths["exclusion_reason"].value_counts()
    return {
        "total": int(len(paths)),
        "usable": int(reasons.get("usable", 0)),
        "gap_decision": int(reasons.get("gap_decision", 0)),
        "gap_label_path": int(reasons.get("gap_label_path", 0)),
        "gap_feature_quarantine": int(reasons.get("gap_feature_quarantine", 0)),
        "right_censored": int(reasons.get("right_censored", 0)),
    }


def _string_counts(values: pd.Series) -> dict[str, int]:
    counts = values.astype(str).value_counts().sort_index()
    return {str(key): int(value) for key, value in counts.items()}


def _usable_with_targets(paths: pd.DataFrame) -> pd.DataFrame:
    usable = paths.loc[paths["usable"].astype(bool)].copy()
    close = usable["future_close_return"].astype(float)
    high = usable["future_high_return"].astype(float).clip(lower=0.0)
    low = (-usable["future_low_return"].astype(float)).clip(lower=0.0)
    usable["future_absolute_close_return"] = close.abs()
    usable["future_absolute_excursion"] = pd.concat([high, low], axis=1).max(axis=1)
    positive = close.ge(0.0)
    usable["favorable_excursion"] = high.where(positive, low)
    usable["adverse_excursion"] = low.where(positive, high)
    return usable


def _non_overlapping_count(index: pd.Index, horizon: int) -> int:
    timestamps = pd.DatetimeIndex(index).sort_values()
    count = 0
    next_allowed: pd.Timestamp | None = None
    spacing = pd.Timedelta(minutes=horizon)
    for timestamp in timestamps:
        if next_allowed is None or timestamp >= next_allowed:
            count += 1
            next_allowed = timestamp + spacing
    return count


def _canonical_summary(usable: pd.DataFrame) -> dict[str, object]:
    primary = usable["primary_regime"].astype(str)
    onsets = primary.ne(primary.shift(1))
    return {
        "state_counts": _string_counts(primary),
        "state_onset_counts": _string_counts(primary.loc[onsets]),
    }


def _range_quality(usable: pd.DataFrame) -> dict[str, object]:
    is_range = usable["primary_regime"].astype(str).eq("RANGE")
    return {
        "RANGE": _movement_summary(usable.loc[is_range]),
        "NON_RANGE": _movement_summary(usable.loc[~is_range]),
        "excursion_definition": "future-close direction; descriptive label only",
    }


def _movement_summary(frame: pd.DataFrame) -> dict[str, object]:
    return {
        "count": int(len(frame)),
        "absolute_close_return": _distribution(frame["future_absolute_close_return"]),
        "favorable_excursion": _distribution(frame["favorable_excursion"]),
        "adverse_excursion": _distribution(frame["adverse_excursion"]),
    }


def _distribution(values: pd.Series) -> dict[str, float | int | None]:
    finite = values.astype(float).replace([np.inf, -np.inf], np.nan).dropna()
    if finite.empty:
        return {"count": 0, "mean": None, "median": None}
    return {
        "count": int(len(finite)),
        "mean": float(finite.mean()),
        "median": float(finite.median()),
    }


def _directional_summary(usable: pd.DataFrame) -> dict[str, object]:
    reports: dict[str, object] = {}
    for side, sign in (("long", 1.0), ("short", -1.0)):
        selected = usable.loc[usable["structural_direction"].eq(side)].copy()
        selected["signed_close_return"] = selected["future_close_return"] * sign
        favorable = (
            selected["future_high_return"]
            if sign > 0
            else -selected["future_low_return"]
        )
        adverse = (
            -selected["future_low_return"]
            if sign > 0
            else selected["future_high_return"]
        )
        reports[side] = {
            "count": int(len(selected)),
            "signed_close_return": _distribution(selected["signed_close_return"]),
            "favorable_excursion": _distribution(favorable.clip(lower=0.0)),
            "adverse_excursion": _distribution(adverse.clip(lower=0.0)),
        }
    return reports


def _categorical_summary(
    paths: pd.DataFrame,
    usable: pd.DataFrame,
) -> dict[str, object]:
    reports: dict[str, object] = {}
    for name in _CATEGORICAL_COMPONENTS:
        if name not in usable:
            continue
        states = usable[name]
        onset_mask = (
            paths[name].ne(paths[name].shift(1)).reindex(usable.index, fill_value=False)
        )
        reports[name] = {
            "states": _state_outcomes(usable, states),
            "state_onsets": _state_outcomes(
                usable.loc[onset_mask], states.loc[onset_mask]
            ),
        }
    return reports


def _state_outcomes(frame: pd.DataFrame, states: pd.Series) -> dict[str, object]:
    reports: dict[str, object] = {}
    for value in sorted(states.dropna().unique()):
        selected = frame.loc[states.eq(value)]
        sign = float(value) if float(value) != 0.0 else None
        signed = (
            selected["future_close_return"] * sign
            if sign is not None
            else pd.Series(dtype=float)
        )
        reports[_category_key(value)] = {
            "count": int(len(selected)),
            "future_close_return": _distribution(selected["future_close_return"]),
            "signed_close_return": _distribution(signed),
        }
    return reports


def _category_key(value: object) -> str:
    numeric = float(value)
    return str(int(numeric)) if numeric.is_integer() else str(numeric)


def _numeric_summary(usable: pd.DataFrame) -> dict[str, object]:
    reports: dict[str, object] = {}
    for name in _NUMERIC_COMPONENTS:
        if name not in usable:
            continue
        reports[name] = {
            target: daily_ic_summary(usable[name], usable[target])
            for target in _IC_TARGETS
        }
    return reports
