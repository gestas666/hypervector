from __future__ import annotations

import importlib

import pandas as pd

from btc_trend_pullback_fixtures import pullback_reacceleration_bars


def test_replay_enters_on_next_minute_with_frozen_60_60_contract() -> None:
    """Use the next minute and the exact V58 sweep-control economics."""
    module = importlib.import_module(
        "hypervector.research.btc_trend_pullback_reacceleration_replay"
    )
    bars, signal_time = pullback_reacceleration_bars()
    bars = _append_one_minute(bars)
    bars["funding_rate"] = 0.0
    replay = module.evaluate_btc_trend_pullback_reacceleration(bars, 2.0)
    assert replay.signal_count == 1
    assert replay.signal_times_utc == (signal_time.isoformat(),)
    assert replay.report.completed_trades == 1
    trade = replay.report.trades[0]
    assert trade.signal_time_utc == signal_time.isoformat()
    assert trade.entry_time_utc == (signal_time + pd.Timedelta(minutes=1)).isoformat()
    assert trade.target_price == trade.entry_price * 1.006
    assert trade.stop_price == trade.entry_price * 0.994
    assert trade.notional_usd == 5000.0
    assert trade.leverage == 10.0


def _append_one_minute(bars: pd.DataFrame) -> pd.DataFrame:
    timestamp = bars.index[-1] + pd.Timedelta(minutes=1)
    price = float(bars["close"].iloc[-1])
    extra = pd.DataFrame(
        {
            "open": [price],
            "high": [price + 0.01],
            "low": [price - 0.01],
            "close": [price],
            "volume": [1.0],
        },
        index=pd.DatetimeIndex([timestamp]),
    )
    return pd.concat([bars, extra])
