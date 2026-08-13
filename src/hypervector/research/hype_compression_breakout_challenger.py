"""Report-only HYPE compression-plus-breakout development challenger."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import pandas as pd

from hypervector.research.hype_breakout_entry_features import (
    build_hype_entry_features,
)
from hypervector.research.hype_breakout_exit_experiment import (
    HypePolicyDevelopment,
    develop_hype_exit_policy,
)
from hypervector.research.hype_breakout_exit_models import (
    HypeExitPolicy,
    HypeExitReplayConfig,
    HypeExitTrade,
)
from hypervector.research.hype_breakout_exit_replay import replay_hype_breakout_exits


@dataclass(frozen=True)
class HypeCompressionPolicy:
    """One causal compression filter around the unchanged breakout onset."""

    policy_id: str
    maximum_5m_bbwp_percentile: float | None = None
    maximum_prior_1m_bbwp_min_15m: float | None = None
    require_nonpositive_directional_body: bool = False
    preserve_breakout_onset: bool = True

    def __post_init__(self) -> None:
        """Reject ambiguous identities and invalid percentile thresholds."""
        if not self.policy_id.strip():
            raise ValueError("HYPE compression policy_id must be non-empty")
        for label, value in (
            ("5m BBWP", self.maximum_5m_bbwp_percentile),
            ("prior 1m BBWP", self.maximum_prior_1m_bbwp_min_15m),
        ):
            _validate_percentile(value, label)
        if not self.preserve_breakout_onset:
            raise ValueError("HYPE compression policy must preserve the breakout onset")


@dataclass(frozen=True)
class HypeCompressionEvidence:
    """Signal-retention counts for one compression policy."""

    raw_signals: int
    eligible_signals: int
    rejected_signals: int


@dataclass(frozen=True)
class HypeCompressionResearchBundle:
    """Development report and exact lifecycle rows for all declared policies."""

    report: dict[str, object]
    trade_rows: pd.DataFrame


@dataclass(frozen=True)
class HypeCompressionConfirmationBundle:
    """Later-window comparison with the development identity held fixed."""

    report: dict[str, object]
    trade_rows: pd.DataFrame


def declared_hype_compression_policies() -> tuple[HypeCompressionPolicy, ...]:
    """Return the frozen control and three predeclared compression revisions."""
    return (
        HypeCompressionPolicy("hype_breakout_control"),
        _compression_policy("compression_5m40_1m40_pullback", 40.0, 40.0),
        _compression_policy("compression_5m50_1m40_pullback", 50.0, 40.0),
        _compression_policy("compression_5m50_1m50_pullback", 50.0, 50.0),
    )


def apply_hype_compression_policy(
    market: pd.DataFrame,
    features: pd.DataFrame,
    policy: HypeCompressionPolicy,
) -> tuple[pd.DataFrame, HypeCompressionEvidence]:
    """Remove only breakout entry events that fail the compression contract."""
    raw_index = market.index[market["entry_side"].notna()]
    if not raw_index.equals(features.index):
        raise ValueError(
            "HYPE compression features must cover every raw signal exactly"
        )
    eligible = pd.Series(True, index=features.index)
    if policy.maximum_5m_bbwp_percentile is not None:
        eligible &= _finite_feature(
            features,
            "authoritative_5m_bbwp_percentile",
        ).le(policy.maximum_5m_bbwp_percentile)
    if policy.maximum_prior_1m_bbwp_min_15m is not None:
        eligible &= _finite_feature(features, "prior_bbwp_min_15m").le(
            policy.maximum_prior_1m_bbwp_min_15m
        )
    if policy.require_nonpositive_directional_body:
        eligible &= _finite_feature(features, "directional_bar_body_bps").le(0.0)
    filtered = market.copy()
    filtered.loc[features.index[~eligible], "entry_side"] = None
    retained = int(eligible.sum())
    evidence = HypeCompressionEvidence(
        len(features), retained, len(features) - retained
    )
    return filtered, evidence


def build_hype_compression_breakout_bundle(
    development: pd.DataFrame,
    *,
    config: HypeExitReplayConfig | None = None,
    fold_count: int = 5,
) -> HypeCompressionResearchBundle:
    """Replay and rank the frozen policies on development evidence only."""
    cfg = config or HypeExitReplayConfig()
    features = build_hype_entry_features(development)
    results = tuple(
        _develop_policy(development, features, policy, cfg, fold_count)
        for policy in declared_hype_compression_policies()
    )
    selected = _select_challenger(results[1:])
    return HypeCompressionResearchBundle(
        _report(results, selected, features, cfg),
        _trade_rows(results),
    )


def build_hype_compression_confirmation(
    segments: tuple[pd.DataFrame, ...],
    *,
    frozen_policy_id: str,
    config: HypeExitReplayConfig | None = None,
) -> HypeCompressionConfirmationBundle:
    """Compare control with one frozen policy across causal continuous segments."""
    _validate_segments(segments)
    policies = declared_hype_compression_policies()
    selected = _policy_by_id(policies[1:], frozen_policy_id)
    cfg = config or HypeExitReplayConfig()
    results = tuple(
        _evaluate_confirmation_policy(segments, policy, cfg)
        for policy in (policies[0], selected)
    )
    report = _confirmation_report(results, selected.policy_id, cfg)
    rows = [row for result in results for row in result[1]]
    return HypeCompressionConfirmationBundle(report, pd.DataFrame(rows))


def _compression_policy(
    policy_id: str,
    maximum_5m: float,
    maximum_prior_1m: float,
) -> HypeCompressionPolicy:
    return HypeCompressionPolicy(
        policy_id,
        maximum_5m_bbwp_percentile=maximum_5m,
        maximum_prior_1m_bbwp_min_15m=maximum_prior_1m,
        require_nonpositive_directional_body=True,
    )


def _policy_by_id(
    policies: tuple[HypeCompressionPolicy, ...],
    policy_id: str,
) -> HypeCompressionPolicy:
    matches = [policy for policy in policies if policy.policy_id == policy_id]
    if len(matches) != 1:
        raise ValueError(
            "frozen HYPE compression policy_id is not a declared challenger"
        )
    return matches[0]


def _evaluate_confirmation_policy(
    segments: tuple[pd.DataFrame, ...],
    policy: HypeCompressionPolicy,
    config: HypeExitReplayConfig,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    resolved: list[HypeExitTrade] = []
    rows: list[dict[str, object]] = []
    raw_signals = eligible_signals = occupied_signals = 0
    gap_censored = cutoff_censored = 0
    for segment_number, market in enumerate(segments, start=1):
        features = build_hype_entry_features(market)
        filtered, evidence = apply_hype_compression_policy(market, features, policy)
        replay = replay_hype_breakout_exits(
            filtered,
            HypeExitPolicy(policy.policy_id),
            config,
        )
        raw_signals += evidence.raw_signals
        eligible_signals += evidence.eligible_signals
        occupied_signals += replay.occupied_signals
        for trade in replay.trades:
            is_censored = trade.exit_reason == "end_of_data"
            cutoff = segment_number == len(segments)
            gap_censored += int(is_censored and not cutoff)
            cutoff_censored += int(is_censored and cutoff)
            if not is_censored:
                resolved.append(trade)
            rows.append(
                {
                    "policy_id": policy.policy_id,
                    "segment": segment_number,
                    "censored": is_censored,
                    **asdict(trade),
                }
            )
    result = {
        "policy": asdict(policy),
        "raw_signals": raw_signals,
        "eligible_signals": eligible_signals,
        "rejected_signals": raw_signals - eligible_signals,
        "occupied_signals": occupied_signals,
        "unresolved_gap_lifecycles": gap_censored,
        "open_at_cutoff_lifecycles": cutoff_censored,
        "metrics": _confirmation_metrics(resolved),
    }
    return result, rows


def _confirmation_report(
    results: tuple[tuple[dict[str, object], list[dict[str, object]]], ...],
    frozen_policy_id: str,
    config: HypeExitReplayConfig,
) -> dict[str, object]:
    summaries = {str(result[0]["policy"]["policy_id"]): result[0] for result in results}
    unresolved = sum(
        int(summary["unresolved_gap_lifecycles"])
        + int(summary["open_at_cutoff_lifecycles"])
        for summary in summaries.values()
    )
    return {
        "schema_version": 1,
        "mode": "hype_compression_breakout_later_confirmation",
        "execution_authority": "none",
        "evidence_status": "resolved" if unresolved == 0 else "technically_unresolved",
        "frozen_policy_id": frozen_policy_id,
        "selection_performed": False,
        "confirmation_policy_trials": len(results),
        "cost_contract": asdict(config),
        "confirmation": summaries,
        "comparison": _confirmation_comparison(summaries, frozen_policy_id),
        "limitations": [
            "six missing venue candle minutes are explicit segment boundaries",
            "lifecycles reaching a gap or final cutoff are censored, not force-closed",
            "the confirmation window is short and cannot establish durable edge",
            "one-minute OHLC cannot reproduce event-level queue position",
        ],
    }


def _confirmation_comparison(
    summaries: dict[str, dict[str, object]],
    frozen_policy_id: str,
) -> dict[str, object]:
    control = summaries["hype_breakout_control"]["metrics"]
    selected = summaries[frozen_policy_id]["metrics"]
    selected_net = float(selected["net_return_bps"])
    control_net = float(control["net_return_bps"])
    return {
        "selected_minus_control_net_bps": selected_net - control_net,
        "selected_positive": selected_net > 0.0,
        "selected_outperformed_control": selected_net > control_net,
    }


def _confirmation_metrics(trades: list[HypeExitTrade]) -> dict[str, object]:
    ordered = sorted(trades, key=lambda trade: trade.entry_time_utc)
    net = [trade.net_return_bps for trade in ordered]
    profits = sum(value for value in net if value > 0.0)
    losses = -sum(value for value in net if value <= 0.0)
    largest = max((value for value in net if value > 0.0), default=0.0)
    return {
        "completed_trades": len(ordered),
        "wins": sum(value > 0.0 for value in net),
        "losses": sum(value <= 0.0 for value in net),
        "net_return_bps": sum(net),
        "profit_factor": profits / losses if losses else None,
        "maximum_drawdown_bps": _maximum_drawdown(net),
        "total_fee_bps": sum(trade.fee_bps for trade in ordered),
        "funding_bps": sum(trade.funding_bps for trade in ordered),
        "without_largest_winner_net_bps": sum(net) - largest,
        "long_trades": sum(trade.side == "long" for trade in ordered),
        "short_trades": sum(trade.side == "short" for trade in ordered),
    }


def _maximum_drawdown(values: list[float]) -> float:
    equity = peak = drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _validate_segments(segments: tuple[pd.DataFrame, ...]) -> None:
    if not segments:
        raise ValueError("HYPE confirmation requires continuous market segments")
    previous_end: pd.Timestamp | None = None
    for segment in segments:
        if segment.empty or not isinstance(segment.index, pd.DatetimeIndex):
            raise ValueError("HYPE confirmation segments require DatetimeIndex rows")
        if segment.index.tz is None or segment.index.has_duplicates:
            raise ValueError(
                "HYPE confirmation segment timestamps must be unique and aware"
            )
        if not segment.index.is_monotonic_increasing:
            raise ValueError("HYPE confirmation segment timestamps must be ordered")
        if previous_end is not None and segment.index[0] <= previous_end:
            raise ValueError("HYPE confirmation segments must be disjoint and ordered")
        previous_end = segment.index[-1]


def _develop_policy(
    market: pd.DataFrame,
    features: pd.DataFrame,
    policy: HypeCompressionPolicy,
    config: HypeExitReplayConfig,
    fold_count: int,
) -> tuple[HypeCompressionPolicy, HypeCompressionEvidence, HypePolicyDevelopment]:
    filtered, evidence = apply_hype_compression_policy(market, features, policy)
    developed = develop_hype_exit_policy(
        filtered,
        HypeExitPolicy(policy.policy_id),
        config,
        fold_count,
    )
    return policy, evidence, developed


def _select_challenger(
    results: tuple[
        tuple[HypeCompressionPolicy, HypeCompressionEvidence, HypePolicyDevelopment],
        ...,
    ],
) -> tuple[HypeCompressionPolicy, HypeCompressionEvidence, HypePolicyDevelopment]:
    if not results:
        raise ValueError("HYPE compression research requires challenger policies")
    ordered = sorted(results, key=lambda item: item[0].policy_id)
    return max(ordered, key=lambda item: _score(item[2]))


def _score(result: HypePolicyDevelopment) -> tuple[float, ...]:
    report = result.report
    return (
        float(result.positive_folds),
        result.median_fold_net_bps,
        report.net_return_bps,
        report.profit_factor or 0.0,
        -report.maximum_drawdown_bps,
    )


def _report(
    results: tuple[
        tuple[HypeCompressionPolicy, HypeCompressionEvidence, HypePolicyDevelopment],
        ...,
    ],
    selected: tuple[
        HypeCompressionPolicy,
        HypeCompressionEvidence,
        HypePolicyDevelopment,
    ],
    features: pd.DataFrame,
    config: HypeExitReplayConfig,
) -> dict[str, object]:
    return {
        **_development_metadata(config, len(results)),
        "feature_rows": len(features),
        "development": {
            policy.policy_id: _development_summary(policy, evidence, developed)
            for policy, evidence, developed in results
        },
        "selection": {
            "selected_challenger": selected[0].policy_id,
            "rule": (
                "positive_folds, median_fold_net, aggregate_net, "
                "profit_factor, lower_drawdown, lexical_id"
            ),
            "holdout_used": False,
        },
        "next_test": {
            "frozen_policy_id": selected[0].policy_id,
            "requires_later_venue_confirmation": True,
            "live_authority": False,
        },
    }


def _development_metadata(
    config: HypeExitReplayConfig,
    policy_count: int,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "hype_compression_breakout_development",
        "execution_authority": "none",
        "evidence_status": "post_hoc_development_only",
        "hypothesis": (
            "retain the completed 5m breakout onset and hourly structural side; "
            "require recent low-volatility compression and a non-chasing signal bar"
        ),
        "trial_accounting": {
            "prior_known_policy_trials": 36,
            "preselection_threshold_diagnostics": 4,
            "current_policy_trials": policy_count,
            "cumulative_known_policy_trials": 36 + policy_count,
        },
        "cost_contract": {
            "fee_bps_per_side": config.fee_bps_per_side,
            "slippage_bps_per_side": config.slippage_bps_per_side,
            "funding": "actual_Hyperliquid_hourly_event_rates",
            "protective_stop_bps": config.stop_bps,
            "maximum_hold_minutes": config.maximum_hold_minutes,
        },
        "limitations": [
            "thresholds were declared after inspecting development attribution",
            "selection remains development-only and does not establish forward edge",
            "one-minute OHLC cannot reproduce event-level queue position",
            "the existing final 60-day block is not reopened for selection",
        ],
    }


def _development_summary(
    policy: HypeCompressionPolicy,
    evidence: HypeCompressionEvidence,
    developed: HypePolicyDevelopment,
) -> dict[str, object]:
    report = developed.report
    return {
        "policy": asdict(policy),
        "signal_evidence": asdict(evidence),
        "completed_trades": report.completed_trades,
        "wins": report.wins,
        "losses": report.losses,
        "net_return_bps": report.net_return_bps,
        "profit_factor": report.profit_factor,
        "maximum_drawdown_bps": report.maximum_drawdown_bps,
        "fold_net_bps": list(developed.fold_net_bps),
        "positive_folds": developed.positive_folds,
        "median_fold_net_bps": developed.median_fold_net_bps,
        "exit_reasons": report.exit_reasons,
    }


def _trade_rows(
    results: tuple[
        tuple[HypeCompressionPolicy, HypeCompressionEvidence, HypePolicyDevelopment],
        ...,
    ],
) -> pd.DataFrame:
    rows = [
        {"policy_id": policy.policy_id, **asdict(trade)}
        for policy, _, developed in results
        for trade in developed.report.trades
    ]
    return pd.DataFrame(rows)


def _finite_feature(features: pd.DataFrame, name: str) -> pd.Series:
    if name not in features:
        raise ValueError(f"HYPE compression features missing policy column: {name}")
    values = features[name].astype(float)
    if not values.map(math.isfinite).all():
        raise ValueError(f"HYPE compression feature contains missing values: {name}")
    return values


def _validate_percentile(value: float | None, label: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not math.isfinite(value) or not 0.0 <= value <= 100.0:
        raise ValueError(f"HYPE {label} threshold must be between 0 and 100")
