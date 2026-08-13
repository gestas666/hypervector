"""Side-specific historical evidence for cohort provider-symbol mappings."""

from typing import TypeAlias

Route: TypeAlias = tuple[str, str]
DirectionalEvidenceRow: TypeAlias = tuple[str, str, str, str, str, str]

_HIP3_DIAGNOSTIC = "data/logs/research/hip3_v25_lifecycle_bar_diagnostic_20260807.json"
_SOL_REVIEW = "docs/reviews/2026-07-31-sol-range-onset-direction-stability.md"
_ETH_REVIEW = "docs/reviews/2026-08-06-eth-breakout-transfer-canary-qualification.md"

_ROWS: dict[Route, tuple[DirectionalEvidenceRow, ...]] = {
    ("range_onset_bidirectional_v1", "SOL"): (
        (
            "long",
            "historical_candidate_concentrated",
            "medium",
            "19 trades / 201 covered days; 5W/14L",
            "After modeled costs: +$391.64, PF 2.959, and positive minimum "
            "leave-one-block-out PnL. The largest winner supplied 49.2% and "
            "the top three supplied 92.3% of gross profit.",
            _SOL_REVIEW,
        ),
        (
            "short",
            "historical_candidate",
            "medium",
            "23 trades / 201 covered days; 7W/16L",
            "After modeled costs: +$895.06, PF 4.580, and positive minimum "
            "leave-one-block-out PnL. The largest winner supplied 28.0% of "
            "gross profit.",
            _SOL_REVIEW,
        ),
    ),
    ("eth_breakout_precompression_pullback_bidirectional_v1", "ETH"): (
        (
            "long",
            "historical_candidate",
            "low",
            "142 development + 26 opened-final-60-day trades",
            "After modeled costs: development +254.70 bps at PF 1.0332 and "
            "opened final block +345.18 bps at PF 1.3109.",
            _ETH_REVIEW,
        ),
        (
            "short",
            "contradictory",
            "low",
            "140 development + 30 opened-final-60-day trades",
            "After modeled costs: development +1,403.28 bps at PF 1.1932, "
            "then opened final block -22.85 bps at PF 0.9853.",
            _ETH_REVIEW,
        ),
    ),
    ("hip3_breakout_pressure_sp500_spcx_bidirectional_v1", "xyz:SP500"): (
        (
            "long",
            "contradictory",
            "medium",
            "15 development + 7 validation stress lifecycles",
            "Stress net PnL reversed from +$1.1788 in development to -$0.3946 "
            "in validation.",
            _HIP3_DIAGNOSTIC,
        ),
        (
            "short",
            "contradictory",
            "medium",
            "15 development + 6 validation stress lifecycles",
            "Stress net PnL reversed from -$3.2592 in development to +$1.0561 "
            "in validation.",
            _HIP3_DIAGNOSTIC,
        ),
    ),
    ("hip3_swing_ha_sndk_gold_brent_bidirectional_v1", "xyz:GOLD"): (
        (
            "long",
            "historical_transfer_negative",
            "medium",
            "16 development + 11 validation stress lifecycles",
            "Stress net PnL was -$2.0697 in development and -$1.4958 in validation.",
            _HIP3_DIAGNOSTIC,
        ),
        (
            "short",
            "contradictory",
            "medium",
            "16 development + 8 validation stress lifecycles",
            "Stress net PnL reversed from -$2.9703 in development to +$1.8862 "
            "in validation.",
            _HIP3_DIAGNOSTIC,
        ),
    ),
    ("hip3_swing_ha_sp500_spcx_bidirectional_v2", "xyz:SPCX"): (
        (
            "long",
            "contradictory",
            "medium",
            "13 development + 3 validation stress lifecycles",
            "Stress net PnL reversed from +$14.2647 in development to -$1.9682 "
            "in validation.",
            _HIP3_DIAGNOSTIC,
        ),
        (
            "short",
            "contradictory",
            "medium",
            "24 development + 19 validation stress lifecycles",
            "Stress net PnL reversed from -$3.8732 in development to +$3.1560 "
            "in validation.",
            _HIP3_DIAGNOSTIC,
        ),
    ),
}


def directional_evidence_rows(
    strategy_id: str,
    symbol: str,
) -> tuple[DirectionalEvidenceRow, ...]:
    """Return immutable side evidence for one exact route mapping."""
    return _ROWS.get((strategy_id, symbol), ())
