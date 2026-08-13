"""Focused successor configuration for the BTC long/short specialists."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError
from hypervector.live.multi_asset_strategy_evidence import strategy_evidence_payloads

_PROFILE = Path("configs/multi_asset_bidirectional_btc_specialists_candidate_v43.toml")


def test_v43_keeps_three_assets_and_replaces_rejected_btc_provider() -> None:
    """The next profile uses distinct BTC sides without fabricating ten assets."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    providers = {provider.strategy_id: provider for provider in config.providers}

    assert config.maximum_positions == 10
    assert config.symbols == ("BTC", "HYPE", "xyz:SP500")
    assert "hulk_expansion_bidirectional_tuned_v2" not in providers
    assert set(providers) == {
        "hulk_expansion_short_robust_v3",
        "liquidity_sweep_long_1h_stop60_v1",
        "hype_breakout_compression_pullback_bidirectional_v1",
        "hip3_breakout_pressure_sp500_spcx_bidirectional_v1",
    }
    assert providers["hulk_expansion_short_robust_v3"].sides == {"short"}
    assert providers["liquidity_sweep_long_1h_stop60_v1"].sides == {"long"}


def test_v43_btc_sizing_scales_from_500_to_5000_without_a_profile_edit() -> None:
    """Percent-based sizing preserves one risk policy across both account stages."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    providers = {provider.strategy_id: provider for provider in config.providers}
    asset = next(value for value in config.assets if value.symbol == "BTC")
    short = providers["hulk_expansion_short_robust_v3"].entry_sizing("BTC")
    long = providers["liquidity_sweep_long_1h_stop60_v1"].entry_sizing("BTC")

    assert short is not None and long is not None
    assert short.planned_notional(account_value_usd=500.0, leverage=asset.leverage) == (
        pytest.approx(333.3333333333333)
    )
    assert short.planned_notional(
        account_value_usd=5_000.0, leverage=asset.leverage
    ) == (pytest.approx(3_333.333333333333))
    assert long.planned_notional(account_value_usd=500.0, leverage=asset.leverage) == (
        pytest.approx(416.6666666666667)
    )
    assert long.planned_notional(
        account_value_usd=5_000.0, leverage=asset.leverage
    ) == (pytest.approx(4_166.666666666667))


def test_v43_btc_exits_and_freshness_match_forward_contracts() -> None:
    """Short and long retain exact stop, target, and no-late-entry policies."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    providers = {provider.strategy_id: provider for provider in config.providers}
    short = providers["hulk_expansion_short_robust_v3"]
    long = providers["liquidity_sweep_long_1h_stop60_v1"]

    assert short.maximum_entry_delay_seconds == 60
    assert short.execution.stop_policy == "structural_clamped_bps"
    assert short.execution.minimum_stop_bps == pytest.approx(20.0)
    assert short.execution.maximum_stop_bps == pytest.approx(75.0)
    assert short.execution.target_r_multiple == pytest.approx(3.0)
    assert long.maximum_entry_delay_seconds == 60
    assert long.execution.entry_liquidity == "taker_ioc"
    assert long.execution.stop_bps == pytest.approx(60.0)
    assert long.execution.target_bps == pytest.approx(26.666666666666668)
    assert short.execution.maximum_hold_seconds == 86_400
    assert long.execution.maximum_hold_seconds == 86_400


def test_v43_btc_evidence_is_exact_and_discloses_single_event_samples() -> None:
    """The cockpit must not relabel either new BTC route as unreviewed."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    rows = {
        (str(row["strategy_id"]), str(row["symbol"])): row
        for row in strategy_evidence_payloads(config.providers)
    }

    short = rows[("hulk_expansion_short_robust_v3", "BTC")]
    long = rows[("liquidity_sweep_long_1h_stop60_v1", "BTC")]
    assert short["research_state"] == "forward_exact_n1_repeatability_unproven"
    assert long["research_state"] == "maker_forward_n1_runtime_taker_mismatch"
    assert "1 exact" in str(short["cadence"])
    assert "1 exact" in str(long["cadence"])
    assert "repeatability" in str(short["summary"]).lower()
    assert "repeatability" in str(long["summary"]).lower()
    assert "maker" in str(long["summary"]).lower()
    assert "not" in str(long["summary"]).lower()


@pytest.mark.parametrize(
    ("old", "new"),
    (
        (
            'entry_liquidity = "taker_ioc", stop_policy = "fixed_bps"',
            'entry_liquidity = "maker_post_only", stop_policy = "fixed_bps"',
        ),
        ("target_r_multiple = 3.0", "target_r_multiple = 2.0"),
    ),
)
def test_v43_btc_provider_contract_drift_is_rejected(
    tmp_path: Path,
    old: str,
    new: str,
) -> None:
    """The candidate cannot silently revert to unverified entry or target rules."""
    profile = tmp_path / "drifted-v43.toml"
    profile.write_text(
        _PROFILE.read_text(encoding="utf-8").replace(old, new, 1),
        encoding="utf-8",
    )

    with pytest.raises(MultiAssetLiveConfigError, match="requires"):
        load_multi_asset_live_config(profile, mode="observe")
