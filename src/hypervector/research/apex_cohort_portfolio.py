"""Deterministic shared-capital accounting for attributed Apex outcomes."""

from __future__ import annotations

from dataclasses import dataclass, field
import math


_CANDIDATES = (
    "hulk_expansion_short_robust_v3",
    "apex_regime_mm_v2",
    "apex_oi_trend_v2",
    "apex_mean_reversion_v2",
)


@dataclass(frozen=True)
class ApexAttributedOutcome:
    """One completed candidate outcome with explicit capital requirements."""

    outcome_id: str
    candidate: str
    symbol: str
    entry_time_ms: int
    exit_time_ms: int
    requested_margin_usd: float
    entry_fee_usd: float
    net_pnl_usd: float

    def __post_init__(self) -> None:
        if not self.outcome_id.strip() or not self.symbol.strip():
            raise ValueError("Apex outcome identity and symbol must be non-empty")
        if self.candidate not in _CANDIDATES:
            raise ValueError(f"unknown shared cohort candidate: {self.candidate}")
        if self.entry_time_ms < 0 or self.exit_time_ms <= self.entry_time_ms:
            raise ValueError("Apex outcome exit must follow a non-negative entry")
        _positive(self.requested_margin_usd, "requested_margin_usd")
        _nonnegative(self.entry_fee_usd, "entry_fee_usd")
        _finite(self.net_pnl_usd, "net_pnl_usd")


@dataclass(frozen=True)
class ApexCohortPortfolioConfig:
    """Shared balance, aggregate margin, and conflict priority contract."""

    initial_equity_usd: float = 15_000.0
    maximum_reserved_margin_fraction: float = 0.25
    candidate_priority: tuple[str, ...] = _CANDIDATES

    def __post_init__(self) -> None:
        _positive(self.initial_equity_usd, "initial_equity_usd")
        if not 0.0 < self.maximum_reserved_margin_fraction <= 1.0:
            raise ValueError("maximum reserved margin fraction must be in (0, 1]")
        if set(self.candidate_priority) != set(_CANDIDATES):
            raise ValueError(
                "candidate priority must contain the frozen cohort exactly"
            )
        if len(self.candidate_priority) != len(set(self.candidate_priority)):
            raise ValueError("candidate priority must be unique")


@dataclass(frozen=True)
class ApexAcceptedOutcome:
    """One accepted outcome after shared-capital conflict resolution."""

    outcome_id: str
    candidate: str
    symbol: str
    requested_margin_usd: float
    entry_fee_usd: float
    net_pnl_usd: float
    equity_after_usd: float


@dataclass(frozen=True)
class ApexRejectedOutcome:
    """One rejected intent retained as attribution telemetry."""

    outcome_id: str
    candidate: str
    symbol: str
    timestamp_ms: int
    reason: str


@dataclass(frozen=True)
class ApexCohortPortfolioReport:
    """Reconciled report from exactly one shared report-only balance."""

    initial_equity_usd: float
    final_equity_usd: float
    net_pnl_usd: float
    maximum_drawdown_pct: float
    total_entry_fees_usd: float
    maximum_concurrent_positions: int
    peak_reserved_margin_usd: float
    strategy_net_pnl_usd: dict[str, float]
    strategy_entry_fees_usd: dict[str, float]
    accepted: tuple[ApexAcceptedOutcome, ...]
    rejected: tuple[ApexRejectedOutcome, ...]
    report_only: bool = True
    execution_authority: str = "none"
    place_attempted: bool = False


@dataclass
class _OpenOutcome:
    outcome: ApexAttributedOutcome


@dataclass
class _State:
    equity: float
    peak_equity: float
    active_by_symbol: dict[str, _OpenOutcome] = field(default_factory=dict)
    active_ids: set[str] = field(default_factory=set)
    accepted: list[ApexAcceptedOutcome] = field(default_factory=list)
    rejected: list[ApexRejectedOutcome] = field(default_factory=list)
    strategy_pnl: dict[str, float] = field(default_factory=dict)
    strategy_fees: dict[str, float] = field(default_factory=dict)
    total_entry_fees: float = 0.0
    maximum_concurrent: int = 0
    peak_reserved_margin: float = 0.0
    maximum_drawdown_pct: float = 0.0


def replay_apex_cohort(
    outcomes: tuple[ApexAttributedOutcome, ...],
    config: ApexCohortPortfolioConfig | None = None,
) -> ApexCohortPortfolioReport:
    """Replay completed outcomes through one deterministic shared balance."""
    resolved = config or ApexCohortPortfolioConfig()
    _validate_unique(outcomes)
    state = _State(resolved.initial_equity_usd, resolved.initial_equity_usd)
    for _, action, _, _, outcome in _events(outcomes, resolved):
        if action == 0:
            _exit(state, outcome)
        else:
            _enter(state, outcome, resolved)
    if state.active_ids:
        raise RuntimeError("Apex shared replay ended with active outcomes")
    return _report(state, resolved)


def _events(
    outcomes: tuple[ApexAttributedOutcome, ...],
    config: ApexCohortPortfolioConfig,
) -> list[tuple[int, int, int, str, ApexAttributedOutcome]]:
    priority = {
        candidate: position
        for position, candidate in enumerate(config.candidate_priority)
    }
    events = [
        event
        for outcome in outcomes
        for event in (
            (
                outcome.entry_time_ms,
                1,
                priority[outcome.candidate],
                outcome.outcome_id,
                outcome,
            ),
            (
                outcome.exit_time_ms,
                0,
                priority[outcome.candidate],
                outcome.outcome_id,
                outcome,
            ),
        )
    ]
    return sorted(events, key=lambda item: item[:4])


def _enter(
    state: _State,
    outcome: ApexAttributedOutcome,
    config: ApexCohortPortfolioConfig,
) -> None:
    if outcome.symbol in state.active_by_symbol:
        _reject(state, outcome, "symbol_occupied")
        return
    reserved = _reserved_margin(state)
    cap = state.equity * config.maximum_reserved_margin_fraction
    if reserved + outcome.requested_margin_usd > cap + 1e-9:
        _reject(state, outcome, "aggregate_margin_cap")
        return
    available = state.equity - reserved
    required = outcome.requested_margin_usd + outcome.entry_fee_usd
    if required > available + 1e-9:
        _reject(state, outcome, "insufficient_shared_capital")
        return
    state.equity -= outcome.entry_fee_usd
    state.total_entry_fees += outcome.entry_fee_usd
    state.active_by_symbol[outcome.symbol] = _OpenOutcome(outcome)
    state.active_ids.add(outcome.outcome_id)
    state.maximum_concurrent = max(
        state.maximum_concurrent,
        len(state.active_by_symbol),
    )
    state.peak_reserved_margin = max(
        state.peak_reserved_margin,
        reserved + outcome.requested_margin_usd,
    )
    _update_drawdown(state)


def _exit(state: _State, outcome: ApexAttributedOutcome) -> None:
    if outcome.outcome_id not in state.active_ids:
        return
    opened = state.active_by_symbol.pop(outcome.symbol, None)
    if opened is None or opened.outcome.outcome_id != outcome.outcome_id:
        raise RuntimeError(f"shared outcome identity mismatch: {outcome.outcome_id}")
    state.active_ids.remove(outcome.outcome_id)
    state.equity += outcome.net_pnl_usd + outcome.entry_fee_usd
    state.peak_equity = max(state.peak_equity, state.equity)
    state.strategy_pnl[outcome.candidate] = (
        state.strategy_pnl.get(outcome.candidate, 0.0) + outcome.net_pnl_usd
    )
    state.strategy_fees[outcome.candidate] = (
        state.strategy_fees.get(outcome.candidate, 0.0) + outcome.entry_fee_usd
    )
    state.accepted.append(
        ApexAcceptedOutcome(
            outcome.outcome_id,
            outcome.candidate,
            outcome.symbol,
            outcome.requested_margin_usd,
            outcome.entry_fee_usd,
            outcome.net_pnl_usd,
            state.equity,
        )
    )
    _update_drawdown(state)


def _reject(state: _State, outcome: ApexAttributedOutcome, reason: str) -> None:
    state.rejected.append(
        ApexRejectedOutcome(
            outcome.outcome_id,
            outcome.candidate,
            outcome.symbol,
            outcome.entry_time_ms,
            reason,
        )
    )


def _reserved_margin(state: _State) -> float:
    return sum(
        opened.outcome.requested_margin_usd
        for opened in state.active_by_symbol.values()
    )


def _report(
    state: _State,
    config: ApexCohortPortfolioConfig,
) -> ApexCohortPortfolioReport:
    net = state.equity - config.initial_equity_usd
    if not math.isclose(net, sum(state.strategy_pnl.values()), abs_tol=1e-8):
        raise RuntimeError("strategy attribution does not reconcile to shared equity")
    return ApexCohortPortfolioReport(
        config.initial_equity_usd,
        state.equity,
        net,
        state.maximum_drawdown_pct,
        state.total_entry_fees,
        state.maximum_concurrent,
        state.peak_reserved_margin,
        dict(state.strategy_pnl),
        dict(state.strategy_fees),
        tuple(state.accepted),
        tuple(state.rejected),
    )


def _update_drawdown(state: _State) -> None:
    drawdown = (state.equity / state.peak_equity - 1.0) * 100.0
    state.maximum_drawdown_pct = min(state.maximum_drawdown_pct, drawdown)


def _validate_unique(outcomes: tuple[ApexAttributedOutcome, ...]) -> None:
    identities = [outcome.outcome_id for outcome in outcomes]
    if len(identities) != len(set(identities)):
        raise ValueError("Apex shared outcome IDs must be unique")


def _finite(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be finite")


def _positive(value: float, label: str) -> None:
    _finite(value, label)
    if value <= 0.0:
        raise ValueError(f"{label} must be positive")


def _nonnegative(value: float, label: str) -> None:
    _finite(value, label)
    if value < 0.0:
        raise ValueError(f"{label} must be non-negative")
