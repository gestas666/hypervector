"""Fail-closed configuration contracts for the SOL canary backend."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.live.sol_range_onset_config import (
    SolCanaryConfigError,
    load_sol_range_onset_config,
)


PROFILE = Path("configs/sol_range_onset_canary.toml")


def test_shadow_and_live_are_explicit_modes_with_one_frozen_profile() -> None:
    """Mode changes authority state, not sizing or strategy identity."""
    shadow = load_sol_range_onset_config(PROFILE, mode="shadow")
    live = load_sol_range_onset_config(
        PROFILE,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )

    assert shadow.mode == "shadow"
    assert shadow.effective_arm_state(credentials_present=False) == "SHADOW"
    assert live.mode == "live"
    assert live.effective_arm_state(credentials_present=False) == "DISARMED"
    assert live.effective_arm_state(credentials_present=True) == "LIVE ARMED"
    assert live.profile_fingerprint == shadow.profile_fingerprint
    assert live.run_fingerprint != shadow.run_fingerprint


def test_canary_profile_binds_capital_strategy_and_separate_ledgers() -> None:
    """The $150 canary profile must not reuse the $15,000 research ledger."""
    config = load_sol_range_onset_config(PROFILE, mode="shadow")

    assert config.symbol == "SOL"
    assert config.network == "mainnet"
    assert config.margin_mode == "isolated"
    assert config.initial_shadow_equity_usd == pytest.approx(150.0)
    assert config.margin_fraction == pytest.approx(0.03)
    assert config.leverage == pytest.approx(5.0)
    assert config.venue_max_leverage == pytest.approx(20.0)
    assert config.market_slippage_cap_fraction == pytest.approx(0.01)
    assert config.max_notional_usd == pytest.approx(22.50)
    assert config.max_positions_per_symbol == 1
    assert config.stop_bps == pytest.approx(80.0)
    assert config.maximum_hold_seconds == pytest.approx(48 * 60 * 60)
    assert config.metalabel_mode == "off"
    assert "canary" in str(config.backend_ledger)
    assert "canary" in str(config.shadow_ledger)
    assert "canary" in str(config.live_ledger)
    assert "canary" in str(config.stop_file)
    assert "canary" in str(config.live_stop_file)
    assert config.backend_ledger != config.shadow_ledger
    assert config.live_ledger != config.backend_ledger
    assert config.live_ledger != config.shadow_ledger
    assert config.stop_file != config.live_stop_file
    assert "live" in config.live_ledger.parts
    assert "live" in config.live_stop_file.parts


def test_authoritative_ledger_tracks_effective_execution_mode() -> None:
    """The TUI and backend cannot silently mix shadow and live histories."""
    shadow = load_sol_range_onset_config(PROFILE, mode="shadow")
    live = load_sol_range_onset_config(
        PROFILE,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )

    assert shadow.authoritative_ledger == shadow.backend_ledger
    assert live.authoritative_ledger == live.live_ledger
    assert shadow.authoritative_stop_file == shadow.stop_file
    assert live.authoritative_stop_file == live.live_stop_file


def test_live_start_requires_mode_flags_and_credentials() -> None:
    """No individual setting may accidentally arm venue execution."""
    shadow = load_sol_range_onset_config(PROFILE, mode="shadow")
    with pytest.raises(SolCanaryConfigError, match="mode is shadow"):
        shadow.require_live_start(credentials_present=True)

    disabled = load_sol_range_onset_config(
        PROFILE,
        mode="live",
        accepts_live_risk=True,
    )
    with pytest.raises(SolCanaryConfigError, match="--enabled"):
        disabled.require_live_start(credentials_present=True)

    unaccepted = load_sol_range_onset_config(
        PROFILE,
        mode="live",
        enabled=True,
    )
    with pytest.raises(SolCanaryConfigError, match="--i-accept-live-risk"):
        unaccepted.require_live_start(credentials_present=True)

    missing_secrets = load_sol_range_onset_config(
        PROFILE,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    with pytest.raises(SolCanaryConfigError, match="credentials"):
        missing_secrets.require_live_start(credentials_present=False)

    missing_secrets.require_live_start(credentials_present=True)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('symbol = "SOL"', 'symbol = "BTC"', "symbol"),
        ('network = "mainnet"', 'network = "testnet"', "mainnet"),
        ('margin_mode = "isolated"', 'margin_mode = "cross"', "isolated"),
        ("leverage = 5.0", "leverage = 21.0", "venue_max_leverage"),
        ("max_notional_usd = 22.5", "max_notional_usd = 0.0", "max_notional"),
        (
            "max_positions_per_symbol = 1",
            "max_positions_per_symbol = 2",
            "one position",
        ),
        ('metalabel_mode = "off"', 'metalabel_mode = "observe"', "metalabel"),
    ],
)
def test_invalid_or_untruthful_canary_profiles_fail_closed(
    tmp_path: Path,
    old: str,
    new: str,
    message: str,
) -> None:
    """Venue, authority, and capital constraints are validated at load."""
    text = PROFILE.read_text(encoding="utf-8")
    assert old in text
    path = tmp_path / "invalid.toml"
    path.write_text(text.replace(old, new), encoding="utf-8")

    with pytest.raises(SolCanaryConfigError, match=message):
        load_sol_range_onset_config(path, mode="shadow")


def test_unknown_config_field_is_rejected(tmp_path: Path) -> None:
    """Typos must not become silent defaults in an execution profile."""
    path = tmp_path / "unknown.toml"
    path.write_text(
        PROFILE.read_text(encoding="utf-8") + "\nunknown_setting = true\n",
        encoding="utf-8",
    )

    with pytest.raises(SolCanaryConfigError, match="unknown"):
        load_sol_range_onset_config(path, mode="shadow")


def test_invalid_mode_is_rejected() -> None:
    """Paper-like aliases cannot blur the shadow/live boundary."""
    with pytest.raises(SolCanaryConfigError, match="shadow or live"):
        load_sol_range_onset_config(PROFILE, mode="paper")  # type: ignore[arg-type]
