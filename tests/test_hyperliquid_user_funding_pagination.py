"""Complete account funding windows at the symbol-scoped reader boundary."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from hypervector.live.hyperliquid_perp_reader import HyperliquidPerpReader
from hypervector.live.hyperliquid_sol_parsing import HyperliquidAdapterError

ADDRESS = "0x1111111111111111111111111111111111111111"
SYMBOL = "xyz:SNDK"
PAGE_SIZE = 500


class FundingInfo:
    """Serve bounded synthetic pages without network or an execution client."""

    def __init__(self, pages: Sequence[object]) -> None:
        """Retain scripted responses and inspectable request bounds."""
        self.pages = list(pages)
        self.calls: list[tuple[int, int | None]] = []

    def user_funding_history(
        self, user: str, startTime: int, endTime: int | None = None
    ) -> object:
        """Return the next page and reject an unexpected extra request."""
        assert user == ADDRESS
        self.calls.append((startTime, endTime))
        assert self.pages, "Unexpected additional funding request"
        return self.pages.pop(0)


def row(
    timestamp: int, coin: str = SYMBOL, amount: str = "0.004137"
) -> dict[str, object]:
    """Create an account funding settlement with a distinct coin/time identity."""
    return {
        "time": timestamp,
        "hash": "0x" + "0" * 64,
        "delta": {
            "type": "funding",
            "coin": coin,
            "usdc": amount,
            "szi": "-0.306",
            "fundingRate": "0.0000082416",
        },
    }


def reader(info: FundingInfo) -> HyperliquidPerpReader:
    """Construct only the public reader with its scriptable funding dependency."""
    return HyperliquidPerpReader(
        info=info, account_address=ADDRESS, symbol=SYMBOL, perp_dex="xyz"
    )


def test_full_foreign_symbol_page_still_fetches_the_owned_symbol() -> None:
    """Page size belongs to the account response, before symbol filtering."""
    first = [row(i, "BTC") for i in range(1, PAGE_SIZE + 1)]
    second = [first[-1], row(PAGE_SIZE), row(PAGE_SIZE + 1)]
    info = FundingInfo([first, second])

    payments = reader(info).funding_payments(start_time_ms=0, end_time_ms=1_000)

    assert [payment.timestamp_ms for payment in payments] == [500, 501]
    assert info.calls == [(0, 1_000), (500, 1_000)]


def test_inclusive_page_boundary_does_not_duplicate_funding() -> None:
    """Re-query the final timestamp and retain each exact funding identity once."""
    first = [row(i) for i in range(1, PAGE_SIZE + 1)]
    info = FundingInfo([first, [first[-1], row(PAGE_SIZE + 1)]])

    payments = reader(info).funding_payments(start_time_ms=0, end_time_ms=1_000)

    assert len(payments) == PAGE_SIZE + 1
    assert len({(p.transaction_hash, p.timestamp_ms) for p in payments}) == len(
        payments
    )
    assert info.calls == [(0, 1_000), (500, 1_000)]


@pytest.mark.parametrize("timestamp", [-1, 1_001, True])
def test_malformed_or_outside_window_timestamp_refuses(timestamp: object) -> None:
    """Untrustworthy timestamps cannot advance a funding cursor."""
    malformed = row(1)
    malformed["time"] = timestamp
    with pytest.raises(HyperliquidAdapterError):
        reader(FundingInfo([[malformed]])).funding_payments(
            start_time_ms=0, end_time_ms=1_000
        )


def test_conflicting_overlap_refuses_instead_of_selecting_a_payment() -> None:
    """The same native identity cannot change amount between pages."""
    first = [row(i) for i in range(1, PAGE_SIZE + 1)]
    conflict = row(PAGE_SIZE, amount="-0.004137")
    with pytest.raises(HyperliquidAdapterError, match="conflict"):
        reader(FundingInfo([first, [conflict]])).funding_payments(
            start_time_ms=0, end_time_ms=1_000
        )


def test_full_nonadvancing_timestamp_refuses_incomplete_history() -> None:
    """A saturated timestamp must fail explicitly rather than skip unseen rows."""
    first = [row(500, f"asset-{i}") for i in range(PAGE_SIZE)]
    with pytest.raises(HyperliquidAdapterError, match="advance"):
        reader(FundingInfo([first, first])).funding_payments(
            start_time_ms=0, end_time_ms=1_000
        )


def test_empty_history_is_explicitly_empty() -> None:
    """A valid empty page completes without requesting a second page."""
    info = FundingInfo([[]])
    assert reader(info).funding_payments(start_time_ms=0, end_time_ms=1_000) == ()
    assert info.calls == [(0, 1_000)]


def test_out_of_order_page_refuses() -> None:
    """A descending page cannot establish a safe continuation cursor."""
    with pytest.raises(HyperliquidAdapterError, match="nondecreasing"):
        reader(FundingInfo([[row(2), row(1)]])).funding_payments(
            start_time_ms=0, end_time_ms=1_000
        )


def test_reversed_query_bounds_refuse_before_sdk_read() -> None:
    """Invalid requests cannot invoke the external read dependency."""
    info = FundingInfo([])
    with pytest.raises(HyperliquidAdapterError, match="precede"):
        reader(info).funding_payments(start_time_ms=2, end_time_ms=1)
    assert info.calls == []
