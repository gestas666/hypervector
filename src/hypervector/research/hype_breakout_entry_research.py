"""Bounded, report-only entry-policy research for HYPE breakout onsets."""

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
)


@dataclass(frozen=True)
class HypeEntryPolicy:
    """One causal entry revision around the unchanged exit contract."""

    policy_id: str
    require_nonpositive_body: bool = False
    maximum_prior_bbwp_min_15m: float | None = None

    def __post_init__(self) -> None:
        """Reject unstable policy identities and invalid thresholds."""
        if not self.policy_id.strip():
            raise ValueError("HYPE entry policy_id must be non-empty")
        threshold = self.maximum_prior_bbwp_min_15m
        if threshold is not None and (
            isinstance(threshold, bool)
            or not math.isfinite(threshold)
            or threshold < 0.0
            or threshold > 100.0
        ):
            raise ValueError("HYPE prior BBWP threshold must be between 0 and 100")


@dataclass(frozen=True)
class HypeEntryPolicyEvidence:
    """Signal retention evidence for one entry policy."""

    raw_signals: int
    eligible_signals: int
    rejected_signals: int


@dataclass(frozen=True)
class HypeEntryResearchBundle:
    """Summary and exact policy trades for one development experiment."""

    report: dict[str, object]
    trade_rows: pd.DataFrame


def declared_hype_entry_policies() -> tuple[HypeEntryPolicy, ...]:
    """Return the post-hoc control and three mechanistic challengers."""
    return (
        HypeEntryPolicy("hype_breakout_control"),
        HypeEntryPolicy("pullback_body_nonpositive", require_nonpositive_body=True),
        HypeEntryPolicy(
            "precompression15_min40",
            maximum_prior_bbwp_min_15m=40.0,
        ),
        HypeEntryPolicy(
            "precompression15_min40_pullback",
            require_nonpositive_body=True,
            maximum_prior_bbwp_min_15m=40.0,
        ),
    )


def apply_hype_entry_policy(
    market: pd.DataFrame,
    features: pd.DataFrame,
    policy: HypeEntryPolicy,
) -> tuple[pd.DataFrame, HypeEntryPolicyEvidence]:
    """Remove only source entry events that do not satisfy one policy."""
    raw_index = market.index[market["entry_side"].notna()]
    if not raw_index.equals(features.index):
        raise ValueError("HYPE entry features must cover every raw signal exactly")
    eligible = pd.Series(True, index=features.index)
    if policy.require_nonpositive_body:
        eligible &= _finite_feature(features, "directional_bar_body_bps").le(0.0)
    threshold = policy.maximum_prior_bbwp_min_15m
    if threshold is not None:
        eligible &= _finite_feature(features, "prior_bbwp_min_15m").le(threshold)
    output = market.copy()
    output.loc[features.index[~eligible], "entry_side"] = None
    retained = int(eligible.sum())
    evidence = HypeEntryPolicyEvidence(
        len(features), retained, len(features) - retained
    )
    return output, evidence


def run_hype_entry_research(
    market: pd.DataFrame,
    *,
    config: HypeExitReplayConfig | None = None,
    fold_count: int = 5,
) -> dict[str, object]:
    """Replay every declared entry policy on development evidence only."""
    return build_hype_entry_research_bundle(
        market,
        config=config,
        fold_count=fold_count,
    ).report


def build_hype_entry_research_bundle(
    market: pd.DataFrame,
    *,
    config: HypeExitReplayConfig | None = None,
    fold_count: int = 5,
) -> HypeEntryResearchBundle:
    """Return the entry-policy summary and exact lifecycle rows."""
    cfg = config or HypeExitReplayConfig()
    features = build_hype_entry_features(market)
    results = tuple(
        _develop_policy(market, features, policy, cfg, fold_count)
        for policy in declared_hype_entry_policies()
    )
    selected = _least_bad_challenger(results[1:])
    report = _report(results, selected, features, fold_count, cfg)
    return HypeEntryResearchBundle(report, _trade_rows(results))


def _develop_policy(
    market: pd.DataFrame,
    features: pd.DataFrame,
    policy: HypeEntryPolicy,
    config: HypeExitReplayConfig,
    fold_count: int,
) -> tuple[HypeEntryPolicy, HypeEntryPolicyEvidence, HypePolicyDevelopment]:
    filtered, evidence = apply_hype_entry_policy(market, features, policy)
    developed = develop_hype_exit_policy(
        filtered,
        HypeExitPolicy(policy.policy_id),
        config,
        fold_count,
    )
    return policy, evidence, developed


def _least_bad_challenger(
    results: tuple[
        tuple[HypeEntryPolicy, HypeEntryPolicyEvidence, HypePolicyDevelopment], ...
    ],
) -> tuple[HypeEntryPolicy, HypeEntryPolicyEvidence, HypePolicyDevelopment]:
    if not results:
        raise ValueError("HYPE entry research requires challenger policies")
    return max(results, key=lambda item: _score(item[2]))


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
        tuple[HypeEntryPolicy, HypeEntryPolicyEvidence, HypePolicyDevelopment], ...
    ],
    selected: tuple[HypeEntryPolicy, HypeEntryPolicyEvidence, HypePolicyDevelopment],
    features: pd.DataFrame,
    fold_count: int,
    config: HypeExitReplayConfig,
) -> dict[str, object]:
    selected_result = selected[2]
    supported = _forward_supported(selected_result, fold_count)
    return {
        "schema_version": 1,
        "mode": "hype_breakout_entry_post_hoc_development",
        "execution_authority": "none",
        "evidence_status": "post_hoc_development_only",
        "trial_accounting": {
            "prior_economic_trials": 32,
            "current_system_policy_trials": len(results),
            "cumulative_known_economic_trials": 32 + len(results),
            "preselection_feature_measurements": 23,
            "preselection_threshold_diagnostics": 20,
        },
        "cost_contract": {
            "fee_bps_per_side": config.fee_bps_per_side,
            "slippage_bps_per_side": config.slippage_bps_per_side,
            "modeled_round_trip_bps": 2.0
            * (config.fee_bps_per_side + config.slippage_bps_per_side),
        },
        "feature_rows": len(features),
        "development": {
            policy.policy_id: _development_summary(policy, evidence, developed)
            for policy, evidence, developed in results
        },
        "least_bad_challenger": selected[0].policy_id,
        "forward_candidate": {
            "policy_id": selected[0].policy_id if supported else None,
            "status": "development_supported"
            if supported
            else "no_supported_candidate",
            "requires_fresh_forward_validation": True,
            "live_authority": False,
        },
        "limitations": [
            "the final 60-day holdout was not reopened",
            "entry thresholds were selected after development diagnostics",
            "one-minute OHLC does not reproduce event-level execution",
            "historical HYPE L2 was unavailable for this bar-feature screen",
        ],
    }


def _development_summary(
    policy: HypeEntryPolicy,
    evidence: HypeEntryPolicyEvidence,
    result: HypePolicyDevelopment,
) -> dict[str, object]:
    report = result.report
    return {
        "policy": asdict(policy),
        "signal_evidence": asdict(evidence),
        "completed_trades": report.completed_trades,
        "net_return_bps": report.net_return_bps,
        "profit_factor": report.profit_factor,
        "maximum_drawdown_bps": report.maximum_drawdown_bps,
        "fold_net_bps": list(result.fold_net_bps),
        "positive_folds": result.positive_folds,
        "median_fold_net_bps": result.median_fold_net_bps,
        "exit_reasons": report.exit_reasons,
    }


def _trade_rows(
    results: tuple[
        tuple[HypeEntryPolicy, HypeEntryPolicyEvidence, HypePolicyDevelopment], ...
    ],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for policy, _, developed in results:
        rows.extend(
            {"policy_id": policy.policy_id, **asdict(trade)}
            for trade in developed.report.trades
        )
    return pd.DataFrame(rows)


def _forward_supported(result: HypePolicyDevelopment, fold_count: int) -> bool:
    report = result.report
    minimum_positive = math.ceil(fold_count * 0.6)
    return (
        report.net_return_bps > 0.0
        and (report.profit_factor or 0.0) > 1.0
        and result.positive_folds >= minimum_positive
    )


def _finite_feature(features: pd.DataFrame, name: str) -> pd.Series:
    if name not in features:
        raise ValueError(f"HYPE entry features missing policy column: {name}")
    values = features[name].astype(float)
    if not values.map(math.isfinite).all():
        raise ValueError(f"HYPE entry policy feature contains missing values: {name}")
    return values
