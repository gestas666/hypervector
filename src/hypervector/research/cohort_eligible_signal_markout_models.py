"""Typed evidence records for executable-BBO eligible-signal markouts."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MarkoutCoverage:
    """Reconciled causal book coverage for one markout evidence subset."""

    eligible_signals: int = 0
    entry_matched: int = 0
    entry_censored: int = 0
    entry_gap: int = 0
    resolved: int = 0
    exit_censored: int = 0
    exit_gap: int = 0
    friction_contract_missing: int = 0

    def as_payload(self) -> dict[str, int]:
        """Return the coverage fields as a JSON-compatible mapping."""
        return dict(vars(self))


@dataclass(frozen=True)
class MarkoutFriction:
    """Provider-specific fee and residual-slippage assumptions."""

    fee_bps_per_side: float
    residual_slippage_bps_per_side: float | None
    source: str


@dataclass(frozen=True)
class ExecutableMarkout:
    """One post-publication BBO-cross outcome at a fixed horizon."""

    source_run_id: str | None
    decision_time_ms: int
    horizon_minutes: int
    signal_available_time_ms: int
    entry_book_time_ms: int
    exit_book_time_ms: int
    side: str
    pressure_stance: str
    state_5m_stance: str
    context_15m_stance: str
    entry_price: float
    exit_price: float
    gross_bbo_bps: float
    after_fee_bps: float | None
    after_modeled_friction_bps: float | None
    fee_bps_per_side: float | None
    residual_slippage_bps_per_side: float | None
    friction_source: str | None
    episode_onset: bool | None


@dataclass
class MarkoutEvidence:
    """All outcomes and coverage for one provider-symbol horizon."""

    coverage: MarkoutCoverage = field(default_factory=MarkoutCoverage)
    episode_coverage: MarkoutCoverage = field(default_factory=MarkoutCoverage)
    outcomes: list[ExecutableMarkout] = field(default_factory=list)
