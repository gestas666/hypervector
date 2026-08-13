"""Tests for HIP-3 scheduled-session trade diagnostics."""

from types import SimpleNamespace
from typing import cast

from hypervector.research.hip3_market_session_reporting import (
    scheduled_session_trade_diagnostics,
)
from hypervector.research.shared_portfolio_models import SharedPortfolioTrade


def _trade(entry_time_utc: str, net_pnl_usd: float) -> SharedPortfolioTrade:
    return cast(
        SharedPortfolioTrade,
        SimpleNamespace(
            direction="long",
            entry_time_utc=entry_time_utc,
            net_pnl_usd=net_pnl_usd,
        ),
    )


def test_skhx_diagnostics_split_scheduled_reference_context() -> None:
    result = scheduled_session_trade_diagnostics(
        "xyz:SKHX",
        (
            _trade("2026-08-10T23:30:00+00:00", 2.0),
            _trade("2026-08-10T23:55:00+00:00", -1.0),
        ),
    )

    assert result["status"] == "classified"
    external = result["diagnostics"]["scheduled_external_reference"]
    internal = result["diagnostics"]["scheduled_internal_or_closed"]
    assert external["trades"] == 1
    assert external["net_pnl_usd"] == 2.0
    assert internal["trades"] == 1
    assert internal["net_pnl_usd"] == -1.0


def test_unclassified_market_does_not_invent_session_evidence() -> None:
    result = scheduled_session_trade_diagnostics("xyz:CL", ())

    assert result["status"] == "unclassified"
    assert result["diagnostics"] == {}
