"""Failure-isolation tests for public checkpoint venue readers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from hyperliquid.utils.error import ClientError

import hypervector.research.cohort_checkpoint_venue as venue
from hypervector.live.policy import SECRET_ENV_WALLET


def test_portfolio_reader_initialization_is_lazy_and_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient Info startup failure must not kill checkpoint publication."""
    attempts = 0

    class FakeInfo:
        def __init__(self, _endpoint: str, *, skip_ws: bool) -> None:
            nonlocal attempts
            assert skip_ws is True
            attempts += 1
            if attempts == 1:
                raise ClientError(429, None, "rate limited", None, {})

    class FakeReader:
        def __init__(self, *, info: object, account_address: str) -> None:
            assert isinstance(info, FakeInfo)
            assert account_address

        def snapshot(self) -> SimpleNamespace:
            return SimpleNamespace(
                as_payload=lambda: {
                    "status": "observed",
                    "portfolio_value_usd": 5000.0,
                }
            )

    monkeypatch.setenv(SECRET_ENV_WALLET, "0xpublic")
    monkeypatch.setattr("hyperliquid.info.Info", FakeInfo)
    monkeypatch.setattr(venue, "HyperliquidPortfolioValueReader", FakeReader)

    reader = venue.official_portfolio_fn()

    assert venue.portfolio_evidence(reader)["status"] == "unavailable"
    assert venue.portfolio_evidence(reader) == {
        "status": "observed",
        "portfolio_value_usd": 5000.0,
    }
    assert attempts == 2
