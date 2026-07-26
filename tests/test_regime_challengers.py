"""Point-in-time, annotation-only regime challenger tests."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from hypervector.cli import main
from hypervector.regime.challengers import (
    evaluate_regime_challengers,
    expanding_volatility_terciles,
)


def _bars(count: int = 900) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=count, freq="1min", tz="UTC")
    increments = np.sin(np.arange(count) / 17.0) * 0.4 + 0.05
    close = 100.0 + np.cumsum(increments)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.1,
            "low": close - 0.1,
            "close": close,
            "volume": 10.0 + np.cos(np.arange(count) / 11.0),
        },
        index=index,
    )


def test_expanding_volatility_terciles_are_prefix_invariant() -> None:
    bars = _bars()

    prefix = expanding_volatility_terciles(
        bars.iloc[:500],
        volatility_window=30,
        minimum_history=90,
    )
    full = expanding_volatility_terciles(
        bars,
        volatility_window=30,
        minimum_history=90,
    )

    pd.testing.assert_series_equal(prefix, full.iloc[:500])


def test_challengers_are_report_only_and_fit_chronologically() -> None:
    report = evaluate_regime_challengers(
        _bars(),
        forward_horizon=15,
        random_state=7,
        n_splits=2,
        wasserstein_window=30,
        wasserstein_sample_cap=120,
    )

    assert report["annotation_only"] is True
    assert report["may_filter"] is False
    assert report["may_size"] is False
    assert report["may_route"] is False
    arms = report["arms"]
    assert isinstance(arms, dict)
    for name in ("expanding_volatility_terciles", "gmm", "wasserstein"):
        arm = arms[name]
        assert isinstance(arm, dict)
        assert arm["status"] == "completed"
        assert arm["point_in_time"] is True
    assert arms["gmm"]["oos_assigned_rows"] > 0
    assert arms["wasserstein"]["oos_assigned_rows"] > 0
    assert arms["hmm"]["status"] in {"unavailable", "not_implemented"}
    assert arms["ms_ar"]["status"] in {"unavailable", "not_implemented"}


def test_challenger_cli_writes_complete_report(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    bars = _bars()
    monkeypatch.setattr(
        "hypervector.cli._load_bars",
        lambda _args: (bars.reset_index(names="timestamp"), {"source": "fixture"}),
    )
    output = tmp_path / "challengers.json"

    rc = main(
        [
            "--data-root",
            str(tmp_path),
            "hypervelocity-regime-challengers",
            "--forward-horizon",
            "15",
            "--n-splits",
            "2",
            "--wasserstein-window",
            "30",
            "--wasserstein-sample-cap",
            "120",
            "--out",
            str(output),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["annotation_only"] is True
    assert json.loads(output.read_text(encoding="utf-8")) == payload
