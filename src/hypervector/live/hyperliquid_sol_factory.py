"""Fail-closed construction of the official mainnet Hyperliquid SDK clients."""

from __future__ import annotations

from typing import Protocol, cast

from hypervector.live.hyperliquid_protocol import (
    HyperliquidExchangeProtocol,
    HyperliquidInfoProtocol,
)
from hypervector.live.hyperliquid_sol_account import require_api_agent_parent
from hypervector.live.hyperliquid_sol_parsing import HyperliquidAdapterError

_SDK_TIMEOUT_SECONDS = 10.0


class SolSdkFactoryError(RuntimeError):
    """The official mainnet SDK clients could not be safely constructed."""


class SolSdkBuilderProtocol(Protocol):
    """Injectable authenticated SDK constructor for offline tests."""

    def build(
        self,
        *,
        account_address: str,
        private_key: str,
        perp_dexes: tuple[str, ...] = (),
    ) -> tuple[HyperliquidInfoProtocol, HyperliquidExchangeProtocol]:
        """Construct paired read and exchange clients for one account."""
        ...


class SolReadOnlySdkBuilderProtocol(Protocol):
    """Injectable Info-only SDK constructor for least-privilege preflight."""

    def build(
        self,
        *,
        perp_dexes: tuple[str, ...] = (),
    ) -> HyperliquidInfoProtocol:
        """Construct a mainnet HTTP client with no signing capability."""
        ...


class OfficialSolSdkBuilder:
    """Construct Hyperliquid SDK 0.24 clients against mainnet only."""

    def build(
        self,
        *,
        account_address: str,
        private_key: str,
        perp_dexes: tuple[str, ...] = (),
    ) -> tuple[HyperliquidInfoProtocol, HyperliquidExchangeProtocol]:
        """Build an account-addressed exchange and reuse its read-only client."""
        try:
            from eth_account import Account  # type: ignore[import-untyped]
            from hyperliquid.exchange import Exchange  # type: ignore[import-untyped]
            from hyperliquid.info import Info  # type: ignore[import-untyped]
            from hyperliquid.utils import constants  # type: ignore[import-untyped]
        except ImportError as exc:
            raise SolSdkFactoryError(
                "official Hyperliquid SDK dependencies are unavailable"
            ) from exc
        api_url = str(constants.MAINNET_API_URL)
        if "testnet" in api_url.lower() or "hyperliquid.xyz" not in api_url:
            raise SolSdkFactoryError("refusing non-mainnet Hyperliquid SDK URL")
        try:
            signing_account = Account.from_key(private_key)
        except (TypeError, ValueError) as exc:
            raise SolSdkFactoryError(
                "configured Hyperliquid private key is invalid"
            ) from exc
        signer_address = getattr(signing_account, "address", None)
        if not isinstance(signer_address, str):
            raise SolSdkFactoryError("configured signing key has no account address")
        identity_info = Info(
            base_url=api_url,
            skip_ws=True,
            timeout=_SDK_TIMEOUT_SECONDS,
        )
        try:
            require_api_agent_parent(
                identity_info.user_role(signer_address),
                account_address=account_address,
            )
        except HyperliquidAdapterError as exc:
            raise SolSdkFactoryError(str(exc)) from exc
        validated_dexes = _validated_perp_dexes(perp_dexes)
        options = {"perp_dexs": list(validated_dexes)} if validated_dexes else {}
        exchange = Exchange(
            signing_account,
            base_url=api_url,
            account_address=account_address,
            timeout=_SDK_TIMEOUT_SECONDS,
            **options,
        )
        info = exchange.info
        return (
            cast(HyperliquidInfoProtocol, info),
            cast(HyperliquidExchangeProtocol, exchange),
        )


def _validated_perp_dexes(perp_dexes: tuple[str, ...]) -> tuple[str, ...]:
    """Reject malformed or duplicate authenticated builder-perp namespaces."""
    for index, value in enumerate(perp_dexes):
        if value == "":
            if index != 0:
                raise SolSdkFactoryError("the empty core perp namespace must be first")
            continue
        if value != value.strip() or value != value.lower():
            raise SolSdkFactoryError("perp_dexes must contain exact lowercase names")
        if not value.replace("-", "").isalnum():
            raise SolSdkFactoryError("perp_dexes contain an invalid namespace")
    if len(set(perp_dexes)) != len(perp_dexes):
        raise SolSdkFactoryError("perp_dexes must not contain duplicates")
    return perp_dexes


class OfficialSolReadOnlySdkBuilder:
    """Construct an HTTP-only official SDK Info client against mainnet."""

    def build(
        self,
        *,
        perp_dexes: tuple[str, ...] = (),
    ) -> HyperliquidInfoProtocol:
        """Build an Info client without accepting or loading a private key."""
        try:
            from hyperliquid.info import Info  # type: ignore[import-untyped]
            from hyperliquid.utils import constants  # type: ignore[import-untyped]
        except ImportError as exc:
            raise SolSdkFactoryError(
                "official Hyperliquid SDK dependencies are unavailable"
            ) from exc
        api_url = str(constants.MAINNET_API_URL)
        if "testnet" in api_url.lower() or "hyperliquid.xyz" not in api_url:
            raise SolSdkFactoryError("refusing non-mainnet Hyperliquid SDK URL")
        validated_dexes = _validated_perp_dexes(perp_dexes)
        options = {"perp_dexs": list(validated_dexes)} if validated_dexes else {}
        return cast(
            HyperliquidInfoProtocol,
            Info(
                base_url=api_url,
                skip_ws=True,
                timeout=_SDK_TIMEOUT_SECONDS,
                **options,
            ),
        )
