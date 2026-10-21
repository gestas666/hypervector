"""Construction barriers for the official mainnet Hyperliquid SDK clients."""

from __future__ import annotations


import pytest

from hypervector.live.hyperliquid_sol_factory import (
    OfficialSolReadOnlySdkBuilder,
    OfficialSolSdkBuilder,
    SolReadOnlySdkBuilderProtocol,
    SolSdkBuilderProtocol,
    SolSdkFactoryError,
)


ADDRESS = "0x1111111111111111111111111111111111111111"
AGENT_ADDRESS = "0x2222222222222222222222222222222222222222"


class StubInfo:
    """SDK-shaped info object that performs no network calls."""

    def meta(self, dex: str = "") -> object:
        return {"universe": []}

    def user_fees(self, address: str) -> object:
        return {}

    def all_mids(self, dex: str = "") -> object:
        return {}

    def user_state(self, address: str, dex: str = "") -> object:
        return {}

    def query_user_abstraction_state(self, address: str) -> object:
        return "disabled"

    def spot_user_state(self, address: str) -> object:
        return {"balances": []}

    def frontend_open_orders(self, address: str, dex: str = "") -> object:
        return []

    def user_fills(self, address: str) -> object:
        return []

    def query_order_by_oid(self, user: str, oid: int) -> object:
        return {}

    def user_funding_history(
        self,
        user: str,
        startTime: int,
        endTime: int | None = None,
    ) -> object:
        return []


class StubExchange:
    """SDK-shaped exchange object that records no external side effects."""

    def update_leverage(
        self, leverage: int, name: str, is_cross: bool = True
    ) -> object:
        return {"status": "ok"}

    def market_open(
        self,
        name: str,
        is_buy: bool,
        sz: float,
        px: float | None = None,
        slippage: float = 0.05,
        cloid: object | None = None,
        builder: object | None = None,
    ) -> object:
        return {}

    def order(
        self,
        name: str,
        is_buy: bool,
        sz: float,
        limit_px: float,
        order_type: object,
        reduce_only: bool = False,
        cloid: object | None = None,
        builder: object | None = None,
    ) -> object:
        return {}

    def cancel(self, name: str, oid: int) -> object:
        return {}

    def market_close(
        self,
        coin: str,
        sz: float | None = None,
        px: float | None = None,
        slippage: float = 0.05,
        cloid: object | None = None,
        builder: object | None = None,
    ) -> object:
        return {}


class RecordingBuilder(SolSdkBuilderProtocol):
    """Record whether authenticated SDK construction was attempted."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def build(
        self, *, account_address: str, private_key: str
    ) -> tuple[StubInfo, StubExchange]:
        self.calls.append((account_address, private_key))
        return StubInfo(), StubExchange()


class RecordingReadBuilder(SolReadOnlySdkBuilderProtocol):
    """Prove read-only construction cannot receive signing material."""

    def __init__(self) -> None:
        self.calls = 0

    def build(self) -> StubInfo:
        self.calls += 1
        return StubInfo()


def _env() -> dict[str, str]:
    return {
        SECRET_ENV_WALLET: ADDRESS,
        SECRET_ENV_API_KEY: "test-private-key",
    }


def test_official_builder_addresses_agent_signing_to_funded_account(
    monkeypatch,
) -> None:
    """The API signing key may differ from the funded account address."""
    import eth_account
    import hyperliquid.exchange
    import hyperliquid.info

    signing_account = type(
        "AgentSigningAccount",
        (),
        {"address": AGENT_ADDRESS},
    )()
    observed: dict[str, object] = {}

    class AgentRoleInfo(StubInfo):
        def __init__(
            self,
            *,
            base_url: str,
            skip_ws: bool,
            timeout: float,
        ) -> None:
            pass

        def user_role(self, address: str) -> object:
            assert address == AGENT_ADDRESS
            return {"role": "agent", "data": {"user": ADDRESS}}

    class FakeBuiltExchange(StubExchange):
        def __init__(
            self,
            account: object,
            *,
            base_url: str,
            account_address: str,
            timeout: float | None = None,
        ) -> None:
            observed.update(
                {
                    "account": account,
                    "base_url": base_url,
                    "account_address": account_address,
                    "timeout": timeout,
                }
            )
            self.info = StubInfo()

    monkeypatch.setattr(
        eth_account.Account,
        "from_key",
        lambda private_key: signing_account,
    )
    monkeypatch.setattr(hyperliquid.info, "Info", AgentRoleInfo)
    monkeypatch.setattr(hyperliquid.exchange, "Exchange", FakeBuiltExchange)

    info, exchange = OfficialSolSdkBuilder().build(
        account_address=ADDRESS,
        private_key="agent-key",
    )

    assert isinstance(info, StubInfo)
    assert isinstance(exchange, FakeBuiltExchange)
    assert observed["account"] is signing_account
    assert observed["account_address"] == ADDRESS
    assert observed["timeout"] == pytest.approx(10.0)
    assert "testnet" not in str(observed["base_url"]).lower()


def test_official_builder_loads_exact_authenticated_perp_dexes(monkeypatch) -> None:
    """Namespaced execution must initialize Exchange with the exact dex roster."""
    import eth_account
    import hyperliquid.exchange
    import hyperliquid.info

    signing_account = type("AgentSigningAccount", (), {"address": AGENT_ADDRESS})()
    observed: dict[str, object] = {}

    class AgentRoleInfo(StubInfo):
        def __init__(
            self,
            *,
            base_url: str,
            skip_ws: bool,
            timeout: float,
        ) -> None:
            pass

        def user_role(self, address: str) -> object:
            return {"role": "agent", "data": {"user": ADDRESS}}

    class FakeBuiltExchange(StubExchange):
        def __init__(
            self,
            account: object,
            *,
            base_url: str,
            account_address: str,
            perp_dexs: list[str],
            timeout: float | None = None,
        ) -> None:
            observed["perp_dexs"] = perp_dexs
            self.info = StubInfo()

    monkeypatch.setattr(eth_account.Account, "from_key", lambda key: signing_account)
    monkeypatch.setattr(hyperliquid.info, "Info", AgentRoleInfo)
    monkeypatch.setattr(hyperliquid.exchange, "Exchange", FakeBuiltExchange)

    OfficialSolSdkBuilder().build(
        account_address=ADDRESS,
        private_key="agent-key",
        perp_dexes=("", "xyz"),
    )

    assert observed["perp_dexs"] == ["", "xyz"]


def test_official_builder_rejects_main_wallet_key_before_exchange_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live startup requires least-privilege agent signing, not the main key."""
    import eth_account
    import hyperliquid.exchange
    import hyperliquid.info

    signing_account = type("MainSigningAccount", (), {"address": ADDRESS})()
    exchange_constructed = False

    class UserRoleInfo(StubInfo):
        def __init__(
            self,
            *,
            base_url: str,
            skip_ws: bool,
            timeout: float,
        ) -> None:
            pass

        def user_role(self, address: str) -> object:
            return {"role": "user"}

    def forbidden_exchange(*args: object, **kwargs: object) -> object:
        nonlocal exchange_constructed
        exchange_constructed = True
        return object()

    monkeypatch.setattr(eth_account.Account, "from_key", lambda key: signing_account)
    monkeypatch.setattr(hyperliquid.info, "Info", UserRoleInfo)
    monkeypatch.setattr(hyperliquid.exchange, "Exchange", forbidden_exchange)

    with pytest.raises(SolSdkFactoryError, match="authorized API agent"):
        OfficialSolSdkBuilder().build(
            account_address=ADDRESS,
            private_key="main-wallet-key",
        )

    assert exchange_constructed is False


def test_official_read_only_builder_uses_mainnet_without_websocket(monkeypatch) -> None:
    """The least-privilege builder creates only an HTTP Info client."""
    import hyperliquid.info

    observed: dict[str, object] = {}

    class FakeBuiltInfo(StubInfo):
        def __init__(
            self,
            *,
            base_url: str,
            skip_ws: bool,
            timeout: float | None = None,
        ) -> None:
            observed.update(
                {"base_url": base_url, "skip_ws": skip_ws, "timeout": timeout}
            )

    monkeypatch.setattr(hyperliquid.info, "Info", FakeBuiltInfo)

    result = OfficialSolReadOnlySdkBuilder().build()

    assert isinstance(result, FakeBuiltInfo)
    assert observed["skip_ws"] is True
    assert observed["timeout"] == pytest.approx(10.0)
    assert "testnet" not in str(observed["base_url"]).lower()


def test_official_read_only_builder_loads_core_and_hip3_metadata(monkeypatch) -> None:
    """Mixed public books require both the empty core and HIP-3 namespace."""
    import hyperliquid.info

    observed: dict[str, object] = {}

    class FakeBuiltInfo(StubInfo):
        def __init__(
            self,
            *,
            base_url: str,
            skip_ws: bool,
            perp_dexs: list[str],
            timeout: float | None = None,
        ) -> None:
            observed["perp_dexs"] = perp_dexs

    monkeypatch.setattr(hyperliquid.info, "Info", FakeBuiltInfo)

    OfficialSolReadOnlySdkBuilder().build(perp_dexes=("", "xyz"))

    assert observed["perp_dexs"] == ["", "xyz"]
