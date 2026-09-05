"""CLI tests for immutable HYPE compression-breakout evidence."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pandas as pd

_SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "hype_compression_breakout_challenger.py"
)


def _load() -> object:
    spec = spec_from_file_location("hype_compression_breakout_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load HYPE compression-breakout script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_parity_replay_config_is_frozen() -> None:
    """The command includes v51 router exits plus the frozen 8h-to-24h timer."""
    config = _load().build_replay_config()

    assert config.stop_bps == 80.0
    assert config.maximum_hold_minutes == 480
    assert config.maximum_hold_policy == "extend_while_regime_supported"
    assert config.hard_maximum_hold_minutes == 1_440
    assert config.exit_on_opposite_signal is True


def test_continuous_candle_segments_preserve_explicit_gaps() -> None:
    """Missing venue candles become boundaries instead of synthetic bars."""
    timestamps = pd.to_datetime(
        [
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:01:00Z",
            "2026-01-01T00:05:00Z",
            "2026-01-01T00:06:00Z",
        ],
        utc=True,
    )
    bars = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [1.0] * 4,
            "high": [1.0] * 4,
            "low": [1.0] * 4,
            "close": [1.0] * 4,
            "volume": [1.0] * 4,
        }
    )

    segments, gaps = _load().continuous_candle_segments(bars)

    assert [len(segment) for segment in segments] == [2, 2]
    assert gaps == [
        {
            "missing_start_utc": "2026-01-01T00:02:00+00:00",
            "missing_end_utc": "2026-01-01T00:04:00+00:00",
            "missing_minutes": 3,
        }
    ]


def test_report_includes_the_frozen_entry_exit_study() -> None:
    """The immutable report preserves the narrower exit-challenger evidence."""
    module = _load()
    exit_study = {"mode": "hype_compression_exit_challenger_report_only"}

    report = module._report({}, {}, {}, {}, [], [], exit_study, {}, {}, {}, {})

    assert report["compression_exit_challenger"] == exit_study


def test_report_includes_the_fixed_regime_loss_exit_study() -> None:
    """The immutable bundle retains the single transferred exit falsifier."""
    module = _load()
    exit_study = {"mode": "hype_compression_exit_challenger_report_only"}
    regime_loss = {"mode": "hype_compression_regime_loss_exit_report_only"}

    report = module._report(
        {},
        {},
        {},
        {},
        [],
        [],
        exit_study,
        regime_loss,
        {},
        {},
        {},
    )

    assert report["compression_regime_loss_exit_challenger"] == regime_loss


def test_report_includes_the_causal_alignment_replay() -> None:
    """The immutable bundle preserves the occupancy-aware alignment test."""
    module = _load()
    alignment = {"mode": "hype_compression_alignment_causal_replay_v1"}

    report = module._report(
        {},
        {},
        {},
        {},
        [],
        [],
        {},
        {},
        alignment,
        {},
        {},
    )

    assert report["compression_alignment_replay"] == alignment
