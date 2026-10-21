"""Fail-closed namespace routing for read-only HIP-3 venue telemetry."""

from __future__ import annotations

import pytest

from hypervector.live.hyperliquid_perp_reader import HyperliquidPerpReader
from hypervector.live.hyperliquid_sol_parsing import HyperliquidAdapterError
from hypervector.live.policy import SECRET_ENV_WALLET

_ADDRESS = "0x1111111111111111111111111111111111111111"
_SYMBOL = "xyz:AAA"


class _Info:
    """Record the dex identity used by each account-sensitive read."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def meta(self, dex: str = "") -> object:
        self.calls.append(("meta", dex))
        return {
            "collateralToken": 0,
            "universe": [
                {
                    "name": _SYMBOL,
                    "szDecimals": 3,
                    "maxLeverage": 50,
                    "growthMode": "enabled",
                }
            ],
        }

    def perp_dexs(self) -> object:
        self.calls.append(("perp_dexs", ""))
        return [{"name": "xyz", "deployerFeeScale": "1.0"}]

    def user_fees(self, address: str) -> object:
        self.calls.append(("user_fees", address))
        return {
            "userAddRate": "0.00015",
            "userCrossRate": "0.00045",
            "activeReferralDiscount": "0.04",
        }

    def all_mids(self, dex: str = "") -> object:
        self.calls.append(("all_mids", dex))
        return {_SYMBOL: "6500.0"}

    def l2_snapshot(self, name: str) -> object:
        self.calls.append(("l2_snapshot", name))
        return {
            "coin": _SYMBOL,
            "time": 1_786_000_000_000,
            "levels": [
                [{"px": "6499.5", "sz": "2.0", "n": 3}],
                [{"px": "6500.5", "sz": "1.5", "n": 2}],
            ],
        }

    def user_state(self, address: str, dex: str = "") -> object:
        self.calls.append(("user_state", (address, dex)))
        return {
            "assetPositions": [
                {
                    "position": {
                        "coin": _SYMBOL,
                        "szi": "0.01",
                        "entryPx": "6490",
                        "liquidationPx": "6200",
                        "marginUsed": "13",
                        "positionValue": "65",
                        "unrealizedPnl": "0.1",
                        "leverage": {"type": "isolated", "value": 5},
                    }
                }
            ],
            "marginSummary": {
                "accountValue": "500",
                "totalMarginUsed": "13",
                "totalNtlPos": "65",
            },
            "withdrawable": "487",
        }

    def query_user_abstraction_state(self, address: str) -> object:
        self.calls.append(("query_user_abstraction_state", address))
        return "disabled"

    def spot_user_state(self, address: str) -> object:
        raise AssertionError("legacy account must not read spot state")

    def frontend_open_orders(self, address: str, dex: str = "") -> object:
        self.calls.append(("frontend_open_orders", (address, dex)))
        return []

    def user_fills(self, address: str) -> object:
        self.calls.append(("user_fills", address))
        return []

    def query_order_by_oid(self, user: str, oid: int | str) -> object:
        raise AssertionError("order lookup is outside this test")

    def user_funding_history(
        self,
        user: str,
        startTime: int,
        endTime: int | None = None,
    ) -> object:
        return []


class _Builder:
    """Construct an Info-only client while recording requested namespaces."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.info = _Info()

    def build(self, *, perp_dexes: tuple[str, ...]) -> _Info:
        self.calls.append(perp_dexes)
        return self.info


def test_reader_scopes_every_supported_hip3_read_to_exact_dex() -> None:
    """Namespaced metadata, mids, state, and orders must never use native scope."""
    info = _Info()
    reader = HyperliquidPerpReader(
        info=info,
        account_address=_ADDRESS,
        symbol=_SYMBOL,
        perp_dex="xyz",
    )

    preflight = reader.preflight(expected_max_leverage=50)
    fee_metadata = reader.hip3_fee_metadata()
    book = reader.book_snapshot(depth_levels=1)
    reconciliation = reader.reconcile()

    assert preflight.market.symbol == _SYMBOL
    assert preflight.position.size_signed == 0.01
    assert preflight.fees.active_referral_discount == 0.04
    assert preflight.hip3_fee_metadata == fee_metadata
    assert fee_metadata.deployer_fee_scale == 1.0
    assert fee_metadata.growth_mode is True
    assert fee_metadata.collateral_token_index == 0
    assert book.mid_price == 6500.0
    assert reconciliation.position.size_signed == 0.01
    assert ("meta", "xyz") in info.calls
    assert ("all_mids", "xyz") in info.calls
    assert ("user_state", (_ADDRESS, "xyz")) in info.calls
    assert ("frontend_open_orders", (_ADDRESS, "xyz")) in info.calls
    assert ("l2_snapshot", _SYMBOL) in info.calls
    assert ("perp_dexs", "") in info.calls
    assert not any(
        method in {"meta", "all_mids"} and argument == ""
        for method, argument in info.calls
    )


@pytest.mark.parametrize(
    ("symbol", "perp_dex"),
    (
        ("xyz:AAA", ""),
        ("xyz:AAA", "cash"),
        ("AAA", "xyz"),
    ),
)
def test_reader_rejects_mismatched_symbol_and_dex_identity(
    symbol: str,
    perp_dex: str,
) -> None:
    """A namespaced read must not silently fall through to another venue scope."""
    with pytest.raises(HyperliquidAdapterError, match="namespace"):
        HyperliquidPerpReader(
            info=_Info(),
            account_address=_ADDRESS,
            symbol=symbol,
            perp_dex=perp_dex,
        )


def test_factory_constructs_info_only_namespaced_reader() -> None:
    """Read-only HIP-3 construction must accept no signer or private-key input."""
    from hypervector.live.hyperliquid_hip3_factory import (
        create_read_only_hip3_reader,
    )

    builder = _Builder()
    reader = create_read_only_hip3_reader(
        symbol=_SYMBOL,
        environ={SECRET_ENV_WALLET: _ADDRESS},
        builder=builder,
    )

    preflight = reader.preflight(expected_max_leverage=50)

    assert preflight.market.symbol == _SYMBOL
    assert builder.calls == [("xyz",)]


def test_default_factory_builds_mainnet_info_with_requested_namespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The production default must initialize Info for xyz without Exchange."""
    import hyperliquid.info

    from hypervector.live.hyperliquid_hip3_factory import (
        create_read_only_hip3_reader,
    )

    observed: dict[str, object] = {}

    class _OfficialInfo(_Info):
        def __init__(
            self,
            *,
            base_url: str,
            skip_ws: bool,
            timeout: float,
            perp_dexs: list[str],
        ) -> None:
            super().__init__()
            observed.update(
                base_url=base_url,
                skip_ws=skip_ws,
                timeout=timeout,
                perp_dexs=perp_dexs,
            )

    monkeypatch.setattr(hyperliquid.info, "Info", _OfficialInfo)

    reader = create_read_only_hip3_reader(
        symbol=_SYMBOL,
        environ={SECRET_ENV_WALLET: _ADDRESS},
    )
    preflight = reader.preflight(expected_max_leverage=50)

    assert preflight.market.symbol == _SYMBOL
    assert observed["perp_dexs"] == ["xyz"]
    assert observed["skip_ws"] is True
    assert "testnet" not in str(observed["base_url"]).lower()
