"""Versioned identity specifications for report-only route-forward tracking."""

from __future__ import annotations

from dataclasses import dataclass

SWING_COMMODITY = "hip3_swing_ha_sndk_gold_brent_bidirectional_v1"
BREAKOUT_COMMODITY = "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1"
SWING_INDEX = "hip3_swing_ha_sp500_spcx_bidirectional_v2"
BREAKOUT_INDEX = "hip3_breakout_pressure_sp500_spcx_bidirectional_v1"


@dataclass(frozen=True)
class CandidateRouteForwardSpec:
    """Declare one exact source-to-candidate route tracking experiment."""

    version_label: str
    schema_version: str
    source_profile: str
    candidate_profile: str
    candidate_phase: str
    journal_revision: int
    candidate_evidence_role: str
    removed_routes: tuple[str, ...]
    retained_control_routes: tuple[str, ...]
    waiting_recommendation: str
    forward_recommendation: str

    @property
    def tracked_routes(self) -> tuple[str, ...]:
        """Return exact removed and retained-control route order."""
        return self.removed_routes + self.retained_control_routes


V31_ROUTE_FORWARD_SPEC = CandidateRouteForwardSpec(
    version_label="v31",
    schema_version="v31_route_forward_snapshot_v1",
    source_profile="multi_asset_bidirectional_complete_portfolio_canary_v25",
    candidate_profile="multi_asset_bidirectional_swing_pruned_candidate_v31",
    candidate_phase="candidate_v31_forward",
    journal_revision=1,
    candidate_evidence_role="inactive_exact_diff_candidate",
    removed_routes=(
        f"{SWING_COMMODITY}|xyz:SNDK",
        f"{SWING_COMMODITY}|xyz:BRENTOIL",
    ),
    retained_control_routes=(
        f"{SWING_COMMODITY}|xyz:GOLD",
        f"{BREAKOUT_COMMODITY}|xyz:SNDK",
        f"{BREAKOUT_COMMODITY}|xyz:GOLD",
        f"{BREAKOUT_COMMODITY}|xyz:BRENTOIL",
    ),
    waiting_recommendation="wait_for_flat_and_explicit_v31_authorization",
    forward_recommendation="collect_candidate_forward_removed_vs_control_evidence",
)

V32_ROUTE_FORWARD_SPEC = CandidateRouteForwardSpec(
    version_label="v32",
    schema_version="v32_route_forward_snapshot_v1",
    source_profile="multi_asset_bidirectional_complete_portfolio_canary_v25",
    candidate_profile=(
        "multi_asset_bidirectional_commodity_swing_retired_candidate_v32"
    ),
    candidate_phase="candidate_v32_forward",
    journal_revision=3,
    candidate_evidence_role="inactive_exact_delta_v32_candidate",
    removed_routes=(
        f"{SWING_COMMODITY}|xyz:SNDK",
        f"{SWING_COMMODITY}|xyz:GOLD",
        f"{SWING_COMMODITY}|xyz:BRENTOIL",
    ),
    retained_control_routes=(
        f"{BREAKOUT_COMMODITY}|xyz:SNDK",
        f"{BREAKOUT_COMMODITY}|xyz:GOLD",
        f"{BREAKOUT_COMMODITY}|xyz:BRENTOIL",
    ),
    waiting_recommendation="wait_for_flat_and_explicit_v32_authorization",
    forward_recommendation="collect_v32_removed_vs_breakout_control_evidence",
)

V33_ROUTE_FORWARD_SPEC = CandidateRouteForwardSpec(
    version_label="v33",
    schema_version="v33_route_forward_snapshot_v1",
    source_profile="multi_asset_bidirectional_complete_portfolio_canary_v25",
    candidate_profile="multi_asset_bidirectional_spcx_swing_retired_candidate_v33",
    candidate_phase="candidate_v33_forward",
    journal_revision=4,
    candidate_evidence_role="inactive_exact_delta_v33_candidate",
    removed_routes=(
        f"{SWING_COMMODITY}|xyz:SNDK",
        f"{SWING_COMMODITY}|xyz:GOLD",
        f"{SWING_COMMODITY}|xyz:BRENTOIL",
        f"{SWING_INDEX}|xyz:SPCX",
    ),
    retained_control_routes=(
        f"{BREAKOUT_COMMODITY}|xyz:SNDK",
        f"{BREAKOUT_COMMODITY}|xyz:GOLD",
        f"{BREAKOUT_COMMODITY}|xyz:BRENTOIL",
        f"{BREAKOUT_INDEX}|xyz:SP500",
        f"{BREAKOUT_INDEX}|xyz:SPCX",
        f"{SWING_INDEX}|xyz:SP500",
    ),
    waiting_recommendation="wait_for_flat_and_explicit_v33_authorization",
    forward_recommendation="collect_v33_removed_vs_retained_control_evidence",
)
