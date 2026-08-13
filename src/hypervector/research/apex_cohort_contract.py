"""Immutable scope and safety contract for the Apex-derived cohort."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal


CandidateFamily = Literal[
    "directional_mean_reversion",
    "directional_oi_trend",
    "two_sided_market_making",
]
SegmentName = Literal["development", "validation", "robustness"]


@dataclass(frozen=True)
class ApexCandidateSpec:
    """Identity and execution family for one Apex-derived hypothesis."""

    name: str
    family: CandidateFamily


@dataclass(frozen=True)
class ApexResearchSegment:
    """One immutable chronological research pass."""

    name: SegmentName
    start_utc: datetime
    end_utc: datetime

    def __post_init__(self) -> None:
        if self.start_utc.tzinfo is None or self.end_utc.tzinfo is None:
            raise ValueError("research segment timestamps must be timezone-aware")
        if self.start_utc >= self.end_utc:
            raise ValueError("research segment start must precede end")


@dataclass(frozen=True)
class ApexCohortContract:
    """Report-only capital, friction, and authority assumptions."""

    initial_equity_usd: float = 15_000.0
    maker_fee_rate: float = 0.00015
    taker_fee_rate: float = 0.00045
    submit_latency_ms: int = 50
    cancel_latency_ms: int = 50
    max_directional_positions_per_symbol: int = 1
    execution_authority: str = "none"
    report_only: bool = True
    place_attempted: bool = False

    def __post_init__(self) -> None:
        if self.initial_equity_usd <= 0.0:
            raise ValueError("initial equity must be positive")
        if not 0.0 <= self.maker_fee_rate < 1.0:
            raise ValueError("maker fee rate must be in [0, 1)")
        if not 0.0 <= self.taker_fee_rate < 1.0:
            raise ValueError("taker fee rate must be in [0, 1)")
        if self.submit_latency_ms < 0 or self.cancel_latency_ms < 0:
            raise ValueError("latency must be non-negative")
        if self.max_directional_positions_per_symbol != 1:
            raise ValueError("directional candidates require one position per symbol")
        if self.execution_authority != "none":
            raise ValueError("execution authority must remain none")
        if not self.report_only:
            raise ValueError("Apex cohort must remain report-only")
        if self.place_attempted:
            raise ValueError("report-only research forbids place attempts")


APEX_CANDIDATES: tuple[ApexCandidateSpec, ...] = (
    ApexCandidateSpec("apex_mean_reversion_v2", "directional_mean_reversion"),
    ApexCandidateSpec("apex_oi_trend_v2", "directional_oi_trend"),
    ApexCandidateSpec("apex_regime_mm_v2", "two_sided_market_making"),
)

RESEARCH_SEGMENTS: tuple[ApexResearchSegment, ...] = (
    ApexResearchSegment(
        "development",
        datetime(2025, 7, 28, tzinfo=UTC),
        datetime(2026, 1, 28, tzinfo=UTC),
    ),
    ApexResearchSegment(
        "validation",
        datetime(2026, 1, 28, tzinfo=UTC),
        datetime(2026, 4, 28, tzinfo=UTC),
    ),
    ApexResearchSegment(
        "robustness",
        datetime(2026, 4, 28, tzinfo=UTC),
        datetime(2026, 7, 27, tzinfo=UTC),
    ),
)
