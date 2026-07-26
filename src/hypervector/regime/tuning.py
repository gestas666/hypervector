"""Chronological, report-only tuning for the Hypervelocity regime detector."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

import numpy as np
import pandas as pd

from hypervector.regime.classifier import RegimeClassifierConfig
from hypervector.regime.composite import classify_multitimeframe
from hypervector.regime.hypervelocity_eval import (
    BreakoutQualityReport,
    EntryAlignmentReport,
    RangeQualityReport,
    _datetime_bars,
    _unique_entry_decisions,
    evaluate_breakout_quality,
    evaluate_entry_alignment,
    evaluate_range_quality,
)
from hypervector.strategies.hypervelocity_contract import faithful_regime_config

CandidateValue = int | float
TrialStatus = Literal["completed", "technical_failure"]

MATCH_REWARD = 4.0
WRONG_DIRECTION_PENALTY = 3.0
NO_ENTRY_PENALTY = 1.0
QUALITY_PERCENT_PENALTY = 0.05
CHURN_PENALTY = 0.001


@dataclass(frozen=True)
class RegimeTuningTrial:
    """One candidate result, including failures and chronological holdout metrics."""

    trial_id: int
    status: TrialStatus
    parameters: dict[str, CandidateValue]
    train_alignment: EntryAlignmentReport | None
    holdout_alignment: EntryAlignmentReport | None
    train_breakout_quality: BreakoutQualityReport | None
    holdout_breakout_quality: BreakoutQualityReport | None
    train_range_quality: RangeQualityReport | None
    holdout_range_quality: RangeQualityReport | None
    state_distribution: dict[str, int]
    label_churn: int
    selection_score: float | None
    error: str | None


@dataclass(frozen=True)
class RegimeTuningBoard:
    """All trials and the candidate selected using training data only."""

    trials: tuple[RegimeTuningTrial, ...]
    selected_trial_id: int | None
    contract_candidate_trial_id: int | None
    selection_basis: str
    train_entry_decisions: int
    holdout_entry_decisions: int
    split_time_utc: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe tuning board."""
        return asdict(self)


@dataclass(frozen=True)
class _SplitData:
    train_positions: pd.DataFrame
    holdout_positions: pd.DataFrame
    split_time: pd.Timestamp


def _sample_parameters(rng: np.random.Generator) -> dict[str, CandidateValue]:
    ema_fast, ema_slow = [(3, 8), (5, 13), (8, 21), (10, 30), (20, 50)][
        int(rng.integers(0, 5))
    ]
    return {
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
        "warmup_bars": 60,
        "structure_lookback": int(rng.choice([120, 180, 240])),
        "trend_strength_percentile": float(rng.choice([50.0, 60.0, 70.0])),
        "range_strength_percentile": float(rng.choice([20.0, 30.0, 40.0])),
        "minimum_trend_gap_bps": float(rng.choice([0.5, 1.0, 2.0, 3.0, 5.0])),
        "choppiness_range_threshold": float(rng.choice([55.0, 65.0, 75.0, 85.0])),
        "coiling_width_bps": float(rng.choice([0.5, 1.0, 3.0, 5.0])),
        "breakout_lookback": int(rng.choice([30, 60, 90])),
        "breakout_clearance_bps": float(rng.choice([3.0, 5.0, 8.0])),
        "breakout_volume_multiple": float(rng.choice([1.5, 2.0, 2.5])),
    }


def generate_candidate_parameters(
    *,
    n_trials: int,
    seed: int,
) -> list[dict[str, CandidateValue]]:
    """Generate a deterministic search led by the current baseline."""
    if n_trials < 1:
        raise ValueError("n_trials must be positive")
    baseline = {
        key: value
        for key, value in asdict(faithful_regime_config()).items()
        if isinstance(value, (int, float))
    }
    rng = np.random.default_rng(seed)
    return [baseline, *[_sample_parameters(rng) for _ in range(n_trials - 1)]]


def _split_positions(positions: pd.DataFrame, train_fraction: float) -> _SplitData:
    if not 0.0 < train_fraction < 1.0:
        raise ValueError("train_fraction must be between zero and one")
    unique = _unique_entry_decisions(positions, cluster_seconds=1.0)
    if len(unique) < 2:
        raise ValueError("at least two unique entry decisions are required")
    train_count = min(len(unique) - 1, max(1, int(len(unique) * train_fraction)))
    train = unique.iloc[:train_count].copy()
    holdout = unique.iloc[train_count:].copy()
    return _SplitData(train, holdout, pd.Timestamp(train["event_time"].iloc[-1]))


def _quality_slice(
    bars: pd.DataFrame,
    decisions: pd.DataFrame,
    mask: pd.Series,
    target: float,
    horizon: int,
) -> tuple[BreakoutQualityReport, RangeQualityReport]:
    selected_bars = bars.loc[mask]
    selected_decisions = decisions.loc[mask]
    breakout = evaluate_breakout_quality(
        selected_bars,
        selected_decisions,
        target_price_fraction=target,
        forward_horizon=horizon,
    )
    ranges = evaluate_range_quality(
        selected_bars,
        selected_decisions,
        target_price_fraction=target,
        forward_horizon=horizon,
    )
    return breakout, ranges


def _selection_score(
    alignment: EntryAlignmentReport,
    breakout: BreakoutQualityReport,
    ranges: RangeQualityReport,
    churn: int,
) -> float:
    wrong = alignment.total_entries - alignment.direction_matches
    wrong -= alignment.no_entry_state_at_entries
    return (
        MATCH_REWARD * alignment.direction_matches
        - WRONG_DIRECTION_PENALTY * wrong
        - NO_ENTRY_PENALTY * alignment.no_entry_state_at_entries
        - QUALITY_PERCENT_PENALTY * breakout.false_breakout_pct
        - QUALITY_PERCENT_PENALTY * ranges.one_sided_expansion_pct
        - CHURN_PENALTY * churn
    )


def _completed_trial(
    trial_id: int,
    parameters: dict[str, CandidateValue],
    bars: pd.DataFrame,
    split: _SplitData,
    target: float,
    horizon: int,
) -> RegimeTuningTrial:
    config = RegimeClassifierConfig(**parameters)
    decisions = classify_multitimeframe(bars, config=config)
    train = evaluate_entry_alignment(decisions, split.train_positions)
    holdout = evaluate_entry_alignment(decisions, split.holdout_positions)
    train_mask = pd.Series(bars.index <= split.split_time, index=bars.index)
    holdout_mask = ~train_mask
    train_breakout, train_range = _quality_slice(
        bars, decisions, train_mask, target, horizon
    )
    holdout_breakout, holdout_range = _quality_slice(
        bars, decisions, holdout_mask, target, horizon
    )
    primary = decisions["primary_regime"].astype(str)
    train_primary = primary.loc[train_mask]
    churn = int(
        train_primary.ne(train_primary.shift()).sum() - int(len(train_primary) > 0)
    )
    return RegimeTuningTrial(
        trial_id,
        "completed",
        asdict(config),
        train,
        holdout,
        train_breakout,
        holdout_breakout,
        train_range,
        holdout_range,
        {str(key): int(value) for key, value in primary.value_counts().items()},
        churn,
        _selection_score(train, train_breakout, train_range, churn),
        None,
    )


def _failed_trial(
    trial_id: int,
    parameters: dict[str, CandidateValue],
    error: ValueError | TypeError | KeyError | IndexError,
) -> RegimeTuningTrial:
    return RegimeTuningTrial(
        trial_id,
        "technical_failure",
        parameters,
        None,
        None,
        None,
        None,
        None,
        None,
        {},
        0,
        None,
        f"{type(error).__name__}: {error}",
    )


def _contract_candidate(
    trials: list[RegimeTuningTrial],
) -> RegimeTuningTrial | None:
    eligible = [
        trial
        for trial in trials
        if trial.train_alignment is not None
        and trial.train_alignment.no_entry_state_at_entries == 0
        and trial.train_alignment.false_range_at_entries == 0
        and trial.train_breakout_quality is not None
        and trial.train_range_quality is not None
    ]
    if not eligible:
        return None
    return max(
        eligible,
        key=lambda trial: (
            trial.train_alignment.direction_matches,
            -trial.train_range_quality.one_sided_expansion_pct,
            -trial.train_breakout_quality.false_breakout_pct,
            -trial.label_churn,
        ),
    )


def autotune_regime_candidates(
    bars: pd.DataFrame,
    positions: pd.DataFrame,
    candidates: list[dict[str, CandidateValue]],
    *,
    train_fraction: float = 0.7,
    target_price_fraction: float = 0.002,
    forward_horizon: int = 30,
) -> RegimeTuningBoard:
    """Evaluate every candidate and select by chronological training metrics only."""
    indexed = _datetime_bars(bars)
    split = _split_positions(positions, train_fraction)
    trials: list[RegimeTuningTrial] = []
    for trial_id, parameters in enumerate(candidates):
        try:
            trial = _completed_trial(
                trial_id,
                parameters,
                indexed,
                split,
                target_price_fraction,
                forward_horizon,
            )
        except (ValueError, TypeError, KeyError, IndexError) as error:
            trial = _failed_trial(trial_id, parameters, error)
        trials.append(trial)
    completed = [trial for trial in trials if trial.selection_score is not None]
    selected = (
        max(completed, key=lambda trial: float(trial.selection_score))
        if completed
        else None
    )
    contract_candidate = _contract_candidate(trials)
    return RegimeTuningBoard(
        tuple(trials),
        selected.trial_id if selected else None,
        contract_candidate.trial_id if contract_candidate else None,
        "train_only",
        len(split.train_positions),
        len(split.holdout_positions),
        split.split_time.isoformat(),
    )
