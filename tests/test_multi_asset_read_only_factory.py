"""Least-privilege tests for shared multi-symbol venue readers."""

from __future__ import annotations

from unittest.mock import Mock

from hypervector.live.multi_asset_read_only_factory import (
    create_multi_asset_read_only_readers,
)
from hypervector.live.policy import SECRET_ENV_API_KEY, SECRET_ENV_WALLET


def test_factory_builds_info_only_readers_without_forwarding_signing_material() -> None:
    """Retired-symbol reconciliation cannot receive a private-key parameter."""
    captured: dict[str, object] = {}

    class Builder:
        def build(self, *, perp_dexes: tuple[str, ...] = ()) -> Mock:
            captured["perp_dexes"] = perp_dexes
            return Mock()

    readers = create_multi_asset_read_only_readers(
        ("BTC", "xyz:DDD"),
        environ={
            SECRET_ENV_WALLET: "0x" + "1" * 40,
            SECRET_ENV_API_KEY: "must-not-be-forwarded",
        },
        builder=Builder(),
    )

    assert set(readers) == {"BTC", "xyz:DDD"}
    assert captured == {"perp_dexes": ("", "xyz")}
