"""Verify VectorBT rust-full install: engine + all [full] integrations."""

from __future__ import annotations

import importlib
from importlib.metadata import packages_distributions, version

import numpy as np
import pandas as pd
import pytest


def test_vectorbt_and_rust_versions_compatible():
    import vectorbt as vbt
    import vectorbt_rust

    vbt_mm = ".".join(vbt.__version__.split(".")[:2])
    rust_mm = ".".join(vectorbt_rust.__version__.split(".")[:2])
    assert vbt_mm == rust_mm, (
        f"version mismatch: vectorbt={vbt.__version__} rust={vectorbt_rust.__version__}"
    )
    assert version("vectorbt") == "1.1.0"
    assert version("vectorbt-rust") == "1.1.0"


def test_rust_engine_forced_ma():
    import vectorbt as vbt

    close = np.arange(100, dtype=np.float64)
    out = vbt.MA.run(close, window=10, engine="rust")
    assert out.ma.values is not None
    assert len(out.ma.values) == 100


def test_rust_vs_numba_parity():
    import vectorbt as vbt

    close = np.linspace(100.0, 200.0, 200)
    rust = vbt.MA.run(close, window=20, engine="rust").ma.values
    numba = vbt.MA.run(close, window=20, engine="numba").ma.values
    assert np.allclose(rust, numba, equal_nan=True)


def test_rust_returns_and_portfolio_parity():
    import vectorbt as vbt

    returns = pd.Series([0.01, -0.005, 0.02, -0.01, 0.015])
    assert returns.vbt.returns.total(engine="rust") == pytest.approx(
        returns.vbt.returns.total(engine="numba")
    )

    close = pd.Series([100.0, 101.0, 99.0, 103.0, 104.0])
    entries = pd.Series([True, False, False, True, False])
    exits = pd.Series([False, False, True, False, True])
    rust = vbt.Portfolio.from_signals(close, entries, exits, engine="rust")
    numba = vbt.Portfolio.from_signals(close, entries, exits, engine="numba")
    np.testing.assert_allclose(rust.value().values, numba.value().values)


def test_global_rust_engine_setting():
    import vectorbt as vbt

    previous = vbt.settings.get("engine", "auto")
    try:
        vbt.settings["engine"] = "rust"
        close = np.arange(50, dtype=np.float64)
        out = vbt.MA.run(close, window=5)
        assert out.ma.values is not None
    finally:
        vbt.settings["engine"] = previous


FULL_INTEGRATIONS = [
    "talib",
    "yfinance",
    "binance",
    "ccxt",
    "alpaca",
    "ray",
    "ta",
    "pandas_ta_classic",
    "telegram",
    "quantstats",
]

FULL_DISTRIBUTIONS = {
    "talib": "TA-Lib",
    "yfinance": "yfinance",
    "binance": "python_binance",
    "ccxt": "ccxt",
    "alpaca": "alpaca-py",
    "ray": "ray",
    "ta": "ta",
    "pandas_ta_classic": "pandas-ta-classic",
    "telegram": "python-telegram-bot",
    "quantstats": "quantstats",
}


@pytest.mark.parametrize("module_name", FULL_INTEGRATIONS)
def test_full_integration_import(module_name: str):
    importlib.import_module(module_name)


@pytest.mark.parametrize(("module_name", "distribution"), FULL_DISTRIBUTIONS.items())
def test_full_integration_distribution(module_name: str, distribution: str):
    assert distribution in packages_distributions()[module_name]
    assert version(distribution)


def test_indicator_integrations_execute_through_vectorbt():
    import vectorbt as vbt

    price = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    expected = np.array([np.nan, 1.5, 2.5, 3.5, 4.5])
    ta_values = vbt.ta("SMAIndicator").run(price, 2).sma_indicator.values
    pandas_ta_values = vbt.pandas_ta("SMA").run(price, 2).sma.values
    talib_values = vbt.talib("SMA").run(price, 2).real.values
    np.testing.assert_allclose(ta_values, expected, equal_nan=True)
    np.testing.assert_allclose(pandas_ta_values, expected, equal_nan=True)
    np.testing.assert_allclose(talib_values, expected, equal_nan=True)


def test_quantstats_adapter_executes_through_vectorbt():
    import vectorbt as vbt  # noqa: F401

    returns = pd.Series([0.01, -0.005, 0.02, -0.01, 0.015])
    assert np.isfinite(returns.vbt.returns.qs.sharpe(periods=252))


def test_data_provider_adapters_are_exposed():
    import vectorbt as vbt

    for adapter in (vbt.YFData, vbt.BinanceData, vbt.CCXTData, vbt.AlpacaData):
        assert callable(adapter.download)
        assert callable(adapter.download_symbol)


def test_telegram_adapter_builds_without_network():
    import vectorbt as vbt

    bot = vbt.TelegramBot(token="123456:offline-test-token")
    assert bot.application is not None
    assert bot.updater is not None
    assert bot.running is False


def test_ray_adapter_executes_through_vectorbt():
    import vectorbt as vbt  # noqa: F401

    def add_iteration(iteration: int, values: np.ndarray) -> np.ndarray:
        return values + iteration

    values = pd.Series([1.0, 2.0, 3.0])
    result = values.vbt.apply_and_concat(
        2,
        apply_func=add_iteration,
        use_ray=True,
        ray_init_kwargs={
            "num_cpus": 1,
            "include_dashboard": False,
            "logging_level": "ERROR",
        },
        ray_shutdown=True,
    )
    expected = pd.DataFrame(
        [[1.0, 2.0], [2.0, 3.0], [3.0, 4.0]],
        columns=pd.Index([0, 1], name="apply_idx"),
    )
    pd.testing.assert_frame_equal(result, expected)
