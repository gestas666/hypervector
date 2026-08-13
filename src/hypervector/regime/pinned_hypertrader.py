"""Checksum-pinned adapter for the original Hypertrader 5m classifier."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping
import importlib
from pathlib import Path
import sys
from types import ModuleType
from typing import Protocol, cast

from hypervector.regime.source_follow_runtime import FiveMinuteBar, SourceRegimeLabel
from hypervector.regime.source_regime_diagnostics import (
    build_source_regime_diagnostics,
)
from hypervector.research.hypertrader_source_adapter import (
    PINNED_HYPERTRADER_REVISION,
    PINNED_SOURCE_HASHES,
    verify_source_files,
)

_NAMESPACE_ROOT_ATTRIBUTE = "__hypervector_pinned_backend_root__"


class _SourceConfig(Protocol):
    warmup_bars: int
    confirmation_bars: int
    min_duration_bars: int
    breakout_confirmation_bars: int
    breakout_ttl_bars: int
    breakout_cooldown_bars: int
    adx_range_pct: float
    adx_weak_pct: float


class _SourceRegime(Protocol):
    primary: object
    secondary: str | None
    confidence: float
    indicators: Mapping[str, object]


class _SourceClassifier(Protocol):
    config: _SourceConfig

    def classify(self, bar: object, history: list[object]) -> _SourceRegime:
        """Classify one source bar from the bounded causal history."""


class _SourceStateMachine(Protocol):
    def update(self, regime: _SourceRegime) -> _SourceRegime | None:
        """Return the latest hysteresis-confirmed source regime."""


class _SourceComponents:
    def __init__(
        self,
        classifier_factory: Callable[..., object],
        state_factory: Callable[..., object],
        bar_factory: Callable[..., object],
        config: _SourceConfig,
    ) -> None:
        self.classifier_factory = classifier_factory
        self.state_factory = state_factory
        self.bar_factory = bar_factory
        self.config = config


class PinnedHypertraderClassifier:
    """Adapt the pinned source classifier to Hypervector runtime bars."""

    def __init__(self, backend_root: Path | str) -> None:
        self.backend_root = Path(backend_root)
        self.source_identity = verify_source_files(
            self.backend_root,
            expected_hashes=PINNED_SOURCE_HASHES,
            revision=PINNED_HYPERTRADER_REVISION,
        )
        components = _load_components(self.backend_root)
        self._bar_factory = components.bar_factory
        self._classifier = cast(
            _SourceClassifier,
            components.classifier_factory(components.config),
        )
        self._state = cast(
            _SourceStateMachine,
            components.state_factory(
                confirmation_bars=components.config.confirmation_bars,
                min_duration_bars=components.config.min_duration_bars,
                coin="BTC",
                breakout_confirmation_bars=(
                    components.config.breakout_confirmation_bars
                ),
                breakout_ttl_bars=components.config.breakout_ttl_bars,
                breakout_cooldown_bars=components.config.breakout_cooldown_bars,
                enable_hooks=False,
            ),
        )
        self._history: deque[object] = deque(maxlen=components.config.warmup_bars)

    def classify(self, bar: FiveMinuteBar) -> SourceRegimeLabel:
        """Classify one completed bar with the exact pinned source algorithm."""
        source_bar = self._bar_factory(
            coin="BTC",
            timeframe="5m",
            timestamp_ms=bar.timestamp_utc.timestamp() * 1_000,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        )
        self._history.append(source_bar)
        raw = self._classifier.classify(source_bar, list(self._history))
        confirmed = self._state.update(raw)
        diagnostics = build_source_regime_diagnostics(
            raw_primary=_enum_text(raw.primary),
            raw_secondary=raw.secondary,
            raw_confidence=float(raw.confidence),
            indicators=raw.indicators,
            adx_range_percentile_threshold=float(self._classifier.config.adx_range_pct),
            adx_weak_percentile_threshold=float(self._classifier.config.adx_weak_pct),
        )
        return SourceRegimeLabel(
            label_time_utc=bar.timestamp_utc,
            primary="UNKNOWN" if confirmed is None else _enum_text(confirmed.primary),
            secondary=None if confirmed is None else confirmed.secondary,
            confidence=0.0 if confirmed is None else float(confirmed.confidence),
            diagnostics=diagnostics,
        )


def _load_components(backend_root: Path) -> _SourceComponents:
    backend_text = str(backend_root.resolve())
    if backend_text not in sys.path:
        sys.path.insert(0, backend_text)
    _isolate_regime_namespace(backend_root.resolve())
    classifier_module = importlib.import_module("app.services.regime.classifier")
    config_module = importlib.import_module("app.services.regime.config")
    models_module = importlib.import_module("app.services.regime.models")
    state_module = importlib.import_module("app.services.regime.state")
    configs = cast(Mapping[str, _SourceConfig], config_module.COIN_CONFIGS)
    return _SourceComponents(
        cast(Callable[..., object], classifier_module.SecondaryClassifier),
        cast(Callable[..., object], state_module.RegimeStateMachine),
        cast(Callable[..., object], models_module.BarData),
        configs["BTC"],
    )


def _isolate_regime_namespace(backend_root: Path) -> None:
    loaded = [name for name in sys.modules if name.startswith("app.services.regime")]
    if loaded:
        package = sys.modules.get("app.services.regime")
        loaded_root = getattr(package, _NAMESPACE_ROOT_ATTRIBUTE, None)
        if loaded_root == str(backend_root):
            return
        raise RuntimeError(
            "pinned Hypertrader regime namespace is already loaded from a "
            "different or unmanaged backend"
        )
    package_paths = {
        "app": backend_root / "app",
        "app.services": backend_root / "app" / "services",
        "app.services.regime": backend_root / "app" / "services" / "regime",
    }
    for name, path in package_paths.items():
        module = ModuleType(name)
        module.__path__ = [str(path)]  # type: ignore[attr-defined]
        setattr(module, _NAMESPACE_ROOT_ATTRIBUTE, str(backend_root))
        sys.modules[name] = module


def _enum_text(value: object) -> str:
    return str(getattr(value, "value", value))
