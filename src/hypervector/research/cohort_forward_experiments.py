"""Frozen identities and causal cutoffs for one-blocker forward experiments."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, NamedTuple

from hypervector.research.cohort_one_blocker_execution_contract import OpiCohort

SourceAuthority = Literal["executable", "observe_only"]


class ForwardExperiment(NamedTuple):
    """Immutable identity and risk geometry for one prospective observer."""

    candidate_strategy_id: str
    source_strategy_id: str
    symbol: str
    blocker: str
    cutoff_time_ms: int
    funding_start_time_ms: int
    source_stop_policy: str
    source_stop_range_bps: tuple[float, float] | None
    stop_proxy_bps: float
    target_proxy_bps: float | None
    opi_cohort: OpiCohort = "all"
    notional_usd: float = 25.0
    source_authority: SourceAuthority = "executable"


_EXPERIMENTS = {
    "v2-fixed": ForwardExperiment(
        "hype_breakout_relaxed_60m_bidirectional_v2",
        "hype_breakout_onset_bidirectional_v1",
        "HYPE",
        "5m_not_breakout",
        1_785_869_880_000,
        1_785_869_880_000,
        "fixed_bps",
        None,
        80.0,
        None,
    ),
    "v3-target20": ForwardExperiment(
        "hype_breakout_relaxed_target20_60m_bidirectional_v3",
        "hype_breakout_onset_bidirectional_v1",
        "HYPE",
        "5m_not_breakout",
        1_785_872_820_000,
        1_785_869_880_000,
        "fixed_bps",
        None,
        80.0,
        20.0,
    ),
    "v4-fixed-matched": ForwardExperiment(
        "hype_breakout_relaxed_fixed60_matched_bidirectional_v4",
        "hype_breakout_onset_bidirectional_v1",
        "HYPE",
        "5m_not_breakout",
        1_785_872_820_000,
        1_785_869_880_000,
        "fixed_bps",
        None,
        80.0,
        None,
    ),
    "v5-btc-structural-fixed": ForwardExperiment(
        "btc_structural_continuation_fixed60_bidirectional_v1",
        "range_onset_bidirectional_v1",
        "BTC",
        "awaiting_hourly_sma_cross",
        1_785_886_080_000,
        1_785_886_080_000,
        "fixed_bps",
        None,
        60.0,
        None,
    ),
    "v6-hype-hulk-squeeze-fixed": ForwardExperiment(
        "hype_hulk_squeeze_relaxed_fixed60_bidirectional_v1",
        "hulk_expansion_bidirectional_tuned_v2",
        "HYPE",
        "squeeze_not_armed",
        1_785_891_480_000,
        1_785_891_480_000,
        "structural_clamped_bps",
        (20.0, 75.0),
        75.0,
        None,
    ),
    "v7-hype-range-absorption-fixed": ForwardExperiment(
        "hype_range_absorption_fixed60_bidirectional_v1",
        "range_onset_bidirectional_v1",
        "HYPE",
        "awaiting_hourly_sma_cross",
        1_785_894_300_000,
        1_785_894_300_000,
        "fixed_bps",
        None,
        60.0,
        None,
        "opposed",
    ),
    "v8-sol-aligned-range-fixed": ForwardExperiment(
        "sol_aligned_range_relaxed_fixed60_bidirectional_v1",
        "range_onset_bidirectional_v1",
        "SOL",
        "awaiting_hourly_sma_cross",
        1_785_901_500_000,
        1_785_901_500_000,
        "fixed_bps",
        None,
        60.0,
        None,
        "aligned",
        75.0,
    ),
    "v9-btc-hulk-flow-fixed": ForwardExperiment(
        "btc_hulk_money_flow_relaxed_fixed60_bidirectional_v1",
        "hulk_expansion_bidirectional_tuned_v2",
        "BTC",
        "money_flow_not_aligned",
        1_785_945_000_000,
        1_785_945_000_000,
        "structural_clamped_bps",
        (20.0, 75.0),
        75.0,
        None,
    ),
    "v10-hype-aligned-breakout-relaxation-fixed": ForwardExperiment(
        "hype_aligned_book_breakout_relaxation_fixed60_bidirectional_v1",
        "hype_breakout_onset_bidirectional_v1",
        "HYPE",
        "5m_not_breakout",
        1_786_054_080_000,
        1_786_054_080_000,
        "fixed_bps",
        None,
        80.0,
        None,
        "aligned",
        75.0,
    ),
    "v11-sol-aligned-breakout-relaxation-fixed": ForwardExperiment(
        "sol_aligned_book_breakout_relaxation_fixed60_bidirectional_v1",
        "hype_breakout_onset_bidirectional_v1",
        "SOL",
        "5m_not_breakout",
        1_786_054_080_000,
        1_786_054_080_000,
        "fixed_bps",
        None,
        80.0,
        None,
        "aligned",
        75.0,
    ),
    "v12-sol-hulk-expansion-trigger-fixed": ForwardExperiment(
        "sol_hulk_expansion_trigger_relaxed_fixed60_bidirectional_v1",
        "hulk_expansion_bidirectional_tuned_v2",
        "SOL",
        "expansion_trigger_not_present",
        1_786_078_920_000,
        1_786_078_920_000,
        "structural_clamped_bps",
        (20.0, 75.0),
        75.0,
        None,
        "all",
        75.0,
        "observe_only",
    ),
    "v13-spcx-swing-pivot-fixed": ForwardExperiment(
        "spcx_swing_pivot_relaxed_fixed60_bidirectional_v1",
        "hip3_swing_ha_sp500_spcx_bidirectional_v2",
        "xyz:SPCX",
        "pivot_break_state_missing",
        1_786_204_800_000,
        1_786_204_800_000,
        "fixed_bps",
        None,
        80.0,
        None,
        "aligned",
        75.0,
    ),
    "v14-sol-breakout-continuation-aligned-fixed": ForwardExperiment(
        "sol_breakout_continuation_aligned_fixed60_bidirectional_v1",
        "hype_breakout_onset_bidirectional_v1",
        "SOL",
        "awaiting_new_5m_breakout_onset",
        1_786_229_400_000,
        1_786_229_400_000,
        "fixed_bps",
        None,
        80.0,
        None,
        "aligned",
        75.0,
    ),
    "v15-sndk-swing-pivot-fixed": ForwardExperiment(
        "sndk_swing_pivot_relaxed_fixed60_bidirectional_v1",
        "hip3_swing_ha_sndk_gold_brent_bidirectional_v1",
        "xyz:SNDK",
        "pivot_break_state_missing",
        1_786_266_000_000,
        1_786_266_000_000,
        "fixed_bps",
        None,
        80.0,
        None,
        "all",
        75.0,
    ),
}

FORWARD_EXPERIMENT_NAMES = tuple(_EXPERIMENTS)


def forward_experiment(name: str) -> ForwardExperiment:
    """Return one exact frozen experiment or reject an unknown identity."""
    try:
        return _EXPERIMENTS[name]
    except KeyError as exc:
        raise ValueError(f"unknown forward experiment: {name}") from exc


def source_authority_matches(
    experiment: ForwardExperiment,
    execution_symbols: Sequence[str],
) -> bool:
    """Return whether a source remains in its frozen execution-authority cohort."""
    executable = experiment.symbol in execution_symbols
    if experiment.source_authority == "executable":
        return executable
    if experiment.source_authority == "observe_only":
        return not executable
    raise ValueError("forward experiment source authority is invalid")
