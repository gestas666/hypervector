"""Native startup must tolerate filled-order visibility lag without issuing a false cancel."""

from dataclasses import replace
from pathlib import Path

import pytest
from test_native_replay_adapter import deny_external_ports
import test_native_replay_stop_engines as stop_cases

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.research.native_replay_sdk import ReplaySdk

__all__ = ["deny_external_ports"]


@pytest.mark.parametrize("fill_delay_ms", [0, 100, 300])
@pytest.mark.parametrize("restart", [False, True])
def test_bracket_recovery_with_fill_history_preceding_terminal_order_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fill_delay_ms: int, restart: bool
) -> None:
    """The owned stop's real fill must close one lifecycle despite a stale open-order row."""
    original = stop_cases.cohort_sdk

    def timed_sdk(config: MultiAssetLiveConfig, decisions: dict[str, int]) -> ReplaySdk:
        replay = original(config, decisions)
        replay.timing = replace(
            replay.timing, fill_visible_delay_ms=fill_delay_ms, order_visible_delay_ms=400
        )
        return replay

    monkeypatch.setattr(stop_cases, "cohort_sdk", timed_sdk)
    stop_cases.test_native_stop_reconciles_engine_cleanup_journal_and_exact_cash(
        tmp_path, "BTC", False, restart
    )
