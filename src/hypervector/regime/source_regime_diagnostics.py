"""Typed, execution-neutral diagnostics from the pinned source classifier."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from numbers import Real


@dataclass(frozen=True)
class SourceRegimeDiagnostics:
    """Raw source output and the causal indicators that selected it."""

    raw_primary: str
    raw_secondary: str | None
    raw_confidence: float
    adx: float | None
    adx_percentile_rank: float | None
    adx_range_percentile_threshold: float
    adx_weak_percentile_threshold: float
    ema_alignment: str
    rsi: float | None
    volume_ratio: float | None
    range_break_up: bool
    range_break_down: bool

    def __post_init__(self) -> None:
        if not self.raw_primary.strip():
            raise ValueError("raw primary regime must be non-empty")
        if self.raw_secondary is not None and not self.raw_secondary.strip():
            raise ValueError("raw secondary regime must be non-empty when present")
        _unit_interval(self.raw_confidence, "raw confidence")
        _unit_interval(
            self.adx_range_percentile_threshold,
            "ADX range percentile threshold",
        )
        _unit_interval(
            self.adx_weak_percentile_threshold,
            "ADX weak percentile threshold",
        )
        if self.adx_range_percentile_threshold >= self.adx_weak_percentile_threshold:
            raise ValueError("ADX range threshold must be below weak threshold")
        if not self.ema_alignment.strip():
            raise ValueError("EMA alignment must be non-empty")

    def to_dict(self, *, confirmed_primary: str) -> dict[str, object]:
        """Return JSON-ready telemetry with explicit non-execution authority."""
        if not confirmed_primary.strip():
            raise ValueError("confirmed primary regime must be non-empty")
        return {
            "authority": "telemetry_only",
            "raw_primary": self.raw_primary,
            "raw_secondary": self.raw_secondary,
            "raw_confidence": self.raw_confidence,
            "confirmed_primary": confirmed_primary,
            "state_filtered": self.raw_primary != confirmed_primary,
            "adx": self.adx,
            "adx_percentile_rank": self.adx_percentile_rank,
            "adx_range_percentile_threshold": (self.adx_range_percentile_threshold),
            "adx_weak_percentile_threshold": self.adx_weak_percentile_threshold,
            "ema_alignment": self.ema_alignment,
            "rsi": self.rsi,
            "volume_ratio": self.volume_ratio,
            "range_break_up": self.range_break_up,
            "range_break_down": self.range_break_down,
        }


def build_source_regime_diagnostics(
    *,
    raw_primary: str,
    raw_secondary: str | None,
    raw_confidence: float,
    indicators: Mapping[str, object],
    adx_range_percentile_threshold: float,
    adx_weak_percentile_threshold: float,
) -> SourceRegimeDiagnostics:
    """Normalize the source classifier's selected indicators fail-closed."""
    return SourceRegimeDiagnostics(
        raw_primary=raw_primary,
        raw_secondary=raw_secondary,
        raw_confidence=raw_confidence,
        adx=_optional_float(indicators, "adx"),
        adx_percentile_rank=_optional_float(indicators, "adx_rank"),
        adx_range_percentile_threshold=adx_range_percentile_threshold,
        adx_weak_percentile_threshold=adx_weak_percentile_threshold,
        ema_alignment=_text(indicators, "ema_alignment"),
        rsi=_optional_float(indicators, "rsi"),
        volume_ratio=_optional_float(indicators, "volume_ratio"),
        range_break_up=_boolean(indicators, "range_break_up"),
        range_break_down=_boolean(indicators, "range_break_down"),
    )


def _optional_float(values: Mapping[str, object], key: str) -> float | None:
    value = _required(values, key)
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"source indicator {key!r} must be numeric")
    normalized = float(value)
    return normalized if math.isfinite(normalized) else None


def _text(values: Mapping[str, object], key: str) -> str:
    value = _required(values, key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"source indicator {key!r} must be non-empty text")
    return value


def _boolean(values: Mapping[str, object], key: str) -> bool:
    value = _required(values, key)
    if not isinstance(value, bool):
        raise ValueError(f"source indicator {key!r} must be boolean")
    return value


def _required(values: Mapping[str, object], key: str) -> object:
    if key not in values:
        raise ValueError(f"source diagnostics missing indicator {key!r}")
    return values[key]


def _unit_interval(value: float, label: str) -> None:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{label} must be finite and within [0, 1]")
