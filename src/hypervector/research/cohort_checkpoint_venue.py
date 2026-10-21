"""Failure-isolated public venue readers for cohort checkpoint publication."""

from __future__ import annotations

from collections.abc import Callable
import os

from hyperliquid.utils.error import ClientError, ServerError  # type: ignore[import-untyped]
from requests import RequestException

from hypervector.live.hyperliquid_portfolio_value import (
    HyperliquidPortfolioValueError,
    HyperliquidPortfolioValueReader,
)
from hypervector.live.policy import SECRET_ENV_WALLET
from hypervector.runtime_env import load_wallet_env_if_present

PortfolioFn = Callable[[], dict[str, object]]


def official_portfolio_fn() -> PortfolioFn:
    """Construct one read-only mainnet portfolio reader from public identity."""
    load_wallet_env_if_present()
    address = (os.environ.get(SECRET_ENV_WALLET) or "").strip()
    if not address:
        raise ValueError(f"venue portfolio requires {SECRET_ENV_WALLET}")
    from hyperliquid.info import Info  # type: ignore[import-untyped]
    from hyperliquid.utils import constants  # type: ignore[import-untyped]

    endpoint = str(constants.MAINNET_API_URL)
    if "testnet" in endpoint.lower():
        raise ValueError("venue portfolio refuses a testnet endpoint")
    reader: HyperliquidPortfolioValueReader | None = None

    def read() -> dict[str, object]:
        nonlocal reader
        if reader is None:
            reader = HyperliquidPortfolioValueReader(
                info=Info(endpoint, skip_ws=True),
                account_address=address,
            )
        return reader.snapshot().as_payload()

    return read


def portfolio_evidence(portfolio_fn: PortfolioFn) -> dict[str, object]:
    """Keep valuation failure explicit without suppressing core telemetry."""
    try:
        return portfolio_fn()
    except (
        HyperliquidPortfolioValueError,
        RequestException,
        ClientError,
        ServerError,
        OSError,
    ) as exc:
        return {
            "status": "unavailable",
            "technical_issue": f"venue portfolio query failed: {type(exc).__name__}",
            "contract": {
                "report_only": True,
                "execution_authority": "none",
                "execution_collateral_unchanged": True,
            },
        }
