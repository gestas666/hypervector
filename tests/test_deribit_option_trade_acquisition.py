"""Tests for bounded Deribit BTC option-trade acquisition."""

from __future__ import annotations

import gzip
import json
from collections.abc import Mapping
from pathlib import Path

import hypervector.research.deribit_option_trade_acquisition as acquisition
import pandas as pd
import pytest
from hypervector.research.deribit_option_bundle_reproduction import (
    reproduce_deribit_option_bundle,
)


class WindowFetcher:
    """Return one deterministic response for each exact half-open window."""

    def __init__(self, responses: dict[tuple[int, int], bytes]) -> None:
        self._responses = responses
        self.requests: list[dict[str, str | int | bool]] = []

    def __call__(
        self,
        url: str,
        parameters: Mapping[str, str | int | bool],
    ) -> bytes:
        """Record one request and return its configured response."""
        assert url == acquisition.DERIBIT_OPTION_TRADES_URL
        request = dict(parameters)
        self.requests.append(request)
        key = (int(request["start_timestamp"]), int(request["end_timestamp"]) + 1)
        return self._responses[key]


class BundleFetcher:
    """Serve one instrument response and bounded trade responses."""

    def __init__(self, trades: dict[tuple[int, int], bytes]) -> None:
        self._trades = trades
        self.instrument_content = _instrument_page()
        self.requests: list[tuple[str, dict[str, str | int | bool]]] = []

    def __call__(
        self,
        url: str,
        parameters: Mapping[str, str | int | bool],
    ) -> bytes:
        """Return source bytes for the exact official endpoint."""
        request = dict(parameters)
        self.requests.append((url, request))
        if url == acquisition.DERIBIT_INSTRUMENTS_URL:
            return self.instrument_content
        assert url == acquisition.DERIBIT_OPTION_TRADES_URL
        key = (int(request["start_timestamp"]), int(request["end_timestamp"]) + 1)
        return self._trades[key]


def test_trade_window_rejects_noninteger_bounds() -> None:
    """Floating-point source bounds cannot silently alter millisecond coverage."""
    with pytest.raises(ValueError, match="integers"):
        acquisition.TradeWindow(1.5, 2)  # type: ignore[arg-type]


def test_parse_trade_page_preserves_required_event_fields() -> None:
    """A valid ordinary option trade must retain its causal source fields."""
    window = acquisition.TradeWindow(1_785_110_400_000, 1_785_110_700_000)
    content = _encoded(
        {
            "jsonrpc": "2.0",
            "result": {
                "has_more": False,
                "trades": [_valid_trade()],
            },
        }
    )

    page = acquisition.parse_trade_page(content, window)

    assert page.window == window
    assert page.has_more is False
    assert page.trades == (
        acquisition.OptionTrade(
            trade_id="438854716",
            trade_seq=4001,
            instrument_name="BTC-31JUL26-70000-C",
            timestamp_ms=1_785_110_400_890,
            direction="buy",
            amount=0.1,
            price=0.0009,
            index_price=65_341.54,
            mark_price=0.00092968,
            iv=38.16,
            tick_direction=3,
            block_trade_id=None,
            block_rfq_id=949,
            combo_id=None,
            combo_trade_id=None,
        ),
    )


def test_parse_trade_page_preserves_zero_option_metrics_but_rejects_negative() -> None:
    """Zero option metrics remain auditable but negative values must fail closed."""
    window = acquisition.TradeWindow(1_785_110_400_000, 1_785_110_700_000)
    zero_metrics = _valid_trade()
    zero_metrics["iv"] = 0.0
    zero_metrics["mark_price"] = 0.0

    page = acquisition.parse_trade_page(
        _page([zero_metrics]),
        window,
    )

    assert page.trades[0].iv == 0.0
    assert page.trades[0].mark_price == 0.0
    negative_iv = _valid_trade()
    negative_iv["iv"] = -0.01
    with pytest.raises(ValueError, match="iv must be finite and nonnegative"):
        acquisition.parse_trade_page(_page([negative_iv]), window)
    negative_mark = _valid_trade()
    negative_mark["mark_price"] = -0.0001
    with pytest.raises(ValueError, match="mark_price must be finite and nonnegative"):
        acquisition.parse_trade_page(_page([negative_mark]), window)


def test_parse_instruments_preserves_expiry_and_contract_metadata() -> None:
    """Expired instrument metadata must bind every feature-defining field."""
    content = _encoded(
        {
            "jsonrpc": "2.0",
            "result": [
                {
                    "instrument_name": "BTC-31JUL26-70000-C",
                    "creation_timestamp": 1_775_000_000_000,
                    "expiration_timestamp": 1_785_484_800_000,
                    "strike": 70_000.0,
                    "option_type": "call",
                    "contract_size": 1.0,
                }
            ],
        }
    )

    instruments = acquisition.parse_instruments(content)

    assert instruments == (
        acquisition.OptionInstrument(
            instrument_name="BTC-31JUL26-70000-C",
            creation_timestamp_ms=1_775_000_000_000,
            expiration_timestamp_ms=1_785_484_800_000,
            strike=70_000.0,
            option_type="call",
            contract_size=1.0,
        ),
    )


def test_parse_exact_instrument_requires_requested_identity() -> None:
    """Exact-name recovery cannot accept a different returned contract."""
    content = _encoded({"jsonrpc": "2.0", "result": _instrument_page_result()})

    instrument = acquisition.parse_exact_instrument(content, "BTC-31JUL26-70000-C")

    assert instrument.instrument_name == "BTC-31JUL26-70000-C"
    with pytest.raises(ValueError, match="identity mismatch"):
        acquisition.parse_exact_instrument(content, "BTC-31JUL26-71000-C")


def test_truncated_window_is_recursively_bisected_without_using_parent_rows() -> None:
    """Only complete child windows may contribute normalized source trades."""
    root = acquisition.TradeWindow(1_000, 1_300)
    left = acquisition.TradeWindow(1_000, 1_150)
    right = acquisition.TradeWindow(1_150, 1_300)
    fetcher = WindowFetcher(
        {
            (1_000, 1_300): _page([], has_more=True),
            (1_000, 1_150): _page([_valid_trade_at("1", 1_050)]),
            (1_150, 1_300): _page([_valid_trade_at("2", 1_200)]),
        }
    )

    result = acquisition.fetch_trade_history(fetcher, root, max_requests=3)

    assert [page.window for page in result.pages] == [root, left, right]
    assert result.terminal_windows == (left, right)
    assert [trade.trade_id for trade in result.trades] == ["1", "2"]
    assert result.truncated_pages == 1
    assert fetcher.requests[0] == {
        "currency": "BTC",
        "kind": "option",
        "start_timestamp": 1_000,
        "end_timestamp": 1_299,
        "count": 10_000,
        "include_old": True,
        "sorting": "asc",
    }


def test_full_history_starts_from_fixed_utc_day_windows() -> None:
    """Long acquisitions must avoid wasteful truncated multi-month root pages."""
    day = acquisition.DAY_MS
    root = acquisition.TradeWindow(0, 2 * day)
    first = acquisition.TradeWindow(0, day)
    second = acquisition.TradeWindow(day, 2 * day)
    fetcher = WindowFetcher(
        {
            (0, day): _page([_valid_trade_at("1", 1_000)]),
            (day, 2 * day): _page([_valid_trade_at("2", day + 1_000)]),
        }
    )

    result = acquisition.fetch_daily_trade_history(fetcher, root, max_requests=2)

    assert [page.window for page in result.pages] == [first, second]
    assert result.terminal_windows == (first, second)
    assert [trade.trade_id for trade in result.trades] == ["1", "2"]


def test_bundle_streams_immutable_raw_pages_and_normalized_parquet(
    tmp_path: Path,
) -> None:
    """Source publication must preserve raw bytes without computing outcomes."""
    day = acquisition.DAY_MS
    window = acquisition.TradeWindow(0, day)
    trade_content = _page([_valid_trade_at("1", 1_000)])
    fetcher = BundleFetcher({(0, day): trade_content})
    output = tmp_path / "options"

    published = acquisition.acquire_deribit_option_bundle(
        output,
        fetcher,
        window=window,
        max_requests_per_day=2,
        context=_context(),
    )

    assert published == output
    assert gzip.decompress((output / "raw/instruments.json.gz").read_bytes()) == (
        fetcher.instrument_content
    )
    assert gzip.decompress(
        (output / "raw/trades/page_000001.json.gz").read_bytes()
    ) == (trade_content)
    trades = pd.read_parquet(output / "trades.parquet")
    instruments = pd.read_parquet(output / "instruments.parquet")
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert len(trades) == 1
    assert len(instruments) == 1
    assert manifest["schema_version"] == "deribit_btc_option_flow_source_bundle_v1"
    assert manifest["coverage"]["trade_rows"] == 1
    assert manifest["coverage"]["instrument_rows"] == 1
    assert manifest["candidate_outcomes_computed"] is False
    assert manifest["execution_authority"] == "none"
    instrument_url, instrument_parameters = fetcher.requests[0]
    assert instrument_url == acquisition.DERIBIT_INSTRUMENTS_URL
    assert instrument_parameters == {
        "currency": "BTC",
        "kind": "option",
        "expired": "true",
    }
    assert set(manifest["files"]) == {
        "instruments.parquet",
        "raw/instruments.json.gz",
        "raw/trades/page_000001.json.gz",
        "trades.parquet",
    }
    reproduction = reproduce_deribit_option_bundle(output)
    assert reproduction.normalized_trade_rows == 1
    assert reproduction.normalized_instrument_rows == 1
    assert reproduction.raw_trade_pages == 1
    assert reproduction.truncated_trade_pages == 0
    assert reproduction.duplicate_trades_removed == 0
    assert reproduction.trade_rows_match is True
    assert reproduction.instrument_rows_match is True
    assert reproduction.all_registered_files_verified is True


def test_reproduction_accepts_only_complete_terminal_children_of_truncated_parent(
    tmp_path: Path,
) -> None:
    """Parent truncation is safe only when verified leaf windows cover the root."""
    day = acquisition.DAY_MS
    midpoint = day // 2
    fetcher = BundleFetcher(
        {
            (0, day): _page([], has_more=True),
            (0, midpoint): _page([_valid_trade_at("1", 1_000)]),
            (midpoint, day): _page([_valid_trade_at("2", midpoint + 1_000)]),
        }
    )
    output = tmp_path / "split-options"
    acquisition.acquire_deribit_option_bundle(
        output,
        fetcher,
        window=acquisition.TradeWindow(0, day),
        max_requests_per_day=3,
        context=_context(),
    )

    reproduction = reproduce_deribit_option_bundle(output)

    assert reproduction.raw_trade_pages == 3
    assert reproduction.truncated_trade_pages == 1
    assert reproduction.terminal_trade_pages == 2
    assert reproduction.terminal_window_coverage_complete is True
    assert reproduction.trade_rows_match is True


def _valid_trade() -> dict[str, object]:
    return {
        "trade_id": "438854716",
        "trade_seq": 4001,
        "instrument_name": "BTC-31JUL26-70000-C",
        "timestamp": 1_785_110_400_890,
        "direction": "buy",
        "amount": 0.1,
        "price": 0.0009,
        "index_price": 65_341.54,
        "mark_price": 0.00092968,
        "iv": 38.16,
        "tick_direction": 3,
        "block_rfq_id": 949,
    }


def _valid_trade_at(trade_id: str, timestamp: int) -> dict[str, object]:
    trade = _valid_trade()
    trade["trade_id"] = trade_id
    trade["timestamp"] = timestamp
    return trade


def _page(
    trades: list[dict[str, object]],
    *,
    has_more: bool = False,
) -> bytes:
    return _encoded(
        {
            "jsonrpc": "2.0",
            "result": {"has_more": has_more, "trades": trades},
        }
    )


def _instrument_page() -> bytes:
    return _encoded(
        {
            "jsonrpc": "2.0",
            "result": [_instrument_page_result()],
        }
    )


def _instrument_page_result() -> dict[str, object]:
    return {
        "instrument_name": "BTC-31JUL26-70000-C",
        "creation_timestamp": 1,
        "expiration_timestamp": 1_785_484_800_000,
        "strike": 70_000.0,
        "option_type": "call",
        "contract_size": 1.0,
    }


def _context() -> dict[str, object]:
    return {
        "hypothesis_id": "V58_BTC_DERIBIT_OTM_DIRECTIONAL_FLOW_LONG_V1",
        "execution_authority": "none",
        "candidate_outcomes_inspected_before_acquisition": False,
        "live_change_authorized": False,
        "preregistration": {"bytes": 14_000, "sha256": "abc"},
    }


def _encoded(payload: object) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")
