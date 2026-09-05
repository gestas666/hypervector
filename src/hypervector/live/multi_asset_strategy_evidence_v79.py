"""Evidence disclosures for the V79 all-active roster routes."""

from __future__ import annotations

from typing import TypeAlias

from hypervector.live.directional_range_onset_provider import (
    ETH_RANGE_LONG_STRATEGY,
    SOL_RANGE_SHORT_STRATEGY,
)
from hypervector.live.spcx_cash_session_breakout_provider import (
    SPCX_CASH_SESSION_LONG_STRATEGY,
)
from hypervector.live.zec_donchian_provider import ZEC_DONCHIAN_LONG_STRATEGY

EvidenceRow: TypeAlias = tuple[str, str, str, str, str, str, str]
_V85_SPCX_EVIDENCE = (
    "data/logs/research/bidirectional_cohort/"
    "v85_spcx_v4_exact_live_lifecycle_20260903_v1.json"
)


def v79_route_evidence_rows() -> tuple[EvidenceRow, ...]:
    """Return non-gating evidence and explicit uncertainty for V79 routes."""
    return (
        (
            ETH_RANGE_LONG_STRATEGY,
            "ETH",
            "historical_directional_candidate_live_probation",
            "medium",
            "45 historical long trades / 365 covered days; zero exact v2 live closes",
            "ETH long was positive in all three modeled partitions. The active "
            "dual-MTF context condition was chosen after historical inspection, "
            "so live repeatability remains unverified and sizing stays probationary.",
            "data/logs/research/"
            "range_onset_context_challenger_ETH_20250728_20260728_v2.json",
        ),
        (
            SOL_RANGE_SHORT_STRATEGY,
            "SOL",
            "historical_short_candidate_posthoc_live_probation",
            "low",
            "23 historical short trades / 201 covered days; zero exact v2 live closes",
            "The SOL short slice was historically positive with profit factor "
            "4.58, but direction was selected after partition review and has no "
            "resolved live outcomes under this exact identity.",
            "docs/reviews/2026-07-31-sol-range-onset-direction-stability.md",
        ),
        (
            ZEC_DONCHIAN_LONG_STRATEGY,
            "ZEC",
            "v79_shape_replayed_largest_winner_falsified_live_probation",
            "low",
            "9 exact V79-shape pseudo-holdout long trades; zero exact live closes",
            "The exact 250-bps capped V79 shape produced 3W/6L, +$160.73 nominal "
            "and PF 3.0378, but -$45.98 after largest-winner removal. The cap "
            "reduced drawdown while adding two extra stop exits and lowering net "
            "versus the uncapped control. Robustness therefore remains falsified; "
            "this is low-confidence probation, not proven edge.",
            "data/logs/research/bidirectional_cohort/"
            "v84_v79_friction_contract_completion_20260903_v1.json",
        ),
        (
            SPCX_CASH_SESSION_LONG_STRATEGY,
            "xyz:SPCX",
            "exact_live_n1_positive_unrepeated",
            "low",
            "1 exact v4 live close: 1W/0L, +$5.940383 net",
            "The first exact v4 cash-session long reached its 120-bps maker target: "
            "$5.988774 gross - $0.057607 fees +$0.009216 funding = $5.940383 net. "
            "Entry IOC slippage was favorable on both fill legs and the protective "
            "60-bps stop rested before the target. This is one winner and becomes "
            "$0 after largest-winner removal, so it does not establish repeatable edge.",
            _V85_SPCX_EVIDENCE,
        ),
    )
