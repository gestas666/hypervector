"""Failure-isolated public venue readers for cohort checkpoint publication."""

from __future__ import annotations

from collections.abc import Callable
import os
import sys

from hyperliquid.utils.error import ClientError, ServerError  # type: ignore[import-untyped]
from requests import RequestException

from hypervector.live.hyperliquid_funding_history import (
    HyperliquidFundingHistoryReader,
)
from hypervector.live.hyperliquid_portfolio_value import (
    HyperliquidPortfolioValueError,
    HyperliquidPortfolioValueReader,
)
from hypervector.live.policy import SECRET_ENV_WALLET
from hypervector.research.cohort_eligible_policy_funding import (
    EligiblePolicyFundingEvidence,
)
from hypervector.runtime_env import load_wallet_env_if_present

PortfolioFn = Callable[[], dict[str, object]]
FundingFn = Callable[[str, int, int], EligiblePolicyFundingEvidence | None]


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
    reader = HyperliquidPortfolioValueReader(
        info=Info(endpoint, skip_ws=True),
        account_address=address,
    )
    return lambda: reader.snapshot().as_payload()


def official_funding_fn() -> FundingFn:
    """Construct one failure-isolated public mainnet funding reader."""
    from hyperliquid.info import Info  # type: ignore[import-untyped]
    from hyperliquid.utils import constants  # type: ignore[import-untyped]

    endpoint = str(constants.MAINNET_API_URL)
    if "testnet" in endpoint.lower():
        raise ValueError("eligible-policy funding refuses a testnet endpoint")
    reader = HyperliquidFundingHistoryReader(Info(endpoint, skip_ws=True))
    return failure_isolated_funding_fn(reader)


def failure_isolated_funding_fn(
    reader: HyperliquidFundingHistoryReader,
) -> FundingFn:
    """Keep public funding failure from suppressing core live telemetry."""

    def read(
        symbol: str,
        start_ms: int,
        end_ms: int,
    ) -> EligiblePolicyFundingEvidence | None:
        try:
            return reader.read(symbol, start_ms, end_ms)
        except (
            RequestException,
            ClientError,
            ServerError,
            OSError,
            ValueError,
        ) as exc:
            print(
                f"eligible-policy funding unavailable: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            return None

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
