"""Causal Hulk Smash tuning models, evaluation, and stability ranking."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math

import pandas as pd

from hypervector.research.hulk_smash_candidates import (
    select_hulk_expansion_moderate_adx,
)
from hypervector.research.hulk_smash_quality import build_hulk_quality_frame
from hypervector.research.hulk_smash_rebuilt_signals import (
    RebuiltHulkConfig,
    evaluate_rebuilt_hulk_signals,
)
from hypervector.research.market_cipher_replay import evaluate_market_cipher_replay
from hypervector.research.market_cipher_replay_models import (
    MarketCipherReplayConfig,
    MarketCipherReplayReport,
)


@dataclass(frozen=True)
class HulkTuneParameters:
    """One coherent, deterministic Hulk signal-parameter trial."""

    supertrend_period: int
    supertrend_multiplier: float
    adx_period: int
    squeeze_period: int
    minimum_score: int
    pivot_bars: int
    adx_usable: float
    adx_trending: float

    def __post_init__(self) -> None:
        """Reject malformed parameter identities before evaluation."""
        periods = (
            self.supertrend_period,
            self.adx_period,
            self.squeeze_period,
            self.minimum_score,
            self.pivot_bars,
        )
        if any(value < 2 for value in periods):
            raise ValueError("Hulk tuning periods and thresholds must be at least two")
        if self.supertrend_multiplier <= 0.0:
            raise ValueError("Hulk supertrend multiplier must be positive")
        if not 0.0 < self.adx_usable <= self.adx_trending:
            raise ValueError("Hulk tuning ADX thresholds are inconsistent")

    @property
    def trial_id(self) -> str:
        """Return a stable content-derived trial identifier."""
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return f"hulk-{sha256(payload.encode()).hexdigest()[:16]}"


@dataclass(frozen=True)
class HulkAutotuneResult:
    """One candidate's result in one chronological fold and scenario."""

    trial_id: str
    fold: str
    scenario: str
    signal_count: int
    completed_trades: int
    wins: int
    losses: int
    net_pnl_usd: float
    profit_factor: float | None
    maximum_drawdown_pct: float
    fees_usd: float
    funding_cashflow_usd: float
    liquidations: int
    rejections: int


@dataclass(frozen=True)
class HulkAutotuneSummary:
    """Complete-matrix stability summary used only to rank trials."""

    trial_id: str
    rank: int
    positive_cells: int
    total_cells: int
    worst_net_pnl_usd: float
    total_net_pnl_usd: float
    minimum_profit_factor: float | None
    maximum_drawdown_pct: float
    total_trades: int
    liquidations: int


@dataclass(frozen=True)
class HulkTuneFold:
    """One clean chronological development fold."""

    name: str
    start_utc: pd.Timestamp
    end_utc: pd.Timestamp

    def __post_init__(self) -> None:
        """Require a named, ordered, timezone-aware fold."""
        start, end = pd.Timestamp(self.start_utc), pd.Timestamp(self.end_utc)
        if not self.name.strip() or start.tz is None or end.tz is None or start >= end:
            raise ValueError("Hulk tuning fold must be named, aware, and ordered")


@dataclass(frozen=True)
class HulkTuneScenario:
    """One predeclared replay-friction scenario."""

    name: str
    replay_config: MarketCipherReplayConfig

    def __post_init__(self) -> None:
        """Require an explicit scenario identity."""
        if not self.name.strip():
            raise ValueError("Hulk tuning scenario name is required")


def build_hulk_tune_signal_matrix(
    bars_by_symbol: dict[str, pd.DataFrame],
    components_by_symbol: dict[str, pd.DataFrame],
    parameters: tuple[HulkTuneParameters, ...],
) -> dict[str, pd.DataFrame]:
    """Build causal short-side Hulk signals for every parameter identity."""
    _validate_signal_inputs(bars_by_symbol, components_by_symbol, parameters)
    quality_cache: dict[tuple[int, float, int, int, str], pd.DataFrame] = {}
    matrix: dict[str, pd.DataFrame] = {}
    for trial in parameters:
        parts = [
            _trial_symbol_signals(
                symbol,
                bars_by_symbol[symbol],
                components_by_symbol[symbol],
                trial,
                quality_cache,
            )
            for symbol in sorted(bars_by_symbol)
        ]
        matrix[trial.trial_id] = (
            pd.concat(parts, ignore_index=True)
            .sort_values(["signal_time_utc", "symbol", "candidate"])
            .reset_index(drop=True)
        )
    return matrix


def evaluate_hulk_autotune_results(
    *,
    bars_by_symbol: dict[str, pd.DataFrame],
    signals_by_trial: dict[str, pd.DataFrame],
    parameters: tuple[HulkTuneParameters, ...],
    folds: tuple[HulkTuneFold, ...],
    scenarios: tuple[HulkTuneScenario, ...],
) -> tuple[HulkAutotuneResult, ...]:
    """Evaluate and retain every candidate/fold/scenario replay cell."""
    identities = _parameter_identities(parameters)
    _validate_evaluation_surface(identities, signals_by_trial, folds, scenarios)
    results: list[HulkAutotuneResult] = []
    for trial_id in identities:
        results.extend(
            _evaluate_trial(
                trial_id, bars_by_symbol, signals_by_trial[trial_id], folds, scenarios
            )
        )
    return tuple(results)


def rank_hulk_autotune_trials(
    parameters: tuple[HulkTuneParameters, ...],
    results: tuple[HulkAutotuneResult, ...],
) -> tuple[HulkAutotuneSummary, ...]:
    """Rank every complete trial by cross-fold and execution stability."""
    identities = _parameter_identities(parameters)
    matrix = _result_matrix(identities, results)
    unordered = [_summarize(trial_id, cells) for trial_id, cells in matrix.items()]
    ranked = sorted(unordered, key=_summary_sort_key)
    return tuple(
        HulkAutotuneSummary(**{**asdict(summary), "rank": rank})
        for rank, summary in enumerate(ranked, start=1)
    )


def _parameter_identities(
    parameters: tuple[HulkTuneParameters, ...],
) -> tuple[str, ...]:
    identities = tuple(value.trial_id for value in parameters)
    if not identities or len(set(identities)) != len(identities):
        raise ValueError("Hulk tuning requires non-empty unique parameters")
    return identities


def _result_matrix(
    identities: tuple[str, ...],
    results: tuple[HulkAutotuneResult, ...],
) -> dict[str, list[HulkAutotuneResult]]:
    matrix = {identity: [] for identity in identities}
    seen: set[tuple[str, str, str]] = set()
    for result in results:
        key = (result.trial_id, result.fold, result.scenario)
        if result.trial_id not in matrix or key in seen:
            raise ValueError(f"invalid or duplicate Hulk tuning result: {key}")
        matrix[result.trial_id].append(result)
        seen.add(key)
    expected = _expected_cells(matrix)
    for identity, cells in matrix.items():
        observed = {(cell.fold, cell.scenario) for cell in cells}
        if not cells or observed != expected:
            raise ValueError(f"Hulk trial {identity} has missing results")
    return matrix


def _expected_cells(
    matrix: dict[str, list[HulkAutotuneResult]],
) -> set[tuple[str, str]]:
    for cells in matrix.values():
        if cells:
            return {(cell.fold, cell.scenario) for cell in cells}
    raise ValueError("Hulk tuning has missing results for every trial")


def _summarize(trial_id: str, cells: list[HulkAutotuneResult]) -> HulkAutotuneSummary:
    finite_factors = [
        cell.profit_factor
        for cell in cells
        if cell.profit_factor is not None and math.isfinite(cell.profit_factor)
    ]
    return HulkAutotuneSummary(
        trial_id=trial_id,
        rank=0,
        positive_cells=sum(cell.net_pnl_usd > 0.0 for cell in cells),
        total_cells=len(cells),
        worst_net_pnl_usd=min(cell.net_pnl_usd for cell in cells),
        total_net_pnl_usd=sum(cell.net_pnl_usd for cell in cells),
        minimum_profit_factor=min(finite_factors) if finite_factors else None,
        maximum_drawdown_pct=max(cell.maximum_drawdown_pct for cell in cells),
        total_trades=sum(cell.completed_trades for cell in cells),
        liquidations=sum(cell.liquidations for cell in cells),
    )


def _summary_sort_key(summary: HulkAutotuneSummary) -> tuple[object, ...]:
    factor = summary.minimum_profit_factor
    factor_rank = factor if factor is not None else math.inf
    return (
        -summary.positive_cells,
        -summary.worst_net_pnl_usd,
        -summary.total_net_pnl_usd,
        -factor_rank,
        summary.maximum_drawdown_pct,
        summary.trial_id,
    )


def _validate_signal_inputs(
    bars: dict[str, pd.DataFrame],
    components: dict[str, pd.DataFrame],
    parameters: tuple[HulkTuneParameters, ...],
) -> None:
    _parameter_identities(parameters)
    if not bars or set(bars) != set(components):
        raise ValueError("Hulk tuning bars and components must cover equal symbols")
    for symbol in bars:
        if not bars[symbol].index.equals(components[symbol].index):
            raise ValueError(f"Hulk tuning inputs are misaligned for {symbol}")


def _trial_symbol_signals(
    symbol: str,
    bars: pd.DataFrame,
    components: pd.DataFrame,
    trial: HulkTuneParameters,
    cache: dict[tuple[int, float, int, int, str], pd.DataFrame],
) -> pd.DataFrame:
    key = (
        trial.supertrend_period,
        trial.supertrend_multiplier,
        trial.adx_period,
        trial.squeeze_period,
        symbol,
    )
    if key not in cache:
        cache[key] = build_hulk_quality_frame(
            bars,
            supertrend_period=trial.supertrend_period,
            supertrend_multiplier=trial.supertrend_multiplier,
            adx_period=trial.adx_period,
            squeeze_period=trial.squeeze_period,
        )
    config = RebuiltHulkConfig(
        minimum_score=trial.minimum_score,
        pivot_bars=trial.pivot_bars,
        adx_usable=trial.adx_usable,
        adx_trending=trial.adx_trending,
    )
    signals = select_hulk_expansion_moderate_adx(
        evaluate_rebuilt_hulk_signals(bars, components, cache[key], config)
    )
    selected = signals.loc[signals["side"].eq("short")].copy()
    selected["candidate"] = trial.trial_id
    selected["symbol"] = symbol
    return selected


def _validate_evaluation_surface(
    identities: tuple[str, ...],
    signals: dict[str, pd.DataFrame],
    folds: tuple[HulkTuneFold, ...],
    scenarios: tuple[HulkTuneScenario, ...],
) -> None:
    if set(identities) != set(signals):
        raise ValueError("Hulk tuning signal matrix differs from parameter surface")
    fold_names = [fold.name for fold in folds]
    scenario_names = [scenario.name for scenario in scenarios]
    if not folds or len(set(fold_names)) != len(fold_names):
        raise ValueError("Hulk tuning folds must be non-empty and unique")
    if not scenarios or len(set(scenario_names)) != len(scenario_names):
        raise ValueError("Hulk tuning scenarios must be non-empty and unique")


def _evaluate_trial(
    trial_id: str,
    bars: dict[str, pd.DataFrame],
    signals: pd.DataFrame,
    folds: tuple[HulkTuneFold, ...],
    scenarios: tuple[HulkTuneScenario, ...],
) -> list[HulkAutotuneResult]:
    cells: list[HulkAutotuneResult] = []
    for fold in folds:
        fold_bars = _fold_bars(bars, fold)
        fold_signals = _fold_signals(signals, fold)
        for scenario in scenarios:
            report = evaluate_market_cipher_replay(
                fold_bars, fold_signals, scenario.replay_config
            )
            cells.append(
                _autotune_result(trial_id, fold, scenario, len(fold_signals), report)
            )
    return cells


def _fold_bars(
    bars: dict[str, pd.DataFrame], fold: HulkTuneFold
) -> dict[str, pd.DataFrame]:
    result = {
        symbol: frame.loc[
            (frame.index >= fold.start_utc) & (frame.index < fold.end_utc)
        ].copy()
        for symbol, frame in bars.items()
    }
    if any(frame.empty for frame in result.values()):
        raise ValueError(f"Hulk tuning fold {fold.name} has empty symbol bars")
    return result


def _fold_signals(signals: pd.DataFrame, fold: HulkTuneFold) -> pd.DataFrame:
    times = pd.to_datetime(signals["signal_time_utc"], utc=True)
    return signals.loc[times.ge(fold.start_utc) & times.lt(fold.end_utc)].copy()


def _autotune_result(
    trial_id: str,
    fold: HulkTuneFold,
    scenario: HulkTuneScenario,
    signal_count: int,
    report: MarketCipherReplayReport,
) -> HulkAutotuneResult:
    return HulkAutotuneResult(
        trial_id=trial_id,
        fold=fold.name,
        scenario=scenario.name,
        signal_count=signal_count,
        completed_trades=report.completed_trades,
        wins=report.wins,
        losses=report.losses,
        net_pnl_usd=report.net_pnl_usd,
        profit_factor=report.profit_factor,
        maximum_drawdown_pct=report.maximum_drawdown_pct,
        fees_usd=report.total_fees_usd,
        funding_cashflow_usd=report.funding_cashflow_usd,
        liquidations=report.liquidations,
        rejections=len(report.rejections),
    )
