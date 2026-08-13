"""Purged report-only return ranking for HT onset lifecycles."""

from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd

from hypervector.ml.hype_entry_challenger import (
    HYPE_ENTRY_MODEL_CANDIDATES,
    HypeEntryChallengerResult,
    evaluate_hype_entry_challengers,
    fit_predict_entry_feature_set,
)
from hypervector.research.hype_breakout_entry_features import (
    HYPE_ENTRY_ATTRIBUTION_FEATURES,
    build_hype_entry_features,
    join_hype_entry_outcomes,
)
from hypervector.research.hype_breakout_exit_experiment import split_hype_exit_market
from hypervector.research.hype_breakout_exit_models import (
    HypeExitPolicy,
    HypeExitReplayConfig,
    HypeExitReplayReport,
)
from hypervector.research.hype_breakout_exit_replay import replay_hype_breakout_exits

_SYMBOLS = frozenset({"BTC", "ETH", "SOL"})


@dataclass(frozen=True)
class HtOnsetMetalabelResult:
    """Development predictions, later descriptions, and authority-none report."""

    development: HypeEntryChallengerResult
    later_predictions: pd.DataFrame
    report: dict[str, object]


def evaluate_ht_onset_metalabel(
    market: pd.DataFrame,
    *,
    symbol: str,
    holdout_days: int = 60,
    n_splits: int = 5,
) -> HtOnsetMetalabelResult:
    """Rank unchanged HT entries without filtering, sizing, or routing authority."""
    if symbol not in _SYMBOLS:
        raise ValueError(f"HT onset ranker symbol is unsupported: {symbol}")
    config = _v39_config()
    development, later, split = split_hype_exit_market(
        market,
        config,
        holdout_days,
    )
    policy = HypeExitPolicy("v39_structural_side_control")
    development_replay = replay_hype_breakout_exits(development, policy, config)
    later_replay = replay_hype_breakout_exits(later, policy, config)
    development_rows = _model_rows(development, development_replay)
    later_rows = _model_rows(later, later_replay)
    developed = evaluate_hype_entry_challengers(
        development_rows,
        n_splits=n_splits,
        embargo_minutes=1_440,
        modeled_round_trip_bps=13.0,
    )
    later_predictions = fit_predict_entry_feature_set(
        development_rows,
        later_rows,
        feature_names=HYPE_ENTRY_ATTRIBUTION_FEATURES,
        candidate_names=HYPE_ENTRY_MODEL_CANDIDATES,
    )
    report = _report(
        symbol,
        split,
        developed,
        later_predictions,
        development_replay,
        later_replay,
    )
    return HtOnsetMetalabelResult(developed, later_predictions, report)


def _model_rows(
    market: pd.DataFrame,
    replay: HypeExitReplayReport,
) -> pd.DataFrame:
    features = build_hype_entry_features(market)
    joined = join_hype_entry_outcomes(features, replay.trades)
    return joined.reset_index(drop=True)


def _report(
    symbol: str,
    split: dict[str, object],
    developed: HypeEntryChallengerResult,
    later_predictions: pd.DataFrame,
    development_replay: HypeExitReplayReport,
    later_replay: HypeExitReplayReport,
) -> dict[str, object]:
    development = dict(developed.report)
    development["used_for_selection"] = True
    development["oos_candidate_attribution"] = _candidate_reports(developed.predictions)
    return {
        "schema_version": 1,
        "mode": "ht_onset_return_ranker_report_only_v1",
        "symbol": symbol,
        "contract": _contract(),
        "split": dict(split),
        "development": development,
        "later_already_opened": {
            "used_for_selection": False,
            "control": _control_summary(later_replay),
            "by_candidate": _candidate_reports(later_predictions),
        },
        "development_control": _control_summary(development_replay),
        "disposition": "ANNOTATION_ONLY_NO_RUNTIME_SELECTION",
        "limitations": _limitations(),
    }


def _candidate_reports(predictions: pd.DataFrame) -> dict[str, object]:
    return {
        candidate: {
            "all": _ranked_summary(
                predictions.loc[predictions["candidate"].eq(candidate)]
            ),
            "long": _ranked_summary(
                predictions.loc[
                    predictions["candidate"].eq(candidate)
                    & predictions["entry_side"].eq("long")
                ]
            ),
            "short": _ranked_summary(
                predictions.loc[
                    predictions["candidate"].eq(candidate)
                    & predictions["entry_side"].eq("short")
                ]
            ),
        }
        for candidate in HYPE_ENTRY_MODEL_CANDIDATES
    }


def _ranked_summary(rows: pd.DataFrame) -> dict[str, object]:
    if rows.empty:
        return _empty_ranked_summary()
    count = max(1, math.ceil(0.2 * len(rows)))
    selected = rows.sort_values("predicted_gross_return_bps", kind="stable").tail(count)
    returns = selected["actual_net_return_bps"].astype(float)
    gains = returns.loc[returns > 0.0]
    losses = -returns.loc[returns < 0.0]
    return {
        "rows": len(rows),
        "selected_rows": len(selected),
        "rank_ic": _rank_ic(rows),
        "wins": int((returns > 0.0).sum()),
        "losses": int((returns < 0.0).sum()),
        "median_net_bps": float(returns.median()),
        "net_return_bps": float(returns.sum()),
        "profit_factor": float(gains.sum() / losses.sum()) if len(losses) else None,
        "net_return_excluding_largest_winner_bps": (
            float(returns.sum() - gains.max()) if len(gains) else float(returns.sum())
        ),
    }


def _rank_ic(rows: pd.DataFrame) -> float | None:
    actual = rows["actual_gross_return_bps"].astype(float)
    predicted = rows["predicted_gross_return_bps"].astype(float)
    if len(rows) < 2 or actual.nunique() < 2 or predicted.nunique() < 2:
        return None
    value = actual.corr(predicted, method="spearman")
    return None if pd.isna(value) else float(value)


def _empty_ranked_summary() -> dict[str, object]:
    return {
        "rows": 0,
        "selected_rows": 0,
        "rank_ic": None,
        "wins": 0,
        "losses": 0,
        "median_net_bps": None,
        "net_return_bps": 0.0,
        "profit_factor": None,
        "net_return_excluding_largest_winner_bps": 0.0,
    }


def _control_summary(replay: HypeExitReplayReport) -> dict[str, object]:
    values = tuple(trade.net_return_bps for trade in replay.trades)
    winners = tuple(value for value in values if value > 0.0)
    return {
        "completed_trades": replay.completed_trades,
        "wins": replay.wins,
        "losses": replay.losses,
        "net_return_bps": replay.net_return_bps,
        "profit_factor": replay.profit_factor,
        "maximum_drawdown_bps": replay.maximum_drawdown_bps,
        "net_return_excluding_largest_winner_bps": (
            sum(values) - max(winners) if winners else sum(values)
        ),
    }


def _v39_config() -> HypeExitReplayConfig:
    return HypeExitReplayConfig(
        stop_bps=80.0,
        maximum_hold_minutes=480,
        maximum_hold_policy="extend_while_regime_supported",
        hard_maximum_hold_minutes=1_440,
        fee_bps_per_side=4.5,
        slippage_bps_per_side=2.0,
    )


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "model_installed": False,
    }


def _limitations() -> list[str]:
    return [
        "the later 60-day block was previously opened and is descriptive only",
        "return ranking cannot repair a structurally losing base strategy by itself",
        "bar-derived features cannot reproduce private IOC latency or queue state",
        "two fixed model candidates still create model-selection uncertainty",
        "no result may filter, size, route, enter, or close a live position",
    ]
