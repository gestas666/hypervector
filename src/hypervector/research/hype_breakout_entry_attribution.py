"""Chronological, cost-aware attribution for HYPE breakout entry features."""

from __future__ import annotations

import math
from statistics import median

import pandas as pd

_OUTCOME_COLUMNS = frozenset({"gross_return_bps", "net_return_bps"})


def analyze_hype_entry_attribution(
    outcomes: pd.DataFrame,
    *,
    feature_names: tuple[str, ...],
    fold_count: int = 5,
    modeled_round_trip_bps: float = 13.0,
    tail_fraction: float = 0.2,
) -> dict[str, object]:
    """Measure feature association and tail spread in chronological folds."""
    _validate_inputs(
        outcomes,
        feature_names,
        fold_count,
        modeled_round_trip_bps,
        tail_fraction,
    )
    fold_ids = _chronological_fold_ids(len(outcomes), fold_count)
    results = {
        name: _feature_report(
            outcomes,
            name,
            fold_ids,
            fold_count,
            modeled_round_trip_bps,
            tail_fraction,
        )
        for name in feature_names
    }
    return {
        "execution_authority": "none",
        "evidence_status": "measurement_only_post_hoc_development",
        "rows": len(outcomes),
        "fold_count": fold_count,
        "tail_fraction": tail_fraction,
        "modeled_round_trip_bps": modeled_round_trip_bps,
        "gross_spread_hurdle_bps": 2.0 * modeled_round_trip_bps,
        "features": results,
    }


def _feature_report(
    outcomes: pd.DataFrame,
    name: str,
    fold_ids: pd.Series,
    fold_count: int,
    cost_bps: float,
    tail_fraction: float,
) -> dict[str, object]:
    folds = [
        _fold_report(
            outcomes.loc[fold_ids.eq(fold).to_numpy()],
            name,
            fold,
            tail_fraction,
        )
        for fold in range(fold_count)
    ]
    correlations = [
        float(row["spearman_ic"]) for row in folds if row["spearman_ic"] is not None
    ]
    spreads = [
        float(row["high_minus_low_gross_bps"])
        for row in folds
        if row["high_minus_low_gross_bps"] is not None
    ]
    median_ic = float(median(correlations)) if correlations else None
    median_spread = float(median(spreads)) if spreads else None
    hurdle = 2.0 * cost_bps
    absolute_spread = abs(median_spread) if median_spread is not None else None
    return {
        "coverage_rows": int(outcomes[name].notna().sum()),
        "valid_ic_folds": len(correlations),
        "median_spearman_ic": median_ic,
        "ic_sign_consistent_folds": _sign_consistency(correlations, median_ic),
        "median_high_minus_low_gross_bps": median_spread,
        "absolute_median_gross_tail_spread_bps": absolute_spread,
        "gross_spread_clears_2x_cost": (
            absolute_spread is not None and absolute_spread >= hurdle
        ),
        "folds": folds,
    }


def _fold_report(
    fold: pd.DataFrame,
    name: str,
    fold_id: int,
    tail_fraction: float,
) -> dict[str, object]:
    valid = fold[[name, "gross_return_bps", "net_return_bps"]].dropna()
    base = _fold_identity(fold, fold_id, len(valid))
    feature = valid[name].astype(float)
    if len(valid) < 5 or feature.nunique() < 2:
        return {**base, **_insufficient_metrics()}
    low_cut = float(feature.quantile(tail_fraction))
    high_cut = float(feature.quantile(1.0 - tail_fraction))
    if not low_cut < high_cut:
        return {**base, **_insufficient_metrics()}
    low = valid.loc[feature <= low_cut]
    high = valid.loc[feature >= high_cut]
    correlation = feature.corr(valid["net_return_bps"], method="spearman")
    if pd.isna(correlation):
        return {**base, **_insufficient_metrics()}
    return {
        **base,
        "status": "measured",
        "spearman_ic": float(correlation),
        "low_cut": low_cut,
        "high_cut": high_cut,
        "low_rows": len(low),
        "high_rows": len(high),
        "low_mean_gross_bps": float(low["gross_return_bps"].mean()),
        "high_mean_gross_bps": float(high["gross_return_bps"].mean()),
        "high_minus_low_gross_bps": float(
            high["gross_return_bps"].mean() - low["gross_return_bps"].mean()
        ),
        "low_mean_net_bps": float(low["net_return_bps"].mean()),
        "high_mean_net_bps": float(high["net_return_bps"].mean()),
    }


def _fold_identity(
    fold: pd.DataFrame, fold_id: int, valid_rows: int
) -> dict[str, object]:
    return {
        "fold": fold_id,
        "start_utc": fold.index[0].isoformat(),
        "end_utc": fold.index[-1].isoformat(),
        "rows": len(fold),
        "valid_rows": valid_rows,
    }


def _insufficient_metrics() -> dict[str, object]:
    return {
        "status": "insufficient_feature_variation",
        "spearman_ic": None,
        "low_cut": None,
        "high_cut": None,
        "low_rows": 0,
        "high_rows": 0,
        "low_mean_gross_bps": None,
        "high_mean_gross_bps": None,
        "high_minus_low_gross_bps": None,
        "low_mean_net_bps": None,
        "high_mean_net_bps": None,
    }


def _chronological_fold_ids(rows: int, fold_count: int) -> pd.Series:
    values = [
        min(position * fold_count // rows, fold_count - 1) for position in range(rows)
    ]
    return pd.Series(values, dtype=int)


def _sign_consistency(values: list[float], center: float | None) -> int:
    if center is None or center == 0.0:
        return 0
    return sum(value * center > 0.0 for value in values)


def _validate_inputs(
    outcomes: pd.DataFrame,
    feature_names: tuple[str, ...],
    fold_count: int,
    cost_bps: float,
    tail_fraction: float,
) -> None:
    if not feature_names or len(set(feature_names)) != len(feature_names):
        raise ValueError("HYPE attribution feature names must be unique and non-empty")
    missing = sorted(
        (set(feature_names) | _OUTCOME_COLUMNS).difference(outcomes.columns)
    )
    if missing:
        raise ValueError(f"HYPE attribution missing feature columns: {missing}")
    if not isinstance(outcomes.index, pd.DatetimeIndex) or outcomes.index.tz is None:
        raise ValueError("HYPE attribution requires a timezone-aware DatetimeIndex")
    if outcomes.index.has_duplicates or not outcomes.index.is_monotonic_increasing:
        raise ValueError("HYPE attribution index must be ordered and unique")
    if isinstance(fold_count, bool) or fold_count < 2 or fold_count > len(outcomes):
        raise ValueError("HYPE attribution fold_count must fit the outcome rows")
    if isinstance(cost_bps, bool) or not math.isfinite(cost_bps) or cost_bps < 0.0:
        raise ValueError("HYPE attribution cost must be finite and non-negative")
    if not math.isfinite(tail_fraction) or not 0.0 < tail_fraction < 0.5:
        raise ValueError(
            "HYPE attribution tail_fraction must be between zero and one-half"
        )
