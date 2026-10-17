"""LiveExecClient protocol + HL adapter (offline; mock transport only)."""

from __future__ import annotations

from typing import Any

import pytest

from hypervector.live.policy import LivePolicy, LivePolicyError


class RecordingTransport:
    """Mock venue transport — records place/cancel calls, never hits network."""

    def __init__(
        self,
        *,
        response: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.cancel_calls: list[dict[str, Any]] = []
        self._response = (
            response if response is not None else {"status": "ok", "oid": "oid-1"}
        )
        self._error = error

    def place_market(
        self,
        *,
        coin: str,
        is_buy: bool,
        sz: float,
        wallet_address: str,
        private_key: str,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "coin": coin,
                "is_buy": is_buy,
                "sz": sz,
                "wallet_address": wallet_address,
                "private_key": private_key,
            }
        )
        if self._error is not None:
            raise self._error
        return dict(self._response)

    def cancel_all(
        self,
        *,
        wallet_address: str,
        private_key: str,
        coin: str | None = None,
    ) -> dict[str, Any]:
        self.cancel_calls.append(
            {
                "wallet_address": wallet_address,
                "private_key": private_key,
                "coin": coin,
            }
        )
        return {"status": "ok", "oid": "cancel-1"}


def _armed_policy(**kwargs: Any) -> LivePolicy:
    base = dict(
        enabled=True,
        armed=True,
        secrets_present=True,
        max_notional_usd=50.0,
    )
    base.update(kwargs)
    return LivePolicy(**base)


def test_place_result_shape_and_protocol():
    from hypervector.live.exec_client import PlaceResult, LiveExecClient

    ok = PlaceResult(submitted=True, venue_order_id="oid-1", error=None)
    assert ok.submitted is True
    assert ok.venue_order_id == "oid-1"
    assert ok.error is None

    bad = PlaceResult(submitted=False, venue_order_id=None, error="rejected")
    assert bad.submitted is False
    assert bad.venue_order_id is None
    assert bad.error == "rejected"

    # Protocol is importable (structural typing).
    assert LiveExecClient is not None


def test_factory_refuses_without_policy_gates():
    from hypervector.live.exec_client import create_live_exec_client

    transport = RecordingTransport()
    with pytest.raises(LivePolicyError, match="enabled"):
        create_live_exec_client(
            _armed_policy(enabled=False),
            wallet_address="0xabc",
            private_key="sekrit",
            transport=transport,
        )
    with pytest.raises(LivePolicyError, match="armed"):
        create_live_exec_client(
            _armed_policy(armed=False),
            wallet_address="0xabc",
            private_key="sekrit",
            transport=transport,
        )
    with pytest.raises(LivePolicyError, match="secrets"):
        create_live_exec_client(
            _armed_policy(secrets_present=False),
            wallet_address="0xabc",
            private_key="sekrit",
            transport=transport,
        )
    assert transport.calls == []


def test_factory_constructs_only_after_require_start():
    from hypervector.live.exec_client import (
        HyperliquidLiveExecClient,
        create_live_exec_client,
    )

    transport = RecordingTransport()
    client = create_live_exec_client(
        _armed_policy(),
        wallet_address="0xabc",
        private_key="sekrit",
        transport=transport,
    )
    assert isinstance(client, HyperliquidLiveExecClient)
    assert client.network == "mainnet"
    assert transport.calls == []  # construct must not place


def test_place_market_armed_calls_transport():
    from hypervector.live.exec_client import create_live_exec_client

    transport = RecordingTransport(response={"status": "ok", "oid": "hl-99"})
    client = create_live_exec_client(
        _armed_policy(max_notional_usd=100.0),
        wallet_address="0xwallet",
        private_key="pk",
        transport=transport,
    )
    result = client.place_market("BTC-PERP", "buy", 0.001, mark_px=50_000.0)
    assert result.submitted is True
    assert result.venue_order_id == "hl-99"
    assert result.error is None
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["coin"] == "BTC"
    assert call["is_buy"] is True
    assert call["sz"] == pytest.approx(0.001)
    assert call["wallet_address"] == "0xwallet"
    assert call["private_key"] == "pk"


def test_place_market_sell_side():
    from hypervector.live.exec_client import create_live_exec_client

    transport = RecordingTransport(response={"status": "ok", "oid": "s-1"})
    client = create_live_exec_client(
        _armed_policy(max_notional_usd=100.0),
        wallet_address="0xabc",
        private_key="k",
        transport=transport,
    )
    result = client.place_market("ETH", "sell", 0.01, mark_px=3000.0)
    assert result.submitted is True
    assert transport.calls[0]["is_buy"] is False
    assert transport.calls[0]["coin"] == "ETH"


def test_place_market_refuses_over_notional_without_transport_call():
    from hypervector.live.exec_client import create_live_exec_client

    transport = RecordingTransport()
    client = create_live_exec_client(
        _armed_policy(max_notional_usd=50.0),
        wallet_address="0xabc",
        private_key="k",
        transport=transport,
    )
    # 0.01 * 50_000 = 500 > 50
    result = client.place_market("BTC", "buy", 0.01, mark_px=50_000.0)
    assert result.submitted is False
    assert result.venue_order_id is None
    assert result.error is not None
    assert "notional" in result.error.lower() or "exceeds" in result.error.lower()
    assert transport.calls == []


def test_place_market_transport_error_returns_not_submitted():
    from hypervector.live.exec_client import create_live_exec_client

    transport = RecordingTransport(error=RuntimeError("venue down"))
    client = create_live_exec_client(
        _armed_policy(max_notional_usd=100.0),
        wallet_address="0xabc",
        private_key="k",
        transport=transport,
    )
    result = client.place_market("BTC", "buy", 0.001, mark_px=50_000.0)
    assert result.submitted is False
    assert result.venue_order_id is None
    assert "venue down" in (result.error or "")
    assert len(transport.calls) == 1


def test_create_from_env_reads_secrets(monkeypatch):
    from hypervector.live.exec_client import create_live_exec_client_from_env
    from hypervector.live.policy import SECRET_ENV_API_KEY, SECRET_ENV_WALLET

    monkeypatch.setenv(SECRET_ENV_WALLET, "0xenvwallet")
    monkeypatch.setenv(SECRET_ENV_API_KEY, "envkey")
    transport = RecordingTransport(response={"status": "ok", "oid": "e-1"})
    client = create_live_exec_client_from_env(
        _armed_policy(),
        transport=transport,
        environ={
            SECRET_ENV_WALLET: "0xenvwallet",
            SECRET_ENV_API_KEY: "envkey",
        },
    )
    result = client.place_market("BTC", "buy", 0.001, mark_px=40_000.0)
    assert result.submitted is True
    assert transport.calls[0]["wallet_address"] == "0xenvwallet"


def test_create_from_env_refuses_missing_secret_values(monkeypatch):
    from hypervector.live.exec_client import create_live_exec_client_from_env
    from hypervector.live.policy import SECRET_ENV_API_KEY, SECRET_ENV_WALLET

    monkeypatch.delenv(SECRET_ENV_WALLET, raising=False)
    monkeypatch.delenv(SECRET_ENV_API_KEY, raising=False)
    transport = RecordingTransport()
    # Policy thinks secrets present, but env empty — still refuse place path.
    with pytest.raises((LivePolicyError, ValueError)):
        create_live_exec_client_from_env(
            _armed_policy(secrets_present=True),
            transport=transport,
            environ={},
        )
    assert transport.calls == []


def test_mainnet_only_exchange_url():
    from hypervector.live.exec_client import HL_EXCHANGE_URL, HL_INFO_URL

    assert "hyperliquid.xyz" in HL_EXCHANGE_URL
    assert "testnet" not in HL_EXCHANGE_URL.lower()
    assert "testnet" not in HL_INFO_URL.lower()
    assert HL_EXCHANGE_URL.startswith("https://api.hyperliquid.xyz")


def test_submit_wired_surface_true():
    from hypervector.live.exec_client import is_submit_wired
    from hypervector.live.policy import LivePolicy

    assert is_submit_wired() is True
    r = LivePolicy().readiness()
    assert r["submit_wired"] is True
    # Default still cannot start
    assert r["can_start"] is False


def test_cancel_all_calls_transport():
    from hypervector.live.exec_client import create_live_exec_client

    transport = RecordingTransport()
    client = create_live_exec_client(
        _armed_policy(),
        wallet_address="0xabc",
        private_key="k",
        transport=transport,
    )
    result = client.cancel_all(symbol="BTC-PERP")
    assert result.submitted is True
    assert result.venue_order_id == "cancel-1"
    assert len(transport.cancel_calls) == 1
    assert transport.cancel_calls[0]["coin"] == "BTC"
