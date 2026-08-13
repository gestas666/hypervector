"""Report-only scheduled-session diagnostics for HIP-3 trade lifecycles."""

from dataclasses import asdict
from datetime import datetime
from typing import Iterable

from hypervector.research.hip3_market_sessions import (
    SCHEDULED_EXTERNAL_REFERENCE,
    SCHEDULED_INTERNAL_OR_CLOSED,
    oracle_session_contract,
    scheduled_oracle_session,
)
from hypervector.research.mu_hip3_candidate import summarize_trades
from hypervector.research.shared_portfolio_models import SharedPortfolioTrade


def scheduled_session_trade_diagnostics(
    symbol: str,
    trades: Iterable[SharedPortfolioTrade],
) -> dict[str, object]:
    """Summarize trades by published schedule without creating a trade gate."""
    contract = oracle_session_contract(symbol)
    if contract["status"] != "classified":
        return {"status": "unclassified", "contract": contract, "diagnostics": {}}
    records = tuple(trades)
    labels = (SCHEDULED_EXTERNAL_REFERENCE, SCHEDULED_INTERNAL_OR_CLOSED)
    diagnostics = {
        label: asdict(
            summarize_trades(
                trade
                for trade in records
                if scheduled_oracle_session(symbol, _entry_time(trade)) == label
            )["all"]
        )
        for label in labels
    }
    return {"status": "classified", "contract": contract, "diagnostics": diagnostics}


def _entry_time(trade: SharedPortfolioTrade) -> datetime:
    return datetime.fromisoformat(trade.entry_time_utc)
