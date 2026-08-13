"""Latest immutable route-evidence rows that supersede older summaries."""

from typing import TypeAlias

EvidenceRow: TypeAlias = tuple[str, str, str, str, str, str, str]

_HULK = "hulk_expansion_bidirectional_tuned_v2"
_RANGE = "range_onset_bidirectional_v1"
_BTC_STRUCTURAL = "btc_structural_continuation_fixed60_bidirectional_v1"
_SOL_ALIGNED = "sol_aligned_range_relaxed_fixed60_bidirectional_v1"
_HULK_JOURNAL = "docs/research-journal/hulk-eth-hype-native-transfer-v1.json"
_RANGE_JOURNAL = "docs/research-journal/range-onset-btc-hype-timeframe-transfer-v1.json"
_SPCX_SIDE_JOURNAL = "docs/research-journal/spcx-side-mechanism-attribution-v1.json"
_ETH_SIDE_JOURNAL = "docs/research-journal/eth-breakout-precompression-pullback-v6.json"
_GOLD_SIDE_JOURNAL = "docs/research-journal/hip3-entry-timing-challenger-v3.json"
_BTC_SHORT_FORWARD = (
    "data/logs/research/20260811_hulk_short_robust_v3_btc_forward_nominal.json"
)
_BTC_LONG_FORWARD = (
    "data/logs/research/"
    "hypervelocity_liquidity_sweep_long_forward_20260730T1200_"
    "20260811T2300_trade_through_v1.json"
)
_BTC_LONG_TAKER_PARITY = (
    "data/logs/research/bidirectional_cohort/"
    "btc_liquidity_sweep_taker_parity_20260811_v2.json"
)
_HIP3_FRESH15_PARITY = (
    "docs/research-journal/hip3-index-preclose-pressure-parity-v3.json"
)


def recent_route_evidence_rows() -> tuple[EvidenceRow, ...]:
    """Return decisions that replace older unreviewed or unresolved evidence."""
    return (
        _btc_specialist_rows()
        + _hip3_corrected_rows()
        + _legacy_transfer_rows()
        + _prospective_rejection_rows()
        + _side_mechanism_rows()
    )


def _hip3_corrected_rows() -> tuple[EvidenceRow, ...]:
    return (
        _hip3_v3_row("xyz:SP500"),
        _hip3_v3_row("xyz:SPCX"),
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
    return (
        (
            "hulk_expansion_short_robust_v3",
            "BTC",
            "forward_exact_n1_repeatability_unproven",
            "low",
            "1 exact forward signal / 12.5 covered days",
            "The frozen short contract reached its 3R target after modeled "
            "costs without a liquidation. It remained positive under the "
            "tested cost stresses, but a two-bar entry delay lost and one "
            "event cannot establish repeatability.",
            _BTC_SHORT_FORWARD,
        ),
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
            "taker_parity_promising_path_unresolved",
            "low",
            "6 development signals / 92 days; 1 forward signal / 12.5 days",
            "The causal taker-IOC challenger at <=30s and a 60/60 bps stop/"
            "target produced 5W/1L in development and 1W/0L forward. The old "
            "exact fills were maker trade-through evidence, not taker fills; "
            "one development mark path remains unresolved and forward N=1 "
            "does not establish repeatability.",
            _BTC_LONG_TAKER_PARITY,
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
            "side_relation_set_falsified_new_mechanism_required",
            "medium",
            "338 fixed-720-minute trades across two chronological partitions",
            "Neither pooled side nor any of four side and breakout-relation "
            "arms survived both partitions after costs and largest-winner "
            "removal. Retain the 12-hour exit, but require a new causal "
            "mechanism identity for the next ETH challenger.",
            _ETH_SIDE_JOURNAL,
        ),
    )
