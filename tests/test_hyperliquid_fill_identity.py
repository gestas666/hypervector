"""Exact Hyperliquid user-fill identity boundary contracts."""

from __future__ import annotations

import pytest

from hypervector.live.hyperliquid_parsing import (
    HyperliquidAdapterError,
    parse_fill,
)
from hypervector.live.hyperliquid_fill_identity import (
    HyperliquidFillIdentityError,
    ledger_fill_keys,
    require_trade_id,
)


def _raw_fill() -> dict[str, object]:
    return {
        "coin": "BTC",
        "oid": 101,
        "px": "73.10",
        "sz": "0.30",
        "side": "B",
        "time": 1_785_495_600_123,
        "fee": "0.00987",
        "feeToken": "USDC",
        "closedPnl": "0.0",
        "crossed": True,
        "dir": "Open Long",
        "hash": "0xfill",
        "tid": 118_906_512_037_719,
    }


def test_user_fill_preserves_venue_trade_id() -> None:
    """The venue trade ID, not order time or transaction hash, identifies a fill."""
    fill = parse_fill(_raw_fill())

    assert fill.trade_id == 118_906_512_037_719


def test_user_fill_without_venue_trade_id_fails_closed() -> None:
    """A fill lacking its exact venue identity cannot enter live accounting."""
    raw = _raw_fill()
    del raw["tid"]

    with pytest.raises(HyperliquidAdapterError, match="fill tid"):
        parse_fill(raw)


@pytest.mark.parametrize("trade_id", [None, False, 0, -1, 1.5, "7"])
def test_invalid_trade_id_fails_closed(trade_id: object) -> None:
    """Synthetic or malformed identities cannot enter lifecycle accounting."""
    with pytest.raises(HyperliquidFillIdentityError, match="positive integer"):
        require_trade_id(trade_id, label="test trade_id")


def test_ledger_fill_keys_rejects_non_object_payload() -> None:
    """Ledger evidence must retain an object payload for exact identity."""
    with pytest.raises(HyperliquidFillIdentityError, match="payload must be an object"):
        ledger_fill_keys(
            [{"payload": "invalid"}],
            timestamp_key="venue_timestamp_ms",
            label="test fill",
        )


def test_ledger_fill_keys_rejects_duplicate_exact_identity() -> None:
    """One venue trade ID cannot be counted twice in the same evidence set."""
    row = {
        "payload": {
            "trade_id": 7_001,
            "oid": 101,
            "venue_timestamp_ms": 1_785_495_600_123,
        }
    }
    with pytest.raises(HyperliquidFillIdentityError, match="duplicate test fill"):
        ledger_fill_keys(
            [row, row],
            timestamp_key="venue_timestamp_ms",
            label="test fill",
        )
