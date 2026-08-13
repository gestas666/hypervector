"""Report-only technical acceptance for the corrected BTC-specialist v44."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.research.btc_specialist_friction_acceptance import (
    FrictionAcceptanceSpec,
    require_friction_evidence,
)
from hypervector.research.v43_poststart_acceptance import (
    BtcSpecialistAcceptanceSpec,
    build_btc_specialist_poststart_acceptance,
)

Record = Mapping[str, object]

_EXPECTED_SIDES = {
    "hulk_expansion_short_robust_v3|BTC": ["short"],
    "liquidity_sweep_long_1h_stop60_target60_v2|BTC": ["long"],
    "hype_breakout_compression_pullback_bidirectional_v1|HYPE": ["long", "short"],
    "hip3_breakout_pressure_sp500_spcx_bidirectional_v1|xyz:SP500": [
        "long",
        "short",
    ],
}
_SPEC = BtcSpecialistAcceptanceSpec(
    label="v44",
    schema_version="v44_poststart_acceptance_v1",
    profile_id="multi_asset_bidirectional_btc_specialists_corrected_candidate_v44",
    profile_fingerprint=(
        "a947c234d900f01ba993358e75ef44589a3262e000d0a67070c94c353dc1249a"
    ),
    expected_sides=_EXPECTED_SIDES,
    evidence_state="short_n1_long_taker_path_unresolved",
    maximum_margin_fraction=0.23203607689310038,
    limitations=(
        "technical acceptance does not establish route profitability",
        "BTC short has one exact forward event",
        "BTC long taker parity is sparse and its development path is unresolved",
        "the preflight must be regenerated at the final flat boundary",
        "this report cannot route, resize, pause, retune, or submit an order",
    ),
)


def build_v44_poststart_acceptance(
    checkpoint: Record,
    config: MultiAssetLiveConfig,
    risk_evidence: Record,
    friction_evidence: Record,
    transition_preflight: Record,
    *,
    now_utc: datetime,
    maximum_checkpoint_age_seconds: float = 90.0,
    maximum_pressure_age_seconds: float = 30.0,
) -> dict[str, object]:
    """Verify a live v44 checkpoint against exact frozen evidence."""
    friction_identity = require_friction_evidence(
        friction_evidence,
        config,
        FrictionAcceptanceSpec(
            label="v44",
            schema_version="v44_portfolio_friction_stress_v1",
            maximum_margin_fraction=0.23203607689310038,
        ),
    )
    report = build_btc_specialist_poststart_acceptance(
        checkpoint,
        config,
        risk_evidence,
        transition_preflight,
        now_utc=now_utc,
        spec=_SPEC,
        maximum_checkpoint_age_seconds=maximum_checkpoint_age_seconds,
        maximum_pressure_age_seconds=maximum_pressure_age_seconds,
    )
    report["friction_identity"] = friction_identity
    return report
