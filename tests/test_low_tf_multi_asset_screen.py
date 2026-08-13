"""Complete-cell ledger tests for the low-timeframe research screen."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from hypervector.research.low_tf_multi_asset_replay_models import LowTfReplayConfig
from hypervector.research.low_tf_multi_asset_features import LowTfFeatureConfig
from hypervector.research.low_tf_multi_asset_signals import LowTfSignalConfig
from hypervector.research.low_tf_multi_asset_screen_journal import LowTfScreenJournal
from hypervector.research.low_tf_multi_asset_screen import (
    LowTfAssetWindowRun,
    LowTfScreenAssetInput,
    build_low_tf_screen_artifact,
    evaluate_low_tf_asset_window,
    evaluate_low_tf_cells,
)


def _minutes() -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=20, freq="1min", tz="UTC"),
            "open": [100.0] * 20,
            "high": [100.2] * 20,
            "low": [99.8] * 20,
            "close": [100.0] * 20,
            "funding_rate": [0.0] * 20,
        }
    )
    frame.loc[6, "high"] = 102.0
    return frame


def _features() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "bar_open_at": pd.date_range(
                "2026-01-01", periods=4, freq="5min", tz="UTC"
            ),
            "close": [100.0] * 4,
            "ema_fast_5m": [101.0] * 4,
            "ema_slow_5m": [100.0] * 4,
            "rsi": [55.0] * 4,
            "rsi_signal": [50.0] * 4,
            "pmarp": [50.0] * 4,
        }
    )


def _one_signal() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "decision_time_utc": "2026-01-01T00:05:00+00:00",
                "symbol": "BTC",
                "family": "range_reclaim_v1",
                "side": "long",
                "exit_variant": "range_wick_atr_stop",
                "stop_anchor_price": 99.0,
                "target_anchor_price": 101.0,
                "invalidation_mode": "intrabar_stop",
                "max_hold_bars": 4,
                "execution_authority": "none",
            }
        ]
    )


def test_screen_retains_every_declared_cell_including_zero_signal_rows() -> None:
    cells = evaluate_low_tf_cells(
        minute_bars=_minutes(),
        features=_features(),
        signals=_one_signal(),
        symbol="BTC",
        segment="development",
        config=LowTfReplayConfig(),
    )
    by_identity = {(cell.family, cell.side, cell.exit_variant): cell for cell in cells}

    assert len(cells) == 18
    traded = by_identity[("range_reclaim_v1", "long", "range_wick_atr_stop")]
    empty = by_identity[
        ("krown_ema55_touch_v1", "short", "krown_touch_hard_stop_rsi_div")
    ]
    assert traded.signal_count == 1
    assert traded.completed_trades == 1
    assert traded.net_pnl_usd > 0.0
    assert empty.signal_count == 0
    assert empty.completed_trades == 0
    assert empty.final_equity == 15_000.0
    assert all(cell.execution_authority == "none" for cell in cells)


def test_duckdb_journal_appends_complete_run_and_rejects_duplicate(
    tmp_path: Path,
) -> None:
    cells = evaluate_low_tf_cells(
        minute_bars=_minutes(),
        features=_features(),
        signals=_one_signal(),
        symbol="BTC",
        segment="development",
        config=LowTfReplayConfig(),
    )
    database = tmp_path / "strategy_trials.duckdb"
    journal = LowTfScreenJournal(database)

    journal.write_run(
        run_id="low_tf_development_test_v1",
        segment="development",
        source_identity={"BTC": {"bars_sha256": "abc"}},
        cells=cells,
    )

    with duckdb.connect(str(database), read_only=True) as connection:
        run_count = connection.execute(
            "SELECT count(*) FROM low_tf_screen_runs"
        ).fetchone()
        cell_count = connection.execute(
            "SELECT count(*) FROM low_tf_screen_cells"
        ).fetchone()
        trade_count = connection.execute(
            "SELECT count(*) FROM low_tf_screen_trades"
        ).fetchone()
    assert run_count == (1,)
    assert cell_count == (18,)
    assert trade_count == (1,)

    with pytest.raises(ValueError, match="already exists"):
        journal.write_run(
            run_id="low_tf_development_test_v1",
            segment="development",
            source_identity={"BTC": {"bars_sha256": "abc"}},
            cells=cells,
        )


def test_asset_window_requires_and_hashes_venue_bars_and_funding(
    tmp_path: Path,
) -> None:
    bars = (
        _minutes()
        .drop(columns="funding_rate")
        .assign(
            volume=10.0,
            source="hl",
        )
    )
    funding = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2026-01-01", tz="UTC")],
            "funding_rate": [0.0001],
            "source": ["hl_funding_history"],
        }
    )
    bars_path = tmp_path / "BTC_1m.parquet"
    funding_path = tmp_path / "BTC_funding.parquet"
    bars.to_parquet(bars_path, index=False)
    funding.to_parquet(funding_path, index=False)
    asset = LowTfScreenAssetInput(
        symbol="BTC",
        venue_max_leverage=40.0,
        bars_path=bars_path,
        funding_paths=(funding_path,),
    )

    run = evaluate_low_tf_asset_window(
        asset=asset,
        start=pd.Timestamp("2026-01-01", tz="UTC"),
        end=pd.Timestamp("2026-01-01 00:20", tz="UTC"),
        segment="development",
        feature_config=LowTfFeatureConfig(
            range_lookback=2,
            breakout_lookback=2,
            ema_fast=2,
            ema_slow=3,
            bbwp_length=2,
            bbwp_lookback=3,
            bbwp_signal=2,
            rsi_length=2,
            rsi_signal=2,
            pmarp_ema=2,
            pmarp_lookback=3,
            pmarp_signal=2,
            atr_length=2,
        ),
        signal_config=LowTfSignalConfig(),
        replay_config=LowTfReplayConfig(),
    )

    assert len(run.cells) == 18
    assert run.source_identity["bar_rows"] == 20
    assert run.source_identity["funding_events"] == 1
    assert run.source_identity["bars_sha256"]
    assert run.source_identity["funding_sha256"]
    assert run.source_identity["execution_authority"] == "none"


def test_json_artifact_is_complete_but_keeps_trade_rows_in_duckdb() -> None:
    cells = evaluate_low_tf_cells(
        minute_bars=_minutes(),
        features=_features(),
        signals=_one_signal(),
        symbol="BTC",
        segment="development",
        config=LowTfReplayConfig(),
    )
    artifact = build_low_tf_screen_artifact(
        run_id="low_tf_development_test_v1",
        segment="development",
        start=pd.Timestamp("2026-01-01", tz="UTC"),
        end=pd.Timestamp("2026-01-02", tz="UTC"),
        asset_runs=(
            LowTfAssetWindowRun({"symbol": "BTC", "bars_sha256": "abc"}, cells),
        ),
    )

    assert artifact["trial_count"] == 18
    assert artifact["report_only"] is True
    assert artifact["execution_authority"] == "none"
    assert artifact["source_identity"]["BTC"]["bars_sha256"] == "abc"
    assert all("trade_records" not in cell for cell in artifact["cells"])
