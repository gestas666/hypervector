"""Verify NautilusTrader + bundled Hyperliquid adapter install."""

from __future__ import annotations

import importlib
from importlib.metadata import version


def test_nautilus_trader_version_is_installed():
    import nautilus_trader

    installed = version("nautilus_trader")
    assert installed, "nautilus_trader metadata version must be non-empty"
    package_version = getattr(nautilus_trader, "__version__", None)
    if package_version is not None:
        assert package_version == installed
    # Project pins a modern release that includes Hyperliquid in the core wheel.
    major_minor = tuple(int(part) for part in installed.split(".")[:2])
    assert major_minor >= (1, 230), f"unexpected nautilus_trader version: {installed}"


def test_hyperliquid_adapter_public_surface():
    hl = importlib.import_module("nautilus_trader.adapters.hyperliquid")

    required = (
        "HYPERLIQUID",
        "HYPERLIQUID_CLIENT_ID",
        "HYPERLIQUID_VENUE",
        "HyperliquidDataClientConfig",
        "HyperliquidExecClientConfig",
        "HyperliquidLiveDataClientFactory",
        "HyperliquidLiveExecClientFactory",
    )
    for name in required:
        assert getattr(hl, name, None) is not None, f"missing public symbol: {name}"

    assert hl.HYPERLIQUID == "HYPERLIQUID"
    assert str(hl.HYPERLIQUID_VENUE) == "HYPERLIQUID"
    assert str(hl.HYPERLIQUID_CLIENT_ID) == "HYPERLIQUID"


def test_hyperliquid_client_configs_construct_offline():
    from nautilus_trader.adapters.hyperliquid import (
        HyperliquidDataClientConfig,
        HyperliquidExecClientConfig,
    )

    data_cfg = HyperliquidDataClientConfig()
    exec_cfg = HyperliquidExecClientConfig()

    assert data_cfg.http_timeout_secs == 10
    assert exec_cfg.http_timeout_secs == 10
    assert exec_cfg.private_key is None
    assert exec_cfg.normalize_prices is True
    assert exec_cfg.include_builder_attribution is True


def test_hyperliquid_live_factories_expose_create():
    from nautilus_trader.adapters.hyperliquid import (
        HyperliquidLiveDataClientFactory,
        HyperliquidLiveExecClientFactory,
    )
    from nautilus_trader.live.factories import LiveDataClientFactory, LiveExecClientFactory

    assert issubclass(HyperliquidLiveDataClientFactory, LiveDataClientFactory)
    assert issubclass(HyperliquidLiveExecClientFactory, LiveExecClientFactory)
    assert callable(HyperliquidLiveDataClientFactory.create)
    assert callable(HyperliquidLiveExecClientFactory.create)
