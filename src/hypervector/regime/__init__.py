"""Regime detection: labels + metrics, not trade gates."""

from hypervector.regime.detectors import REGIME_LABELS, detect_regime_ema
from hypervector.regime.metrics import regime_detection_metrics
from hypervector.regime.models import BreakoutDirection, PrimaryRegime

__all__ = [
    "REGIME_LABELS",
    "BreakoutDirection",
    "PrimaryRegime",
    "detect_regime_ema",
    "regime_detection_metrics",
]
