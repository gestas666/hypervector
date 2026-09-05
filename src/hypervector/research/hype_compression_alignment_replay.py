"""Causal report-only replay of the frozen HYPE compression alignment split."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
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
from hypervector.research.hype_breakout_exit_replay import (
    replay_hype_breakout_exits,
)
from hypervector.research.hype_compression_breakout_challenger import (
    HypeCompressionEvidence,
    HypeCompressionPolicy,
    apply_hype_compression_policy,
    declared_hype_compression_policies,
)

_COHORTS = ("control", "aligned_only", "opposed_only")
_SIDES = ("long", "short")


@dataclass(frozen=True)
class HypeCompressionAlignmentReplay:
    """Report and exact lifecycle sidecars for the alignment replay."""

    report: dict[str, object]
    development_trades: pd.DataFrame
    confirmation_trades: pd.DataFrame


@dataclass(frozen=True)
class HypeCompressionAlignmentMarkets:
    """Frozen compression cohorts before exit-policy replay."""

    markets: dict[str, pd.DataFrame]
    compression: HypeCompressionEvidence
    accounting: dict[str, int]


def build_hype_compression_alignment_markets(
    market: pd.DataFrame,
    *,
    frozen_policy_id: str,
) -> HypeCompressionAlignmentMarkets:
    """Build exact control, aligned, and opposed signal streams."""
    policy = _frozen_policy(frozen_policy_id)
    compressed, compression = _compressed_market(market, policy)
    markets, accounting = _cohort_markets(compressed)
    return HypeCompressionAlignmentMarkets(markets, compression, accounting)


def build_hype_compression_alignment_replay(
    development: pd.DataFrame,
    confirmation_segments: tuple[pd.DataFrame, ...],
    *,
    frozen_policy_id: str,
    config: HypeExitReplayConfig,
    fold_count: int = 5,
) -> HypeCompressionAlignmentReplay:
    """Replay alignment from signal time with the frozen v51 lifecycle contract."""
    _validate_fold_count(fold_count)
    if not confirmation_segments:
        raise ValueError("HYPE alignment replay requires confirmation segments")
    policy = _frozen_policy(frozen_policy_id)
    alignment = build_hype_compression_alignment_markets(
        development,
        frozen_policy_id=frozen_policy_id,
    )
    markets = alignment.markets
    developed = {
        cohort: _develop(markets[cohort], policy, cohort, config, fold_count)
        for cohort in _COHORTS
    }
    confirmation, confirmation_rows = _confirmation(
        confirmation_segments,
        policy,
        config,
    )
    report = _report(
        policy,
        config,
        fold_count,
        alignment.compression,
        alignment.accounting,
        developed,
        confirmation,
    )
    return HypeCompressionAlignmentReplay(
        report,
        _development_rows(developed),
        pd.DataFrame(confirmation_rows),
    )


def _compressed_market(
    market: pd.DataFrame,
    policy: HypeCompressionPolicy,
) -> tuple[pd.DataFrame, HypeCompressionEvidence]:
    signals = int(market["entry_side"].notna().sum())
    if signals == 0:
        return market.copy(), HypeCompressionEvidence(0, 0, 0)
    features = build_hype_entry_features(market)
    return apply_hype_compression_policy(market, features, policy)


def _cohort_markets(
    compressed: pd.DataFrame,
) -> tuple[dict[str, pd.DataFrame], dict[str, int]]:
    if "breakout_side" not in compressed:
        raise ValueError("HYPE alignment replay requires breakout_side")
    entry = compressed["entry_side"]
    breakout = compressed["breakout_side"]
    _validate_sides(entry, "entry_side")
    _validate_sides(breakout, "breakout_side")
    eligible = entry.isin(_SIDES)
    attributable = eligible & breakout.isin(_SIDES)
    aligned = attributable & entry.eq(breakout)
    opposed = attributable & entry.ne(breakout)
    masks = {"control": eligible, "aligned_only": aligned, "opposed_only": opposed}
    output: dict[str, pd.DataFrame] = {}
    for cohort, mask in masks.items():
        output[cohort] = compressed.copy()
        output[cohort]["entry_side"] = entry.where(mask, None)
    accounting = {
        "compression_eligible_onsets": int(eligible.sum()),
        "breakout_side_attributable": int(attributable.sum()),
        "aligned_onsets": int(aligned.sum()),
        "opposed_onsets": int(opposed.sum()),
        "unavailable_onsets": int((eligible & ~attributable).sum()),
    }
    return output, accounting


def _develop(
    market: pd.DataFrame,
    policy: HypeCompressionPolicy,
    cohort: str,
    config: HypeExitReplayConfig,
    fold_count: int,
) -> HypePolicyDevelopment:
    identity = HypeExitPolicy(f"{policy.policy_id}|{cohort}")
    return develop_hype_exit_policy(market, identity, config, fold_count)


def _confirmation(
    segments: tuple[pd.DataFrame, ...],
    policy: HypeCompressionPolicy,
    config: HypeExitReplayConfig,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    resolved: dict[str, list[HypeExitTrade]] = {cohort: [] for cohort in _COHORTS}
    censored = Counter[str]()
    occupied = Counter[str]()
    signals = Counter[str]()
    rows: list[dict[str, object]] = []
    for segment_number, segment in enumerate(segments, start=1):
        compressed, _ = _compressed_market(segment, policy)
        markets, _ = _cohort_markets(compressed)
        for cohort, market in markets.items():
            result = replay_hype_breakout_exits(
                market,
                HypeExitPolicy(f"{policy.policy_id}|{cohort}"),
                config,
            )
            occupied[cohort] += result.occupied_signals
            signals[cohort] += int(market["entry_side"].notna().sum())
            _collect_confirmation_rows(
                cohort, segment_number, result.trades, resolved, censored, rows
            )
    report = {
        cohort: {
            **_trade_summary(resolved[cohort]),
            "resolved_trades": len(resolved[cohort]),
            "censored_lifecycles": censored[cohort],
            "entry_signals": signals[cohort],
            "occupied_signals": occupied[cohort],
        }
        for cohort in _COHORTS
    }
    return report, rows


def _collect_confirmation_rows(
    cohort: str,
    segment: int,
    trades: tuple[HypeExitTrade, ...],
    resolved: dict[str, list[HypeExitTrade]],
    censored: Counter[str],
    rows: list[dict[str, object]],
) -> None:
    for trade in trades:
        is_censored = trade.exit_reason == "end_of_data"
        censored[cohort] += int(is_censored)
        if not is_censored:
            resolved[cohort].append(trade)
        rows.append(
            {
                "cohort": cohort,
                "segment": segment,
                "censored": is_censored,
                **asdict(trade),
            }
        )


def _report(
    policy: HypeCompressionPolicy,
    config: HypeExitReplayConfig,
    fold_count: int,
    compression: HypeCompressionEvidence,
    accounting: dict[str, int],
    developed: dict[str, HypePolicyDevelopment],
    confirmation: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "hype_compression_alignment_causal_replay_v1",
        "execution_authority": "none",
        "selection_performed": False,
        "automatic_promotion": False,
        "contract": {
            "frozen_compression_policy_id": policy.policy_id,
            "challenger_rule": "retain_only_structural_and_breakout_side_agreement",
            "execution": asdict(config),
        },
        "trial_accounting": {"development_arms": 3, "confirmation_arms": 3},
        "development_compression": asdict(compression),
        "development_entry_accounting": accounting,
        "development": {
            cohort: _development_summary(result, fold_count)
            for cohort, result in developed.items()
        },
        "later_confirmation": confirmation,
        "limitations": _limitations(),
    }


def _development_summary(
    developed: HypePolicyDevelopment,
    fold_count: int,
) -> dict[str, object]:
    report = developed.report
    return {
        **_trade_summary(list(report.trades)),
        "entry_signals": report.completed_trades + report.occupied_signals,
        "occupied_signals": report.occupied_signals,
        "reset_blocked_signals": report.reset_blocked_signals,
        "chronological_fold_count": fold_count,
        "chronological_fold_net_bps": list(developed.fold_net_bps),
        "positive_folds": developed.positive_folds,
        "median_fold_net_bps": developed.median_fold_net_bps,
    }


def _trade_summary(trades: list[HypeExitTrade]) -> dict[str, object]:
    ordered = sorted(trades, key=lambda trade: trade.entry_time_utc)
    values = [trade.net_return_bps for trade in ordered]
    profits = [value for value in values if value > 0.0]
    losses = [-value for value in values if value < 0.0]
    return {
        "completed_trades": len(ordered),
        "wins": len(profits),
        "losses": len(losses),
        "net_return_bps": sum(values),
        "profit_factor": sum(profits) / sum(losses) if losses else None,
        "maximum_drawdown_bps": _maximum_drawdown(values),
        "total_fee_bps": sum(trade.fee_bps for trade in ordered),
        "funding_bps": sum(trade.funding_bps for trade in ordered),
        "net_excluding_largest_winner_bps": sum(values) - max(profits, default=0.0),
        "exit_reasons": dict(
            sorted(Counter(trade.exit_reason for trade in ordered).items())
        ),
        "side_summary": {side: _side_summary(ordered, side) for side in _SIDES},
    }


def _side_summary(trades: list[HypeExitTrade], side: str) -> dict[str, object]:
    values = [trade.net_return_bps for trade in trades if trade.side == side]
    profits = [value for value in values if value > 0.0]
    losses = [-value for value in values if value < 0.0]
    return {
        "completed_trades": len(values),
        "wins": len(profits),
        "losses": len(losses),
        "net_return_bps": sum(values),
        "profit_factor": sum(profits) / sum(losses) if losses else None,
        "net_excluding_largest_winner_bps": sum(values) - max(profits, default=0.0),
    }


def _development_rows(
    developed: dict[str, HypePolicyDevelopment],
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"cohort": cohort, **asdict(trade)}
            for cohort, result in developed.items()
            for trade in result.report.trades
        ]
    )


def _frozen_policy(policy_id: str) -> HypeCompressionPolicy:
    matches = tuple(
        policy
        for policy in declared_hype_compression_policies()
        if policy.policy_id == policy_id and policy.policy_id != "hype_breakout_control"
    )
    if len(matches) != 1:
        raise ValueError("HYPE alignment replay requires one frozen compression policy")
    return matches[0]


def _validate_sides(values: pd.Series, label: str) -> None:
    invalid = values.notna() & ~values.isin(_SIDES)
    if invalid.any():
        raise ValueError(f"HYPE alignment {label} contains unsupported values")


def _validate_fold_count(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 2:
        raise ValueError("HYPE alignment fold_count must be at least two")


def _maximum_drawdown(values: list[float]) -> float:
    equity = peak = drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _limitations() -> list[str]:
    return [
        "the alignment mechanism was specified after inspecting subgroup attribution",
        "the later confirmation window was previously opened and is descriptive",
        "different retained signals causally change later per-asset occupancy",
        "one-minute OHLC and fixed slippage cannot reproduce every live IOC fill",
        "no result can route, size, retain, close, or promote a live position",
    ]
