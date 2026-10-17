"""Chronological, report-only tuning for the Hypervelocity regime detector."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from hypervector.regime import hypervelocity_eval as _eval
from hypervector.regime.classifier import RegimeClassifierConfig
from hypervector.regime.composite import classify_multitimeframe
from hypervector.regime.hypervelocity_eval import (
    BreakoutQualityReport,
    EntryAlignmentReport,
    RangeQualityReport,
    _datetime_bars,
    _unique_entry_decisions,
    evaluate_breakout_quality,
    evaluate_entry_alignment as evaluate_entry_alignment,
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
REGIME_BOARD_SCHEMA = "regime_tuning_board/v1"
_ENTRY_CLUSTER_SECONDS = 1.0
_LOOKBACK_MINUTES = (0, 1, 5, 10, 30)
_BAR_DURATION = pd.Timedelta(minutes=1)


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
    ema_fast, ema_slow = [(3, 8), (5, 13), (8, 21), (10, 30), (21, 55)][
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
        "bbwp_length": 20,
        "bbwp_lookback": int(rng.choice([120, 180, 240])),
        "bbwp_compression_threshold": float(rng.choice([15.0, 20.0, 25.0, 30.0])),
        "rsi_length": 14,
        "rsi_signal_length": 7,
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
    inactive = {"choppiness_length", "choppiness_range_threshold"}
    baseline = {
        key: value
        for key, value in asdict(faithful_regime_config()).items()
        if key not in inactive and isinstance(value, (int, float))
    }
    rng = np.random.default_rng(seed)
    return [baseline, *[_sample_parameters(rng) for _ in range(n_trials - 1)]]


def _split_positions(positions: pd.DataFrame, train_fraction: float) -> _SplitData:
    if not 0.0 < train_fraction < 1.0:
        raise ValueError("train_fraction must be between zero and one")
    unique = _unique_entry_decisions(positions, cluster_seconds=_ENTRY_CLUSTER_SECONDS)
    if len(unique) < 2:
        raise ValueError("at least two unique entry decisions are required")
    train_count = min(len(unique) - 1, max(1, int(len(unique) * train_fraction)))
    train = unique.iloc[:train_count].copy()
    holdout = unique.iloc[train_count:].copy()
    return _SplitData(train, holdout, pd.Timestamp(train["event_time"].iloc[-1]))


@dataclass(frozen=True)
class _SliceInputs:
    """Bars of one chronological slice and its parameter-independent extremes."""

    bars: pd.DataFrame
    future_high: pd.Series
    future_low: pd.Series


@dataclass(frozen=True)
class _SharedInputs:
    """Work that depends only on bars, entries and horizon: done once per run."""

    split_position: int
    train: _SliceInputs
    holdout: _SliceInputs
    train_entries: _eval._PreparedEntries
    holdout_entries: _eval._PreparedEntries


def _slice_inputs(bars: pd.DataFrame, horizon: int) -> _SliceInputs:
    # Computed per slice, so training windows never reach into holdout bars.
    return _SliceInputs(
        bars,
        _eval._future_extreme(bars["high"].astype(float), horizon, "max"),
        _eval._future_extreme(bars["low"].astype(float), horizon, "min"),
    )


def _shared_inputs(bars: pd.DataFrame, split: _SplitData, horizon: int) -> _SharedInputs:
    # bars has a unique increasing index (_datetime_bars), so the original
    # ``bars.index <= split_time`` mask is exactly this positional prefix.
    # Count the mask rather than ``searchsorted``: the latter refuses a split
    # time finer than the index unit (e.g. ns entries against us bars).
    position = int(np.count_nonzero(bars.index <= split.split_time))
    return _SharedInputs(
        position,
        _slice_inputs(bars.iloc[:position], horizon),
        _slice_inputs(bars.iloc[position:], horizon),
        _eval._prepare_entries(
            split.train_positions, cluster_seconds=_ENTRY_CLUSTER_SECONDS
        ),
        _eval._prepare_entries(
            split.holdout_positions, cluster_seconds=_ENTRY_CLUSTER_SECONDS
        ),
    )


def _quality_slice(
    inputs: _SliceInputs,
    decisions: pd.DataFrame,
    target: float,
    horizon: int,
) -> tuple[BreakoutQualityReport, RangeQualityReport]:
    breakout = evaluate_breakout_quality(
        inputs.bars,
        decisions,
        target_price_fraction=target,
        forward_horizon=horizon,
        future_high=inputs.future_high,
        future_low=inputs.future_low,
    )
    ranges = evaluate_range_quality(
        inputs.bars,
        decisions,
        target_price_fraction=target,
        forward_horizon=horizon,
        future_high=inputs.future_high,
        future_low=inputs.future_low,
    )
    return breakout, ranges


def _alignment(
    decisions: pd.DataFrame,
    prepared: _eval._PreparedDecisions | None,
    entries: _eval._PreparedEntries,
) -> EntryAlignmentReport:
    if prepared is not None:
        return _eval._entry_alignment_report(prepared, entries, _LOOKBACK_MINUTES)
    return _eval._loop_entry_alignment(
        decisions, entries, _LOOKBACK_MINUTES, _BAR_DURATION
    )


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
    shared: _SharedInputs,
    target: float,
    horizon: int,
) -> RegimeTuningTrial:
    config = RegimeClassifierConfig(**parameters)
    decisions = classify_multitimeframe(bars, config=config)
    # Directions and prefix counts are derived once and shared by both splits.
    prepared = _eval._prepare_decisions(decisions, _BAR_DURATION)
    train = _alignment(decisions, prepared, shared.train_entries)
    holdout = _alignment(decisions, prepared, shared.holdout_entries)
    states = decisions.loc[:, ["primary_regime", "breakout_direction"]]
    primary = decisions["primary_regime"].astype(str)
    split = shared.split_position
    if decisions.index.equals(bars.index):
        train_states, holdout_states = states.iloc[:split], states.iloc[split:]
        train_primary = primary.iloc[:split]
    else:  # keep the original label-aligned masks for any other index
        train_mask = pd.Series(
            np.arange(len(bars)) < split, index=bars.index, dtype=bool
        )
        train_states, holdout_states = states.loc[train_mask], states.loc[~train_mask]
        train_primary = primary.loc[train_mask]
    train_breakout, train_range = _quality_slice(
        shared.train, train_states, target, horizon
    )
    holdout_breakout, holdout_range = _quality_slice(
        shared.holdout, holdout_states, target, horizon
    )
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
    error: Exception,
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
    """Evaluate every candidate and select by chronological training metrics only.

    Any ``Exception`` raised for one candidate is recorded as that trial's
    technical failure and the remaining candidates are still evaluated.
    """
    indexed = _datetime_bars(bars)
    split = _split_positions(positions, train_fraction)
    shared: _SharedInputs | None = None
    shared_error: Exception | None = None
    try:
        shared = _shared_inputs(indexed, split, forward_horizon)
    except Exception as error:  # noqa: BLE001 - reported on every trial below
        shared_error = error
    trials: list[RegimeTuningTrial] = []
    for trial_id, parameters in enumerate(candidates):
        try:
            if shared is None:
                raise shared_error or RuntimeError("shared tuning inputs unavailable")
            trial = _completed_trial(
                trial_id,
                parameters,
                indexed,
                shared,
                target_price_fraction,
                forward_horizon,
            )
        except Exception as error:  # noqa: BLE001 - per-trial technical failure
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


def regime_tuning_document(
    board: RegimeTuningBoard,
    *,
    bars: pd.DataFrame,
    data_provenance: dict[str, object],
    seed: int,
    n_trials: int,
    train_fraction: float,
    forward_horizon: int,
    target_price_fraction: float = 0.002,
) -> dict[str, object]:
    """Wrap a tuning board with the provenance needed to reproduce it."""
    from hypervector.sweep.autotune_provenance import bars_window, code_identity

    return {
        "schema": REGIME_BOARD_SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "ok": True,
        "report_only": True,
        "seed": seed,
        "n_trials_requested": n_trials,
        "candidate_generator": "generate_candidate_parameters",
        "train_fraction": train_fraction,
        "forward_horizon": forward_horizon,
        "target_price_fraction": target_price_fraction,
        "data_provenance": data_provenance,
        "data_window": bars_window(bars),
        "code_identity": code_identity(),
        "tuning_board": board.to_dict(),
    }


def publish_regime_tuning_board(
    document: dict[str, object],
    directory: Path,
    *,
    name: str | None = None,
) -> Path:
    """Write a durable board with exclusive create; never overwrite evidence.

    Without ``name`` a UTC-stamped ``regime_autotune_*.json`` is used, with a
    numeric suffix on collision; an explicit ``name`` that exists raises
    ``FileExistsError``.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(document, indent=2, default=str) + "\n"
    if name is not None:
        target = directory / name
        with target.open("x", encoding="utf-8") as stream:
            stream.write(rendered)
        return target
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    for attempt in range(1000):
        suffix = "" if attempt == 0 else f"_{attempt}"
        target = directory / f"regime_autotune_{stamp}{suffix}.json"
        try:
            with target.open("x", encoding="utf-8") as stream:
                stream.write(rendered)
        except FileExistsError:
            continue
        return target
    raise FileExistsError(f"no unique regime board name available in {directory}")
