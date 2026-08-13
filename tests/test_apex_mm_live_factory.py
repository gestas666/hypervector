"""Fail-closed official SDK construction for the Apex MM canary."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.live.apex_mm_live_config import load_apex_mm_live_config
from hypervector.live.apex_mm_live_factory import create_armed_apex_mm_adapter
from hypervector.live.apex_mm_streaming_venue import ApexMMStreamingVenue


class _Builder:
    def __init__(self) -> None:
        self.calls = 0

    def build(self, *, account_address: str, private_key: str) -> tuple[object, object]:
        self.calls += 1
        return object(), object()


def test_factory_does_not_build_authenticated_client_while_disarmed() -> None:
    builder = _Builder()
    config = load_apex_mm_live_config(Path("configs/apex_regime_mm_canary.toml"))

    with pytest.raises(Exception, match="--enabled"):
        create_armed_apex_mm_adapter(
            config,
            environ={
                "HYPERVECTOR_HL_WALLET_ADDRESS": "0x" + "1" * 40,
                "HYPERVECTOR_HL_API_PRIVATE_KEY": "configured",
            },
            builder=builder,
        )

    assert builder.calls == 0


def test_factory_builds_btc_adapter_only_after_all_gates() -> None:
    builder = _Builder()
    config = load_apex_mm_live_config(
        "configs/apex_regime_mm_canary.toml",
        enabled=True,
        accepts_live_risk=True,
    )

    adapter = create_armed_apex_mm_adapter(
        config,
        environ={
            "HYPERVECTOR_HL_WALLET_ADDRESS": "0x" + "1" * 40,
            "HYPERVECTOR_HL_API_PRIVATE_KEY": "configured",
        },
        builder=builder,
    )

    assert isinstance(adapter, ApexMMStreamingVenue)
    assert builder.calls == 1


def test_factory_refuses_missing_credentials_before_builder() -> None:
    builder = _Builder()
    config = load_apex_mm_live_config(
        "configs/apex_regime_mm_canary.toml",
        enabled=True,
        accepts_live_risk=True,
    )

    with pytest.raises(Exception, match="credentials"):
        create_armed_apex_mm_adapter(config, environ={}, builder=builder)

    assert builder.calls == 0
