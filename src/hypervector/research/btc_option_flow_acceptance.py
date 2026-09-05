"""Frozen acceptance gates for the BTC option-flow candidate."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import math

import numpy as np


_PARTITIONS = ("validation", "pseudo_holdout")
_SCENARIOS = ("nominal", "stress", "delayed")
_ARMS = (
    "candidate",
    "direction_inverted_placebo",
    "sweep_control",
    "no_action",
)


@dataclass(frozen=True)
class TradeBootstrapEstimate:
    """Deterministic percentile bootstrap for pooled OOS trade mean PnL."""

    point_mean_usd: float
    lower_90pct_usd: float
    upper_90pct_usd: float
    resamples: int
    seed: int

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible bootstrap record."""
        return asdict(self)


def trade_bootstrap_90pct(
    values: Sequence[float], *, resamples: int, seed: int
) -> TradeBootstrapEstimate:
    """Bootstrap the mean of complete candidate trade PnL observations."""
    sample = np.asarray(values, dtype=float)
    if sample.ndim != 1 or len(sample) < 1 or not np.isfinite(sample).all():
        raise ValueError("option-flow bootstrap values must be a finite vector")
    if resamples < 1 or seed < 0:
        raise ValueError("option-flow bootstrap resamples and seed must be positive")
    rng = np.random.default_rng(seed)
    means = np.empty(resamples, dtype=float)
    for offset in range(0, resamples, 1_000):
        count = min(1_000, resamples - offset)
        indices = rng.integers(0, len(sample), size=(count, len(sample)))
        means[offset : offset + count] = sample[indices].mean(axis=1)
    lower, upper = np.quantile(means, (0.05, 0.95))
    return TradeBootstrapEstimate(
        float(sample.mean()), float(lower), float(upper), resamples, seed
    )


def evaluate_frozen_option_flow_acceptance(
    summary_rows: Sequence[Mapping[str, object]],
    development_fold_rows: Sequence[Mapping[str, object]],
    *,
    pooled_oos_trade_net_pnl_usd: Sequence[float],
    bootstrap_resamples: int,
    bootstrap_seed: int,
) -> dict[str, object]:
    """Apply every preregistered standalone gate without granting live authority."""
    indexed = _validated_rows(summary_rows)
    folds = _validated_folds(development_fold_rows)
    failures: list[str] = []
    bootstrap = _optional_bootstrap(
        pooled_oos_trade_net_pnl_usd,
        bootstrap_resamples,
        bootstrap_seed,
        failures,
    )
    _check_development_folds(folds, failures)
    _check_oos_candidate(indexed, failures)
    _check_nominal_controls(indexed, failures)
    if bootstrap is not None and bootstrap.lower_90pct_usd <= 0.0:
        failures.append("pooled_oos_bootstrap_90pct_lower_positive")
    return {
        "candidate_supported_for_future_only_capture": not failures,
        "failed_checks": failures,
        "development_positive_folds": sum(value > 0.0 for value in folds.values()),
        "pooled_oos_trade_bootstrap": (
            bootstrap.to_dict() if bootstrap is not None else None
        ),
        "historical_pass_authority": "future_only_report_only_capture",
        "live_promotion_authorized": False,
        "retuning_authorized": False,
    }


def _optional_bootstrap(
    values: Sequence[float],
    resamples: int,
    seed: int,
    failures: list[str],
) -> TradeBootstrapEstimate | None:
    if len(values) > 0:
        return trade_bootstrap_90pct(values, resamples=resamples, seed=seed)
    if resamples < 1 or seed < 0:
        raise ValueError("option-flow bootstrap resamples and seed must be positive")
    failures.append("pooled_oos_bootstrap_requires_completed_trades")
    return None


def _validated_rows(
    rows: Sequence[Mapping[str, object]],
) -> dict[tuple[str, str, str], Mapping[str, object]]:
    indexed: dict[tuple[str, str, str], Mapping[str, object]] = {}
    for row in rows:
        key = (str(row.get("partition")), str(row.get("scenario")), str(row.get("arm")))
        if key in indexed:
            raise ValueError(f"duplicate option-flow acceptance row: {key}")
        indexed[key] = row
    required = {
        (partition, scenario, arm)
        for partition in _PARTITIONS
        for scenario in _SCENARIOS
        for arm in _ARMS
    }
    if set(indexed) != required:
        raise ValueError("option-flow acceptance rows are incomplete or unexpected")
    return indexed


def _validated_folds(
    rows: Sequence[Mapping[str, object]],
) -> dict[int, float]:
    output: dict[int, float] = {}
    for row in rows:
        fold = _integer(row.get("fold_id"), "development fold ID")
        net = _number(row.get("net_pnl_usd"), "development fold net PnL")
        if fold in output:
            raise ValueError("option-flow development fold rows are duplicated")
        output[fold] = net
    if set(output) != set(range(5)):
        raise ValueError(
            "option-flow development fold rows must cover IDs zero through four"
        )
    return output


def _check_development_folds(folds: Mapping[int, float], failures: list[str]) -> None:
    if sum(value > 0.0 for value in folds.values()) < 3:
        failures.append("development_minimum_three_positive_folds")


def _check_oos_candidate(
    indexed: Mapping[tuple[str, str, str], Mapping[str, object]],
    failures: list[str],
) -> None:
    for partition in _PARTITIONS:
        nominal = indexed[(partition, "nominal", "candidate")]
        if _integer(nominal.get("completed_trades"), "completed trades") < 10:
            failures.append(f"{partition}_minimum_ten_primary_trades")
        for scenario in _SCENARIOS:
            row = indexed[(partition, scenario, "candidate")]
            _check_candidate_cell(row, partition, scenario, failures)


def _check_candidate_cell(
    row: Mapping[str, object], partition: str, scenario: str, failures: list[str]
) -> None:
    prefix = f"{partition}_{scenario}"
    if _number(row.get("net_pnl_usd"), "net PnL") <= 0.0:
        failures.append(f"{prefix}_positive_net")
    if not _profit_factor_above_one(row):
        failures.append(f"{prefix}_profit_factor_above_one")
    if _number(row.get("net_pnl_excluding_largest_winner_usd"), "repeatability") <= 0.0:
        failures.append(f"{prefix}_positive_excluding_largest_winner")
    if _integer(row.get("liquidations"), "liquidations") != 0:
        failures.append(f"{prefix}_zero_liquidations")
    if row.get("insolvent") is not False:
        failures.append(f"{prefix}_no_insolvency")


def _check_nominal_controls(
    indexed: Mapping[tuple[str, str, str], Mapping[str, object]],
    failures: list[str],
) -> None:
    for partition in _PARTITIONS:
        candidate = _number(
            indexed[(partition, "nominal", "candidate")].get("net_pnl_usd"),
            "candidate net PnL",
        )
        for arm in ("no_action", "sweep_control", "direction_inverted_placebo"):
            control = _number(
                indexed[(partition, "nominal", arm)].get("net_pnl_usd"),
                f"{arm} net PnL",
            )
            if candidate <= control:
                failures.append(f"{partition}_nominal_exceeds_{arm}")


def _profit_factor_above_one(row: Mapping[str, object]) -> bool:
    value = row.get("profit_factor")
    if value is None:
        return (
            _integer(row.get("wins"), "wins") > 0
            and _integer(row.get("losses"), "losses") == 0
        )
    return _number(value, "profit factor") > 1.0


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"option-flow {label} is not numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"option-flow {label} is not finite")
    return number


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"option-flow {label} is not a nonnegative integer")
    return value
