"""Tests for Deribit option instrument-dictionary completeness auditing."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd


_SCRIPT = Path("scripts/v58_btc_deribit_instrument_completeness_audit.py")


def test_audit_identifies_exact_missing_names_without_candidate_outcomes(
    tmp_path: Path,
) -> None:
    """The anti-join must expose source metadata gaps only."""
    module = _load_module()
    trades = tmp_path / "trades.parquet"
    instruments = tmp_path / "instruments.parquet"
    pd.DataFrame(
        {
            "instrument_name": ["BTC-A", "BTC-B", "BTC-B"],
            "timestamp_ms": [1, 2, 3],
        }
    ).to_parquet(trades, index=False)
    pd.DataFrame({"instrument_name": ["BTC-A"]}).to_parquet(instruments, index=False)

    result = module.instrument_completeness(trades, instruments)

    assert result["trade_rows"] == 3
    assert result["unmatched_trade_rows"] == 2
    assert result["unmatched_instrument_count"] == 1
    assert result["unmatched_instrument_names"] == ["BTC-B"]


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("instrument_audit", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script: {_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
