"""Exact profile identities supported by seven-asset post-start monitoring."""

from __future__ import annotations

from dataclasses import dataclass
import math

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.live.multi_asset_read_only_preflight import (
    maximum_executable_margin_fraction,
)

_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE", "ZEC", "xyz:SPCX", "xyz:SNDK")
_DIRECTIONS = frozenset(
    {
        ("hulk_expansion_short_robust_v3", "BTC", "short"),
        ("hulk_expansion_short_tuned_v2", "BTC", "short"),
        ("liquidity_sweep_long_1h_stop60_target60_v2", "BTC", "long"),
        ("eth_range_onset_long_dual_mtf_v2", "ETH", "long"),
        ("sol_range_onset_short_dual_mtf_v2", "SOL", "short"),
        ("hype_breakout_compression_alignment_bidirectional_v2", "HYPE", "long"),
        ("zec_donchian_20_10_atr20_long_v1", "ZEC", "long"),
        ("hip3_spcx_cash_session_fresh15_long_v4", "xyz:SPCX", "long"),
        ("hip3_breakout_pressure_sndk_fresh15s_bidirectional_v3", "xyz:SNDK", "short"),
    }
)
_V85_DIRECTIONS = _DIRECTIONS.difference(
    {("hulk_expansion_short_tuned_v2", "BTC", "short")}
)
_V86_DIRECTIONS = _V85_DIRECTIONS.difference(
    {
        ("hulk_expansion_short_robust_v3", "BTC", "short"),
        ("zec_donchian_20_10_atr20_long_v1", "ZEC", "long"),
    }
)


@dataclass(frozen=True)
class SevenAssetPoststartProfile:
    """One immutable identity accepted by the shared monitoring contract."""

    profile_id: str
    profile_fingerprint: str
    schema_version: str
    executable_directions: frozenset[tuple[str, str, str]]
    maximum_executable_margin_fraction: float


_PROFILES = (
    SevenAssetPoststartProfile(
        "multi_asset_growth_first_5000_seven_asset_all_active_v79",
        "6c12d96e3fe09dd5dcefd24761bc7462ec6d6aa0b0d0f023a21e4b8597b646f7",
        "v79_poststart_acceptance_v1",
        _DIRECTIONS,
        0.24,
    ),
    SevenAssetPoststartProfile(
        "multi_asset_growth_first_5000_seven_asset_entry_ioc_hardened_v80",
        "89c84ecf8f927d1b22b3db7b28a9b6e62c89685d7049ef02f0cca90fc568d5ca",
        "v80_poststart_acceptance_v1",
        _DIRECTIONS,
        0.24,
    ),
    SevenAssetPoststartProfile(
        "multi_asset_growth_first_5000_seven_asset_btc_tuned_retired_v85",
        "18306afaaad1912b368f483c770c507a94a2403f9bd2741691776220b38633e8",
        "v85_poststart_acceptance_v1",
        _V85_DIRECTIONS,
        0.24,
    ),
    SevenAssetPoststartProfile(
        "multi_asset_growth_first_5000_seven_asset_failed_routes_retired_v86",
        "f454101eadaef46fd026c1a901bb7873bad61d7e7183a4c2e342e477e4e38733",
        "v86_poststart_acceptance_v1",
        _V86_DIRECTIONS,
        0.22,
    ),
)


def require_exact_seven_asset_profile(
    config: MultiAssetLiveConfig,
) -> SevenAssetPoststartProfile:
    """Return the exact supported profile or fail closed on any contract drift."""
    profile = next(
        (
            candidate
            for candidate in _PROFILES
            if candidate.profile_id == config.profile_id
            and candidate.profile_fingerprint == config.profile_fingerprint
        ),
        None,
    )
    exact = (
        profile is not None
        and config.network == "mainnet"
        and config.margin_mode == "isolated"
        and config.symbols == _SYMBOLS
        and config.maximum_positions == 7
        and len(config.providers) == 9
        and frozenset(config.executable_provider_directions)
        == profile.executable_directions
        and math.isclose(
            maximum_executable_margin_fraction(config),
            profile.maximum_executable_margin_fraction,
            abs_tol=1e-12,
        )
    )
    if not exact or profile is None:
        raise ValueError("post-start acceptance requires an exact supported profile")
    return profile
