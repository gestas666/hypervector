"""Fail-closed contract tests for the BTC 5m source-follow live canary."""

from dataclasses import replace
from pathlib import Path

import pytest

from hypervector.live.source_follow_live_config import (
    SourceFollowLiveConfigError,
    load_source_follow_live_config,
)

CONFIG = Path("configs/hypervelocity_source_follow_minrange12_alloc35_canary.toml")
BIDIRECTIONAL_CONFIG = Path(
    "configs/hypervelocity_source_follow_bidirectional_minrange12_alloc35_canary.toml"
)


def test_live_canary_inherits_the_selected_five_minute_contract() -> None:
    """The live wrapper cannot silently alter the measured strategy profile."""
    config = load_source_follow_live_config(CONFIG)

    assert config.profile.profile_id == (
        "hypervelocity_source_follow_minrange12_alloc35_shadow_v1"
    )
    assert config.symbol == "BTC"
    assert config.signal_timeframe == "5m"
    assert config.context_timeframe == "15m"
    assert config.leverage == 30.0
    assert config.margin_fraction == 0.35
    assert config.target_margin_pct == 8.0
    assert config.entry_ttl_seconds == 60.0
    assert config.maximum_hold_seconds == 86_400.0
    assert config.max_notional_usd == 1_700.0
    assert config.effective_arm_state(credentials_present=True) == "DISARMED"
    policy = config.profile.regime_policy()
    assert policy["execution_timeframe"] == "5m"
    assert policy["classified_timeframes"] == ["5m"]
    assert policy["state_1m_role"] == "not_classified"
    assert policy["context_role"] == "not_classified"


def test_live_canary_requires_two_flags_and_credentials() -> None:
    """No single CLI switch or configured secret can arm execution alone."""
    missing_enabled = load_source_follow_live_config(
        CONFIG,
        accepts_live_risk=True,
    )
    missing_acceptance = load_source_follow_live_config(CONFIG, enabled=True)
    missing_credentials = load_source_follow_live_config(
        CONFIG,
        enabled=True,
        accepts_live_risk=True,
    )

    with pytest.raises(SourceFollowLiveConfigError, match="--enabled"):
        missing_enabled.require_live_start(credentials_present=True)
    with pytest.raises(SourceFollowLiveConfigError, match="--i-accept-live-risk"):
        missing_acceptance.require_live_start(credentials_present=True)
    with pytest.raises(SourceFollowLiveConfigError, match="credentials"):
        missing_credentials.require_live_start(credentials_present=False)


def test_live_canary_fingerprint_excludes_transient_arm_flags() -> None:
    """The same strategy/config identity survives disarmed and armed checks."""
    disarmed = load_source_follow_live_config(CONFIG)
    armed = load_source_follow_live_config(
        CONFIG,
        enabled=True,
        accepts_live_risk=True,
    )

    assert disarmed.profile_fingerprint == armed.profile_fingerprint
    assert disarmed.run_fingerprint != armed.run_fingerprint
    assert armed.effective_arm_state(credentials_present=True) == "LIVE ARMED"


def test_live_canary_fingerprint_includes_the_resolved_strategy_contract() -> None:
    """A code-level policy change cannot retain the same profile identity."""
    baseline = load_source_follow_live_config(BIDIRECTIONAL_CONFIG)
    changed_profile = replace(
        baseline.profile,
        breakout_requires_direction=False,
    )
    changed = replace(baseline, profile=changed_profile)

    assert baseline.profile.profile_id == changed.profile.profile_id
    assert baseline.profile_fingerprint != changed.profile_fingerprint


def test_live_canary_rejects_unknown_or_changed_fields(tmp_path: Path) -> None:
    """Typos and risk drift fail closed instead of becoming silent defaults."""
    changed = tmp_path / CONFIG.name
    payload = CONFIG.read_text(encoding="utf-8").replace(
        "max_notional_usd = 1700.0",
        "max_notional_usd = 5000.0\nunknown_gate = true",
    )
    changed.write_text(payload, encoding="utf-8")

    with pytest.raises(SourceFollowLiveConfigError, match="unknown risk keys"):
        load_source_follow_live_config(changed)


def test_bidirectional_live_wrapper_is_distinct_and_fail_closed() -> None:
    """Two-sided authority requires its own immutable config and both arm flags."""
    config = load_source_follow_live_config(BIDIRECTIONAL_CONFIG)

    assert config.profile_id == (
        "hypervelocity_source_follow_bidirectional_minrange12_alloc35_live_canary_v1"
    )
    assert config.profile.direction_mode == "source_follow_bidirectional"
    assert config.runtime_direction_mode == "trend_bidirectional"
    assert config.profile.regime_policy()["side"] == "bidirectional"
    assert config.effective_arm_state(credentials_present=True) == "DISARMED"
    with pytest.raises(SourceFollowLiveConfigError, match="--enabled"):
        config.require_live_start(credentials_present=True)
