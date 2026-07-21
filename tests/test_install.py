"""Verify VectorBT rust-full install: engine + all [full] integrations."""

from __future__ import annotations

import importlib

import numpy as np
import pytest


def test_vectorbt_and_rust_versions_compatible():
    import vectorbt as vbt
    import vectorbt_rust

    vbt_mm = ".".join(vbt.__version__.split(".")[:2])
    rust_mm = ".".join(vectorbt_rust.__version__.split(".")[:2])
    assert vbt_mm == rust_mm, f"version mismatch: vectorbt={vbt.__version__} rust={vectorbt_rust.__version__}"


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


@pytest.mark.parametrize("module_name", FULL_INTEGRATIONS)
def test_full_integration_import(module_name: str):
    importlib.import_module(module_name)
