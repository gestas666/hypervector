"""Report-only technical acceptance for six-asset growth profile v50."""

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
_PROFILE_ID = "multi_asset_growth_first_5000_six_asset_candidate_v50"
_PROFILE_FINGERPRINT = (
    "375281af0b683e0ddd6c22c02b6a20ea2807705a124a1fce23da76bb39ccc7dd"
)
_ASSETS = frozenset({"BTC", "ETH", "SOL", "HYPE", "xyz:SP500", "xyz:SPCX"})
_EXPECTED_SIDES = {
    "hulk_expansion_short_robust_v3|BTC": ["short"],
    "liquidity_sweep_long_1h_stop60_target60_v2|BTC": ["long"],
    "range_onset_bidirectional_v1|ETH": ["long", "short"],
    "range_onset_bidirectional_v1|SOL": ["long", "short"],
    "hype_breakout_compression_pullback_bidirectional_v1|HYPE": ["long", "short"],
    "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3|xyz:SP500": [
        "long",
        "short",
    ],
    "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3|xyz:SPCX": [
        "long",
        "short",
    ],
}
_FRICTION_SPEC = FrictionAcceptanceSpec(
    label="v50",
    schema_version="v50_growth_sizing_stress_v1",
    maximum_margin_fraction=0.6,
    explicit_candidate_depth=True,
    configured_leverage=10.0,
    variable_tiers="telemetry_only_not_execution_authorized",
    assets=_ASSETS,
    maximum_simultaneous_positions=6,
)
_SPEC = GrowthAcceptanceSpec(
    label="v50",
    schema_version="v50_poststart_acceptance_v1",
    profile_id=_PROFILE_ID,
    profile_fingerprint=_PROFILE_FINGERPRINT,
    expected_sides=_EXPECTED_SIDES,
    evidence_state="six_asset_fresh15_v3_live_trial",
    maximum_margin_fraction=0.6,
    limitations=(
        "technical acceptance does not establish route profitability",
        "the preflight must be regenerated at the final flat boundary",
        "fresh15 v3 live outcomes remain prospective trial evidence",
        "this report cannot route, resize, pause, retune, or submit an order",
    ),
    assets=_ASSETS,
    provider_count=5,
    configured_leverage=10.0,
    pressure_age_seconds=15.0,
    friction=_FRICTION_SPEC,
)


def build_v50_poststart_acceptance(
    checkpoint: Record,
    config: MultiAssetLiveConfig,
    friction_evidence: Record,
    transition_preflight: Record,
    *,
    now_utc: datetime,
    maximum_checkpoint_age_seconds: float = 90.0,
    maximum_pressure_age_seconds: float = 15.0,
) -> dict[str, object]:
    """Verify exact live v50 identity, route scope, and venue protection."""
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
