"""Unsigned V58 BTC venue-mark capture tests."""

from __future__ import annotations

from hypervector.research.v58_btc_sweep_marks import parse_btc_mark_snapshot


def test_core_context_response_binds_exact_btc_mark_at_receipt() -> None:
    """Position-aligned public context data must retain exact BTC identity."""
    row = parse_btc_mark_snapshot(
        [
            {"universe": [{"name": "ETH"}, {"name": "BTC"}]},
            [
                _context("1900", "1901"),
                _context("69000", "69001"),
            ],
        ],
        run_id="observer-v58",
        received_ts_ns=1_787_150_000_123_456_789,
    )

    assert row == {
        "schema_version": 1,
        "symbol": "BTC",
        "source": "hyperliquid_info_metaAndAssetCtxs_rest",
        "run_id": "observer-v58",
        "received_ts_ms": 1_787_150_000_123,
        "received_ts_ns": 1_787_150_000_123_456_789,
        "mark_price": 69000.0,
        "oracle_price": 69001.0,
        "funding_rate_hourly": 0.00001,
        "open_interest": 12.5,
    }


def test_core_context_response_rejects_ambiguous_btc_identity() -> None:
    """Duplicate metadata names cannot silently choose a mark context."""
    response = [
        {"universe": [{"name": "BTC"}, {"name": "BTC"}]},
        [_context("69000", "69001"), _context("69002", "69003")],
    ]

    try:
        parse_btc_mark_snapshot(
            response,
            run_id="observer-v58",
            received_ts_ns=1_787_150_000_123_456_789,
        )
    except ValueError as exc:
        assert "exactly once" in str(exc)
    else:
        raise AssertionError("ambiguous BTC mark identity must fail closed")


def _context(mark: str, oracle: str) -> dict[str, str]:
    return {
        "markPx": mark,
        "oraclePx": oracle,
        "funding": "0.00001",
        "openInterest": "12.5",
    }
