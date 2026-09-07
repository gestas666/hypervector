"""Latest immutable route-evidence rows that supersede older summaries."""

from typing import TypeAlias
from hypervector.live.hourly_price_evidence import hourly_price_evidence_rows

from hypervector.live.hype_native_breakout_provider import (
    HYPE_NATIVE_BREAKOUT_LONG_STRATEGY,
    HYPE_NATIVE_BREAKOUT_STRATEGY,
)

EvidenceRow: TypeAlias = tuple[str, str, str, str, str, str, str]

_HULK = "hulk_expansion_bidirectional_tuned_v2"
_RANGE = "range_onset_bidirectional_v1"
_HIP3_COMMODITY_FRESH15 = (
    "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2"
)
_HIP3_SNDK_FRESH15 = "hip3_breakout_pressure_sndk_fresh15s_bidirectional_v3"
_RESEARCH_PENDING_MARKET = "research_pending_market_observer_bidirectional_15m_v1"
_V76_ROSTER_EVIDENCE = (
    "data/logs/research/bidirectional_cohort/"
    "v76_seven_asset_roster_and_authority_20260901_v1.json"
)
_BTC_STRUCTURAL = "btc_structural_continuation_fixed60_bidirectional_v1"
_SOL_ALIGNED = "sol_aligned_range_relaxed_fixed60_bidirectional_v1"
_HULK_JOURNAL = "docs/research-journal/hulk-eth-hype-native-transfer-v1.json"
_RANGE_JOURNAL = "docs/research-journal/range-onset-btc-hype-timeframe-transfer-v1.json"
_SPCX_SIDE_JOURNAL = "docs/research-journal/spcx-side-mechanism-attribution-v1.json"
_ETH_SIDE_JOURNAL = (
    "docs/research-journal/eth-breakout-precompression-pullback-v17.json"
)
_GOLD_SIDE_JOURNAL = "docs/research-journal/hip3-entry-timing-challenger-v3.json"
_BTC_LONG_FORWARD = (
    "data/logs/research/"
    "hypervelocity_liquidity_sweep_long_forward_20260730T1200_"
    "20260811T2300_trade_through_v1.json"
)
_HIP3_FRESH15_PARITY = (
    "docs/research-journal/hip3-index-preclose-pressure-parity-v3.json"
)
_V58_OPPORTUNITY_AUDIT = (
    "docs/research-journal/v58-eight-asset-opportunity-coverage-audit-20260819-v1.json"
)
_V84_ROUTE_EVIDENCE = (
    "data/logs/research/bidirectional_cohort/"
    "v84_active_route_tui_evidence_refresh_20260903_v1.json"
)
_V86_BTC_SWEEP_CONTRACT_CORRECTION = (
    "data/logs/research/bidirectional_cohort/"
    "v86_btc_sweep_contract_evidence_correction_20260904_v1.json"
)


def recent_route_evidence_rows() -> tuple[EvidenceRow, ...]:
    """Return decisions that replace older unreviewed or unresolved evidence."""
    return (
        _btc_specialist_rows()
        + _hip3_corrected_rows()
        + _legacy_transfer_rows()
        + _prospective_rejection_rows()
        + _side_mechanism_rows()
        + _hype_alignment_rows()
        + _hype_native_rows()
        + _v58_commodity_rows()
        + _research_pending_market_rows()
        + _sndk_onset_correction_rows()
        + hourly_price_evidence_rows()
    )


def _sndk_onset_correction_rows() -> tuple[EvidenceRow, ...]:
    return (
        (
            _HIP3_SNDK_FRESH15,
            "xyz:SNDK",
            "entry_contract_discrepancy_confirmed",
            "high",
            "predecessor n2; exact v3 n0; four synthetic boundary mismatches",
            "Current v3 resets prior pressure and can refire a continuing breakout. "
            "The canonical research onset engine disagrees at all four tested "
            "boundaries. This establishes a technical defect, not realized loss attribution.",
            "docs/research-journal/portfolio-overhaul-sndk-onset-fidelity-20260905-v1.json",
        ),
        (
            "hip3_breakout_pressure_sndk_fresh15s_bidirectional_v4",
            "xyz:SNDK",
            "durable_onset_correction_economics_pending",
            "medium",
            "synthetic continuation/reset/restart validation; exact live n0",
            "V4 preserves prior pressure state and verifies exchange age and book "
            "coverage. Short direction, sizing, stop and hold remain frozen. "
            "Technical tests do not establish profitability; lifecycle and portfolio "
            "validation remain pending.",
            "docs/research-journal/portfolio-overhaul-sndk-durable-correction-20260905-v1.json",
        ),
    )


def _research_pending_market_rows() -> tuple[EvidenceRow, ...]:
    return (
        (
            _RESEARCH_PENDING_MARKET,
            "ETH",
            "tested_families_rejected_new_mechanism_required",
            "medium",
            "current 15m market data only; no executable strategy",
            "The tested ETH precompression and unchanged universal trend families "
            "did not establish cross-partition after-cost edge. Keep ETH visible "
            "while withholding entries until a new preregistered causal mechanism "
            "survives validation.",
            _V76_ROSTER_EVIDENCE,
        ),
        (
            _RESEARCH_PENDING_MARKET,
            "ZEC",
            "development_positive_largest_winner_dependent",
            "low",
            "two frozen development mechanisms; validation unopened",
            "Both unchanged ZEC transfer screens were positive before removing "
            "their largest winner and negative afterward. Keep ZEC visible with "
            "no entry authority; do not spend validation on either failed shape.",
            _V76_ROSTER_EVIDENCE,
        ),
        (
            _RESEARCH_PENDING_MARKET,
            "xyz:SPCX",
            "side_timing_set_falsified_new_mechanism_required",
            "medium",
            "eight tested timing/side arms plus failed cash-open transfer",
            "The tested SPCX timing/side set did not repeat after costs across "
            "partitions. Keep SPCX visible while withholding entries until a new "
            "causal mechanism clears sealed validation.",
            _V76_ROSTER_EVIDENCE,
        ),
    )


def _v58_commodity_rows() -> tuple[EvidenceRow, ...]:
    return (
        (
            _HIP3_SNDK_FRESH15,
            "xyz:SNDK",
            "predecessor_n2_positive_exact_v3_n0",
            "low",
            "zero exact v3 closes; semantic predecessor 2 closes",
            "The current v3 identity has zero resolved closes. Its semantic predecessor "
            "produced 1W/1L and +$18.30 net, but became -$6.24 after removing "
            "the largest winner and included an operator close. Keep short-only "
            "probation while treating exact v3 expectancy as unmeasured.",
            _V84_ROUTE_EVIDENCE,
        ),
        (
            _HIP3_COMMODITY_FRESH15,
            "xyz:SNDK",
            "identity_and_side_mismatch_no_current_edge_evidence",
            "low",
            "current short identity has no exact lifecycle cadence",
            "The older route produced two long protective-stop losses totaling "
            "-$1.343329. Those outcomes are not the current short-only identity "
            "and cannot establish current expectancy or cadence.",
            _V58_OPPORTUNITY_AUDIT,
        ),
        (
            _HIP3_COMMODITY_FRESH15,
            "xyz:BRENTOIL",
            "older_route_negative_and_current_identity_unmeasured",
            "low",
            "current identity has no stable exact lifecycle cadence",
            "The older breakout route produced 1W/1L, -$0.232469 net, PF "
            "0.6621, and -$0.687962 excluding its largest winner. The current "
            "identity remains unmeasured.",
            _V58_OPPORTUNITY_AUDIT,
        ),
    )


def _hype_native_rows() -> tuple[EvidenceRow, ...]:
    return (
        (
            HYPE_NATIVE_BREAKOUT_STRATEGY,
            "HYPE",
            "live_seed_promising_history_contradictory",
            "low_to_medium",
            "7 exact early HYPE-only closes; current prospective cadence unverified",
            "The isolated early HYPE-only slice was 6W/1L, +$2.160920, PF "
            "10.6505, and +$1.261432 excluding its largest winner. The generic "
            "one-year control was negative, and later sizing/profile revisions "
            "lost; this new identity is a prospective reconstruction, not proven edge.",
            "docs/research-journal/"
            "v54-hype-native-breakout-reconstruction-proposal-v1.json",
        ),
        (
            HYPE_NATIVE_BREAKOUT_LONG_STRATEGY,
            "HYPE",
            "directional_challenger_report_only",
            "low",
            "1,025 development bidirectional trades; 532 long-only trades",
            "Full-occupancy development remained negative, but long-only improved "
            "on bidirectional by 5,189.82 bps and materially outperformed short-only. "
            "The already-opened block was long-only positive but winner-dependent; "
            "this supports report-only directional isolation, not proven edge.",
            "docs/research-journal/"
            "v54-hype-native-directional-authority-challenger-v1.json",
        ),
    )


def _hype_alignment_rows() -> tuple[EvidenceRow, ...]:
    return (
        (
            "hype_breakout_compression_alignment_bidirectional_v2",
            "HYPE",
            "development_promising_exact_live_n2_mixed",
            "low",
            "41 causal development trades; 2 exact live closes",
            "The occupancy-aware aligned-only replay produced PF 1.8569, "
            "+2,298.23 bps, 3/5 positive folds, and +289.26 bps after removing "
            "its largest winner. Exact live long was 1W/1L and +$6.34 net, but "
            "-$46.43 excluding its largest winner. Forward repeatability remains "
            "sparse and generic profit locks remain rejected.",
            _V84_ROUTE_EVIDENCE,
        ),
    )


def _hip3_corrected_rows() -> tuple[EvidenceRow, ...]:
    return (
        _hip3_v3_row("xyz:SP500"),
        _hip3_v3_row("xyz:SPCX"),
        (
            "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1",
            "xyz:SPCX",
            "development_positive_technically_unresolved",
            "low",
            "20 trades / development window (~3.94/week); OOS sealed",
            "Development stress replay was +$418.13 at PF 1.815 and +$225.28 "
            "excluding its largest winner. Eleven entry lifecycles remain "
            "technically unresolved, so this is an aggressive forward trial, "
            "not established edge.",
            "data/logs/research/"
            "xyz_spcx_cash_open_gap_reversal_development_20260817_v2.json",
        ),
        (
            "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v2",
            "xyz:SP500",
            "fresh15_v2_parity_defect_retired",
            "high",
            "v2 threshold narrowed, but exchange-age/count/onset parity remained broken",
            "The v2 provider used receipt-time freshness, accepted one book, "
            "and rebuilt prior pressure as zero. It is retired from qualification. "
            "The isolated v3 observer uses exchange-boundary age, at least two "
            "books, and persisted prior onset state; it has no execution authority.",
            _HIP3_FRESH15_PARITY,
        ),
        (
            "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v2",
            "xyz:SPCX",
            "fresh15_v2_parity_defect_retired",
            "high",
            "v2 technical parity invalid; SPCX validation also stress-negative",
            "The v2 route is not corrected forward evidence because its pressure "
            "time and onset state do not match the archive contract. SPCX's "
            "frozen validation was stress-negative. Distinct v3 collection is "
            "report-only and cannot inherit the open legacy-v1 lifecycle.",
            _HIP3_FRESH15_PARITY,
        ),
    )


def _hip3_v3_row(symbol: str) -> EvidenceRow:
    return (
        "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3",
        symbol,
        "prospective_v3_technical_parity_live_outcomes_unresolved",
        "low",
        "prospective observer active; no resolved v3 live outcomes at review cutoff",
        "The v3 adapter repairs exchange-boundary freshness, minimum book count, "
        "and persisted prior-onset state. Technical parity does not establish "
        "profitable edge. Retired v2 and legacy-v1 outcomes cannot be relabeled "
        "as v3 evidence.",
        _HIP3_FRESH15_PARITY,
    )


def _btc_specialist_rows() -> tuple[EvidenceRow, ...]:
    return _btc_hulk_rows() + _btc_liquidity_sweep_rows()


def _btc_hulk_rows() -> tuple[EvidenceRow, ...]:
    return (
        (
            "hulk_expansion_short_tuned_v2",
            "BTC",
            "exact_btc_partitions_mixed_live_probation",
            "low_to_medium",
            "59 exact BTC historical trades / 338 covered days; 3 exact live closes",
            "BTC-only development was 34 trades, +$736.86, PF 1.9158; "
            "validation was 16 trades, +$495.53, PF 2.3624; pseudo-holdout "
            "9 trades, -$111.49, PF 0.6570. Cost stress remained positive "
            "but overlaps later chronology. SOL rows excluded: the prior "
            "106-trade summary pooled another asset. Exact live was 1W/2L, "
            "-$63.04, PF 0.4962. Keep reduced-size probation; no established edge.",
            _V84_ROUTE_EVIDENCE,
        ),
        (
            "hulk_expansion_short_robust_v3",
            "BTC",
            "historical_mixed_exact_live_n2_negative",
            "low",
            "66 frozen historical BTC trades / 338 covered days; 2 exact live closes",
            "The V77 component-exit repair improved every frozen partition, but "
            "the 9-trade pseudo-holdout remained -$11.97. Exact live was 0W/2L, "
            "-$113.13, PF 0.0, with $12.91 fees. Retain only reduced-size "
            "probation; N2 repeatability and future expectancy remain unverified.",
            _V84_ROUTE_EVIDENCE,
        ),
    )


def _btc_liquidity_sweep_rows() -> tuple[EvidenceRow, ...]:
    return (
        (
            "liquidity_sweep_long_1h_stop60_v1",
            "BTC",
            "maker_forward_n1_runtime_taker_mismatch",
            "low",
            "1 exact forward signal / 12.5 covered days",
            "The one observed liquidity-sweep long reached its fixed target "
            "through a maker post-only trade-through fill. It was not a "
            "causal taker entry and therefore does not match the v43 taker-IOC "
            "runtime contract; one event also cannot establish repeatability.",
            _BTC_LONG_FORWARD,
        ),
        (
            "liquidity_sweep_long_1h_stop60_target60_v2",
            "BTC",
            "historical_candidate_current_20bp_entry_contract_unmeasured",
            "low",
            "6 development + 1 forward historical signals; 2 pre-cap live "
            "closes; 0 current 20-bps-contract closes",
            "The causal taker-IOC challenger at <=30s and a 60/60 bps stop/"
            "target produced 5W/1L in development and 1W/0L forward. Older "
            "replay fills were maker trade-through evidence, not taker parity. "
            "Live execution was 1W/1L, -$8.37, PF 0.7583 under the pre-cap "
            "contract; the loss entered 31.44 bps beyond the backend reference. "
            "V86 retains the 20-bps entry IOC cap and has zero compatible closes, "
            "so current-contract repeatability remains unverified.",
            _V86_BTC_SWEEP_CONTRACT_CORRECTION,
        ),
    )


def _legacy_transfer_rows() -> tuple[EvidenceRow, ...]:
    return (
        (
            _HULK,
            "ETH",
            "historical_native_transfer_negative",
            "medium",
            "100 continuous trades / 365 covered days",
            "The unchanged native-candle transfer lost $1,394.24 at PF 0.5919; "
            "both long and short directions were negative, and every "
            "chronological segment lost after modeled costs.",
            _HULK_JOURNAL,
        ),
        (
            _HULK,
            "HYPE",
            "historical_native_transfer_negative",
            "medium",
            "97 continuous trades / 365 covered days",
            "The unchanged native-candle transfer lost $1,819.30 at PF 0.4639; "
            "both long and short directions were negative, and every "
            "chronological segment lost after modeled costs.",
            _HULK_JOURNAL,
        ),
        (
            _RANGE,
            "BTC",
            "historical_timeframe_route_negative",
            "medium",
            "106 hourly-source trades / 365 covered days",
            "The exact hourly-source route produced 106 trades and lost "
            "$582.43 at PF 0.8440; both directions lost over the continuous "
            "year despite positive later slices.",
            _RANGE_JOURNAL,
        ),
        (
            _RANGE,
            "HYPE",
            "historical_timeframe_route_contradictory",
            "medium",
            "56 hourly-source trades / 365 covered days",
            "The route made $260.15 at PF 1.0942, but long lost $1,156.32, "
            "four short winners carried the result, and the pseudo-holdout "
            "lost $119.19 at PF 0.6759.",
            _RANGE_JOURNAL,
        ),
    )


def _prospective_rejection_rows() -> tuple[EvidenceRow, ...]:
    return (
        (
            _BTC_STRUCTURAL,
            "BTC",
            "prospective_rejected_n11",
            "medium",
            "11 resolved forward paths; all long and position-overlapping",
            "The frozen forward rule produced 4W/7L, -77.3943 bps, and PF "
            "0.4794. Every path overlapped an existing BTC position, so no "
            "portfolio-deployable benefit was observed.",
            "docs/research-journal/btc-structural-continuation-v1.json",
        ),
        (
            _SOL_ALIGNED,
            "SOL",
            "prospective_rejected_n9",
            "medium",
            "9 resolved forward paths; all long and portfolio-deployable",
            "The frozen aligned-range fixed-60 rule produced 4W/5L, "
            "-113.0855 bps, and PF 0.3472. The earlier N4 gain was stale; all "
            "nine paths were deployable, all-long, and no short path resolved.",
            "docs/research-journal/sol-aligned-range-v1.json",
        ),
    )


def _side_mechanism_rows() -> tuple[EvidenceRow, ...]:
    return (
        (
            "hip3_swing_ha_sp500_spcx_bidirectional_v2",
            "xyz:SPCX",
            "side_timing_set_falsified_new_mechanism_required",
            "medium",
            "eight timing/side arms across development and validation",
            "All eight timing/side arms across provider, alignment-onset, "
            "next-bar-confirmation, and fast-EMA pullback failed "
            "cross-partition after-cost repeatability. "
            "Do not repeat a static side/timing split; the next SPCX challenger "
            "requires a new causal mechanism identity.",
            _SPCX_SIDE_JOURNAL,
        ),
        (
            "hip3_swing_ha_sndk_gold_brent_bidirectional_v1",
            "xyz:GOLD",
            "side_timing_set_falsified_new_mechanism_required",
            "medium",
            "eight timing/side arms across development and validation",
            "Zero of eight provider, alignment-onset, next-bar-confirmation, "
            "or fast-EMA-pullback long/short arms survived both partitions, "
            "nominal/stress costs, and largest-winner removal. Do not repeat "
            "a static side/timing split; the next GOLD challenger requires a "
            "new causal mechanism identity.",
            _GOLD_SIDE_JOURNAL,
        ),
        (
            "eth_breakout_precompression_pullback_bidirectional_v1",
            "ETH",
            "prospective_requalification_open_long_only",
            "low",
            "two exact eligible long lifecycles; zero exact short lifecycles",
            "Revision 7 reopened only report-only requalification of the "
            "unchanged pooled mechanism after new evidence. The first exact "
            "long stopped and the second exact long remains open; zero short "
            "lifecycles exist. Retain the 12-hour exit and claim no edge or "
            "live authority.",
            _ETH_SIDE_JOURNAL,
        ),
    )
