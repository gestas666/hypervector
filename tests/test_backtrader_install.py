"""Verify full Backtrader install (package + plotting extra)."""

from __future__ import annotations

from importlib.metadata import version

import numpy as np


def test_backtrader_version_is_installed():
    import backtrader as bt

    installed = version("backtrader")
    assert installed, "backtrader metadata version must be non-empty"
    package_version = getattr(bt, "__version__", None)
    if package_version is not None:
        assert package_version == installed
    # Project pins the current PyPI release series used by official docs.
    assert installed.startswith("1.9."), f"unexpected backtrader version: {installed}"


def test_plotting_extra_pulls_matplotlib():
    import matplotlib

    assert version("matplotlib")
    assert matplotlib.__version__


def test_core_public_surface():
    import backtrader as bt

    required = (
        "Cerebro",
        "Strategy",
        "Indicator",
        "Order",
        "BrokerBase",
        "AbstractDataBase",
        "TimeFrame",
        "feeds",
        "indicators",
        "analyzers",
        "observers",
        "sizers",
        "filters",
        "commissions",
    )
    for name in required:
        assert getattr(bt, name, None) is not None, f"missing public symbol: {name}"


def test_minimal_offline_backtest_runs():
    """Drive the real Cerebro path with synthetic bars (no network)."""
    import backtrader as bt

    class SMACross(bt.Strategy):
        params = (("period", 5),)

        def __init__(self):
            self.sma = bt.indicators.SMA(self.data.close, period=self.p.period)

        def next(self):
            if not self.position and self.data.close[0] > self.sma[0]:
                self.buy(size=1)
            elif self.position and self.data.close[0] < self.sma[0]:
                self.close()

    # Synthetic OHLC so the run is fully offline and deterministic.
    closes = np.concatenate(
        [
            np.linspace(100.0, 110.0, 20),
            np.linspace(110.0, 95.0, 20),
            np.linspace(95.0, 105.0, 20),
        ]
    )
    opens = closes - 0.25
    highs = closes + 0.5
    lows = closes - 0.5
    volumes = np.full(len(closes), 1000.0)
    openinterest = np.zeros(len(closes))

    data = bt.feeds.PandasData(
        dataname=__import__("pandas").DataFrame(
            {
                "open": opens,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": volumes,
                "openinterest": openinterest,
            },
            index=__import__("pandas").date_range(
                "2020-01-01", periods=len(closes), freq="B"
            ),
        )
    )

    cerebro = bt.Cerebro()
    cerebro.addstrategy(SMACross)
    cerebro.adddata(data)
    cerebro.broker.setcash(100_000.0)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
    cerebro.addsizer(bt.sizers.FixedSize, stake=1)

    results = cerebro.run()
    assert results, "Cerebro returned no strategy results"
    strat = results[0]
    assert strat.analyzers.trades.get_analysis() is not None
    # Plotting backend must import for the [plotting] extra; do not open a GUI.
    assert hasattr(cerebro, "plot")
    assert callable(cerebro.plot)


def test_feeds_and_indicators_modules_importable():
    import backtrader.feeds as feeds
    import backtrader.indicators as indicators
    import backtrader.analyzers as analyzers

    assert hasattr(feeds, "PandasData")
    assert hasattr(indicators, "SMA")
    assert hasattr(indicators, "EMA")
    assert hasattr(analyzers, "SharpeRatio")
    assert hasattr(analyzers, "TradeAnalyzer")
