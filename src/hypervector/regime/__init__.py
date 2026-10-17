"""Lazy public exports for Hypervector regime services."""

from importlib import import_module

_EXPORTS = {
    "RegimeClassifierConfig": (
        "hypervector.regime.classifier",
        "RegimeClassifierConfig",
    ),
    "classify_timeframe": ("hypervector.regime.classifier", "classify_timeframe"),
    "classify_multitimeframe": (
        "hypervector.regime.composite",
        "classify_multitimeframe",
    ),
    "compose_regimes": ("hypervector.regime.composite", "compose_regimes"),
    "REGIME_LABELS": ("hypervector.regime.detectors", "REGIME_LABELS"),
    "detect_regime_ema": ("hypervector.regime.detectors", "detect_regime_ema"),
    "regime_detection_metrics": (
        "hypervector.regime.metrics",
        "regime_detection_metrics",
    ),
    "BreakoutDirection": ("hypervector.regime.models", "BreakoutDirection"),
    "PrimaryRegime": ("hypervector.regime.models", "PrimaryRegime"),
}

__all__ = [
    "REGIME_LABELS",
    "BreakoutDirection",
    "PrimaryRegime",
    "RegimeClassifierConfig",
    "classify_multitimeframe",
    "classify_timeframe",
    "compose_regimes",
    "detect_regime_ema",
    "regime_detection_metrics",
]


def __getattr__(name: str) -> object:
    """Resolve public services without importing unrelated execution engines."""
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module, attribute = _EXPORTS[name]
    value = getattr(import_module(module), attribute)
    globals()[name] = value
    return value
