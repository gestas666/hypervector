from pathlib import Path

import pytest

from hypervector.live.hulk_smash_live_config import (
    HulkSmashLiveConfigError,
    load_hulk_smash_live_config,
)


CONFIG = Path("tests/fixtures/profiles/hulk_smash_short_robust.toml")


def test_hulk_canary_config_freezes_the_validated_profile() -> None:
    config = load_hulk_smash_live_config(CONFIG, mode="observe")

    assert config.symbol == "BTC"
    assert config.strategy_id == "hulk_expansion_short_robust_v3"
    assert config.signal_timeframe == "30m"
    assert config.source_timeframe == "5m"
    assert config.leverage == 5.0
    assert config.risk_fraction == 0.0025
    assert config.minimum_stop_bps == 20.0
    assert config.maximum_stop_bps == 75.0
    assert config.target_r_multiple == 3.0
    assert config.maximum_hold_bars == 48
    assert config.maximum_entry_delay_seconds == 60
    assert config.markout_horizon_ms == 5_000
    assert config.effective_arm_state(credentials_present=True) == "DISARMED"


def test_hulk_canary_live_authority_requires_both_flags_and_credentials() -> None:
    disarmed = load_hulk_smash_live_config(CONFIG, mode="live")
    with pytest.raises(HulkSmashLiveConfigError, match="--enabled"):
        disarmed.require_live_start(credentials_present=True)

    enabled = load_hulk_smash_live_config(CONFIG, mode="live", enabled=True)
    with pytest.raises(HulkSmashLiveConfigError, match="--i-accept-live-risk"):
        enabled.require_live_start(credentials_present=True)

    accepted = load_hulk_smash_live_config(
        CONFIG,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    with pytest.raises(HulkSmashLiveConfigError, match="credentials"):
        accepted.require_live_start(credentials_present=False)
    accepted.require_live_start(credentials_present=True)
    assert accepted.effective_arm_state(credentials_present=True) == "LIVE ARMED"


def test_hulk_canary_rejects_live_flags_in_observe_mode() -> None:
    with pytest.raises(HulkSmashLiveConfigError, match="observe mode"):
        load_hulk_smash_live_config(
            CONFIG,
            mode="observe",
            enabled=True,
            accepts_live_risk=True,
        )
