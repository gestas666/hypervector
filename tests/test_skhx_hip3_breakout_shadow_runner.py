"""Prospective, execution-incapable SKHX shadow runner contracts."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path

import pandas as pd

from hypervector.live.mu_hip3_breakout_shadow import SKHX_SHADOW_SPEC
from hypervector.live.mu_hip3_breakout_shadow_runner import (
    MuHip3BreakoutShadowRunner,
    MuHip3ShadowPaths,
)
from hypervector.paper.book import BookLevel, BookSnapshot


_SCRIPT = Path("scripts/skhx_hip3_breakout_shadow_observe.py")


def _bars(periods: int = 60) -> pd.DataFrame:
    timestamps = pd.date_range("2026-08-12T00:00:00Z", periods=periods, freq="15min")
    closes = [100.0] * periods
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": closes,
            "high": [100.1] * periods,
            "low": [99.9] * periods,
            "close": closes,
            "volume": [10.0] * periods,
        }
    )


def _book(exchange_ms: int, recv_ms: int) -> BookSnapshot:
    return BookSnapshot(
        symbol="xyz:SKHX",
        bids=tuple(BookLevel(99.9 - index * 0.1, 3.0) for index in range(20)),
        asks=tuple(BookLevel(100.1 + index * 0.1, 1.0) for index in range(20)),
        ts_recv_ms=float(recv_ms),
        ts_exchange_ms=float(exchange_ms),
        source="hl_rest_l2",
    )


@dataclass
class _Source:
    book: BookSnapshot
    bars: pd.DataFrame

    def book_snapshot(self) -> BookSnapshot:
        return self.book

    def completed_candle_history(self, *, observed_at_ms: int) -> pd.DataFrame:
        assert observed_at_ms >= 0
        return self.bars.copy()


def _paths(tmp_path: Path) -> MuHip3ShadowPaths:
    return MuHip3ShadowPaths(
        asset_ledger=tmp_path / "xyz:skhx_breakout_shadow.jsonl",
        cohort_ledger=tmp_path / "unused_cohort.jsonl",
        cursor=tmp_path / "cursor.json",
        journal=tmp_path / "journal.jsonl",
        status=tmp_path / "status.json",
    )


def test_skhx_bootstrap_freezes_selected_config_without_execution_authority(
    tmp_path: Path,
) -> None:
    """SKHX bootstrap persists its exact selected identity and no-order contract."""
    observed_ms = int(pd.Timestamp("2026-08-12T15:00:01Z").timestamp() * 1_000)
    runner = MuHip3BreakoutShadowRunner(
        source=_Source(_book(observed_ms - 100, observed_ms - 50), _bars()),
        paths=_paths(tmp_path),
        spec=SKHX_SHADOW_SPEC,
    )

    result = runner.poll(observed_at_ms=observed_ms)

    cursor = json.loads(_paths(tmp_path).cursor.read_text())
    status = json.loads(_paths(tmp_path).status.read_text())
    assert result.intents == ()
    assert result.execution_authority == "none"
    assert cursor["symbol"] == "xyz:SKHX"
    assert cursor["provider_id"] == SKHX_SHADOW_SPEC.provider_id
    assert cursor["profile_id"] == SKHX_SHADOW_SPEC.profile_id
    assert status["symbol"] == "xyz:SKHX"
    assert status["signing_client_constructed"] is False
    assert status["orders_supported"] is False
    assert runner.config.breakout_lookback_bars == 16
    assert runner.config.fast_ema == 21
    assert runner.config.slow_ema == 55
    assert runner.config.minimum_abs_imbalance == 0.5
    assert runner.config.maximum_stop_bps == 40.0


def test_skhx_book_capture_retains_exact_symbol_and_profile(tmp_path: Path) -> None:
    """The SKHX asset ledger cannot masquerade as MU or another HIP-3 route."""
    observed_ms = int(pd.Timestamp("2026-08-12T15:00:01Z").timestamp() * 1_000)
    runner = MuHip3BreakoutShadowRunner(
        source=_Source(_book(observed_ms - 100, observed_ms - 50), _bars()),
        paths=_paths(tmp_path),
        spec=SKHX_SHADOW_SPEC,
    )

    runner.poll(observed_at_ms=observed_ms)

    row = json.loads(_paths(tmp_path).asset_ledger.read_text())
    assert row["profile_id"] == SKHX_SHADOW_SPEC.ledger_profile_id
    assert row["payload"]["symbol"] == "xyz:SKHX"
    assert row["payload"]["source"] == "hyperliquid_mainnet_l2_rest"
    assert len(row["payload"]["bids"]) == 10
    assert len(row["payload"]["asks"]) == 10


def test_skhx_command_defaults_are_isolated_from_mu_and_live_ledgers() -> None:
    """The standalone command writes only SKHX research paths by default."""
    spec = importlib.util.spec_from_file_location("skhx_shadow_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    defaults = module.SKHX_DEFAULTS

    assert defaults.asset == Path("data/live/research/xyz:skhx_breakout_shadow.jsonl")
    assert defaults.cursor == Path(
        "data/runtime/research/skhx_hip3_breakout_shadow_cursor.json"
    )
    assert "mu_hip3_breakout_shadow" not in str(defaults.status)
