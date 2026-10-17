"""CLI contract for Hypervelocity-specific regime evaluation."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from hypervector.cli import main


def test_cli_hypervelocity_regime_eval_is_report_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI must expose regime evaluation without enabling execution."""
    n = 240
    index = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    close = np.linspace(100.0, 110.0, n)
    bars = pd.DataFrame(
        {
            "timestamp": index,
            "open": close,
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
            "volume": 100.0,
            "source": "binance",
        }
    )
    monkeypatch.setattr(
        "hypervector.commands.regime._load_bars",
        lambda _args: (bars, {"source": "fixture"}),
    )
    positions_path = tmp_path / "positions.csv"
    pd.DataFrame(
        {
            "open_time_utc": [index[-1] + pd.Timedelta(minutes=1)],
            "side": ["long"],
            "symbol": ["BTC"],
        }
    ).to_csv(positions_path, index=False)

    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "hypervelocity-regime-eval",
            "--symbol",
            "BTC",
            "--timeframe",
            "1m",
            "--lookback",
            "30",
            "--positions",
            str(positions_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert output["ok"] is True
    assert output["report_only"] is True
    assert output["entry_alignment"]["total_entries"] == 1
