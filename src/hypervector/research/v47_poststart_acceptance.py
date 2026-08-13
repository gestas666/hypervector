"""Report-only technical acceptance for repaired growth profile v47."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.research.btc_specialist_friction_acceptance import (
    FrictionAcceptanceSpec,
)
from hypervector.research.growth_poststart_acceptance import (
    GrowthAcceptanceSpec,
    build_growth_poststart_acceptance,
)
from hypervector.research.v39_poststart_acceptance import (
    _acceptance_checks as _shared_acceptance_checks,
)

Record = Mapping[str, object]
_PROFILE_ID = "multi_asset_growth_first_5000_repaired_candidate_v47"
_PROFILE_FINGERPRINT = (
    "cb1482029e230069bb6615cb5232975728602c3c14b925ef7f0c734a90b1bc0f"
)
_ASSETS = frozenset({"BTC", "ETH", "SOL", "HYPE", "xyz:SP500"})
_EXPECTED_SIDES = {
    "hulk_expansion_short_robust_v3|BTC": ["short"],
    "liquidity_sweep_long_1h_stop60_target60_v2|BTC": ["long"],
    "range_onset_bidirectional_v1|ETH": ["long", "short"],
    "range_onset_bidirectional_v1|SOL": ["long", "short"],
    "hype_breakout_compression_pullback_bidirectional_v1|HYPE": ["long", "short"],
    "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v2|xyz:SP500": [
        "long",
        "short",
    ],
}
_FRICTION_SPEC = FrictionAcceptanceSpec(
    label="v47",
    schema_version="v47_portfolio_friction_stress_v1",
    maximum_margin_fraction=0.6,
    explicit_candidate_depth=True,
    configured_leverage=10.0,
    variable_tiers="telemetry_only_not_execution_authorized",
    assets=_ASSETS,
    maximum_simultaneous_positions=5,
)
_SPEC = GrowthAcceptanceSpec(
    label="v47",
    schema_version="v47_poststart_acceptance_v1",
    profile_id=_PROFILE_ID,
    profile_fingerprint=_PROFILE_FINGERPRINT,
    expected_sides=_EXPECTED_SIDES,
    evidence_state="repaired_growth_routes_report_only",
    maximum_margin_fraction=0.6,
    limitations=(
        "technical acceptance does not establish route profitability",
        "the preflight must be regenerated at the final flat boundary",
        "fresh15 pressure parity remains forward-unproven",
        "this report cannot route, resize, pause, retune, or submit an order",
    ),
    assets=_ASSETS,
    provider_count=5,
    configured_leverage=10.0,
    pressure_age_seconds=15.0,
    friction=_FRICTION_SPEC,
)


def build_v47_poststart_acceptance(
    checkpoint: Record,
    config: MultiAssetLiveConfig,
    friction_evidence: Record,
    transition_preflight: Record,
    *,
    now_utc: datetime,
    maximum_checkpoint_age_seconds: float = 90.0,
    maximum_pressure_age_seconds: float = 15.0,
) -> dict[str, object]:
    """Verify exact live v47 identity, pressure, sizing, and protection."""
    return build_growth_poststart_acceptance(
        checkpoint,
        config,
        friction_evidence,
        transition_preflight,
        now_utc=now_utc,
        spec=_SPEC,
        shared_checks=_shared_acceptance_checks,
        maximum_checkpoint_age_seconds=maximum_checkpoint_age_seconds,
        maximum_pressure_age_seconds=maximum_pressure_age_seconds,
    )
