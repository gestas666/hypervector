"""Convert completed Hyperliquid candles into causal SOL live decisions."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from hypervector.live.sol_range_onset_controller import SolLiveDecision
from hypervector.live.provider_readiness import ReadinessMetric, SignalReadiness
from hypervector.regime.composite import classify_multitimeframe
from hypervector.regime.component_telemetry import build_regime_component_frame
from hypervector.research.range_onset_observation import (
    prepare_completed_range_onset_frames,
)
from hypervector.research.range_onset_signals import build_range_onset_signals

_MINUTE = pd.Timedelta(minutes=1)


def build_completed_live_decisions(
    raw_bars: pd.DataFrame,
    *,
    observed_at: pd.Timestamp,
    after_decision_time_ms: int | None = None,
) -> tuple[SolLiveDecision, ...]:
    """Return every unseen completed-bar decision in chronological order."""
    after = _optional_timestamp(after_decision_time_ms)
    bars, signals, regimes = prepare_completed_range_onset_frames(
        raw_bars,
        observed_at=observed_at,
        signal_builder=build_range_onset_signals,
        regime_builder=classify_multitimeframe,
    )
    _validate_alignment(bars, signals, regimes)
    components = build_regime_component_frame(bars)
    _validate_alignment(bars, components, regimes)
    decisions: list[SolLiveDecision] = []
    for timestamp in bars.index:
        decision_time = pd.Timestamp(timestamp) + _MINUTE
        decision_ms = int(decision_time.timestamp() * 1_000)
        if after is not None and decision_ms <= after:
            continue
        decisions.append(
            _decision_from_rows(
                decision_ms,
                bars.loc[timestamp],
                signals.loc[timestamp],
                regimes.loc[timestamp],
                components.loc[timestamp],
            )
        )
    return tuple(decisions)


def _decision_from_rows(
    decision_time_ms: int,
    bar: pd.Series,
    signal: pd.Series,
    regime: pd.Series,
    components: pd.Series,
) -> SolLiveDecision:
    return SolLiveDecision(
        decision_time_ms=decision_time_ms,
        reference_price=_positive_float(bar.get("close"), "close"),
        long_entry=_boolean(signal.get("long_entry"), "long_entry"),
        short_entry=_boolean(signal.get("short_entry"), "short_entry"),
        long_exit=_boolean(signal.get("long_exit"), "long_exit"),
        short_exit=_boolean(signal.get("short_exit"), "short_exit"),
        primary_regime=_text(regime.get("primary_regime"), "primary_regime"),
        state_1m=_text(regime.get("state_1m"), "state_1m"),
        state_5m=_text(regime.get("state_5m"), "state_5m"),
        context_15m=_text(regime.get("context_15m"), "context_15m"),
        confidence=_finite_float(regime.get("confidence"), "confidence"),
        structural_direction=_text(
            signal.get("structural_direction"),
            "structural_direction",
        ),
        regime_admitted=_boolean(signal.get("regime_admitted"), "regime_admitted"),
        open_price=_positive_float(bar.get("open"), "open"),
        high_price=_positive_float(bar.get("high"), "high"),
        low_price=_positive_float(bar.get("low"), "low"),
        volume=_nonnegative_float(bar.get("volume"), "volume"),
        readiness=_range_readiness(signal, regime, components),
        breakout_side=_regime_breakout_side(regime),
    )


def _regime_breakout_side(regime: pd.Series) -> str | None:
    if regime.get("state_5m") != "BREAKOUT":
        return None
    value = regime.get("structural_direction")
    if value in {None, "neutral"} or pd.isna(value):
        return None
    if value not in {"long", "short"}:
        raise ValueError("5m breakout structural_direction must be long or short")
    return str(value)


def _range_readiness(
    signal: pd.Series,
    regime: pd.Series,
    components: pd.Series,
) -> SignalReadiness:
    if not _RANGE_READINESS_FIELDS.issubset(signal.index):
        return _unavailable_readiness()
    fast = float(signal["sma_fast"])
    slow = float(signal["sma_slow"])
    gap = float(signal["sma_gap_bps"])
    history_ready = all(math.isfinite(value) for value in (fast, slow, gap))
    long_cross = bool(signal["raw_long_cross"])
    short_cross = bool(signal["raw_short_cross"])
    crossed = long_cross or short_cross
    admitted = bool(signal["regime_admitted"])
    conditions = (history_ready, admitted, crossed)
    blockers = tuple(
        name for name, met in zip(_RANGE_BLOCKERS, conditions, strict=True) if not met
    )
    structural = str(signal["structural_direction"])
    side = (
        "long"
        if long_cross or (not short_cross and structural == "long")
        else "short"
        if short_cross or structural == "short"
        else None
    )
    context_indicator, context_admitted = _dual_mtf_challenger(side, components)
    return SignalReadiness(
        side=side,
        conditions_met=sum(conditions),
        conditions_required=len(conditions),
        blockers=blockers,
        indicators=(
            _sma_value("SMA10", fast),
            _sma_value("SMA30", slow),
            _sma_gap(gap),
            f"RAW CROSS {'LONG' if long_cross else 'SHORT' if short_cross else 'NONE'}",
            f"5m REGIME {'ADMITTED' if admitted else 'BLOCKED'}",
            f"STRUCT {structural.upper()}",
            *_regime_indicators(regime),
            *_component_indicators(components),
            context_indicator,
        ),
        metrics={
            **_range_metrics(
                fast, slow, gap, long_cross, short_cross, admitted, structural
            ),
            **_regime_metrics(regime),
            **_component_metrics(components),
            "dual_mtf_context_challenger_admitted": context_admitted,
            "dual_mtf_context_challenger_authority": "report_only",
        },
    )


_RANGE_READINESS_FIELDS = {
    "raw_long_cross",
    "raw_short_cross",
    "sma_fast",
    "sma_slow",
    "sma_gap_bps",
    "regime_admitted",
    "structural_direction",
}
_RANGE_BLOCKERS = (
    "hourly_sma_warmup",
    "5m_regime_not_admitted",
    "awaiting_hourly_sma_cross",
)

CANONICAL_REGIME_METRIC_FIELDS = (
    "rsi",
    "regime_1m_reason",
    "regime_5m_reason",
    "regime_15m_reason",
    "regime_1m_strength_percentile",
    "regime_5m_strength_percentile",
    "regime_15m_strength_percentile",
    "regime_1m_bbwp_percentile",
    "regime_5m_bbwp_percentile",
    "regime_15m_bbwp_percentile",
    "regime_1m_ema_gap_bps",
    "regime_5m_ema_gap_bps",
    "regime_15m_ema_gap_bps",
    "regime_1m_coiling",
    "regime_5m_coiling",
    "regime_15m_coiling",
    "regime_1m_range_cause_coiling",
    "regime_5m_range_cause_coiling",
    "regime_15m_range_cause_coiling",
    "regime_1m_range_cause_strength",
    "regime_5m_range_cause_strength",
    "regime_15m_range_cause_strength",
    "regime_1m_range_cause_gap",
    "regime_5m_range_cause_gap",
    "regime_15m_range_cause_gap",
    "regime_1m_range_cause_filter",
    "regime_5m_range_cause_filter",
    "regime_15m_range_cause_filter",
    "regime_1m_breakout_volume_ratio",
    "regime_5m_breakout_volume_ratio",
    "regime_15m_breakout_volume_ratio",
    "regime_range_filter_name",
    "regime_bbwp_threshold_pct",
    "regime_minimum_gap_bps",
    "regime_range_strength_threshold_pct",
    "regime_trend_strength_threshold_pct",
    "regime_breakout_volume_multiple",
)
CANONICAL_REGIME_TEXT_METRIC_FIELDS = frozenset(
    {name for name in CANONICAL_REGIME_METRIC_FIELDS if name.endswith("reason")}
    | {"regime_range_filter_name"}
)
CANONICAL_REGIME_BOOLEAN_METRIC_FIELDS = frozenset(
    name
    for name in CANONICAL_REGIME_METRIC_FIELDS
    if "coiling" in name or "range_cause" in name
)


def _range_metrics(
    fast: float,
    slow: float,
    gap: float,
    long_cross: bool,
    short_cross: bool,
    admitted: bool,
    structural: str,
) -> dict[str, ReadinessMetric]:
    return {
        "raw_long_cross": long_cross,
        "raw_short_cross": short_cross,
        "regime_admitted": admitted,
        "sma_fast": _optional_metric(fast),
        "sma_gap_bps": _optional_metric(gap),
        "sma_slow": _optional_metric(slow),
        "structural_direction": structural,
    }


def _regime_metrics(values: pd.Series) -> dict[str, ReadinessMetric]:
    """Copy typed canonical diagnostic values into report-only readiness."""
    output: dict[str, ReadinessMetric] = {}
    for name in CANONICAL_REGIME_METRIC_FIELDS:
        raw = values.get(name)
        if name in CANONICAL_REGIME_TEXT_METRIC_FIELDS:
            output[name] = _optional_text_metric(raw)
        elif name in CANONICAL_REGIME_BOOLEAN_METRIC_FIELDS:
            output[name] = _optional_boolean_metric(raw)
        else:
            output[name] = _optional_metric(raw)
    return output


def _regime_indicators(values: pd.Series) -> tuple[str, ...]:
    bbwp = _ratio_indicator(
        values.get("regime_5m_bbwp_percentile"),
        values.get("regime_bbwp_threshold_pct"),
    )
    gap = _ratio_indicator(
        values.get("regime_5m_ema_gap_bps"),
        values.get("regime_minimum_gap_bps"),
    )
    causes = _range_cause_indicator(values)
    return (f"5M BBWP {bbwp}", f"5M EMA GAP {gap}bps", causes)


def _range_cause_indicator(values: pd.Series) -> str:
    names = ("FILTER", "COILING", "WEAK", "GAP")
    fields = (
        "regime_5m_range_cause_filter",
        "regime_5m_range_cause_coiling",
        "regime_5m_range_cause_strength",
        "regime_5m_range_cause_gap",
    )
    active = [
        name
        for name, field in zip(names, fields, strict=True)
        if values.get(field) is True
    ]
    return "5M RANGE CAUSES " + ("+".join(active) if active else "NONE/UNAVAILABLE")


def _ratio_indicator(value: object, threshold: object) -> str:
    left = _optional_metric(value)
    right = _optional_metric(threshold)
    if left is None or right is None:
        return "N/A"
    return f"{left:.1f}/{right:.1f}"


def _component_metrics(values: pd.Series) -> dict[str, ReadinessMetric]:
    metrics: dict[str, ReadinessMetric] = {
        "component_authority": "observe_only",
        "component_provenance": "causal_completed_1m_v1",
        "component_weight_mode": "unweighted_observe_v1",
    }
    for name in CANONICAL_COMPONENT_METRIC_FIELDS:
        raw = values.get(name)
        metrics[name] = (
            _optional_integer_metric(raw)
            if name in CANONICAL_COMPONENT_CATEGORICAL_FIELDS
            else _optional_metric(raw)
        )
    return metrics


CANONICAL_COMPONENT_METRIC_FIELDS = (
    "ema_21_55_gap_bps",
    "ema_21_55_direction",
    "sma_100_200_gap_bps",
    "sma_100_200_direction",
    "cipher_a_direction",
    "harsi_direction",
    "harsi_smoothed_rsi",
    "choppiness_14",
    "mtf_5m_bias",
    "mtf_15m_bias",
    "trend_slope_bps",
    "trend_r2",
    "self_aware_tqi",
)
CANONICAL_COMPONENT_CATEGORICAL_FIELDS = frozenset(
    {
        "ema_21_55_direction",
        "sma_100_200_direction",
        "cipher_a_direction",
        "harsi_direction",
        "mtf_5m_bias",
        "mtf_15m_bias",
    }
)


def _optional_metric(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _optional_integer_metric(value: object) -> int | None:
    number = _optional_metric(value)
    if number is None:
        return None
    integer = int(number)
    if number != integer:
        raise ValueError("categorical regime component must be integer-valued")
    return integer


def _optional_boolean_metric(value: object) -> bool | None:
    return bool(value) if isinstance(value, (bool, np.bool_)) else None


def _optional_text_metric(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _component_indicators(values: pd.Series) -> tuple[str, ...]:
    return (
        _indicator("EMA21/55", values.get("ema_21_55_gap_bps"), "bps"),
        _indicator("SMA100/200", values.get("sma_100_200_gap_bps"), "bps"),
        _direction_indicator("CIPHER A", values.get("cipher_a_direction")),
        _direction_indicator("HARSI", values.get("harsi_direction")),
        _indicator("CHOP14", values.get("choppiness_14"), ""),
        _bias_indicator(values),
        _indicator("TREND R2", values.get("trend_r2"), ""),
        _indicator("TQI", values.get("self_aware_tqi"), ""),
    )


def _indicator(label: str, value: object, suffix: str) -> str:
    number = _optional_metric(value)
    return f"{label} N/A" if number is None else f"{label} {number:+.2f}{suffix}"


def _direction_indicator(label: str, value: object) -> str:
    number = _optional_metric(value)
    state = (
        "N/A"
        if number is None
        else "UP"
        if number > 0.0
        else "DOWN"
        if number < 0.0
        else "NEUTRAL"
    )
    return f"{label} {state}"


def _bias_indicator(values: pd.Series) -> str:
    five = _optional_metric(values.get("mtf_5m_bias"))
    fifteen = _optional_metric(values.get("mtf_15m_bias"))
    left = "N/A" if five is None else f"{five:+.0f}"
    right = "N/A" if fifteen is None else f"{fifteen:+.0f}"
    return f"MTF BIAS 5M {left} / 15M {right}"


def _dual_mtf_challenger(
    side: str | None,
    values: pd.Series,
) -> tuple[str, bool | None]:
    five = _optional_metric(values.get("mtf_5m_bias"))
    fifteen = _optional_metric(values.get("mtf_15m_bias"))
    if side not in {"long", "short"} or five is None or fifteen is None:
        return "DUAL-MTF CHALLENGER N/A [REPORT ONLY]", None
    side_sign = 1.0 if side == "long" else -1.0
    opposed = five * side_sign < 0.0 and fifteen * side_sign < 0.0
    state = "OPPOSED" if opposed else "CLEAR"
    return f"DUAL-MTF CHALLENGER {state} [REPORT ONLY]", not opposed


def _sma_value(label: str, value: float) -> str:
    return f"{label} {value:.4f}" if math.isfinite(value) else f"{label} N/A"


def _sma_gap(value: float) -> str:
    return f"SMA GAP {value:+.1f}bps" if math.isfinite(value) else "SMA GAP N/A"


def _unavailable_readiness() -> SignalReadiness:
    return SignalReadiness(
        side=None,
        conditions_met=0,
        conditions_required=1,
        blockers=("indicator_telemetry_unavailable",),
        indicators=("INDICATOR TELEMETRY UNAVAILABLE",),
    )


def _validate_alignment(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    regimes: pd.DataFrame,
) -> None:
    if not bars.index.equals(signals.index) or not bars.index.equals(regimes.index):
        raise ValueError("SOL live bars, signals, and regimes must share one index")
    if bars.index.has_duplicates or not bars.index.is_monotonic_increasing:
        raise ValueError("SOL live decision index must be unique and increasing")


def _optional_timestamp(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("after_decision_time_ms must be a nonnegative integer")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, (bool, np.bool_)):
        raise ValueError(f"SOL live {label} must be boolean")
    return bool(value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"SOL live {label} must be non-empty text")
    return value.strip()


def _finite_float(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"SOL live {label} must be numeric")
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"SOL live {label} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"SOL live {label} must be finite")
    return result


def _positive_float(value: object, label: str) -> float:
    result = _finite_float(value, label)
    if result <= 0.0:
        raise ValueError(f"SOL live {label} must be positive")
    return result


def _nonnegative_float(value: object, label: str) -> float:
    result = _finite_float(value, label)
    if result < 0.0:
        raise ValueError(f"SOL live {label} must be nonnegative")
    return result
