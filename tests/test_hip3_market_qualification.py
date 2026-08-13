"""Pure qualification tests for proposed XYZ HIP-3 roster assets."""

from __future__ import annotations

import pytest

from hypervector.research.hip3_market_qualification import (
    Hip3QualificationError,
    build_hip3_market_qualification,
)


def _dex() -> dict[str, object]:
    return {
        "name": "xyz",
        "fullName": "XYZ",
        "deployerFeeScale": "1.0",
        "assetToStreamingOiCap": [
            ["xyz:SP500", "1250000000.0"],
            ["xyz:SPCX", "750000000.0"],
        ],
        "assetToFundingMultiplier": [
            ["xyz:SP500", "0.5"],
            ["xyz:SPCX", "0.5"],
        ],
    }


def _metadata() -> dict[str, object]:
    return {
        "collateralToken": 0,
        "marginTables": [
            [
                50,
                {
                    "description": "",
                    "marginTiers": [{"lowerBound": "0", "maxLeverage": 50}],
                },
            ]
        ],
        "universe": [
            {
                "name": "xyz:SP500",
                "szDecimals": 3,
                "maxLeverage": 50,
                "marginTableId": 50,
                "growthMode": "enabled",
            },
            {
                "name": "xyz:SPCX",
                "szDecimals": 2,
                "maxLeverage": 20,
                "marginTableId": 20,
                "growthMode": "enabled",
            },
        ],
    }


def _contexts() -> list[dict[str, object]]:
    return [
        {
            "markPx": "7727.0",
            "midPx": "7727.05",
            "oraclePx": "7728.8",
            "funding": "-0.000002052",
            "openInterest": "66847.188",
            "dayNtlVlm": "474017175.38",
        },
        {
            "markPx": "113.59",
            "midPx": "113.5",
            "oraclePx": "113.62",
            "funding": "0.00000625",
            "openInterest": "1776690.38",
            "dayNtlVlm": "388931244.15",
        },
    ]


def _spot_metadata() -> dict[str, object]:
    return {"tokens": [{"name": "USDC", "index": 0, "szDecimals": 8, "weiDecimals": 8}]}


def _book(symbol: str, bid: str, ask: str) -> dict[str, object]:
    return {
        "coin": symbol,
        "time": 1_786_026_775_880,
        "levels": [
            [{"px": bid, "sz": "10", "n": 2}],
            [{"px": ask, "sz": "12", "n": 3}],
        ],
    }


def _candles(start: int, step: int, count: int) -> list[dict[str, object]]:
    return [
        {"t": start + step * index, "T": start + step * (index + 1) - 1}
        for index in range(count)
    ]


def test_builds_report_only_qualification_for_both_requested_markets() -> None:
    """Official metadata, book, and coverage facts remain execution-incapable."""
    symbols = ("xyz:SP500", "xyz:SPCX")
    books = {
        symbols[0]: _book(symbols[0], "7727.0", "7727.1"),
        symbols[1]: _book(symbols[1], "113.61", "113.63"),
    }
    candles = {
        symbol: {
            "1m": _candles(1_000_000, 60_000, 5_000),
            "5m": _candles(1_000_000, 300_000, 4),
            "15m": _candles(1_000_000, 900_000, 3),
        }
        for symbol in symbols
    }

    report = build_hip3_market_qualification(
        dex=_dex(),
        metadata=_metadata(),
        spot_metadata=_spot_metadata(),
        contexts=_contexts(),
        books=books,
        candles=candles,
        requested_symbols=symbols,
        observed_at_utc="2026-08-06T14:32:00+00:00",
    )

    assert report["execution_authority"] == "none"
    assert report["automatic_promotion"] is False
    assert report["status"] == "qualified_for_observation_only"
    assert report["collateral_token_index"] == 0
    assert report["collateral"] == {
        "name": "USDC",
        "index": 0,
        "size_decimals": 8,
        "wei_decimals": 8,
    }
    markets = report["markets"]
    assert isinstance(markets, list)
    sp500, spcx = markets
    assert sp500["symbol"] == "xyz:SP500"
    assert sp500["max_leverage"] == 50
    assert sp500["size_decimals"] == 3
    assert sp500["positive_fee_multiplier_vs_native"] == pytest.approx(0.2)
    assert sp500["streaming_open_interest_cap_usd"] == 1_250_000_000.0
    assert sp500["funding_multiplier"] == 0.5
    assert sp500["margin_table_details_available"] is True
    assert sp500["margin_tiers"] == [{"lower_bound_usd": 0.0, "max_leverage": 50}]
    assert sp500["book"]["spread_bps"] > 0.0
    assert sp500["candles"]["1m"]["api_row_cap_reached"] is True
    assert spcx["symbol"] == "xyz:SPCX"
    assert spcx["max_leverage"] == 20
    assert spcx["size_decimals"] == 2
    assert spcx["margin_table_details_available"] is False
    assert spcx["margin_tiers"] == []
    assert report["readiness"]["all_margin_tables_resolved"] is False
    assert report["readiness"]["live_execution_supported"] is False
    assert report["readiness"]["strategy_transfer_validated"] is False


def test_rejects_missing_exact_symbol_instead_of_guessing_alias() -> None:
    """A missing HIP-3 namespace must fail rather than fall back to native SP500."""
    with pytest.raises(Hip3QualificationError, match="xyz:SPCX metadata"):
        build_hip3_market_qualification(
            dex=_dex(),
            metadata={**_metadata(), "universe": _metadata()["universe"][:1]},
            spot_metadata=_spot_metadata(),
            contexts=_contexts()[:1],
            books={"xyz:SP500": _book("xyz:SP500", "7727.0", "7727.1")},
            candles={"xyz:SP500": {"15m": _candles(1, 900_000, 2)}},
            requested_symbols=("xyz:SP500", "xyz:SPCX"),
            observed_at_utc="2026-08-06T14:32:00+00:00",
        )


def test_rejects_native_or_malformed_symbols() -> None:
    """Qualification accepts only exact lower-case dex namespaces."""
    for symbol in ("SP500", "XYZ:SP500", "xyz:", "xyz:sp500"):
        with pytest.raises(Hip3QualificationError, match="HIP-3 symbol"):
            build_hip3_market_qualification(
                dex=_dex(),
                metadata=_metadata(),
                spot_metadata=_spot_metadata(),
                contexts=_contexts(),
                books={},
                candles={},
                requested_symbols=(symbol,),
                observed_at_utc="2026-08-06T14:32:00+00:00",
            )


def test_rejects_crossed_or_empty_books() -> None:
    """Observation readiness requires a coherent live two-sided book."""
    symbol = "xyz:SP500"
    with pytest.raises(Hip3QualificationError, match="crossed or locked"):
        build_hip3_market_qualification(
            dex=_dex(),
            metadata={**_metadata(), "universe": _metadata()["universe"][:1]},
            spot_metadata=_spot_metadata(),
            contexts=_contexts()[:1],
            books={symbol: _book(symbol, "7727.1", "7727.0")},
            candles={symbol: {"15m": _candles(1, 900_000, 2)}},
            requested_symbols=(symbol,),
            observed_at_utc="2026-08-06T14:32:00+00:00",
        )


def test_reports_candle_gaps_without_fabricating_bars() -> None:
    """Missing completed intervals remain measurable data-quality evidence."""
    symbol = "xyz:SP500"
    rows = _candles(1_000_000, 900_000, 2)
    rows.append({"t": 3_700_000, "T": 4_599_999})
    report = build_hip3_market_qualification(
        dex=_dex(),
        metadata={**_metadata(), "universe": _metadata()["universe"][:1]},
        spot_metadata=_spot_metadata(),
        contexts=_contexts()[:1],
        books={symbol: _book(symbol, "7727.0", "7727.1")},
        candles={symbol: {"15m": rows}},
        requested_symbols=(symbol,),
        observed_at_utc="2026-08-06T14:32:00+00:00",
    )

    market = report["markets"][0]
    assert market["candles"]["15m"]["gap_count"] == 1
    assert market["candles"]["15m"]["maximum_gap_ms"] == 1_800_000


def test_preserves_missing_growth_mode_as_unresolved_fee_evidence() -> None:
    """Observation can proceed when venue metadata omits fee-mode evidence."""
    symbol = "xyz:SP500"
    market = dict(_metadata()["universe"][0])
    market.pop("growthMode")
    report = build_hip3_market_qualification(
        dex=_dex(),
        metadata={**_metadata(), "universe": [market]},
        spot_metadata=_spot_metadata(),
        contexts=_contexts()[:1],
        books={symbol: _book(symbol, "7727.0", "7727.1")},
        candles={symbol: {"15m": _candles(1, 900_000, 2)}},
        requested_symbols=(symbol,),
        observed_at_utc="2026-08-06T14:32:00+00:00",
    )

    qualified = report["markets"][0]
    assert qualified["growth_mode"] is None
    assert qualified["positive_fee_multiplier_vs_native"] is None
    assert report["readiness"]["all_fee_multipliers_resolved"] is False
