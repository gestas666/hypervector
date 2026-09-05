"""Contract tests for the immutable ETH adaptive-stop experiment command."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pandas as pd

_SCRIPT = Path(__file__).parents[1] / "scripts" / "eth_adaptive_stop_challenger.py"


def _load() -> object:
    spec = spec_from_file_location("eth_adaptive_stop_challenger_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load ETH adaptive-stop challenger script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_replay_configs_match_preregistered_live_parity_contract() -> None:
    """Control and challenger may differ only in the declared stop mechanism."""
    script = _load()

    control = script.build_control_config()
    candidate = script.build_candidate_config()

    for config in (control, candidate):
        assert config.maximum_hold_minutes == 720
        assert config.fee_bps_per_side == 4.5
        assert config.slippage_bps_per_side == 2.0
        assert config.exit_on_opposite_signal is True
    assert control.stop_bps == 60.0
    assert control.stop_anchor_column is None
    assert candidate.stop_anchor_column == "eth_adaptive_stop_anchor"
    assert candidate.minimum_stop_bps == 60.0
    assert candidate.maximum_stop_bps == 120.0


def test_partition_market_withholds_purge_and_out_of_window_signals() -> None:
    """Partition replays retain indicator history but admit only declared signals."""
    index = pd.date_range("2026-03-28T11:58:00Z", periods=6, freq="1min")
    market = pd.DataFrame({"entry_side": ["long"] * 6}, index=index)

    selected = _load().select_partition_market(
        market,
        signal_start_utc="2026-03-28T12:02:00Z",
        signal_end_exclusive_utc="2026-03-28T12:04:00Z",
        replay_end_exclusive_utc="2026-03-28T12:03:00Z",
    )

    assert tuple(selected.index) == tuple(index[:5])
    assert selected["entry_side"].iloc[:4].isna().all()
    assert selected["entry_side"].iloc[4] == "long"


def test_signal_timestamp_parity_detects_direction_changes() -> None:
    """Signal parity includes direction and timestamp, not only row counts."""
    index = pd.date_range("2026-01-01", periods=2, freq="1min", tz="UTC")
    control = pd.DataFrame({"entry_side": ["long", None]}, index=index)
    candidate = pd.DataFrame({"entry_side": ["short", None]}, index=index)

    assert _load().source_signal_parity(control, control) is True
    assert _load().source_signal_parity(control, candidate) is False
