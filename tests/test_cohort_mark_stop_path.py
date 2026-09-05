"""Exact venue-mark path diagnostics for one live cohort lifecycle."""

from __future__ import annotations

import importlib

import pytest


def _subject() -> object:
    try:
        return importlib.import_module("hypervector.research.cohort_mark_stop_path")
    except ModuleNotFoundError:
        pytest.fail("cohort mark-stop path module is missing")


def _row(
    timestamp_ms: int,
    mark: float,
    *,
    symbol: str = "xyz:SPCX",
    source: str = "hyperliquid_ws_activeAssetCtx",
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "observed_ts_ms": timestamp_ms,
        "received_ts_ns": timestamp_ms * 1_000_000,
        "mark_price": mark,
        "source": source,
    }


def test_short_path_reports_exact_first_observed_stop_cross() -> None:
    module = _subject()
    spec = module.MarkStopPathSpec(
        symbol="xyz:SPCX",
        side="short",
        entry_time_ms=1_000,
        as_of_time_ms=5_000,
        stop_price=105.0,
        maximum_gap_ms=2_000,
    )

    report = module.build_mark_stop_path(
        [_row(1_000, 100.0), _row(2_000, 104.0), _row(3_000, 105.0)],
        spec,
    )

    assert report["observed_stop_crossed"] is True
    assert report["first_observed_stop_cross_time_ms"] == 3_000
    assert report["maximum_mark_price"] == 105.0
    assert report["path_status"] == "observed_stop_cross"
    assert report["continuous_at_declared_gap_bound"] is True


def test_gap_without_cross_remains_incomplete_not_safe_shaped() -> None:
    module = _subject()
    spec = module.MarkStopPathSpec(
        symbol="xyz:SPCX",
        side="short",
        entry_time_ms=1_000,
        as_of_time_ms=12_000,
        stop_price=105.0,
        maximum_gap_ms=2_000,
    )

    report = module.build_mark_stop_path(
        [_row(1_000, 100.0), _row(11_000, 101.0), _row(12_000, 102.0)],
        spec,
    )

    assert report["observed_stop_crossed"] is False
    assert report["path_status"] == "incomplete_no_observed_cross"
    assert report["maximum_receipt_gap_ms"] == 10_000.0
    assert report["continuous_at_declared_gap_bound"] is False
    assert report["unobserved_stop_cross_ruled_out"] is False


def test_path_uses_only_exact_symbol_and_websocket_mark_rows() -> None:
    module = _subject()
    spec = module.MarkStopPathSpec(
        symbol="xyz:SPCX",
        side="long",
        entry_time_ms=1_000,
        as_of_time_ms=2_000,
        stop_price=95.0,
        maximum_gap_ms=2_000,
    )

    with pytest.raises(ValueError, match="exact symbol"):
        module.build_mark_stop_path([_row(1_000, 100.0, symbol="xyz:MU")], spec)
    with pytest.raises(ValueError, match="websocket activeAssetCtx"):
        module.build_mark_stop_path(
            [_row(1_000, 100.0, source="hyperliquid_rest_metaAndAssetCtxs")],
            spec,
        )


def test_spec_rejects_noncausal_or_invalid_contract() -> None:
    module = _subject()

    with pytest.raises(ValueError, match="later than entry"):
        module.MarkStopPathSpec("xyz:SPCX", "short", 2_000, 2_000, 105.0, 2_000)
    with pytest.raises(ValueError, match="side"):
        module.MarkStopPathSpec("xyz:SPCX", "flat", 1_000, 2_000, 105.0, 2_000)
    with pytest.raises(ValueError, match="maximum gap"):
        module.MarkStopPathSpec("xyz:SPCX", "short", 1_000, 2_000, 105.0, 0)
