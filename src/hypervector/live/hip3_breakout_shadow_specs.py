"""Frozen exact identities for execution-incapable HIP-3 observers."""

from __future__ import annotations

from dataclasses import dataclass

from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)


@dataclass(frozen=True)
class Hip3BreakoutShadowSpec:
    """Frozen identity and signal configuration for one report-only route."""

    symbol: str
    provider_id: str
    profile_id: str
    ledger_profile_id: str
    config: Hip3BreakoutPressureConfig

    def __post_init__(self) -> None:
        """Reject aliased or incomplete HIP-3 shadow identities."""
        token = self.symbol.lower()
        identities = (self.provider_id, self.profile_id, self.ledger_profile_id)
        asset = token.removeprefix("xyz:")
        if not token.startswith("xyz:") or any(
            asset not in identity.lower() for identity in identities
        ):
            raise ValueError("HIP-3 shadow spec identity is inconsistent")


MU_SHADOW_SPEC = Hip3BreakoutShadowSpec(
    "xyz:MU",
    "hip3_mu_full_l2_breakout_pressure_bidirectional_15m_v1",
    "mu_full_l2_breakout_pressure_bidirectional_15m_research_v1",
    "mu_breakout_shadow_xyz:mu",
    Hip3BreakoutPressureConfig(32, 9, 21, 0.1, 80.0),
)
SKHX_SHADOW_SPEC = Hip3BreakoutShadowSpec(
    "xyz:SKHX",
    "hip3_skhx_full_l2_breakout_pressure_bidirectional_15m_v1",
    "skhx_full_l2_breakout_pressure_bidirectional_15m_research_v1",
    "skhx_breakout_shadow_xyz:skhx",
    Hip3BreakoutPressureConfig(16, 21, 55, 0.5, 40.0),
)
CL_SHADOW_SPEC = Hip3BreakoutShadowSpec(
    "xyz:CL",
    "hip3_cl_full_l2_breakout_pressure_bidirectional_15m_v1",
    "cl_full_l2_breakout_pressure_bidirectional_15m_research_v1",
    "cl_breakout_shadow_xyz:cl",
    Hip3BreakoutPressureConfig(4, 21, 55, 0.1, 40.0),
)
SILVER_SHADOW_SPEC = Hip3BreakoutShadowSpec(
    "xyz:SILVER",
    "hip3_silver_full_l2_breakout_pressure_bidirectional_15m_v1",
    "silver_full_l2_breakout_pressure_bidirectional_15m_research_v1",
    "silver_breakout_shadow_xyz:silver",
    Hip3BreakoutPressureConfig(4, 21, 55, 0.35, 120.0),
)
SP500_SHADOW_SPEC = Hip3BreakoutShadowSpec(
    "xyz:SP500",
    "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3",
    "sp500_fresh15_pressure_shadow_research_v3",
    "index_fresh15_shadow_xyz:sp500",
    Hip3BreakoutPressureConfig(32, 21, 55, 0.1, 120.0),
)
SPCX_SHADOW_SPEC = Hip3BreakoutShadowSpec(
    "xyz:SPCX",
    "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3",
    "spcx_fresh15_pressure_shadow_research_v3",
    "index_fresh15_shadow_xyz:spcx",
    Hip3BreakoutPressureConfig(32, 21, 55, 0.1, 120.0),
)
HIP3_SHADOW_SPECS = (
    MU_SHADOW_SPEC,
    SKHX_SHADOW_SPEC,
    CL_SHADOW_SPEC,
    SILVER_SHADOW_SPEC,
    SP500_SHADOW_SPEC,
    SPCX_SHADOW_SPEC,
)
