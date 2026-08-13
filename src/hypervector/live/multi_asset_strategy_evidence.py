"""Report-only research evidence bound to cohort provider-symbol mappings."""

from __future__ import annotations

from dataclasses import replace

from hypervector.live.btc_structural_contract import BTC_STRUCTURAL_FIXED60_STRATEGY
from hypervector.live.eth_breakout_transfer_provider import (
    ETH_BREAKOUT_TRANSFER_STRATEGY,
)
from hypervector.live.hype_relaxed_contract import (
    HYPE_RELAXED_FIXED_STRATEGY,
    HYPE_RELAXED_MATCHED_FIXED_STRATEGY,
    HYPE_RELAXED_TARGET20_STRATEGY,
)
from hypervector.live.hype_breakout_retest_provider import (
    HYPE_BREAKOUT_RETEST_STRATEGY,
)
from hypervector.live.hype_breakout_compression_provider import (
    HYPE_COMPRESSION_BREAKOUT_STRATEGY,
)
from hypervector.live.multi_asset_live_config import StrategyProviderConfig
from hypervector.live.multi_asset_strategy_directional_evidence import (
    directional_evidence_rows,
)
from hypervector.live.multi_asset_strategy_evidence_models import (
    StrategyDirectionalEvidence,
    StrategyResearchEvidence,
)
from hypervector.live.multi_asset_strategy_evidence_recent import (
    recent_route_evidence_rows,
)
from hypervector.live.sol_aligned_range_contract import (
    SOL_ALIGNED_RANGE_FIXED60_STRATEGY,
)

_HULK = "hulk_expansion_bidirectional_tuned_v2"
_RANGE = "range_onset_bidirectional_v1"
_SOURCE = "hypervelocity_source_follow_bidirectional_5m_v1"
_HYPE = "hype_breakout_onset_bidirectional_v1"
_HYPE_RELAXED_V1 = "hype_breakout_relaxed_60m_bidirectional_v1"
_HIP3_SWING_INDEX = "hip3_swing_ha_sp500_spcx_bidirectional_v2"
_HIP3_BREAKOUT_INDEX = "hip3_breakout_pressure_sp500_spcx_bidirectional_v1"
_HIP3_SWING_COMMODITY = "hip3_swing_ha_sndk_gold_brent_bidirectional_v1"
_HIP3_BREAKOUT_COMMODITY = "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1"
_HIP3_V25_DIAGNOSTIC = (
    "data/logs/research/hip3_v25_lifecycle_bar_diagnostic_20260807.json"
)


_EVIDENCE = {
    (_HULK, "BTC"): StrategyResearchEvidence(
        _HULK,
        "BTC",
        "contradictory",
        "high",
        "110 trades / 337 covered days (~2.3/week)",
        "BTC was positive in development and validation but negative in the "
        "pseudo-holdout; the short-only survivor is a different provider.",
        "docs/reviews/2026-08-01-market-cipher-strategy-rehabilitation.md",
    ),
    (_HULK, "SOL"): StrategyResearchEvidence(
        _HULK,
        "SOL",
        "contradictory",
        "high",
        "104 trades / 337 covered days (~2.2/week)",
        "SOL failed validation materially and does not have stable evidence "
        "under this bidirectional provider contract.",
        "docs/reviews/2026-08-01-market-cipher-strategy-rehabilitation.md",
    ),
    (_RANGE, "SOL"): StrategyResearchEvidence(
        _RANGE,
        "SOL",
        "historical_candidate",
        "medium",
        "42 trades / 201 covered days (~1.5/week)",
        "Both directions were positive across the accepted clean blocks, with "
        "long profits concentrated in a small number of winners.",
        "docs/reviews/2026-07-31-sol-range-onset-direction-stability.md",
    ),
    (_RANGE, "ETH"): StrategyResearchEvidence(
        _RANGE,
        "ETH",
        "directional_candidate",
        "medium",
        "45 long trades; 86 baseline / 70 dual-MTF trades over 365 covered days",
        "ETH long was positive in all three segments while baseline short was "
        "mixed. The report-only dual-MTF audit retained 15/17 winners and "
        "94.7% of baseline gross profit, excluded 14/69 losses, and improved "
        "continuous PF from 1.513 to 1.841. The next-run profile explicitly "
        "uses that symmetric condition; it was specified after a live loss.",
        "data/logs/research/"
        "range_onset_context_challenger_ETH_20250728_20260728_v2.json",
        directional_evidence=(
            StrategyDirectionalEvidence(
                "long",
                "historical_candidate",
                "medium",
                "45 trades / 365 covered days; 3 chronological segments",
                "After modeled costs: development +$623.84 PF 1.595; validation "
                "+$281.24 PF 1.547; pseudo-holdout +$570.44 PF 6.378. The "
                "pseudo-holdout contains only 5 trades.",
                "data/logs/research/"
                "multi_asset_range_onset_shape_surface_ETH_20250728_20260728_"
                "v2_by_side_posthoc.json",
            ),
            StrategyDirectionalEvidence(
                "short",
                "contradictory",
                "medium",
                "41 trades / 365 covered days; 3 chronological segments",
                "After modeled costs: development -$1,105.52 PF 0.094; validation "
                "+$1,475.10 PF 6.602; pseudo-holdout -$75.71 PF 0.710.",
                "data/logs/research/"
                "multi_asset_range_onset_shape_surface_ETH_20250728_20260728_"
                "v2_by_side_posthoc.json",
            ),
        ),
    ),
    (_SOURCE, "BTC"): StrategyResearchEvidence(
        _SOURCE,
        "BTC",
        "historical_deployed_shape_negative",
        "medium",
        "782 trades / 365 days (~2.1/day); 815 eligible signals",
        "Exact deployed-shape replay ended -$17.82 with PF 0.6193 after "
        "$13.08 fees; 571 targets did not offset 208 wider stops.",
        "data/logs/research/source_follow_deployed_shape_btc_1y_20260804.json",
        directional_evidence=(
            StrategyDirectionalEvidence(
                "long",
                "historical_deployed_shape_negative",
                "medium",
                "365 trades / 365 covered days",
                "261W/104L, -$9.9154 net, PF 0.5707 under the deployed shape.",
                "data/logs/research/source_follow_deployed_shape_btc_1y_20260804.json",
            ),
            StrategyDirectionalEvidence(
                "short",
                "historical_deployed_shape_negative",
                "medium",
                "417 trades / 365 covered days",
                "310W/107L, -$7.9083 net, PF 0.6667 under the deployed shape.",
                "data/logs/research/source_follow_deployed_shape_btc_1y_20260804.json",
            ),
        ),
    ),
    (_HYPE, "BTC"): StrategyResearchEvidence(
        _HYPE,
        "BTC",
        "unstable_recent_short_observer",
        "low",
        "669 development + 121 final-60-day fixed-eight-hour trades",
        "The unchanged transfer was negative in development (PF 0.7873, "
        "-7,068.02 bps) but positive in the opened final-60-day block "
        "(PF 1.2211, +1,064.83 bps). Recent profit came entirely from shorts, "
        "whose development result was PF 0.7777 and -3,930.95 bps; observe "
        "prospectively without execution authority.",
        "docs/reviews/2026-08-05-hype-breakout-cross-asset-transfer.md",
        directional_evidence=(
            StrategyDirectionalEvidence(
                "long",
                "historical_transfer_negative",
                "medium",
                "58 trades / opened final 60 days",
                "Recent long transfer produced PF 0.9270 and -165.56 bps.",
                "docs/reviews/2026-08-05-hype-breakout-cross-asset-transfer.md",
            ),
            StrategyDirectionalEvidence(
                "short",
                "regime_sensitive_observer",
                "low",
                "339 development + 63 opened final-60-day trades",
                "Shorts reversed from development PF 0.7777 and -3,930.95 bps "
                "to recent PF 1.4831 and +1,230.40 bps.",
                "docs/reviews/2026-08-05-hype-breakout-cross-asset-transfer.md",
            ),
        ),
    ),
    (_HYPE, "ETH"): StrategyResearchEvidence(
        _HYPE,
        "ETH",
        "historical_transfer_rejected",
        "medium",
        "797 development + 154 final-60-day fixed-eight-hour trades",
        "The unchanged transfer was negative after modeled costs in both "
        "development (PF 0.8426, -7,679.54 bps) and the opened final-60-day "
        "block (PF 0.8220, -1,593.88 bps), including both directions.",
        "docs/reviews/2026-08-05-hype-breakout-cross-asset-transfer.md",
    ),
    (_HYPE, "SOL"): StrategyResearchEvidence(
        _HYPE,
        "SOL",
        "historical_transfer_rejected",
        "medium",
        "854 development + 162 final-60-day fixed-eight-hour trades",
        "The unchanged transfer was materially negative after modeled costs "
        "in development (PF 0.8336, -8,948.62 bps) and the opened final-60-day "
        "block (PF 0.6344, -3,596.19 bps), including both directions.",
        "docs/reviews/2026-08-05-hype-breakout-cross-asset-transfer.md",
    ),
    (_HYPE, "HYPE"): StrategyResearchEvidence(
        _HYPE,
        "HYPE",
        "historical_deployed_shape_negative",
        "medium",
        "2,029 raw onsets / 365 days; 956 development + 200 opened-holdout "
        "trades under the deployed extension",
        "Exact 8h-to-24h extension replay was negative in development "
        "(PF 0.8524, -9,756.73 bps) and the already-opened 60-day holdout "
        "(PF 0.9629, -495.98 bps). A 1,011-trade development audit of 5m "
        "intensity found no cost-clearing feature among strength, BBWP, EMA "
        "gap, or breakout volume. Modeled friction and regime-supported "
        "holding did not establish edge.",
        "docs/reviews/2026-08-04-hype-authoritative-5m-entry-attribution.md",
    ),
    (HYPE_COMPRESSION_BREAKOUT_STRATEGY, "HYPE"): StrategyResearchEvidence(
        HYPE_COMPRESSION_BREAKOUT_STRATEGY,
        "HYPE",
        "development_positive_fold_unstable_confirmation_concentrated",
        "low",
        "138 development trades / 5 folds; 4 later-confirmation trades",
        "The frozen 50/40 compression arm produced development PF 1.1146 and "
        "+1,044.36 bps, but only 2/5 folds were positive and its median fold "
        "was -202.36 bps. Later confirmation produced PF 2.4102 and +255.91 "
        "bps, but became -96.19 bps after removing its largest winner.",
        "data/logs/research/"
        "hype_compression_breakout_challenger_20260811_v4/report.json",
    ),
    (HYPE_BREAKOUT_RETEST_STRATEGY, "HYPE"): StrategyResearchEvidence(
        HYPE_BREAKOUT_RETEST_STRATEGY,
        "HYPE",
        "live_entry_revision_unresolved",
        "low",
        "zero resolved retest-v2 live trades at staging",
        "Fresh 5m breakouts now arm a three-bar 1m retest window; actual breakout "
        "direction is authoritative and the frozen immediate-entry v1 remains an "
        "observe-only control. This policy has no resolved live outcome yet.",
        "tests/test_hype_breakout_retest_provider.py",
    ),
    (ETH_BREAKOUT_TRANSFER_STRATEGY, "ETH"): StrategyResearchEvidence(
        ETH_BREAKOUT_TRANSFER_STRATEGY,
        "ETH",
        "prospective_transfer_candidate",
        "low",
        "282 development + 56 opened final-60-day trades",
        "Prior BBWP compression plus a directional pullback, 60 bps stop, and "
        "12-hour hold produced development PF 1.1111 and +1,657.98 bps with "
        "4/5 positive folds, then opened-final-block PF 1.1208 and +322.33 bps. "
        "Observe prospectively; bar replay does not establish executable edge.",
        "docs/reviews/2026-08-06-eth-breakout-transfer-canary-qualification.md",
    ),
    (_HYPE_RELAXED_V1, "HYPE"): StrategyResearchEvidence(
        _HYPE_RELAXED_V1,
        "HYPE",
        "forward_diagnostic_n2",
        "low",
        "2 resolved non-overlapping forward executions after the frozen cutoff",
        "The exact 5m_not_breakout paths produced one win and one fee-flipped "
        "loss for +18.2742 bps total net. Both were long and 92.2% of absolute "
        "outcome came from the first, so v1 is diagnostic rather than promotable.",
        "docs/reviews/2026-08-04-live-executable-opportunity-matrix.md",
    ),
    (HYPE_RELAXED_FIXED_STRATEGY, "HYPE"): StrategyResearchEvidence(
        HYPE_RELAXED_FIXED_STRATEGY,
        "HYPE",
        "prospective_fixed_horizon_candidate_n1",
        "low",
        "1 resolved post-cutoff long with 75-minute accepted-entry spacing",
        "V2 resolved +8.7264 bps net after fees and funding. It remained "
        "long-only with 100% outcome concentration and therefore does not "
        "establish repeatable edge.",
        "data/logs/research/"
        "cohort_hype_relaxed_v2_forward_resolution_20260804T2002Z.json",
    ),
    (HYPE_RELAXED_TARGET20_STRATEGY, "HYPE"): StrategyResearchEvidence(
        HYPE_RELAXED_TARGET20_STRATEGY,
        "HYPE",
        "prospective_target_first_falsified_n3",
        "low",
        "3 resolved post-cutoff longs; 20 bps target with 60m fallback",
        "V3 produced two target wins and one fixed-horizon loss (2W/1L) for "
        "-15.5073 bps total net and PF 0.6738. It remains long-only, the loss "
        "contributes 59.7% of absolute outcomes, and it is not staged.",
        "data/logs/research/cohort_hype_target20_v3_resolution_n3_20260804T2314Z.json",
    ),
    (HYPE_RELAXED_MATCHED_FIXED_STRATEGY, "HYPE"): StrategyResearchEvidence(
        HYPE_RELAXED_MATCHED_FIXED_STRATEGY,
        "HYPE",
        "prospective_matched_fixed_horizon_candidate_n3",
        "low",
        "N3 matched post-cutoff longs with 75-minute accepted-entry spacing",
        "Matched fixed-60 exits produced N3, 2W/1L, +8.9711 bps net, and PF 1.1887. "
        "The batch was all-long and one loss contributed 45.7% of absolute "
        "outcomes, so this is a live candidate rather than established edge.",
        "data/logs/research/"
        "cohort_hype_fixed60_matched_v4_resolution_n3_20260804T2318Z.json",
    ),
    (BTC_STRUCTURAL_FIXED60_STRATEGY, "BTC"): StrategyResearchEvidence(
        BTC_STRUCTURAL_FIXED60_STRATEGY,
        "BTC",
        "retrospective_candidate_prospective_unresolved",
        "low",
        "N10 retrospective fixed-60 paths; prospective N0 with one pending path",
        "Removing only awaiting_hourly_sma_cross produced retrospective N10, "
        "6W/4L, +83.2546 bps, and PF 2.8098. The sample was all-long; the "
        "frozen prospective N0 path is unresolved and conflicts with an existing "
        "BTC position, so forward repeatability is unproven.",
        "data/logs/research/cohort_execution_opportunity_matrix_20260804T2325Z_v3.json",
    ),
    (SOL_ALIGNED_RANGE_FIXED60_STRATEGY, "SOL"): StrategyResearchEvidence(
        SOL_ALIGNED_RANGE_FIXED60_STRATEGY,
        "SOL",
        "prospective_live_candidate_n4",
        "low",
        "4 deployable fixed-60 paths after the frozen live cutoff",
        "Side-aligned live L2 pressure produced 3W/1L, +31.1801 bps net, and "
        "PF 3.2251. The sample is all-long and the largest outcome contributes "
        "51.3% of absolute results, so the small next-flat canary is an "
        "information-gathering experiment rather than established edge.",
        "docs/reviews/2026-08-05-live-portfolio-selective-allocation.md",
    ),
    (_HIP3_SWING_INDEX, "xyz:SP500"): StrategyResearchEvidence(
        _HIP3_SWING_INDEX,
        "xyz:SP500",
        "v25_lifecycle_diagnostic_stress_negative",
        "medium",
        "8 nominal and 8 stress validation lifecycles",
        "The exact-entry fixed-80/24h 15m independent-asset approximation produced "
        "nominal -$1.0192 PF 0.4145 and stress -$1.1908 PF 0.3521. This is not "
        "live parity; the index Swing route aggregate was not stress-positive.",
        _HIP3_V25_DIAGNOSTIC,
    ),
    (_HIP3_SWING_INDEX, "xyz:SPCX"): StrategyResearchEvidence(
        _HIP3_SWING_INDEX,
        "xyz:SPCX",
        "v25_lifecycle_diagnostic_positive_unrouted",
        "medium",
        "21 nominal and 22 stress validation lifecycles",
        "The exact-entry fixed-80/24h 15m independent-asset approximation produced "
        "nominal +$2.7716 PF 1.2967 and stress +$1.1878 PF 1.1124. This is not "
        "live parity; the index Swing route aggregate was not stress-positive.",
        _HIP3_V25_DIAGNOSTIC,
    ),
    (_HIP3_BREAKOUT_INDEX, "xyz:SP500"): StrategyResearchEvidence(
        _HIP3_BREAKOUT_INDEX,
        "xyz:SP500",
        "v25_lifecycle_diagnostic_positive_unrouted",
        "medium",
        "13 nominal and 13 stress validation lifecycles",
        "The exact-entry fixed-80/24h 15m independent-asset approximation produced "
        "nominal +$0.9830 PF 1.7641 and stress +$0.6615 PF 1.4539. This is not "
        "live parity; the index Breakout route aggregate was not stress-positive.",
        _HIP3_V25_DIAGNOSTIC,
    ),
    (_HIP3_BREAKOUT_INDEX, "xyz:SPCX"): StrategyResearchEvidence(
        _HIP3_BREAKOUT_INDEX,
        "xyz:SPCX",
        "v25_lifecycle_diagnostic_stress_negative",
        "medium",
        "17 nominal and 17 stress validation lifecycles",
        "The exact-entry fixed-80/24h 15m independent-asset approximation produced "
        "nominal -$0.0639 PF 0.9920 and stress -$0.7825 PF 0.9071. This is not "
        "live parity; the index Breakout route aggregate was not stress-positive.",
        _HIP3_V25_DIAGNOSTIC,
    ),
    (_HIP3_SWING_COMMODITY, "xyz:SNDK"): StrategyResearchEvidence(
        _HIP3_SWING_COMMODITY,
        "xyz:SNDK",
        "v25_lifecycle_diagnostic_stress_negative",
        "medium",
        "31 nominal and 31 stress validation lifecycles",
        "The exact-entry fixed-80/24h independent-asset approximation produced "
        "nominal -$1.1362 PF 0.9267 and stress -$6.6113 PF 0.6600. The commodity "
        "Swing route aggregate was negative; this diagnostic is not live parity.",
        _HIP3_V25_DIAGNOSTIC,
    ),
    (_HIP3_SWING_COMMODITY, "xyz:GOLD"): StrategyResearchEvidence(
        _HIP3_SWING_COMMODITY,
        "xyz:GOLD",
        "v25_lifecycle_diagnostic_positive_unrouted",
        "medium",
        "19 nominal and 19 stress validation lifecycles",
        "The exact-entry fixed-80/24h independent-asset approximation produced "
        "nominal +$0.7620 PF 1.1064 and stress +$0.3904 PF 1.0530. The commodity "
        "Swing route aggregate was negative; this diagnostic is not live parity.",
        _HIP3_V25_DIAGNOSTIC,
    ),
    (_HIP3_SWING_COMMODITY, "xyz:BRENTOIL"): StrategyResearchEvidence(
        _HIP3_SWING_COMMODITY,
        "xyz:BRENTOIL",
        "v25_lifecycle_diagnostic_stress_negative",
        "medium",
        "28 nominal and 30 stress validation lifecycles",
        "The exact-entry fixed-80/24h independent-asset approximation produced "
        "nominal -$3.5837 PF 0.7535 and stress -$6.4518 PF 0.6173. The commodity "
        "Swing route aggregate was negative; this diagnostic is not live parity.",
        _HIP3_V25_DIAGNOSTIC,
    ),
    (_HIP3_BREAKOUT_COMMODITY, "xyz:SNDK"): StrategyResearchEvidence(
        _HIP3_BREAKOUT_COMMODITY,
        "xyz:SNDK",
        "v25_lifecycle_diagnostic_stress_negative",
        "medium",
        "24 nominal and 27 stress validation lifecycles",
        "The exact-entry fixed-80/24h independent-asset approximation reversed "
        "from nominal +$4.5585 PF 1.3783 to stress -$3.4611 PF 0.8077. The "
        "commodity Breakout route aggregate was not stress-positive.",
        _HIP3_V25_DIAGNOSTIC,
    ),
    (_HIP3_BREAKOUT_COMMODITY, "xyz:GOLD"): StrategyResearchEvidence(
        _HIP3_BREAKOUT_COMMODITY,
        "xyz:GOLD",
        "v25_lifecycle_diagnostic_stress_negative",
        "medium",
        "21 nominal and 21 stress validation lifecycles",
        "The exact-entry fixed-80/24h independent-asset approximation produced "
        "nominal -$1.2562 PF 0.8522 and stress -$1.6603 PF 0.8097. The "
        "commodity Breakout route aggregate was not stress-positive.",
        _HIP3_V25_DIAGNOSTIC,
    ),
    (_HIP3_BREAKOUT_COMMODITY, "xyz:BRENTOIL"): StrategyResearchEvidence(
        _HIP3_BREAKOUT_COMMODITY,
        "xyz:BRENTOIL",
        "v25_lifecycle_diagnostic_stress_negative",
        "medium",
        "23 nominal and 23 stress validation lifecycles",
        "The exact-entry fixed-80/24h independent-asset approximation produced "
        "nominal -$3.1993 PF 0.7128 and stress -$4.4700 PF 0.6293. The "
        "commodity Breakout route aggregate was not stress-positive.",
        _HIP3_V25_DIAGNOSTIC,
    ),
}

_EVIDENCE.update(
    {
        (row[0], row[1]): StrategyResearchEvidence(*row)
        for row in recent_route_evidence_rows()
    }
)


def strategy_evidence_payloads(
    providers: tuple[StrategyProviderConfig, ...],
) -> list[dict[str, object]]:
    """Cover every configured mapping without changing its execution scope."""
    records = [
        strategy_research_evidence(provider.strategy_id, symbol)
        for provider in providers
        for symbol in provider.symbols
    ]
    return [record.as_payload() for record in records]


def strategy_research_evidence(
    strategy_id: str,
    symbol: str,
) -> StrategyResearchEvidence:
    """Return explicit evidence or an equally explicit unreviewed record."""
    evidence = _EVIDENCE.get((strategy_id, symbol)) or _unreviewed(strategy_id, symbol)
    rows = directional_evidence_rows(strategy_id, symbol)
    if not rows:
        return evidence
    if evidence.directional_evidence:
        raise ValueError(f"duplicate directional evidence for {strategy_id}|{symbol}")
    return replace(
        evidence,
        directional_evidence=tuple(StrategyDirectionalEvidence(*row) for row in rows),
    )


def _unreviewed(strategy_id: str, symbol: str) -> StrategyResearchEvidence:
    return StrategyResearchEvidence(
        strategy_id,
        symbol,
        "unreviewed_exact_mapping",
        "low",
        "not established for this exact provider-symbol mapping",
        "No accepted matched outcome record is bound to this exact mapping; "
        "execution eligibility is an operator scope choice, not evidence of edge.",
        "docs/reviews/2026-08-02-measured-hypervelocity-tui-acceptance.md",
    )
