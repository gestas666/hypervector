"""Preregistered statistics for BTC liquidation development economics."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, cast

import numpy as np
import pandas as pd

from hypervector.research.btc_liquidation_covariate_models import (
    BurstArm,
    CandidateBranch,
    PurgeCandidate,
)
from hypervector.research.btc_liquidation_covariate_replay import (
    purge_overlapping_entries,
)

_BASIS_POINTS = Decimal("10000")
_BRANCHES = frozenset({"continuation_long", "exhaustion_reclaim_long"})
_ARMS = frozenset({"5s_p95", "5s_p99", "15s_p95", "15s_p99"})
_HORIZONS = frozenset({30_000, 120_000, 300_000, 900_000})
_DAY_MS = 86_400_000


@dataclass(frozen=True)
class OutcomeEconomics:
    """One stored horizon status and its exact after-cost economics."""

    horizon_ms: int
    status: str
    reason: str | None
    nominal_net_pnl_usd: Decimal | None
    stressed_net_pnl_usd: Decimal | None


@dataclass(frozen=True)
class DevelopmentArmEconomics:
    """One unique development episode-arm result."""

    episode_id: str
    partition: str
    branch: CandidateBranch
    arm: BurstArm
    entry_status: str
    decision_time_ms: int
    entry_time_ms: int | None
    entry_quote_notional_usd: Decimal | None
    regime: str
    outcomes: tuple[OutcomeEconomics, ...]


@dataclass(frozen=True)
class PurgedArmGroup:
    """Retained and overlap-suppressed eligible episode-arm results."""

    retained: tuple[DevelopmentArmEconomics, ...]
    suppressed: tuple[DevelopmentArmEconomics, ...]


@dataclass(frozen=True)
class EconomicObservation:
    """One retained resolved after-cost observation."""

    episode_id: str
    branch: CandidateBranch
    arm: BurstArm
    decision_time_ms: int
    regime: str
    nominal_return_bps: Decimal
    stressed_return_bps: Decimal
    nominal_net_pnl_usd: Decimal


@dataclass(frozen=True)
class BootstrapEstimate:
    """Stationary UTC-day block-bootstrap estimate and null test."""

    point_estimate: float
    lower: float
    upper: float
    one_sided_p_value: float
    resamples: int
    expected_block_days: int
    seed: int


def parse_development_arm_results(
    rows: tuple[Mapping[str, object], ...],
) -> tuple[DevelopmentArmEconomics, ...]:
    """Parse and validate unique development-only raw arm records."""
    parsed = tuple(_parse_arm_result(row) for row in rows)
    identities = tuple((row.episode_id, row.arm) for row in parsed)
    if not parsed or len(identities) != len(set(identities)):
        raise ValueError("development statistics require unique arm identities")
    if any(row.partition != "development" for row in parsed):
        raise ValueError("development statistics contain a sealed partition")
    return parsed


def purge_arm_group(
    rows: tuple[DevelopmentArmEconomics, ...],
    *,
    branch: CandidateBranch,
    arm: BurstArm,
    overlap_horizon_ms: int,
) -> PurgedArmGroup:
    """Apply the frozen overlap rule to one exact branch-arm group."""
    selected = tuple(
        row
        for row in rows
        if row.branch == branch and row.arm == arm and row.entry_status == "eligible"
    )
    if any(row.entry_time_ms is None for row in selected):
        raise ValueError("eligible development entry is missing execution time")
    candidates = tuple(
        PurgeCandidate(
            row.episode_id,
            row.partition,
            row.branch,
            row.arm,
            row.decision_time_ms,
            _required_integer(row.entry_time_ms, "entry time"),
        )
        for row in selected
    )
    purge = purge_overlapping_entries(candidates, overlap_horizon_ms=overlap_horizon_ms)
    by_id = {row.episode_id: row for row in selected}
    return PurgedArmGroup(
        tuple(by_id[row.episode_id] for row in purge.retained),
        tuple(by_id[row.episode_id] for row in purge.suppressed),
    )


def economic_observations(
    rows: tuple[DevelopmentArmEconomics, ...], *, horizon_ms: int
) -> tuple[EconomicObservation, ...]:
    """Return resolved retained outcomes with executable-return denominators."""
    if horizon_ms not in _HORIZONS:
        raise ValueError("development outcome horizon is not frozen")
    output: list[EconomicObservation] = []
    for row in rows:
        outcome = _one_horizon(row.outcomes, horizon_ms)
        if outcome.status != "resolved":
            continue
        quote = _required_decimal(row.entry_quote_notional_usd, "entry quote")
        nominal = _required_decimal(outcome.nominal_net_pnl_usd, "nominal PnL")
        stress = _required_decimal(outcome.stressed_net_pnl_usd, "stressed PnL")
        output.append(
            EconomicObservation(
                row.episode_id,
                row.branch,
                row.arm,
                row.decision_time_ms,
                row.regime,
                nominal / quote * _BASIS_POINTS,
                stress / quote * _BASIS_POINTS,
                nominal,
            )
        )
    return tuple(output)


def summarize_observations(
    rows: tuple[EconomicObservation, ...],
) -> dict[str, Decimal | int | None]:
    """Compute exact point metrics for retained resolved observations."""
    if not rows:
        return _empty_summary()
    nominal = tuple(row.nominal_return_bps for row in rows)
    stressed = tuple(row.stressed_return_bps for row in rows)
    pnl = tuple(row.nominal_net_pnl_usd for row in rows)
    positive = tuple(value for value in pnl if value > 0)
    negative = tuple(-value for value in pnl if value < 0)
    gross_positive = sum(positive, Decimal())
    gross_negative = sum(negative, Decimal())
    count = Decimal(len(rows))
    return {
        "count": len(rows),
        "mean_nominal_return_bps": sum(nominal, Decimal()) / count,
        "mean_stressed_return_bps": sum(stressed, Decimal()) / count,
        "total_nominal_net_pnl_usd": sum(pnl, Decimal()),
        "win_rate": Decimal(len(positive)) / count,
        "profit_factor": (
            None if gross_negative == 0 else gross_positive / gross_negative
        ),
        "largest_positive_pnl_contribution": (
            None if gross_positive == 0 else max(positive) / gross_positive
        ),
    }


def stationary_day_bootstrap(
    rows: tuple[EconomicObservation, ...],
    *,
    value: Literal["nominal_return_bps", "stressed_return_bps"],
    expected_block_days: int,
    resamples: int,
    seed: int,
) -> BootstrapEstimate:
    """Bootstrap ordered UTC-day aggregates with stationary circular blocks."""
    if not rows or expected_block_days < 1 or resamples < 1 or seed < 0:
        raise ValueError("stationary bootstrap inputs must be nonempty and positive")
    sums, counts = _daily_aggregates(rows, value)
    point = float(sums.sum() / counts.sum())
    rng = np.random.default_rng(seed)
    means = np.empty(resamples, dtype=float)
    null_means = np.empty(resamples, dtype=float)
    centered = sums - point * counts
    for index in range(resamples):
        sample = _stationary_indices(len(sums), expected_block_days, rng)
        denominator = counts[sample].sum()
        means[index] = sums[sample].sum() / denominator
        null_means[index] = centered[sample].sum() / denominator
    lower, upper = np.quantile(means, (0.025, 0.975))
    exceedances = int(np.count_nonzero(null_means >= point))
    return BootstrapEstimate(
        point,
        float(lower),
        float(upper),
        (exceedances + 1) / (resamples + 1),
        resamples,
        expected_block_days,
        seed,
    )


def holm_adjust(p_values: Mapping[str, float]) -> dict[str, float]:
    """Return monotone Holm family-wise adjusted p-values."""
    if not p_values or any(not 0.0 <= value <= 1.0 for value in p_values.values()):
        raise ValueError("Holm p-values must be nonempty and within [0, 1]")
    ordered = sorted(p_values.items(), key=lambda row: (row[1], row[0]))
    adjusted: dict[str, float] = {}
    prior = 0.0
    total = len(ordered)
    for rank, (name, value) in enumerate(ordered):
        current = min(1.0, (total - rank) * value)
        prior = max(prior, current)
        adjusted[name] = prior
    return {name: adjusted[name] for name in p_values}


def monthly_summaries(
    rows: tuple[EconomicObservation, ...],
) -> dict[str, dict[str, Decimal | int | None]]:
    """Summarize every observed UTC calendar month without selection."""
    grouped: dict[str, list[EconomicObservation]] = defaultdict(list)
    for row in rows:
        timestamp = pd.Timestamp(row.decision_time_ms, unit="ms", tz="UTC")
        grouped[timestamp.strftime("%Y-%m")].append(row)
    return {
        month: summarize_observations(tuple(values))
        for month, values in sorted(grouped.items())
    }


def regime_summaries(
    rows: tuple[EconomicObservation, ...],
) -> dict[str, dict[str, Decimal | int | None]]:
    """Summarize descriptive regime strata without granting selection authority."""
    grouped: dict[str, list[EconomicObservation]] = defaultdict(list)
    for row in rows:
        grouped[row.regime].append(row)
    return {
        regime: summarize_observations(tuple(values))
        for regime, values in sorted(grouped.items())
    }


def _parse_arm_result(row: Mapping[str, object]) -> DevelopmentArmEconomics:
    if row.get("schema_version") != "btc_liquidation_development_arm_result_v1":
        raise ValueError("development statistics raw schema is invalid")
    branch = cast(CandidateBranch, _choice(row.get("branch"), _BRANCHES, "branch"))
    arm = cast(BurstArm, _choice(row.get("arm"), _ARMS, "arm"))
    entry = _mapping(row.get("entry"), "entry")
    entry_status = _text(entry.get("status"), "entry status")
    if entry_status not in {"eligible", "signal_blocked", "technical_excluded"}:
        raise ValueError("development entry status is invalid")
    fill = entry.get("fill")
    quote = (
        None
        if fill is None
        else _decimal(_mapping(fill, "entry fill").get("quote_notional"), "entry quote")
    )
    return DevelopmentArmEconomics(
        _text(row.get("episode_id"), "episode identity"),
        _text(row.get("partition"), "partition"),
        branch,
        arm,
        entry_status,
        _integer(entry.get("decision_time_ms"), "decision time"),
        _optional_integer(entry.get("decision_book_time_ms"), "entry time"),
        quote,
        _text(_mapping(row.get("regime"), "regime").get("primary_regime"), "regime"),
        _parse_outcomes(row.get("outcomes")),
    )


def _parse_outcomes(value: object) -> tuple[OutcomeEconomics, ...]:
    rows = _sequence(value, "outcomes")
    output = tuple(_parse_outcome(_mapping(row, "outcome")) for row in rows)
    horizons = tuple(row.horizon_ms for row in output)
    if len(horizons) != len(set(horizons)) or any(
        horizon not in _HORIZONS for horizon in horizons
    ):
        raise ValueError("development outcome horizons are invalid")
    return output


def _parse_outcome(row: Mapping[str, object]) -> OutcomeEconomics:
    status = _text(row.get("status"), "outcome status")
    if status not in {"resolved", "technical_excluded"}:
        raise ValueError("development outcome status is invalid")
    reason = row.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise ValueError("development outcome reason must be text or null")
    return OutcomeEconomics(
        _integer(row.get("horizon_ms"), "outcome horizon"),
        status,
        reason,
        _optional_decimal(row.get("nominal_net_pnl_usd"), "nominal PnL"),
        _optional_decimal(row.get("stressed_net_pnl_usd"), "stressed PnL"),
    )


def _one_horizon(
    rows: tuple[OutcomeEconomics, ...], horizon_ms: int
) -> OutcomeEconomics:
    selected = tuple(row for row in rows if row.horizon_ms == horizon_ms)
    if len(selected) != 1:
        raise ValueError("retained entry lacks exactly one requested horizon")
    return selected[0]


def _daily_aggregates(
    rows: tuple[EconomicObservation, ...],
    value: Literal["nominal_return_bps", "stressed_return_bps"],
) -> tuple[np.ndarray, np.ndarray]:
    grouped: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        number = (
            row.nominal_return_bps
            if value == "nominal_return_bps"
            else row.stressed_return_bps
        )
        grouped[row.decision_time_ms // _DAY_MS].append(float(number))
    sums = np.array([sum(grouped[day]) for day in sorted(grouped)], dtype=float)
    counts = np.array([len(grouped[day]) for day in sorted(grouped)], dtype=float)
    return sums, counts


def _stationary_indices(
    count: int, expected_block_days: int, rng: np.random.Generator
) -> np.ndarray:
    selected = np.empty(count, dtype=int)
    selected[0] = int(rng.integers(count))
    restart_probability = 1.0 / expected_block_days
    for index in range(1, count):
        selected[index] = (
            int(rng.integers(count))
            if rng.random() < restart_probability
            else (selected[index - 1] + 1) % count
        )
    return selected


def _empty_summary() -> dict[str, Decimal | int | None]:
    return {
        "count": 0,
        "mean_nominal_return_bps": None,
        "mean_stressed_return_bps": None,
        "total_nominal_net_pnl_usd": None,
        "win_rate": None,
        "profit_factor": None,
        "largest_positive_pnl_contribution": None,
    }


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"development statistics {label} must be an object")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"development statistics {label} must be a sequence")
    return value


def _choice(value: object, choices: frozenset[str], label: str) -> str:
    text = _text(value, label)
    if text not in choices:
        raise ValueError(f"development statistics {label} is unsupported")
    return text


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"development statistics {label} must be nonempty text")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"development statistics {label} must be nonnegative integer")
    return value


def _optional_integer(value: object, label: str) -> int | None:
    return None if value is None else _integer(value, label)


def _required_integer(value: int | None, label: str) -> int:
    if value is None:
        raise ValueError(f"development statistics {label} is required")
    return value


def _decimal(value: object, label: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"development statistics {label} must be exact text")
    number = Decimal(value)
    if not number.is_finite():
        raise ValueError(f"development statistics {label} must be finite")
    return number


def _optional_decimal(value: object, label: str) -> Decimal | None:
    return None if value is None else _decimal(value, label)


def _required_decimal(value: Decimal | None, label: str) -> Decimal:
    if value is None or value <= 0 and label == "entry quote":
        raise ValueError(f"development statistics {label} is missing or invalid")
    return value
