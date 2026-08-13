"""Tests for the report-only Cipher suite friction screen."""

from __future__ import annotations

from datetime import UTC

import pandas as pd
import pytest

from hypervector.research.cipher_suite_screen import (
    CipherExitSpec,
    CipherScreenConfig,
    screen_cipher_suite,
)


def _bars(rows: int = 10, frequency: str = "5min") -> pd.DataFrame:
    times = pd.date_range("2026-01-01", periods=rows, freq=frequency, tz=UTC)
    return pd.DataFrame(
        {
            "bar_open_at": times,
            "open": [100.0] * rows,
            "high": [100.1] * rows,
            "low": [99.9] * rows,
            "close": [100.0] * rows,
        }
    )


def _signals(bars: pd.DataFrame, positions: tuple[int, ...]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "candidate": ["cipher_a"] * len(positions),
            "signal_time_utc": [bars.loc[index, "bar_open_at"] for index in positions],
            "side": ["long"] * len(positions),
        }
    )


def _config(spec: CipherExitSpec) -> CipherScreenConfig:
    return CipherScreenConfig(candidates=("cipher_a",), exit_specs=(spec,))


def test_next_bar_entry_target_and_fees_are_applied() -> None:
    """Signals must enter at the next bar open and pay both frozen fees."""
    bars = _bars(rows=16)
    bars.loc[1, ["open", "high", "low", "close"]] = [101.0, 101.3, 100.9, 101.2]
    report = screen_cipher_suite(
        bars,
        _signals(bars, (0,)),
        _config(CipherExitSpec(target_bps=20.0, stop_bps=15.0, horizon_bars=6)),
    )

    trial = report.trials[0]
    assert report.execution_authority == "none"
    assert not report.place_attempted
    assert trial.trade_count == 1
    assert trial.trades[0].entry_price == 101.0
    assert trial.trades[0].gross_return_bps == pytest.approx(20.0)
    assert trial.trades[0].net_return_bps == pytest.approx(17.0)
    assert trial.total_fee_bps == 3.0


def test_same_bar_ambiguity_resolves_stop_first() -> None:
    """An OHLC bar touching both levels must take the adverse outcome."""
    bars = _bars()
    bars.loc[1, ["high", "low"]] = [100.3, 99.8]
    report = screen_cipher_suite(
        bars,
        _signals(bars, (0,)),
        _config(CipherExitSpec(target_bps=20.0, stop_bps=15.0, horizon_bars=6)),
    )

    trade = report.trials[0].trades[0]
    assert trade.status == "ambiguous_stop_first"
    assert trade.ambiguous
    assert trade.net_return_bps == pytest.approx(-21.0)
    assert trade.fee_bps == 6.0


def test_one_position_suppresses_signals_until_resolution() -> None:
    """A candidate cannot overlap multiple positions in one symbol."""
    bars = _bars(rows=16)
    report = screen_cipher_suite(
        bars,
        _signals(bars, (0, 1, 7)),
        _config(CipherExitSpec(target_bps=50.0, stop_bps=50.0, horizon_bars=6)),
    )

    trial = report.trials[0]
    assert trial.trade_count == 2
    assert trial.expired_occupied_signals == 1


def test_missing_immediate_entry_bar_is_censored() -> None:
    """A gap after a signal cannot be crossed by a fabricated fill."""
    bars = _bars().drop(index=1).reset_index(drop=True)
    report = screen_cipher_suite(
        bars,
        _signals(bars, (0,)),
        _config(CipherExitSpec(target_bps=20.0, stop_bps=15.0, horizon_bars=6)),
    )

    trial = report.trials[0]
    assert trial.trade_count == 0
    assert trial.censored_signals == 1


def test_fifteen_minute_config_uses_next_fifteen_minute_bar() -> None:
    """The same execution contract must honor an explicitly frozen 15m clock."""
    bars = _bars(rows=10, frequency="15min")
    config = CipherScreenConfig(
        candidates=("cipher_a",),
        exit_specs=(CipherExitSpec(20.0, 15.0, 6),),
        bar_minutes=15,
    )

    report = screen_cipher_suite(bars, _signals(bars, (0,)), config)

    assert report.trials[0].trades[0].entry_ts_ms == int(
        bars.loc[1, "bar_open_at"].timestamp() * 1_000
    )
