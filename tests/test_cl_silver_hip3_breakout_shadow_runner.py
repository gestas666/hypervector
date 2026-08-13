"""Prospective no-authority CL and SILVER shadow observer contracts."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.live.mu_hip3_breakout_shadow import (
    CL_SHADOW_SPEC,
    SILVER_SHADOW_SPEC,
    Hip3BreakoutShadowSpec,
)
from hypervector.live.mu_hip3_breakout_shadow_runner import (
    MuHip3BreakoutShadowRunner,
    MuHip3ShadowPaths,
)
from hypervector.paper.book import BookLevel, BookSnapshot


_CASES = (
    (
        CL_SHADOW_SPEC,
        Path("scripts/cl_hip3_breakout_shadow_observe.py"),
        4,
        21,
        55,
        0.1,
        40.0,
    ),
    (
        SILVER_SHADOW_SPEC,
        Path("scripts/silver_hip3_breakout_shadow_observe.py"),
        4,
        21,
        55,
        0.35,
        120.0,
    ),
)


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


def _book(symbol: str, exchange_ms: int, recv_ms: int) -> BookSnapshot:
    return BookSnapshot(
        symbol=symbol,
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
        """Return one deterministic public book."""
        return self.book

    def completed_candle_history(self, *, observed_at_ms: int) -> pd.DataFrame:
        """Return deterministic completed-candle input."""
        assert observed_at_ms >= 0
        return self.bars.copy()


def _paths(tmp_path: Path, symbol: str) -> MuHip3ShadowPaths:
    token = symbol.removeprefix("xyz:").lower()
    return MuHip3ShadowPaths(
        asset_ledger=tmp_path / f"xyz:{token}_breakout_shadow.jsonl",
        cohort_ledger=tmp_path / f"{token}_unused_cohort.jsonl",
        cursor=tmp_path / f"{token}_cursor.json",
        journal=tmp_path / f"{token}_journal.jsonl",
        status=tmp_path / f"{token}_status.json",
    )


@pytest.mark.parametrize(
    ("spec", "_script", "lookback", "fast", "slow", "imbalance", "stop"),
    _CASES,
)
def test_archive_selected_specs_are_frozen_for_report_only_observation(
    spec: Hip3BreakoutShadowSpec,
    _script: Path,
    lookback: int,
    fast: int,
    slow: int,
    imbalance: float,
    stop: float,
) -> None:
    """Prospective observers retain exact development-selected identities."""
    assert spec.config.breakout_lookback_bars == lookback
    assert spec.config.fast_ema == fast
    assert spec.config.slow_ema == slow
    assert spec.config.minimum_abs_imbalance == imbalance
    assert spec.config.maximum_stop_bps == stop


@pytest.mark.parametrize(
    ("spec", "_script", "_lookback", "_fast", "_slow", "_imbalance", "_stop"),
    _CASES,
)
def test_bootstrap_has_no_execution_surface(
    tmp_path: Path,
    spec: Hip3BreakoutShadowSpec,
    _script: Path,
    _lookback: int,
    _fast: int,
    _slow: int,
    _imbalance: float,
    _stop: float,
) -> None:
    """CL and SILVER bootstrap only exact public research telemetry."""
    observed_ms = int(pd.Timestamp("2026-08-12T15:00:01Z").timestamp() * 1_000)
    paths = _paths(tmp_path, spec.symbol)
    runner = MuHip3BreakoutShadowRunner(
        source=_Source(
            _book(spec.symbol, observed_ms - 100, observed_ms - 50),
            _bars(),
        ),
        paths=paths,
        spec=spec,
    )

    result = runner.poll(observed_at_ms=observed_ms)

    cursor = json.loads(paths.cursor.read_text())
    status = json.loads(paths.status.read_text())
    assert result.intents == ()
    assert result.execution_authority == "none"
    assert cursor["symbol"] == spec.symbol
    assert status["provider_id"] == spec.provider_id
    assert status["signing_client_constructed"] is False
    assert status["orders_supported"] is False


@pytest.mark.parametrize(
    ("spec", "script", "_lookback", "_fast", "_slow", "_imbalance", "_stop"),
    _CASES,
)
def test_commands_use_isolated_exact_symbol_paths(
    spec: Hip3BreakoutShadowSpec,
    script: Path,
    _lookback: int,
    _fast: int,
    _slow: int,
    _imbalance: float,
    _stop: float,
) -> None:
    """Standalone commands cannot alias MU, SKHX, or live ledgers."""
    module_spec = importlib.util.spec_from_file_location(script.stem, script)
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)

    defaults = module.DEFAULTS
    token = spec.symbol.removeprefix("xyz:").lower()
    assert defaults.asset == Path(
        f"data/live/research/xyz:{token}_breakout_shadow.jsonl"
    )
    assert defaults.cursor == Path(
        f"data/runtime/research/{token}_hip3_breakout_shadow_cursor.json"
    )
    assert "bidirectional_cohort" not in str(defaults.status)
