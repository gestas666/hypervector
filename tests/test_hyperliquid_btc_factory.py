"""Fail-closed construction tests for the BTC authenticated adapter."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from hypervector.live.hyperliquid_btc_adapter import BtcHyperliquidAdapter
from hypervector.live.hyperliquid_btc_factory import (
    create_armed_btc_adapter,
    create_armed_hulk_btc_adapter,
)
from hypervector.live.hulk_smash_live_config import load_hulk_smash_live_config
from hypervector.live.hyperliquid_protocol import (
    HyperliquidExchangeProtocol,
    HyperliquidInfoProtocol,
)
from hypervector.live.policy import SECRET_ENV_API_KEY, SECRET_ENV_WALLET
from hypervector.live.source_follow_live_config import (
    SourceFollowLiveConfigError,
    load_source_follow_live_config,
)

CONFIG = Path("configs/hypervelocity_source_follow_minrange12_alloc35_canary.toml")
_ADDRESS = "0x1111111111111111111111111111111111111111"


class _Builder:
    def __init__(self) -> None:
        self.calls = 0

    def build(
        self,
        *,
        account_address: str,
        private_key: str,
    ) -> tuple[HyperliquidInfoProtocol, HyperliquidExchangeProtocol]:
        self.calls += 1
        return (
            Mock(spec=HyperliquidInfoProtocol),
            Mock(spec=HyperliquidExchangeProtocol),
        )


def test_disarmed_config_refuses_before_authenticated_builder() -> None:
    """Configured secrets cannot bypass either operator arm flag."""
    config = load_source_follow_live_config(CONFIG)
    builder = _Builder()

    with pytest.raises(SourceFollowLiveConfigError, match="--enabled"):
        create_armed_btc_adapter(
            config,
            environ={SECRET_ENV_WALLET: _ADDRESS, SECRET_ENV_API_KEY: "0x01"},
            builder=builder,
        )

    assert builder.calls == 0


def test_both_flags_construct_exactly_one_adapter() -> None:
    """Armed construction passes the account identity to one SDK builder call."""
    config = load_source_follow_live_config(
        CONFIG,
        enabled=True,
        accepts_live_risk=True,
    )
    builder = _Builder()

    adapter = create_armed_btc_adapter(
        config,
        environ={SECRET_ENV_WALLET: _ADDRESS, SECRET_ENV_API_KEY: "0x01"},
        builder=builder,
    )

    assert isinstance(adapter, BtcHyperliquidAdapter)
    assert builder.calls == 1


def test_armed_hulk_config_constructs_same_btc_adapter_boundary() -> None:
    """The Hulk canary reuses the authenticated adapter after its own arm gate."""
    config = load_hulk_smash_live_config(
        "configs/hulk_smash_short_robust_v3_canary.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    builder = _Builder()

    adapter = create_armed_hulk_btc_adapter(
        config,
        environ={SECRET_ENV_WALLET: _ADDRESS, SECRET_ENV_API_KEY: "0x01"},
        builder=builder,
    )

    assert isinstance(adapter, BtcHyperliquidAdapter)
    assert builder.calls == 1
    assert adapter.slippage_fraction == config.market_slippage_cap_fraction
