"""Development-only fixed-target challengers for cash-open long entries."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math

import pandas as pd

from hypervector.research.hip3_archive_inputs import (
    signal_source_bars,
    validate_archive_bar_timing,
    validate_archive_bars,
    validate_archive_windows,
)
from hypervector.research.hip3_cash_open_gap_reversal_candidate import (
    hip3_cash_open_gap_reversal_portfolio_config,
)
from hypervector.research.hip3_cash_open_gap_reversal_signals import (
    Hip3CashOpenGapReversalConfig,
    build_hip3_cash_open_gap_reversal_signals,
)
from hypervector.research.hip3_development_partitions import (
    evaluate_hip3_development_partitions,
)
from hypervector.research.mu_hip3_archive_candidate import MuArchiveExecution
from hypervector.research.mu_hip3_candidate import (
    MuChronologicalWindows,
    MuPartitionResult,
    summarize_trades,
)
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioConfig,
    SharedPortfolioReport,
)


@dataclass(frozen=True)
class CashOpenLongExitScenario:
    """One long-only control or fixed-target development scenario."""

    name: str
    target_bps: float | None
    development: MuPartitionResult
    folds: tuple[MuPartitionResult, ...]


@dataclass(frozen=True)
class CashOpenLongExitChallengerResult:
    """Preregistered control and target family with no live authority."""

    symbol: str
    windows: MuChronologicalWindows
    control: CashOpenLongExitScenario
    challengers: tuple[CashOpenLongExitScenario, ...]
    selected_target_bps: float
    challenger_improves_control: bool
    validation_accessed: bool = False
    holdout_accessed: bool = False
    execution_authority: str = "none"
    automatic_promotion: bool = False


def evaluate_cash_open_long_exit_challengers(
    bars: pd.DataFrame,
    execution: MuArchiveExecution,
    *,
    windows: MuChronologicalWindows,
    target_bps: tuple[float, ...],
    signal: Hip3CashOpenGapReversalConfig = Hip3CashOpenGapReversalConfig(),
) -> CashOpenLongExitChallengerResult:
    """Compare entry-anchored long targets without reading OOS economics."""
    _validate_targets(target_bps)
    validate_archive_bars(bars)
    validate_archive_bar_timing(bars, "15m")
    validate_archive_windows(bars, windows, "15m")
    causal = bars.loc[bars.index < windows.development_end_utc].copy()
    signals = build_hip3_cash_open_gap_reversal_signals(
        signal_source_bars(causal), signal
    )
    long_only = _long_only(signals)
    control = _evaluate_scenario(causal, long_only, execution, signal, windows, None)
    challengers = tuple(
        _evaluate_scenario(causal, long_only, execution, signal, windows, value)
        for value in target_bps
    )
    _require_entry_parity(control, challengers)
    selected = max(challengers, key=_scenario_key)
    return CashOpenLongExitChallengerResult(
        execution.symbol,
        windows,
        control,
        challengers,
        float(selected.target_bps),
        _scenario_key(selected) > _scenario_key(control),
    )


def _evaluate_scenario(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    execution: MuArchiveExecution,
    signal: Hip3CashOpenGapReversalConfig,
    windows: MuChronologicalWindows,
    target_bps: float | None,
) -> CashOpenLongExitScenario:
    scenario_signals = signals.copy()
    if target_bps is not None:
        scenario_signals.loc[scenario_signals["long_entry"], "target_price"] = None
    development, folds = evaluate_hip3_development_partitions(
        bars,
        scenario_signals,
        windows,
        lambda stress: _portfolio_config(
            execution, signal, stress=stress, target_bps=target_bps
        ),
    )
    name = (
        "prior_cash_close_control"
        if target_bps is None
        else f"target_{target_bps:g}bps"
    )
    return CashOpenLongExitScenario(name, target_bps, development, folds)


def _portfolio_config(
    execution: MuArchiveExecution,
    signal: Hip3CashOpenGapReversalConfig,
    *,
    stress: bool,
    target_bps: float | None,
) -> SharedPortfolioConfig:
    base = hip3_cash_open_gap_reversal_portfolio_config(
        execution, signal, stress=stress
    )
    target_margin_pct = (
        None if target_bps is None else target_bps * base.leverage / 100.0
    )
    return replace(base, target_margin_pct=target_margin_pct)


def _long_only(signals: pd.DataFrame) -> pd.DataFrame:
    output = signals.copy()
    output["short_entry"] = False
    return output


def _scenario_key(scenario: CashOpenLongExitScenario) -> tuple[float, ...]:
    stress = scenario.development.stress
    diagnostics = summarize_trades(stress.trades)["all"]
    fold_net = [fold.stress.net_pnl_usd for fold in scenario.folds]
    return (
        float(sum(value > 0.0 for value in fold_net)),
        min(fold_net),
        diagnostics.net_without_largest_winner_usd,
        stress.net_pnl_usd,
        -abs(stress.maximum_drawdown_pct),
    )


def _require_entry_parity(
    control: CashOpenLongExitScenario,
    challengers: tuple[CashOpenLongExitScenario, ...],
) -> None:
    expected = _entry_identities(control.development.nominal)
    for scenario in challengers:
        if _entry_identities(scenario.development.nominal) != expected:
            raise RuntimeError("cash-open target scenario entry identities diverged")
        if _entry_identities(scenario.development.stress) != expected:
            raise RuntimeError("cash-open target stress entry identities diverged")


def _entry_identities(
    report: SharedPortfolioReport,
) -> tuple[tuple[str, str], ...]:
    return tuple(
        (trade.signal_time_utc, trade.entry_time_utc) for trade in report.trades
    )


def _validate_targets(target_bps: tuple[float, ...]) -> None:
    values = tuple(float(value) for value in target_bps)
    valid = values and len(values) == len(set(values))
    valid = valid and all(math.isfinite(value) and value > 0.0 for value in values)
    if not valid:
        raise ValueError("cash-open target bps must be unique positive values")
