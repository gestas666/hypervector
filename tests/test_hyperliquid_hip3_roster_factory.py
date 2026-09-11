"""Tests for one shared Info-only HIP-3 roster factory."""

from __future__ import annotations

import pytest

from hypervector.live.hyperliquid_hip3_roster_factory import (
    create_read_only_hip3_roster_readers,
)
from hypervector.live.hyperliquid_sol_parsing import HyperliquidAdapterError
from hypervector.live.policy import SECRET_ENV_WALLET

_ADDRESS = "0x1111111111111111111111111111111111111111"


class _Info:
    """Placeholder Info-only client sufficient for construction tests."""

    def post(self, path: str, payload: dict[str, object]) -> object:
        """Supply only the precise public context request in source wiring tests."""
        assert path == "/info"
        assert payload == {"type": "metaAndAssetCtxs", "dex": "xyz"}
        return [{"universe": [{"name": "xyz:SPCX"}]}, [{"funding": "0.00001"}]]


class _Builder:
    """Record how many exact namespace-aware SDK clients were constructed."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.info = _Info()

    def build(self, *, perp_dexes: tuple[str, ...]) -> _Info:
        self.calls.append(perp_dexes)
        return self.info


def test_roster_factory_shares_one_info_only_client() -> None:
    """Five research readers must not construct five independent SDK clients."""
    builder = _Builder()
    readers = create_read_only_hip3_roster_readers(
        symbols=(
            "xyz:SP500",
            "xyz:SPCX",
            "xyz:SNDK",
            "xyz:GOLD",
            "xyz:BRENTOIL",
        ),
        environ={SECRET_ENV_WALLET: _ADDRESS},
        builder=builder,
    )

    assert tuple(readers) == (
        "xyz:SP500",
        "xyz:SPCX",
        "xyz:SNDK",
        "xyz:GOLD",
        "xyz:BRENTOIL",
    )
    assert builder.calls == [("xyz",)]


def test_roster_sources_share_one_info_client_for_books_accounts_and_funding() -> None:
    """Adding funding must not build a signer or an SDK client per asset."""
    from hypervector.live.hyperliquid_hip3_roster_factory import (
        create_read_only_hip3_roster_sources,
    )

    builder = _Builder()
    sources = create_read_only_hip3_roster_sources(
        symbols=("xyz:SPCX",),
        environ={SECRET_ENV_WALLET: _ADDRESS},
        builder=builder,
    )
    assert tuple(sources.readers) == ("xyz:SPCX",)
    assert sources.funding.snapshot() == {"xyz:SPCX": 0.00001}
    assert builder.calls == [("xyz",)]


@pytest.mark.parametrize(
    "symbols",
    (
        ("xyz:SP500", "cash:WTI"),
        ("xyz:SP500", "xyz:SP500"),
        ("SP500",),
    ),
)
def test_roster_factory_rejects_mixed_or_ambiguous_identity(
    symbols: tuple[str, ...],
) -> None:
    """The observer roster cannot silently span or duplicate namespaces."""
    with pytest.raises(HyperliquidAdapterError):
        create_read_only_hip3_roster_readers(
            symbols=symbols,
            environ={SECRET_ENV_WALLET: _ADDRESS},
            builder=_Builder(),
        )
