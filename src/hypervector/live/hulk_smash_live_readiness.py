"""Exact Hulk Smash setup readiness derived from decision-time indicators."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from hypervector.live.provider_readiness import ReadinessMetric, SignalReadiness

_COMPONENT_FIELDS = {"ema_trend", "money_flow_direction", "volume_ratio"}
_QUALITY_FIELDS = {
    "supertrend_direction",
    "adx",
    "squeeze_on",
    "squeeze_release",
    "ha_choppy",
}
_ENTRY_CONTRACT = "hulk_expansion_moderate_adx_v1"


@dataclass(frozen=True)
class HulkEntryReadinessFacts:
    """Exact signal facts consumed by the Hulk execution disposition."""

    candidate: str
    evidence: tuple[str, ...]
    score: int
    minimum_score: int
    signal_eligible: bool
    side: str | None
    allowed_sides: frozenset[str]

    def __post_init__(self) -> None:
        """Reject facts that cannot represent one deterministic disposition."""
        if not self.candidate.strip():
            raise ValueError("Hulk readiness candidate must be non-empty")
        if any(not value.strip() for value in self.evidence):
            raise ValueError("Hulk readiness evidence must be non-empty text")
        if self.score < 0 or self.minimum_score < 1:
            raise ValueError("Hulk readiness scores are invalid")
        if not isinstance(self.signal_eligible, bool):
            raise ValueError("Hulk signal eligibility must be boolean")
        if self.side not in {None, "long", "short"}:
            raise ValueError("Hulk readiness side is invalid")
        if not self.allowed_sides or not self.allowed_sides.issubset({"long", "short"}):
            raise ValueError("Hulk readiness allowed sides are invalid")


@dataclass(frozen=True)
class _HulkReadinessValues:
    ema: int
    trend: int
    flow: int
    volume: float
    adx: float
    adx_usable: float
    squeeze_on: bool
    release: bool
    choppy: bool


def build_hulk_readiness(
    components: pd.Series | None,
    quality: pd.Series | None,
    *,
    adx_usable: float,
    entry: HulkEntryReadinessFacts,
) -> SignalReadiness:
    """Build exact entry readiness plus non-authoritative quality context."""
    values = _readiness_values(components, quality, adx_usable)
    if values is None:
        return _unavailable_readiness()
    conditions = _entry_conditions(entry)
    return SignalReadiness(
        side=entry.side,
        conditions_met=sum(conditions),
        conditions_required=len(conditions),
        blockers=_entry_blockers(entry, conditions),
        indicators=_entry_indicators(entry) + _context_indicators(values),
        metrics=_metrics(values, entry, conditions),
    )


def _entry_conditions(entry: HulkEntryReadinessFacts) -> tuple[bool, ...]:
    return (
        entry.candidate == "hulk_rebuilt_expansion_v1",
        "adx_usable" in entry.evidence,
        entry.signal_eligible,
        entry.side in entry.allowed_sides,
    )


def _entry_blockers(
    entry: HulkEntryReadinessFacts,
    conditions: tuple[bool, ...],
) -> tuple[str, ...]:
    names = (
        "expansion_trigger_not_present",
        "moderate_adx_not_present",
        "signal_score_not_eligible",
        "entry_side_unavailable" if entry.side is None else "entry_side_not_allowed",
    )
    return tuple(name for name, met in zip(names, conditions, strict=True) if not met)


def _readiness_values(
    components: pd.Series | None,
    quality: pd.Series | None,
    adx_usable: float,
) -> _HulkReadinessValues | None:
    if (
        components is None
        or quality is None
        or not _COMPONENT_FIELDS.issubset(components.index)
        or not _QUALITY_FIELDS.issubset(quality.index)
    ):
        return None
    return _HulkReadinessValues(
        ema=int(components["ema_trend"]),
        trend=int(quality["supertrend_direction"]),
        flow=int(components["money_flow_direction"]),
        volume=float(components["volume_ratio"]),
        adx=float(quality["adx"]),
        adx_usable=float(adx_usable),
        squeeze_on=bool(quality["squeeze_on"]),
        release=bool(quality["squeeze_release"]),
        choppy=bool(quality["ha_choppy"]),
    )


def _metrics(
    values: _HulkReadinessValues,
    entry: HulkEntryReadinessFacts,
    conditions: tuple[bool, ...],
) -> dict[str, ReadinessMetric]:
    return {
        "adx": values.adx,
        "adx_usable": values.adx_usable,
        "ema_trend": values.ema,
        "entry_candidate": entry.candidate,
        "entry_candidate_exact": conditions[0],
        "entry_contract": _ENTRY_CONTRACT,
        "entry_moderate_adx_evidence": conditions[1],
        "entry_score": entry.score,
        "entry_score_eligible": conditions[2],
        "entry_score_minimum": entry.minimum_score,
        "entry_side_allowed": conditions[3],
        "heikin_ashi_choppy": values.choppy,
        "money_flow_direction": values.flow,
        "squeeze_on": values.squeeze_on,
        "squeeze_release": values.release,
        "supertrend_direction": values.trend,
        "volume_ratio": values.volume,
    }


def _entry_indicators(entry: HulkEntryReadinessFacts) -> tuple[str, ...]:
    exact = entry.candidate == "hulk_rebuilt_expansion_v1"
    moderate = "adx_usable" in entry.evidence
    allowed = "+".join(value.upper() for value in sorted(entry.allowed_sides))
    side = (entry.side or "N/A").upper()
    return (
        f"EXPANSION TRIGGER {'YES' if exact else 'NO'}",
        f"MODERATE ADX EVIDENCE {'YES' if moderate else 'NO'}",
        f"SCORE {entry.score}/{entry.minimum_score} "
        f"{'ELIGIBLE' if entry.signal_eligible else 'NOT ELIGIBLE'}",
        f"SIDE {side} / ALLOWED {allowed}",
    )


def _context_indicators(values: _HulkReadinessValues) -> tuple[str, ...]:
    squeeze = (
        "RELEASE YES"
        if values.release
        else ("ARMED / RELEASE NO" if values.squeeze_on else "OFF / RELEASE NO")
    )
    return (
        f"SQUEEZE {squeeze}",
        f"EMA {values.ema:+d} / ST {values.trend:+d}",
        f"ADX {values.adx:.1f}/{values.adx_usable:.1f}",
        f"FLOW {values.flow:+d}",
        f"VOLUME {values.volume:.2f}x",
        f"CHOP {'YES' if values.choppy else 'NO'}",
    )


def _unavailable_readiness() -> SignalReadiness:
    return SignalReadiness(
        side=None,
        conditions_met=0,
        conditions_required=1,
        blockers=("indicator_telemetry_unavailable",),
        indicators=("INDICATOR TELEMETRY UNAVAILABLE",),
    )
