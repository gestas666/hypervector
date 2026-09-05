"""Tests for V58 live-versus-cached-observer candle parity."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
import importlib

import pytest

_MINUTE_MS = 60_000
_START_MS = 1_800_000
_SYMBOLS = (
    "BTC",
    "ETH",
    "SOL",
    "HYPE",
    "xyz:SP500",
    "xyz:SPCX",
    "xyz:SNDK",
    "xyz:BRENTOIL",
)


def _builder() -> Callable[..., dict[str, object]]:
    """Load the wished-for builder without breaking test collection."""
    try:
        module = importlib.import_module(
            "hypervector.research.v58_completed_candle_cache_parity"
        )
    except ModuleNotFoundError:
        pytest.fail("V58 completed-candle cache parity is not implemented")
    return module.build_v58_completed_candle_cache_parity


def _market_row(
    *,
    live: bool,
    sequence: int,
    timestamp_ms: int,
    close_delta: dict[str, float] | None = None,
    omitted_symbols: frozenset[str] = frozenset(),
) -> dict[str, object]:
    """Return one causal all-symbol completed-candle event."""
    authority = "hyperliquid_mainnet" if live else "none"
    run_kind = "live" if live else "observer"
    deltas = close_delta or {}
    bars = {
        symbol: [
            {
                "timestamp_ms": timestamp_ms,
                "open": 100.0 + index,
                "high": 101.0 + index,
                "low": 99.0 + index,
                "close": 100.5 + index + deltas.get(symbol, 0.0),
                "volume": 10.0 + index,
            }
        ]
        for index, symbol in enumerate(_SYMBOLS)
        if symbol not in omitted_symbols
    }
    observed_ms = timestamp_ms + _MINUTE_MS + 15_000
    return {
        "event_type": "market_candles",
        "sequence": sequence,
        "observed_at_utc": "1970-01-01T00:32:15+00:00"
        if timestamp_ms == _START_MS
        else "1970-01-01T00:33:15+00:00",
        "execution_mode": "live" if live else "observe",
        "live_armed": live,
        "execution_authority": authority,
        "profile_id": "multi_asset_growth_first_5000_eight_asset_incremental_v58",
        "profile_fingerprint": f"{run_kind}-profile-fingerprint",
        "run_fingerprint": f"{run_kind}-run-fingerprint",
        "run_id": f"{run_kind}-run",
        "payload": {
            "timeframe": "1m",
            "observed_at_ms": observed_ms,
            "bars": bars,
        },
    }


def _report(
    live_rows: list[dict[str, object]],
    observer_rows: list[dict[str, object]],
    *,
    minimum_minutes: int = 1_440,
) -> dict[str, object]:
    """Build one deterministic report for the fixture identities."""
    return _builder()(
        live_rows=live_rows,
        observer_rows=observer_rows,
        live_run_id="live-run",
        observer_run_id="observer-run",
        prospective_start_ms=_START_MS,
        minimum_contiguous_minutes=minimum_minutes,
        generated_at_utc="2026-08-21T06:00:00+00:00",
    )


def test_exact_duplicate_consistent_prefix_reports_collecting_parity() -> None:
    """Identical cached repeats must not create false candle mismatches."""
    live = [
        _market_row(live=True, sequence=1, timestamp_ms=_START_MS),
        _market_row(live=True, sequence=2, timestamp_ms=_START_MS + _MINUTE_MS),
    ]
    first_observer = _market_row(live=False, sequence=1, timestamp_ms=_START_MS)
    observer = [
        first_observer,
        deepcopy(first_observer),
        _market_row(live=False, sequence=2, timestamp_ms=_START_MS + _MINUTE_MS),
    ]
    observer[1]["sequence"] = 3

    report = _report(live, observer)

    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
        "promotion_authority": "none",
    }
    assert report["comparison"]["exact_ohlcv_rows"] == 16
    assert report["comparison"]["mismatches"] == []
    assert report["sources"]["observer"]["duplicate_consistent_rows"] == 8
    assert report["coverage"]["contiguous_exact_minutes"] == 2
    assert report["coverage"]["gate_status"] == "collecting"


def test_cross_source_value_mismatch_is_explicit_and_breaks_prefix() -> None:
    """One changed close must falsify exact parity at that minute."""
    live = [_market_row(live=True, sequence=1, timestamp_ms=_START_MS)]
    observer = [
        _market_row(
            live=False,
            sequence=1,
            timestamp_ms=_START_MS,
            close_delta={"HYPE": 0.25},
        )
    ]

    report = _report(live, observer, minimum_minutes=1)

    assert report["comparison"]["exact_ohlcv_rows"] == 7
    assert report["comparison"]["mismatches"] == [
        {
            "symbol": "HYPE",
            "timestamp_ms": _START_MS,
            "field": "close",
            "live": 103.5,
            "observer": 103.75,
        }
    ]
    assert report["coverage"]["contiguous_exact_minutes"] == 0
    assert report["coverage"]["gate_status"] == "mismatch"


def test_missing_symbol_bar_is_reported_without_success_shaped_fallback() -> None:
    """A source gap must stay visible rather than being treated as parity."""
    live = [_market_row(live=True, sequence=1, timestamp_ms=_START_MS)]
    observer = [
        _market_row(
            live=False,
            sequence=1,
            timestamp_ms=_START_MS,
            omitted_symbols=frozenset(("xyz:BRENTOIL",)),
        )
    ]

    report = _report(live, observer, minimum_minutes=1)

    assert report["comparison"]["observer_missing_rows"] == [
        {"symbol": "xyz:BRENTOIL", "timestamp_ms": _START_MS}
    ]
    assert report["coverage"]["gate_status"] == "incomplete"


def test_complete_predeclared_window_reaches_evidence_gate() -> None:
    """Only a fully contiguous exact window may satisfy the parity gate."""
    live = [
        _market_row(live=True, sequence=1, timestamp_ms=_START_MS),
        _market_row(live=True, sequence=2, timestamp_ms=_START_MS + _MINUTE_MS),
    ]
    observer = [
        _market_row(live=False, sequence=1, timestamp_ms=_START_MS),
        _market_row(live=False, sequence=2, timestamp_ms=_START_MS + _MINUTE_MS),
    ]

    report = _report(live, observer, minimum_minutes=2)

    assert report["coverage"]["gate_status"] == "satisfied"
    assert report["coverage"]["gate_satisfied"] is True
    assert report["coverage"]["prospective_end_exclusive_ms"] == (
        _START_MS + 2 * _MINUTE_MS
    )
    assert report["evidence_scope"] == {
        "first_published_completed_bar_ohlcv_only": True,
        "same_timestamp_late_revision_observable": False,
        "provider_decision_parity_proven": False,
        "profit_lock_cache_cutover_supported": False,
    }


def test_newer_observer_tail_is_visible_without_falsifying_shared_prefix() -> None:
    """Expected bounded import lag must not masquerade as an internal data gap."""
    live = [_market_row(live=True, sequence=1, timestamp_ms=_START_MS)]
    observer = [
        _market_row(live=False, sequence=1, timestamp_ms=_START_MS),
        _market_row(live=False, sequence=2, timestamp_ms=_START_MS + _MINUTE_MS),
    ]

    report = _report(live, observer, minimum_minutes=2)

    assert report["comparison"]["live_missing_rows"] == []
    assert report["comparison"]["trailing_observer_only_rows"] == [
        {"symbol": symbol, "timestamp_ms": _START_MS + _MINUTE_MS}
        for symbol in _SYMBOLS
    ]
    assert report["coverage"]["contiguous_exact_minutes"] == 1
    assert report["coverage"]["gate_status"] == "collecting"


def test_observer_authority_must_remain_none() -> None:
    """A parity input with execution authority must fail closed."""
    live = [_market_row(live=True, sequence=1, timestamp_ms=_START_MS)]
    observer = [_market_row(live=False, sequence=1, timestamp_ms=_START_MS)]
    observer[0]["execution_authority"] = "hyperliquid_mainnet"

    with pytest.raises(ValueError, match="observer authority"):
        _report(live, observer)


def test_incomplete_candle_timestamp_is_rejected_as_noncausal() -> None:
    """A bar observed before its close cannot enter the parity evidence."""
    live = [_market_row(live=True, sequence=1, timestamp_ms=_START_MS)]
    observer = [_market_row(live=False, sequence=1, timestamp_ms=_START_MS)]
    observer[0]["observed_at_utc"] = "1970-01-01T00:30:30+00:00"

    with pytest.raises(ValueError, match="completed before observation"):
        _report(live, observer)
