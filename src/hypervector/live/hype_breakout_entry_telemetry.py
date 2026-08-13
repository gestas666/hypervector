"""Causal live parity telemetry for HYPE breakout entry attribution."""

from __future__ import annotations

import math

from hypervector.live.provider_readiness import ReadinessMetric
from hypervector.live.sol_range_onset_controller import SolLiveDecision
from hypervector.regime.classifier import RegimeClassifierConfig
from hypervector.research.hype_breakout_entry_features import (
    HYPE_ENTRY_ATTRIBUTION_FEATURES,
)

_MINUTE_MS = 60_000
_HISTORY_MINUTES = 60
_AUTHORITY = "report_only"
_PROVENANCE = "causal_completed_multitimeframe_historical_parity_v2"
_EMA_CONFIG = RegimeClassifierConfig()
_EMA_SEMANTIC_SOURCE_IDENTITY = (
    "hypervector_regime_classifier_completed_close_ema_gap_bps_v1"
)


def build_hype_entry_feature_telemetry(
    decisions: tuple[SolLiveDecision, ...],
    position: int,
    side: str | None,
) -> dict[str, ReadinessMetric]:
    """Return historical-parity signal features without execution authority."""
    if side is None:
        return _unavailable("neutral_side_unavailable")
    if side not in {"long", "short"}:
        raise ValueError("HYPE entry feature side must be long or short")
    if isinstance(position, bool) or not 0 <= position < len(decisions):
        raise ValueError("HYPE entry feature position is outside decision history")
    start = position - _HISTORY_MINUTES
    if start < 0:
        return _unavailable("insufficient_60m_history")
    window = decisions[start : position + 1]
    if not _contiguous(window):
        return _unavailable("non_contiguous_1m_history")
    if not _sources_available(window):
        return _unavailable("source_metrics_unavailable")
    values = _feature_values(window, side)
    if set(values) != set(HYPE_ENTRY_ATTRIBUTION_FEATURES):
        raise ValueError("HYPE live and historical feature contracts diverged")
    if not all(math.isfinite(value) for value in values.values()):
        return _unavailable("non_finite_feature")
    return {
        **_contract_metadata(),
        "entry_feature_status": "measured",
        **values,
    }


def _feature_values(
    window: tuple[SolLiveDecision, ...],
    side: str,
) -> dict[str, float]:
    current = window[-1]
    side_sign = 1.0 if side == "long" else -1.0
    close = current.reference_price
    prior_bbwp = [
        _metric(value, "regime_1m_bbwp_percentile") for value in window[-16:-1]
    ]
    prior_20 = window[-21:-1]
    prior_high = max(_bar(value, "high_price") for value in prior_20)
    prior_low = min(_bar(value, "low_price") for value in prior_20)
    clearance = close / prior_high - 1.0 if side_sign > 0.0 else prior_low / close - 1.0
    return {
        "sma_gap_directional_bps": _metric(current, "sma_gap_bps") * side_sign,
        "regime_strength": current.confidence,
        "current_bbwp_percentile": _metric(current, "regime_1m_bbwp_percentile"),
        "prior_bbwp_min_15m": min(prior_bbwp),
        "prior_bbwp_below25_count_15m": float(
            sum(value < 25.0 for value in prior_bbwp)
        ),
        "ema_gap_directional_bps": _metric(current, "regime_1m_ema_gap_bps")
        * side_sign,
        "rsi_directional_distance": (_metric(current, "rsi") - 50.0) * side_sign,
        "breakout_volume_ratio": _metric(current, "regime_1m_breakout_volume_ratio"),
        "directional_return_5m_bps": _return_bps(window, 5, side_sign),
        "directional_return_15m_bps": _return_bps(window, 15, side_sign),
        "directional_return_60m_bps": _return_bps(window, 60, side_sign),
        "volume_ratio_20m": _bar(current, "volume")
        / (sum(_bar(value, "volume") for value in prior_20) / len(prior_20)),
        "bar_range_bps": (_bar(current, "high_price") - _bar(current, "low_price"))
        / close
        * 10_000.0,
        "directional_bar_body_bps": (close / _bar(current, "open_price") - 1.0)
        * 10_000.0
        * side_sign,
        "breakout_clearance_20m_bps": clearance * 10_000.0,
        "state_1m_alignment": float(
            current.state_1m == ("TREND_UP" if side_sign > 0.0 else "TREND_DOWN")
        ),
        "context_15m_alignment": float(
            current.context_15m == ("TREND_UP" if side_sign > 0.0 else "TREND_DOWN")
        ),
        "authoritative_5m_strength_percentile": _metric(
            current, "regime_5m_strength_percentile"
        ),
        "authoritative_5m_bbwp_percentile": _metric(
            current, "regime_5m_bbwp_percentile"
        ),
        "authoritative_5m_ema_gap_directional_bps": _metric(
            current, "regime_5m_ema_gap_bps"
        )
        * side_sign,
        "authoritative_5m_breakout_volume_ratio": _metric(
            current, "regime_5m_breakout_volume_ratio"
        ),
    }


def _return_bps(
    window: tuple[SolLiveDecision, ...],
    minutes: int,
    side_sign: float,
) -> float:
    return (
        (window[-1].reference_price / window[-1 - minutes].reference_price - 1.0)
        * 10_000.0
        * side_sign
    )


def _metric(decision: SolLiveDecision, name: str) -> float:
    raw = None if decision.readiness is None else decision.readiness.metrics.get(name)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError(f"HYPE entry feature metric is unavailable: {name}")
    return float(raw)


def _bar(decision: SolLiveDecision, name: str) -> float:
    raw = decision.volume if name == "volume" else getattr(decision, name)
    if raw is None:
        raise ValueError(f"HYPE entry feature bar value is unavailable: {name}")
    return float(raw)


def _sources_available(window: tuple[SolLiveDecision, ...]) -> bool:
    try:
        for decision in window:
            for name in (
                "sma_gap_bps",
                "regime_1m_bbwp_percentile",
                "regime_1m_ema_gap_bps",
                "rsi",
                "regime_1m_breakout_volume_ratio",
                "regime_5m_strength_percentile",
                "regime_5m_bbwp_percentile",
                "regime_5m_ema_gap_bps",
                "regime_5m_breakout_volume_ratio",
            ):
                _metric(decision, name)
            for name in ("open_price", "high_price", "low_price", "volume"):
                _bar(decision, name)
    except ValueError:
        return False
    return True


def _contiguous(window: tuple[SolLiveDecision, ...]) -> bool:
    return all(
        right.decision_time_ms - left.decision_time_ms == _MINUTE_MS
        for left, right in zip(window, window[1:])
    )


def _unavailable(reason: str) -> dict[str, ReadinessMetric]:
    return {
        **_contract_metadata(),
        "entry_feature_status": reason,
        **{name: None for name in HYPE_ENTRY_ATTRIBUTION_FEATURES},
    }


def _contract_metadata() -> dict[str, ReadinessMetric]:
    return {
        "entry_feature_authority": _AUTHORITY,
        "entry_feature_provenance": _PROVENANCE,
        "ema_fast_period": _EMA_CONFIG.ema_fast,
        "ema_slow_period": _EMA_CONFIG.ema_slow,
        "ema_semantic_source_identity": _EMA_SEMANTIC_SOURCE_IDENTITY,
    }
