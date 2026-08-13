"""Fail-closed configuration contracts for the Apex MM measurement canary."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.live.apex_mm_live_config import (
    ApexMMLiveConfigError,
    load_apex_mm_live_config,
)


_CONFIG = Path("configs/apex_regime_mm_canary.toml")


def test_canary_profile_is_disarmed_and_frozen_to_small_btc_inventory() -> None:
    config = load_apex_mm_live_config(_CONFIG)

    assert config.profile_id == "apex_regime_mm_canary_v1"
    assert config.strategy_id == "apex_regime_mm_v2"
    assert config.symbol == "BTC"
    assert config.network == "mainnet"
    assert config.margin_mode == "isolated"
    assert config.leverage == 3
    assert config.base_order_notional_usd == pytest.approx(12.5)
    assert config.max_inventory_notional_usd == pytest.approx(30.0)
    assert config.minimum_order_notional_usd == pytest.approx(10.0)
    assert config.max_positions_per_symbol == 1
    assert config.quote_refresh_ms == 1_000
    assert config.maximum_book_age_ms == 1_000
    assert not config.enabled
    assert not config.accepts_live_risk
    assert config.execution_authority == "none"


def test_live_start_requires_both_flags_and_credentials() -> None:
    config = load_apex_mm_live_config(
        _CONFIG,
        enabled=True,
        accepts_live_risk=True,
    )

    with pytest.raises(ApexMMLiveConfigError, match="credentials"):
        config.require_live_start(credentials_present=False)
    config.require_live_start(credentials_present=True)
    assert config.execution_authority == "hyperliquid_mainnet"


def test_profile_fingerprint_excludes_runtime_arm_state() -> None:
    disarmed = load_apex_mm_live_config(_CONFIG)
    armed = load_apex_mm_live_config(
        _CONFIG,
        enabled=True,
        accepts_live_risk=True,
    )

    assert disarmed.profile_fingerprint == armed.profile_fingerprint
    assert disarmed.run_fingerprint != armed.run_fingerprint


def test_config_rejects_inventory_smaller_than_one_order(tmp_path: Path) -> None:
    text = _CONFIG.read_text(encoding="utf-8").replace(
        "max_inventory_notional_usd = 30.0",
        "max_inventory_notional_usd = 10.0",
    )
    path = tmp_path / "invalid.toml"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ApexMMLiveConfigError, match="inventory cap"):
        load_apex_mm_live_config(path)


def test_config_rejects_nonisolated_margin(tmp_path: Path) -> None:
    text = _CONFIG.read_text(encoding="utf-8").replace(
        'margin_mode = "isolated"',
        'margin_mode = "cross"',
    )
    path = tmp_path / "invalid.toml"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ApexMMLiveConfigError, match="margin_mode"):
        load_apex_mm_live_config(path)
