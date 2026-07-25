"""Walk-forward tuning tests for the Hypervelocity regime detector."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from hypervector.cli import main
from hypervector.regime.tuning import (
    autotune_regime_candidates,
    generate_candidate_parameters,
)


def _bars() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=300, freq="1min", tz="UTC")
    close = np.concatenate(
        [
            np.linspace(100.0, 105.0, 150),
            np.linspace(105.0, 99.0, 150),
        ]
    )
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
            "volume": 100.0,
            "source": "fixture",
        },
        index=index,
    )


def _positions(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open_time_utc": [index[100], index[140], index[250]],
            "side": ["long", "long", "short"],
            "symbol": ["BTC", "BTC", "BTC"],
        }
    )


def test_candidate_generation_is_seeded_and_includes_baseline() -> None:
    first = generate_candidate_parameters(n_trials=4, seed=7)
    second = generate_candidate_parameters(n_trials=4, seed=7)

    assert first == second
    assert len(first) == 4
    assert first[0]["ema_fast"] == 20
    assert first[0]["ema_slow"] == 50


def test_tuner_reports_every_trial_and_keeps_holdout_out_of_selection() -> None:
    bars = _bars()
    candidates: list[dict[str, int | float]] = [
        {
            "ema_fast": 3,
            "ema_slow": 8,
            "warmup_bars": 60,
            "structure_lookback": 180,
            "minimum_trend_gap_bps": 0.5,
            "choppiness_range_threshold": 85.0,
            "coiling_width_bps": 0.5,
            "breakout_clearance_bps": 3.0,
        },
        {"ema_fast": 10, "ema_slow": 5},
    ]

    board = autotune_regime_candidates(
        bars,
        _positions(bars.index),
        candidates,
        train_fraction=2.0 / 3.0,
        forward_horizon=5,
    )

    assert board.selection_basis == "train_only"
    assert board.train_entry_decisions == 2
    assert board.holdout_entry_decisions == 1
    assert len(board.trials) == 2
    assert board.trials[0].status == "completed"
    assert board.trials[0].train_alignment is not None
    assert board.trials[0].holdout_alignment is not None
    assert board.trials[1].status == "technical_failure"
    assert "ema_fast" in str(board.trials[1].error)
    assert board.selected_trial_id == 0


def test_tuner_does_not_abort_when_performance_is_poor() -> None:
    bars = _bars()
    board = autotune_regime_candidates(
        bars,
        _positions(bars.index),
        [
            {
                "ema_fast": 20,
                "ema_slow": 50,
                "minimum_trend_gap_bps": 500.0,
            }
        ],
        train_fraction=2.0 / 3.0,
        forward_horizon=5,
    )

    assert board.trials[0].status == "completed"
    assert board.trials[0].train_alignment is not None
    assert board.trials[0].train_alignment.direction_matches == 0
    assert board.selected_trial_id == 0


def test_cli_autotune_emits_complete_report_only_board(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    bars = _bars()
    monkeypatch.setattr(
        "hypervector.cli._load_bars",
        lambda _args: (bars.reset_index(names="timestamp"), {"source": "fixture"}),
    )
    positions_path = tmp_path / "positions.csv"
    _positions(bars.index).to_csv(positions_path, index=False)

    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "hypervelocity-regime-autotune",
            "--positions",
            str(positions_path),
            "--n-trials",
            "2",
            "--seed",
            "11",
            "--forward-horizon",
            "5",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["ok"] is True
    assert payload["report_only"] is True
    assert len(payload["tuning_board"]["trials"]) == 2
    assert payload["tuning_board"]["selection_basis"] == "train_only"
