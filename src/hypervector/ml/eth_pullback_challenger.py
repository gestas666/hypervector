"""Report-only ETH pullback metalabel challenger."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
import math

import numpy as np
import pandas as pd

from hypervector.ml.hype_entry_challenger import (
    HypeEntryChallengerResult,
    evaluate_hype_entry_feature_set,
    fit_predict_entry_feature_set,
)
from hypervector.research.hype_breakout_entry_features import (
    HYPE_ENTRY_ATTRIBUTION_FEATURES,
    build_hype_entry_features,
    join_hype_entry_outcomes,
)
from hypervector.research.hype_breakout_exit_models import HypeExitTrade

ETH_PULLBACK_MODEL_CANDIDATES: tuple[str, str] = (
    "ridge_return",
    "lightgbm_return",
)
ETH_PULLBACK_MODEL_FEATURES = HYPE_ENTRY_ATTRIBUTION_FEATURES + (
    "side_sign",
    "breakout_relation_aligned",
)


@dataclass(frozen=True)
class EthPullbackMetalabelResult:
    """Development and opened-final report-only model evidence."""

    development: HypeEntryChallengerResult
    final_predictions: pd.DataFrame
    report: dict[str, object]


def build_eth_pullback_model_rows(
    market: pd.DataFrame,
    trades: Sequence[HypeExitTrade],
) -> pd.DataFrame:
    """Build causal entry rows with exact ETH lifecycle outcomes."""
    selected = tuple(trades)
    if not selected:
        raise ValueError("ETH pullback metalabel requires resolved trades")
    features = build_hype_entry_features(market)
    rows = join_hype_entry_outcomes(features, selected)
    breakout = market.loc[rows.index, "breakout_side"]
    invalid = ~breakout.isin(("long", "short"))
    if invalid.any():
        raise ValueError("ETH pullback breakout side must be long or short")
    rows["side_sign"] = rows["entry_side"].map({"long": 1.0, "short": -1.0})
    rows["breakout_relation_aligned"] = rows["entry_side"].eq(breakout).astype(float)
    return rows.reset_index(drop=True)


def evaluate_eth_pullback_metalabel(
    rows: pd.DataFrame,
    *,
    development_end_utc: str,
    opened_final_start_utc: str,
    opened_final_end_utc: str,
    n_splits: int = 5,
    embargo_minutes: int = 720,
    modeled_round_trip_bps: float = 13.0,
) -> EthPullbackMetalabelResult:
    """Evaluate fixed baseline models without granting execution authority."""
    boundaries = _boundaries(
        development_end_utc,
        opened_final_start_utc,
        opened_final_end_utc,
    )
    development, confirmation, purged = _partition_rows(rows, boundaries)
    developed = evaluate_hype_entry_feature_set(
        development,
        feature_names=ETH_PULLBACK_MODEL_FEATURES,
        candidate_names=ETH_PULLBACK_MODEL_CANDIDATES,
        n_splits=n_splits,
        embargo_minutes=embargo_minutes,
        modeled_round_trip_bps=modeled_round_trip_bps,
    )
    development_predictions = _attach_confirmation_identity(
        developed.predictions,
        development,
    )
    developed = replace(developed, predictions=development_predictions)
    predicted = fit_predict_entry_feature_set(
        development,
        confirmation,
        feature_names=ETH_PULLBACK_MODEL_FEATURES,
        candidate_names=ETH_PULLBACK_MODEL_CANDIDATES,
    )
    predicted = _attach_confirmation_identity(predicted, confirmation)
    report = _report(
        developed,
        development_predictions,
        predicted,
        boundaries,
        len(purged),
        modeled_round_trip_bps,
    )
    return EthPullbackMetalabelResult(developed, predicted, report)


def _boundaries(
    development_end_utc: str,
    final_start_utc: str,
    final_end_utc: str,
) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    values = tuple(
        pd.Timestamp(value).tz_convert("UTC")
        for value in (development_end_utc, final_start_utc, final_end_utc)
    )
    if not values[0] < values[1] < values[2]:
        raise ValueError("ETH metalabel boundaries must be strictly ordered")
    return values


def _partition_rows(
    raw: pd.DataFrame,
    boundaries: tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows = raw.copy()
    for field in ("signal_time_utc", "entry_time_utc", "exit_time_utc"):
        rows[field] = pd.to_datetime(rows[field], utc=True, errors="coerce")
    if rows[["signal_time_utc", "entry_time_utc", "exit_time_utc"]].isna().any().any():
        raise ValueError("ETH metalabel timestamps must be valid UTC values")
    development_end, final_start, final_end = boundaries
    development = rows.loc[
        rows["signal_time_utc"].lt(development_end)
        & rows["exit_time_utc"].lt(development_end)
    ].copy()
    confirmation = rows.loc[
        rows["signal_time_utc"].ge(final_start) & rows["signal_time_utc"].lt(final_end)
    ].copy()
    if development.empty or confirmation.empty:
        raise ValueError("ETH metalabel partitions must both contain trades")
    if confirmation["exit_time_utc"].ge(final_end).any():
        raise ValueError(
            "ETH confirmation outcomes must be resolved inside final block"
        )
    selected = development.index.union(confirmation.index)
    return development, confirmation, rows.drop(index=selected)


def _attach_confirmation_identity(
    predictions: pd.DataFrame,
    confirmation: pd.DataFrame,
) -> pd.DataFrame:
    identity = confirmation[
        ["signal_time_utc", "side_sign", "breakout_relation_aligned"]
    ].copy()
    identity["signal_time_utc"] = pd.to_datetime(identity["signal_time_utc"], utc=True)
    output = predictions.merge(identity, on="signal_time_utc", validate="many_to_one")
    output["breakout_relation"] = output["breakout_relation_aligned"].map(
        {1.0: "aligned", 0.0: "opposed"}
    )
    if output["breakout_relation"].isna().any():
        raise ValueError("ETH confirmation breakout relation is invalid")
    return output


def _report(
    development: HypeEntryChallengerResult,
    development_predictions: pd.DataFrame,
    predictions: pd.DataFrame,
    boundaries: tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp],
    purged_rows: int,
    modeled_round_trip_bps: float,
) -> dict[str, object]:
    development_report = development.report
    return {
        "schema_version": 1,
        "mode": "eth_pullback_metalabel_challenger_v1",
        "contract": _contract(),
        "model_protocol": _model_protocol(modeled_round_trip_bps),
        "boundaries": _boundary_report(boundaries, purged_rows),
        "trial_accounting": development_report["trial_accounting"],
        "development": development_report,
        "development_oos_attribution": _attribution_report(
            development_predictions,
            used_for_selection=True,
        ),
        "opened_final_confirmation": _attribution_report(
            predictions,
            used_for_selection=False,
        ),
        "limitations": _limitations(),
    }


def _model_protocol(modeled_round_trip_bps: float) -> dict[str, object]:
    return {
        "modeled_round_trip_bps": modeled_round_trip_bps,
        "training_target": "gross_return_bps",
        "economic_evaluation": "actual_net_return_bps",
    }


def _attribution_report(
    predictions: pd.DataFrame,
    *,
    used_for_selection: bool,
) -> dict[str, object]:
    return {
        "rows": len(predictions) // len(ETH_PULLBACK_MODEL_CANDIDATES),
        "used_for_selection": used_for_selection,
        "by_candidate": {
            name: _candidate_confirmation(
                predictions.loc[predictions["candidate"].eq(name)]
            )
            for name in ETH_PULLBACK_MODEL_CANDIDATES
        },
    }


def _candidate_confirmation(rows: pd.DataFrame) -> dict[str, object]:
    return {
        "all": _rank_summary(rows),
        "by_side": {
            side: _rank_summary(rows.loc[rows["entry_side"].eq(side)])
            for side in ("long", "short")
        },
        "by_relation": {
            relation: _rank_summary(rows.loc[rows["breakout_relation"].eq(relation)])
            for relation in ("aligned", "opposed")
        },
        "by_side_relation": {
            f"{side}|{relation}": _rank_summary(
                rows.loc[
                    rows["entry_side"].eq(side) & rows["breakout_relation"].eq(relation)
                ]
            )
            for side in ("long", "short")
            for relation in ("aligned", "opposed")
        },
    }


def _rank_summary(rows: pd.DataFrame) -> dict[str, object]:
    if rows.empty:
        return _empty_rank_summary()
    count = max(1, math.ceil(0.2 * len(rows)))
    ordered = rows.sort_values("predicted_gross_return_bps", kind="stable")
    selected = ordered.tail(count)
    returns = selected["actual_net_return_bps"].to_numpy(dtype=float)
    gains = returns[returns > 0.0]
    losses = -returns[returns < 0.0]
    rank = _rank_ic(rows)
    return {
        "rows": len(rows),
        "rank_ic": rank,
        "top_quintile_rows": len(selected),
        "top_quintile_wins": int((returns > 0.0).sum()),
        "top_quintile_losses": int((returns < 0.0).sum()),
        "top_quintile_net_bps": float(returns.sum()),
        "top_quintile_profit_factor": (
            float(gains.sum() / losses.sum()) if losses.size else None
        ),
        "top_quintile_net_excluding_largest_winner_bps": float(
            returns.sum() - gains.max() if gains.size else returns.sum()
        ),
    }


def _rank_ic(rows: pd.DataFrame) -> float | None:
    actual = rows["actual_gross_return_bps"].astype(float)
    predicted = rows["predicted_gross_return_bps"].astype(float)
    if len(rows) < 2 or np.ptp(actual) <= 1e-12 or np.ptp(predicted) <= 1e-12:
        return None
    value = actual.corr(predicted, method="spearman")
    return None if pd.isna(value) else float(value)


def _empty_rank_summary() -> dict[str, object]:
    return {
        "rows": 0,
        "rank_ic": None,
        "top_quintile_rows": 0,
        "top_quintile_wins": 0,
        "top_quintile_losses": 0,
        "top_quintile_net_bps": 0.0,
        "top_quintile_profit_factor": None,
        "top_quintile_net_excluding_largest_winner_bps": 0.0,
    }


def _boundary_report(
    boundaries: tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp],
    purged_rows: int,
) -> dict[str, object]:
    return {
        "development_end_exclusive_utc": boundaries[0].isoformat(),
        "opened_final_start_utc": boundaries[1].isoformat(),
        "opened_final_end_exclusive_utc": boundaries[2].isoformat(),
        "purged_or_out_of_scope_rows": purged_rows,
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "live_gate": False,
        "model_installed": False,
    }


def _limitations() -> list[str]:
    return [
        "the opened final 60-day block was previously inspected and is descriptive",
        "the exact ETH entry and lifecycle shape was selected after multiple trials",
        "bar features cannot reproduce private IOC latency or event-level order flow",
        "subgroup and top-quintile results have smaller effective samples",
        "model evidence cannot route, size, filter, enter, or close a live trade",
    ]
