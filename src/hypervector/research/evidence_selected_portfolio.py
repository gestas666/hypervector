"""Priority-aware shared-account replay for evidence-selected portfolios."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math

from hypervector.research.current_cohort_shared_portfolio import CohortOutcome


@dataclass(frozen=True)
class PrioritizedPortfolioConfig:
    """Fixed account, slot ceiling, and provider conflict priority."""

    initial_equity_usd: float
    maximum_positions: int
    strategy_priority: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject ambiguous or impossible shared-account contracts."""
        _positive(self.initial_equity_usd, "initial_equity_usd")
        if isinstance(self.maximum_positions, bool) or self.maximum_positions < 1:
            raise ValueError("maximum_positions must be a positive integer")
        if not self.strategy_priority or any(
            not value.strip() for value in self.strategy_priority
        ):
            raise ValueError("strategy priority identities must be non-empty")
        if len(self.strategy_priority) != len(set(self.strategy_priority)):
            raise ValueError("strategy priority identities must be unique")


@dataclass(frozen=True)
class AcceptedPortfolioOutcome:
    """One lifecycle accepted by shared ownership and capacity arbitration."""

    trade_id: str
    strategy_id: str
    symbol: str
    side: str
    entry_time_ms: int
    exit_time_ms: int
    scaling_base_usd: float
    margin_reserved_usd: float
    entry_fee_usd: float
    net_pnl_usd: float
    equity_after_usd: float
    outcome: str


@dataclass(frozen=True)
class RejectedPortfolioOutcome:
    """One unexecuted lifecycle retained with its exact rejection reason."""

    trade_id: str
    strategy_id: str
    symbol: str
    side: str
    entry_time_ms: int
    reason: str


@dataclass(frozen=True)
class PrioritizedPortfolioReport:
    """Reconciled shared-account outcomes and attribution."""

    initial_equity_usd: float
    final_equity_usd: float
    net_pnl_usd: float
    return_pct: float
    maximum_drawdown_pct: float
    completed_trades: int
    wins: int
    losses: int
    breakeven: int
    profit_factor: float | None
    maximum_concurrent_positions: int
    peak_reserved_margin_usd: float
    accepted: tuple[AcceptedPortfolioOutcome, ...]
    rejected: tuple[RejectedPortfolioOutcome, ...]
    by_strategy: dict[str, dict[str, float | int | None]]
    by_strategy_side: dict[str, dict[str, float | int | None]]
    execution_authority: str = "none"
    report_only: bool = True

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe report representation."""
        return asdict(self)


@dataclass
class _OpenOutcome:
    source: CohortOutcome
    scaling_base: float
    margin: float
    entry_fee: float


@dataclass
class _ReplayState:
    equity: float
    peak_equity: float
    maximum_drawdown: float = 0.0
    maximum_concurrent: int = 0
    peak_reserved_margin: float = 0.0
    open_by_symbol: dict[str, _OpenOutcome] = field(default_factory=dict)
    open_ids: set[str] = field(default_factory=set)
    accepted: list[AcceptedPortfolioOutcome] = field(default_factory=list)
    rejected: list[RejectedPortfolioOutcome] = field(default_factory=list)


def replay_prioritized_outcomes(
    outcomes: tuple[CohortOutcome, ...],
    config: PrioritizedPortfolioConfig,
) -> PrioritizedPortfolioReport:
    """Replay completed route outcomes through one priority-aware account."""
    _validate_outcomes(outcomes, config)
    state = _ReplayState(config.initial_equity_usd, config.initial_equity_usd)
    for _time, action, _priority, _identity, outcome in _events(outcomes, config):
        if action == 0:
            _exit(state, outcome)
        else:
            _enter(state, outcome, config)
    if state.open_ids:
        raise RuntimeError("priority replay ended with active outcomes")
    return _build_report(state, config)


def _events(
    outcomes: tuple[CohortOutcome, ...],
    config: PrioritizedPortfolioConfig,
) -> list[tuple[int, int, int, str, CohortOutcome]]:
    priorities = {
        strategy: index for index, strategy in enumerate(config.strategy_priority)
    }
    events = [
        event
        for row in outcomes
        for event in (
            (
                row.outcome.entry_time_ms,
                1,
                priorities[row.strategy_id],
                row.trade_id,
                row,
            ),
            (
                row.outcome.exit_time_ms,
                0,
                priorities[row.strategy_id],
                row.trade_id,
                row,
            ),
        )
    ]
    return sorted(events, key=lambda value: value[:4])


def _enter(
    state: _ReplayState,
    row: CohortOutcome,
    config: PrioritizedPortfolioConfig,
) -> None:
    source = row.outcome
    if source.symbol in state.open_by_symbol:
        _reject(state, row, "symbol_occupied")
        return
    if len(state.open_by_symbol) >= config.maximum_positions:
        _reject(state, row, "maximum_positions")
        return
    base = min(state.equity, source.source_equity_usd)
    scale = base / source.source_equity_usd
    entry_fee = source.entry_fee_usd * scale
    margin = source.margin_fraction * base
    if _reserved_margin(state) + margin + entry_fee > state.equity + 1e-9:
        _reject(state, row, "insufficient_shared_capital")
        return
    state.equity -= entry_fee
    state.open_by_symbol[source.symbol] = _OpenOutcome(row, base, margin, entry_fee)
    state.open_ids.add(source.trade_id)
    state.maximum_concurrent = max(state.maximum_concurrent, len(state.open_ids))
    state.peak_reserved_margin = max(
        state.peak_reserved_margin,
        _reserved_margin(state),
    )
    _update_drawdown(state)


def _exit(state: _ReplayState, row: CohortOutcome) -> None:
    source = row.outcome
    if source.trade_id not in state.open_ids:
        return
    opened = state.open_by_symbol.pop(source.symbol, None)
    if opened is None or opened.source.trade_id != source.trade_id:
        raise RuntimeError(f"priority replay identity mismatch: {source.trade_id}")
    state.open_ids.remove(source.trade_id)
    scale = opened.scaling_base / source.source_equity_usd
    scaled_net = source.net_pnl_usd * scale
    state.equity += (source.net_pnl_usd + source.entry_fee_usd) * scale
    state.peak_equity = max(state.peak_equity, state.equity)
    state.accepted.append(_accepted(row, opened, scaled_net, state.equity))
    _update_drawdown(state)


def _accepted(
    row: CohortOutcome,
    opened: _OpenOutcome,
    scaled_net: float,
    equity_after: float,
) -> AcceptedPortfolioOutcome:
    source = row.outcome
    return AcceptedPortfolioOutcome(
        source.trade_id,
        row.strategy_id,
        source.symbol,
        row.side,
        source.entry_time_ms,
        source.exit_time_ms,
        opened.scaling_base,
        opened.margin,
        opened.entry_fee,
        scaled_net,
        equity_after,
        source.outcome,
    )


def _reject(state: _ReplayState, row: CohortOutcome, reason: str) -> None:
    source = row.outcome
    state.rejected.append(
        RejectedPortfolioOutcome(
            source.trade_id,
            row.strategy_id,
            source.symbol,
            row.side,
            source.entry_time_ms,
            reason,
        )
    )


def _build_report(
    state: _ReplayState,
    config: PrioritizedPortfolioConfig,
) -> PrioritizedPortfolioReport:
    values = [row.net_pnl_usd for row in state.accepted]
    summary = _summary(values)
    net = state.equity - config.initial_equity_usd
    if not math.isclose(net, sum(values), abs_tol=1e-8):
        raise RuntimeError("priority replay PnL does not reconcile to shared equity")
    return PrioritizedPortfolioReport(
        config.initial_equity_usd,
        state.equity,
        net,
        net / config.initial_equity_usd * 100.0,
        state.maximum_drawdown,
        summary["trades"],
        summary["wins"],
        summary["losses"],
        summary["breakeven"],
        summary["profit_factor"],
        state.maximum_concurrent,
        state.peak_reserved_margin,
        tuple(state.accepted),
        tuple(state.rejected),
        _attribution(state.accepted, by_side=False),
        _attribution(state.accepted, by_side=True),
    )


def _attribution(
    rows: list[AcceptedPortfolioOutcome],
    *,
    by_side: bool,
) -> dict[str, dict[str, float | int | None]]:
    groups: dict[str, list[float]] = {}
    for row in rows:
        key = f"{row.strategy_id}|{row.side}" if by_side else row.strategy_id
        groups.setdefault(key, []).append(row.net_pnl_usd)
    return {key: _summary(values) for key, values in sorted(groups.items())}


def _summary(values: list[float]) -> dict[str, float | int | None]:
    profits = [value for value in values if value > 0.0]
    losses = [-value for value in values if value < 0.0]
    gross_profit = sum(profits)
    gross_loss = sum(losses)
    return {
        "trades": len(values),
        "wins": len(profits),
        "losses": len(losses),
        "breakeven": len(values) - len(profits) - len(losses),
        "net_pnl_usd": sum(values),
        "gross_profit_usd": gross_profit,
        "gross_loss_usd": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
    }


def _validate_outcomes(
    outcomes: tuple[CohortOutcome, ...],
    config: PrioritizedPortfolioConfig,
) -> None:
    identities = [row.trade_id for row in outcomes]
    if not outcomes:
        raise ValueError("priority replay requires at least one outcome")
    if len(identities) != len(set(identities)):
        raise ValueError("priority replay trade identities must be unique")
    missing = sorted(
        {row.strategy_id for row in outcomes} - set(config.strategy_priority)
    )
    if missing:
        raise ValueError(f"strategy priority must cover outcomes: {missing}")
    if any(row.side not in {"long", "short"} for row in outcomes):
        raise ValueError("priority replay sides must be long or short")


def _reserved_margin(state: _ReplayState) -> float:
    return sum(row.margin for row in state.open_by_symbol.values())


def _update_drawdown(state: _ReplayState) -> None:
    drawdown = (state.peak_equity - state.equity) / state.peak_equity * 100.0
    state.maximum_drawdown = max(state.maximum_drawdown, drawdown)


def _positive(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(float(value)) or value <= 0.0:
        raise ValueError(f"{label} must be positive and finite")
