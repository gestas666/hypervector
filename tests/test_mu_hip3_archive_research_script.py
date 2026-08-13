"""Immutable full-archive MU HIP-3 research command contract."""

from __future__ import annotations

import argparse
import duckdb
import importlib.util
import json
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)
from hypervector.research.hip3_midpoint_bars import Hip3MidpointBars
from hypervector.research.mu_hip3_archive_provenance import source_tree_identity
from hypervector.research.swing_ha_signals import SwingHaSignalConfig

_SCRIPT = Path("scripts/mu_hip3_archive_research.py")
_SPEC = importlib.util.spec_from_file_location("mu_hip3_archive_script", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def _midpoint(bar_minutes: int = 15, symbol: str = "xyz:MU") -> Hip3MidpointBars:
    periods = 800 * 15 // bar_minutes
    index = pd.date_range(
        "2026-02-26T18:00:00Z", periods=periods, freq=f"{bar_minutes}min"
    )
    cycle = np.array([0.8] * 20 + [-0.9] * 30 + [0.9] * 30 + [-0.8] * 20)
    close = 100.0 + np.cumsum(np.resize(cycle, len(index)))
    open_price = np.roll(close, 1)
    open_price[0] = close[0]
    direction = np.sign(pd.Series(close).diff().fillna(0.0)).to_numpy()
    bars = pd.DataFrame(
        {
            "open": open_price,
            "high": np.maximum(open_price, close) + 0.05,
            "low": np.minimum(open_price, close) - 0.05,
            "close": close,
            "entry_bid": open_price * 0.9997,
            "entry_ask": open_price * 1.0003,
            "decision_bid": close * 0.9997,
            "decision_ask": close * 1.0003,
            "decision_micro_price": close,
            "decision_spread_bps": 6.0,
            "decision_imbalance_5": direction * 0.5,
            "decision_imbalance_10": direction * 0.6,
            "source_snapshot_count": 100,
            "first_boundary_delay_ms": 100,
            "end_boundary_age_ms": 100,
            "maximum_snapshot_interval_ms": 500,
            "gap_before_bars": 0,
            "source": "0xarchive_hyperliquid_hip3_l2_midpoint",
        },
        index=index,
    )
    return Hip3MidpointBars(
        symbol,
        index[0],
        index[-1] + pd.Timedelta(minutes=bar_minutes),
        200,
        80_000,
        len(index),
        0,
        bars,
    )


def _funding() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-02-26T18:00:00Z", "2026-03-07T02:00:00Z", freq="h"
            ),
            "funding_rate": 0.00001,
            "source": "hl_funding_history",
        }
    )


def _write_inputs(root: Path, symbol: str = "xyz:MU") -> tuple[Path, Path, Path]:
    qualification = root / "qualification.json"
    liquidity = root / "liquidity.json"
    audit = root / "audit.json"
    qualification.write_text(
        json.dumps({"markets": [{"symbol": symbol, "max_leverage": 10}]})
    )
    liquidity.write_text(
        json.dumps(
            {
                "profile": {
                    "symbol": symbol,
                    "fees": {"effective_taker_rate": 0.0000864},
                    "notionals": [
                        {
                            "notional_usd": 75.0,
                            "both_complete_rate": 1.0,
                            "round_trip_visible_cost_bps": {
                                "p90": 11.0,
                                "p99": 14.0,
                            },
                        }
                    ],
                }
            }
        )
    )
    audit.write_text(
        json.dumps(
            {
                "symbol": symbol,
                "market_family": "hip3",
                "requested_start_utc": "2026-02-26T18:00:00+00:00",
                "requested_end_utc": "2026-03-07T02:00:00+00:00",
                "chunk_seconds": 3_600,
                "book_only": False,
                "complete": True,
                "expected_bundles": 200,
                "present_bundles": 200,
                "book_snapshots": 80_000,
                "empty_book_windows": 0,
                "empty_book_ranges_utc": [],
            }
        )
    )
    return qualification, liquidity, audit


def _write_paired_inputs(root: Path, symbol: str = "xyz:MU") -> tuple[Path, Path, Path]:
    qualification, liquidity, audit = _write_inputs(root, symbol)
    payload = json.loads(audit.read_text(encoding="utf-8"))
    payload.update(
        {
            "expected_bundles": 400,
            "present_bundles": 400,
            "public_trades": 10,
            "empty_trade_windows": 0,
            "empty_trade_ranges_utc": [],
        }
    )
    audit.write_text(json.dumps(payload), encoding="utf-8")
    return qualification, liquidity, audit


def _resolved_venue_paths(
    _args: argparse.Namespace,
    midpoints: dict[str, Hip3MidpointBars],
    _audit: dict[str, object],
) -> dict[str, Hip3MidpointBars]:
    output: dict[str, Hip3MidpointBars] = {}
    for timeframe, midpoint in midpoints.items():
        bars = midpoint.bars.copy()
        bars["risk_high"] = bars["high"]
        bars["risk_low"] = bars["low"]
        bars["risk_entry_high"] = bars["high"]
        bars["risk_entry_low"] = bars["low"]
        bars["risk_path_source"] = "0xarchive_mark_price_with_public_trade_context_v1"
        bars["mark_path_complete"] = True
        bars["entry_mark_path_complete"] = True
        bars["mark_snapshot_count"] = 100
        bars["entry_mark_snapshot_count"] = 100
        bars["maximum_mark_interval_ms"] = 100.0
        bars["entry_maximum_mark_interval_ms"] = 100.0
        bars["trade_bundle_complete"] = True
        for name in ("open", "high", "low", "close"):
            bars[f"signal_{name}"] = bars[name]
        bars["signal_gap_before_bars"] = bars["gap_before_bars"]
        bars["signal_ohlc_source"] = "0xarchive_public_trade_ohlc_v1"
        bars["signal_ohlc_synthetic_no_trade"] = False
        bars["signal_volume"] = 1.0
        bars["public_trade_count"] = 1
        bars["source_public_trade_rows"] = 10
        bars["canonical_public_trade_rows"] = 10
        bars["duplicate_public_trade_rows"] = 0
        bars["conflicting_duplicate_trade_ids"] = 0
        bars["price_archive_mark_rows"] = len(bars)
        bars["price_archive_missing_mark_rows"] = 0
        bars["price_archive_empty_partitions"] = 0
        bars["price_archive_maximum_observed_gap_ms"] = 100
        output[timeframe] = replace(midpoint, bars=bars)
    return output


def test_archive_command_rejects_unpaired_book_only_audit(tmp_path: Path) -> None:
    qualification, liquidity, audit = _write_inputs(tmp_path)
    args = _MODULE.build_parser().parse_args(
        [
            "--qualification-report",
            str(qualification),
            "--liquidity-report",
            str(liquidity),
            "--archive-audit-report",
            str(audit),
            "--output",
            str(tmp_path / "unpaired.json"),
            "--trades-output",
            str(tmp_path / "unpaired.trades.parquet"),
            "--sources-output",
            str(tmp_path / "unpaired.sources.parquet"),
        ]
    )

    with pytest.raises(ValueError, match="paired trade"):
        _MODULE.run_command(args)


def test_explicit_bounds_are_bound_to_audit_and_midpoint_builders(
    tmp_path: Path,
) -> None:
    qualification, liquidity, audit = _write_paired_inputs(tmp_path)
    start = "2026-02-26T18:00:00+00:00"
    end = "2026-03-07T02:00:00+00:00"
    args = _MODULE.build_parser().parse_args(
        [
            "--start",
            start,
            "--end",
            end,
            "--qualification-report",
            str(qualification),
            "--liquidity-report",
            str(liquidity),
            "--archive-audit-report",
            str(audit),
            "--output",
            str(tmp_path / "bounded.json"),
            "--trades-output",
            str(tmp_path / "bounded.trades.parquet"),
            "--sources-output",
            str(tmp_path / "bounded.sources.parquet"),
        ]
    )
    observed: list[tuple[pd.Timestamp, pd.Timestamp]] = []

    def midpoint_builder(
        _path: Path,
        *,
        symbol: str,
        bar_minutes: int,
        start_utc: pd.Timestamp,
        end_utc: pd.Timestamp,
    ) -> Hip3MidpointBars:
        assert symbol == "xyz:MU"
        observed.append((start_utc, end_utc))
        return _midpoint(bar_minutes)

    report = _MODULE.run_command(
        args,
        midpoint_builder=midpoint_builder,
        funding_fetcher=lambda *_args, **_kwargs: _funding(),
        venue_path_loader=_resolved_venue_paths,
        swing_configs=(SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),),
        breakout_configs=(Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),),
    )

    assert observed == [(pd.Timestamp(start), pd.Timestamp(end))] * 2
    assert report["qualification_window"]["audit_bound"] is True


def test_explicit_bounds_reject_audit_window_mismatch(tmp_path: Path) -> None:
    qualification, liquidity, audit = _write_paired_inputs(tmp_path)
    args = _MODULE.build_parser().parse_args(
        [
            "--start",
            "2026-06-08T08:00:00+00:00",
            "--end",
            "2026-08-10T09:39:14+00:00",
            "--qualification-report",
            str(qualification),
            "--liquidity-report",
            str(liquidity),
            "--archive-audit-report",
            str(audit),
            "--output",
            str(tmp_path / "mismatch.json"),
            "--trades-output",
            str(tmp_path / "mismatch.trades.parquet"),
            "--sources-output",
            str(tmp_path / "mismatch.sources.parquet"),
        ]
    )

    with pytest.raises(ValueError, match="audit bounds disagree"):
        _MODULE.run_command(args)


def test_archive_command_writes_two_family_evidence(tmp_path: Path) -> None:
    qualification, liquidity, audit = _write_paired_inputs(tmp_path)
    output = tmp_path / "report.json"
    trades = tmp_path / "trades.parquet"
    sources = tmp_path / "sources.parquet"
    args = _MODULE.build_parser().parse_args(
        [
            "--database",
            str(tmp_path / "unused.duckdb"),
            "--qualification-report",
            str(qualification),
            "--liquidity-report",
            str(liquidity),
            "--archive-audit-report",
            str(audit),
            "--output",
            str(output),
            "--trades-output",
            str(trades),
            "--sources-output",
            str(sources),
        ]
    )

    report = _MODULE.run_command(
        args,
        midpoint_builder=lambda *_args, **kwargs: _midpoint(kwargs["bar_minutes"]),
        funding_fetcher=lambda *_args, **_kwargs: _funding(),
        venue_path_loader=_resolved_venue_paths,
        swing_configs=(SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),),
        breakout_configs=(Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),),
    )

    assert output.is_file() and trades.is_file() and sources.is_file()
    assert report["symbol"] == "xyz:MU"
    assert report["execution_authority"] == "none"
    session_contract = report["scheduled_oracle_session_contract"]
    assert session_contract["schedule_id"] == "us_equity_24x5_reference_v1"
    assert session_contract["execution_gate"] is False
    assert report["automatic_promotion"] is False
    assert set(report["timeframes"]) == {"15m", "5m"}
    assert report["timeframes"]["15m"]["archive_coverage"]["missing_bars"] == 0
    assert report["timeframes"]["5m"]["archive_coverage"]["book_snapshots"] == 80_000
    assert (
        report["timeframes"]["5m"]["archive_coverage"][
            "bars_with_snapshot_interval_over_15000ms"
        ]
        == 0
    )
    assert report["promotion_verdict"] == "NO_LIVE_PROMOTION_REPORT_ONLY"
    window = report["qualification_window"]
    assert window["scope"] == "exact_mark_risk_qualification"
    assert window["start_utc"] == "2026-02-26T18:00:00+00:00"
    assert window["end_utc"] == "2026-03-07T02:00:00+00:00"
    assert window["window_id"].startswith("xyz:MU|exact-mark-risk-v1|")
    assert window["mark_incomplete_ranges_utc"] == {"15m": [], "5m": []}
    assert window["mark_incomplete_bar_count"] == {"15m": 0, "5m": 0}
    assert len(report["validation_advanced_tracks"]) <= 1
    assert report["development_selected_track"]["provider_id"]
    assert report["proposed_runtime_contract"]["provider_recipe_exit_policy"] == "honor"
    assert report["proposed_runtime_contract"]["signal_ohlc_source"] == (
        "0xarchive_public_trade_ohlc_v1"
    )
    assert (
        report["proposed_runtime_contract"]["live_decision_pressure_parity_status"]
        == "blocked_live_collector_uses_first_postclose_snapshot"
    )
    assert report["proposed_runtime_contract"]["live_candle_parity_status"].startswith(
        "blocked"
    )
    for timeframe, timeframe_report in report["timeframes"].items():
        assert (
            timeframe_report["side_assessments_are_diagnostics_not_selection_inputs"]
            is True
        )
        assert set(timeframe_report["families"]) == {"swing_ha", "breakout_pressure"}
        for family in timeframe_report["families"].values():
            assert "development" in family["partitions"]
            nominal = family["partitions"]["development"]["nominal"]
            assert nominal["trades_per_week"] >= 0.0
            assert set(nominal["diagnostics"]) >= {"long", "short", "us_regular_hours"}
            scheduled = nominal["scheduled_oracle_session_diagnostics"]
            assert scheduled["status"] == "classified"
            assert "trades_per_week" in nominal["diagnostics"]["long"]
        proposed = [
            family["proposed_provider_id"]
            for family in timeframe_report["families"].values()
        ]
        assert all(("_5m_" in item) == (timeframe == "5m") for item in proposed)


def test_archive_command_preserves_exact_cl_identity_end_to_end(
    tmp_path: Path,
) -> None:
    symbol = "xyz:CL"
    qualification, liquidity, audit = _write_paired_inputs(tmp_path, symbol)
    output = tmp_path / "cl.json"
    trades = tmp_path / "cl.trades.parquet"
    sources = tmp_path / "cl.sources.parquet"
    args = _MODULE.build_parser().parse_args(
        [
            "--symbol",
            symbol,
            "--qualification-report",
            str(qualification),
            "--liquidity-report",
            str(liquidity),
            "--archive-audit-report",
            str(audit),
            "--output",
            str(output),
            "--trades-output",
            str(trades),
            "--sources-output",
            str(sources),
        ]
    )

    report = _MODULE.run_command(
        args,
        midpoint_builder=lambda *_args, **kwargs: _midpoint(
            kwargs["bar_minutes"], kwargs["symbol"]
        ),
        funding_fetcher=lambda *_args, **_kwargs: _funding(),
        venue_path_loader=_resolved_venue_paths,
        swing_configs=(SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),),
        breakout_configs=(Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),),
    )

    assert report["symbol"] == symbol
    assert report["development_selected_track"]["symbol"] == symbol
    assert report["qualification_window"]["window_id"].startswith("xyz:CL|")
    assert set(pd.read_parquet(trades)["symbol"]) == {symbol}
    assert set(pd.read_parquet(sources)["symbol"]) == {symbol}
    assert all(
        family["proposed_provider_id"].startswith("hip3_cl_")
        for timeframe in report["timeframes"].values()
        for family in timeframe["families"].values()
    )


def test_paired_archive_command_replays_verified_mark_risk_columns(
    tmp_path: Path,
) -> None:
    qualification, liquidity, audit = _write_paired_inputs(tmp_path)
    args = _MODULE.build_parser().parse_args(
        [
            "--database",
            str(tmp_path / "unused.duckdb"),
            "--qualification-report",
            str(qualification),
            "--liquidity-report",
            str(liquidity),
            "--archive-audit-report",
            str(audit),
            "--output",
            str(tmp_path / "venue.json"),
            "--trades-output",
            str(tmp_path / "venue.trades.parquet"),
            "--sources-output",
            str(tmp_path / "venue.sources.parquet"),
        ]
    )

    report = _MODULE.run_command(
        args,
        midpoint_builder=lambda *_args, **kwargs: _midpoint(kwargs["bar_minutes"]),
        funding_fetcher=lambda *_args, **_kwargs: _funding(),
        venue_path_loader=_resolved_venue_paths,
        swing_configs=(SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),),
        breakout_configs=(Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),),
    )

    for execution in report["execution_friction"].values():
        assert execution["risk_high_column"] == "risk_high"
        assert execution["risk_low_column"] == "risk_low"
        assert execution["entry_risk_high_column"] == "risk_entry_high"
        assert execution["entry_risk_low_column"] == "risk_entry_low"
    for timeframe in report["timeframes"].values():
        coverage = timeframe["archive_coverage"]
        assert coverage["signal_ohlc_source"] == "0xarchive_public_trade_ohlc_v1"
        assert coverage["mark_complete_bars"] == coverage["observed_bars"]
        assert coverage["audit_public_trades"] == 10
        assert coverage["source_public_trade_rows"] == 10
        assert coverage["canonical_public_trade_rows"] == 10
        assert coverage["duplicate_public_trade_rows"] == 0
        assert coverage["conflicting_duplicate_trade_ids"] == 0
        assert coverage["price_archive_mark_rows"] == coverage["observed_bars"]
        assert coverage["price_archive_missing_mark_rows"] == 0
        assert coverage["price_archive_empty_partitions"] == 0
        assert coverage["price_archive_maximum_observed_gap_ms"] == 100


def test_production_venue_loader_rejects_db_trade_count_audit_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _MODULE.build_parser().parse_args(
        ["--database", str(tmp_path / "unused.duckdb"), "--data-root", str(tmp_path)]
    )
    midpoints = {"15m": _midpoint(15), "5m": _midpoint(5)}
    audit = {
        "complete": True,
        "expected_bundles": 400,
        "present_bundles": 400,
        "public_trades": 10,
        "empty_trade_windows": 0,
        "empty_trade_ranges_utc": [],
    }
    monkeypatch.setattr(
        _MODULE,
        "load_verified_price_archive",
        lambda _config: SimpleNamespace(
            frame=pd.DataFrame(),
            mark_row_count=1,
            missing_mark_row_count=0,
            empty_partition_count=0,
            maximum_observed_gap_ms=100,
        ),
    )
    monkeypatch.setattr(
        _MODULE,
        "load_hip3_public_trades",
        lambda *_args, **_kwargs: pd.DataFrame(columns=["ts_exchange_ms", "price"]),
    )

    with pytest.raises(ValueError, match="trade rows disagree"):
        _MODULE._load_venue_path_midpoints(args, midpoints, audit)


def test_production_loader_rejects_missing_marks_before_trade_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _MODULE.build_parser().parse_args(
        ["--database", str(tmp_path / "unused.duckdb"), "--data-root", str(tmp_path)]
    )
    midpoints = {"15m": _midpoint(15), "5m": _midpoint(5)}
    audit = {
        "complete": True,
        "expected_bundles": 400,
        "present_bundles": 400,
        "public_trades": 10,
        "empty_trade_windows": 0,
        "empty_trade_ranges_utc": [],
    }
    monkeypatch.setattr(
        _MODULE,
        "load_verified_price_archive",
        lambda _config: SimpleNamespace(
            frame=pd.DataFrame(),
            mark_row_count=9,
            missing_mark_row_count=1,
            empty_partition_count=0,
            maximum_observed_gap_ms=100,
        ),
    )
    monkeypatch.setattr(
        _MODULE,
        "load_hip3_public_trades",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("trade replay must not start")
        ),
    )

    with pytest.raises(ValueError, match="contains 1 missing mark rows"):
        _MODULE._load_venue_path_midpoints(args, midpoints, audit)


def test_loaded_trade_reconciliation_accepts_identical_boundary_duplicates(
    tmp_path: Path,
) -> None:
    database = tmp_path / "trades.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            """
            CREATE TABLE public_trades (
                symbol VARCHAR, trade_id BIGINT, ts_exchange_ms BIGINT,
                ts_utc TIMESTAMPTZ, aggressor_side VARCHAR, price DOUBLE,
                size DOUBLE, source VARCHAR, vendor_request_id VARCHAR,
                bundle_id VARCHAR
            )
            """
        )
        connection.executemany(
            "INSERT INTO public_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "xyz:MU",
                    1,
                    1_000,
                    pd.Timestamp(1_000, unit="ms", tz="UTC"),
                    "buy",
                    100.0,
                    1.0,
                    "source",
                    "request",
                    "left",
                ),
                (
                    "xyz:MU",
                    1,
                    1_000,
                    pd.Timestamp(1_000, unit="ms", tz="UTC"),
                    "buy",
                    100.0,
                    1.0,
                    "source",
                    "request",
                    "right",
                ),
                (
                    "xyz:MU",
                    2,
                    2_000,
                    pd.Timestamp(2_000, unit="ms", tz="UTC"),
                    "sell",
                    101.0,
                    2.0,
                    "source",
                    "request",
                    "right",
                ),
            ],
        )
    trades = pd.DataFrame(
        {
            "trade_id": [1, 2],
            "ts_exchange_ms": [1_000, 2_000],
            "price": [100.0, 101.0],
        }
    )
    audit = {
        "complete": True,
        "expected_bundles": 2,
        "present_bundles": 2,
        "public_trades": 3,
        "empty_trade_windows": 0,
        "empty_trade_ranges_utc": [],
    }

    evidence = _MODULE._reconcile_loaded_trade_archive(
        trades,
        audit,
        pd.Timestamp(0, unit="ms", tz="UTC"),
        pd.Timestamp(3_000, unit="ms", tz="UTC"),
        database_path=database,
    )

    assert evidence == {
        "source_public_trade_rows": 3,
        "duplicate_public_trade_rows": 1,
        "conflicting_duplicate_trade_ids": 0,
        "canonical_public_trade_rows": 2,
    }


@pytest.mark.parametrize(
    ("p90", "p99"),
    [(-1.0, 14.0), (11.0, -1.0), (14.0, 11.0)],
)
def test_execution_rejects_invalid_visible_cost_quantiles(
    tmp_path: Path,
    p90: float,
    p99: float,
) -> None:
    qualification_path, liquidity_path, _audit = _write_inputs(tmp_path)
    qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
    liquidity = json.loads(liquidity_path.read_text(encoding="utf-8"))
    visible = liquidity["profile"]["notionals"][0]["round_trip_visible_cost_bps"]
    visible.update({"p90": p90, "p99": p99})
    args = _MODULE.build_parser().parse_args([])

    with pytest.raises(ValueError, match="visible cost quantiles"):
        _MODULE._execution(args, qualification, liquidity)


def test_holdout_cannot_change_track_or_validation_advance_membership(
    tmp_path: Path,
) -> None:
    qualification, liquidity, audit = _write_paired_inputs(tmp_path)

    def run(label: str, *, alter_holdout: bool) -> dict[str, object]:
        args = _MODULE.build_parser().parse_args(
            [
                "--database",
                str(tmp_path / "unused.duckdb"),
                "--qualification-report",
                str(qualification),
                "--liquidity-report",
                str(liquidity),
                "--archive-audit-report",
                str(audit),
                "--output",
                str(tmp_path / f"{label}.json"),
                "--trades-output",
                str(tmp_path / f"{label}.trades.parquet"),
                "--sources-output",
                str(tmp_path / f"{label}.sources.parquet"),
            ]
        )

        def venue_paths(
            loader_args: argparse.Namespace,
            midpoints: dict[str, Hip3MidpointBars],
            audit_payload: dict[str, object],
        ) -> dict[str, Hip3MidpointBars]:
            output = _resolved_venue_paths(loader_args, midpoints, audit_payload)
            if not alter_holdout:
                return output
            for timeframe, midpoint in output.items():
                bars = midpoint.bars.copy()
                holdout = bars.index[int(len(bars) * 0.80) :]
                bars.loc[holdout, "risk_low"] = 0.01
                bars.loc[holdout, "risk_high"] = 10_000.0
                output[timeframe] = replace(midpoint, bars=bars)
            return output

        return _MODULE.run_command(
            args,
            midpoint_builder=lambda *_args, **kwargs: _midpoint(kwargs["bar_minutes"]),
            funding_fetcher=lambda *_args, **_kwargs: _funding(),
            venue_path_loader=venue_paths,
            swing_configs=(SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),),
            breakout_configs=(Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),),
        )

    baseline = run("baseline", alter_holdout=False)
    changed = run("changed", alter_holdout=True)

    invariant_keys = (
        "development_selected_track",
        "validation_advanced_tracks",
        "validation_advance_verdict",
        "promotion_verdict",
    )
    assert {key: changed[key] for key in invariant_keys} == {
        key: baseline[key] for key in invariant_keys
    }
    assert baseline["validation_advance_verdict"] == "ADVANCED"
    assert baseline["validation_advanced_tracks"]
    assert baseline["final_evaluation"]["outcome"] == "PASS"
    assert changed["final_evaluation"]["outcome"] == "FAIL"
    assert changed["final_evaluation"] != baseline["final_evaluation"]


def test_development_l2_outages_abort_before_validation_without_reselection(
    tmp_path: Path,
) -> None:
    qualification, liquidity, audit = _write_paired_inputs(tmp_path)
    args = _MODULE.build_parser().parse_args(
        [
            "--qualification-report",
            str(qualification),
            "--liquidity-report",
            str(liquidity),
            "--archive-audit-report",
            str(audit),
            "--output",
            str(tmp_path / "outage.json"),
            "--trades-output",
            str(tmp_path / "outage.trades.parquet"),
            "--sources-output",
            str(tmp_path / "outage.sources.parquet"),
        ]
    )

    def outage_venue_paths(
        args: argparse.Namespace,
        midpoints: dict[str, Hip3MidpointBars],
        audit_payload: dict[str, object],
    ) -> dict[str, Hip3MidpointBars]:
        output = _resolved_venue_paths(args, midpoints, audit_payload)
        for timeframe, midpoint in output.items():
            bars = midpoint.bars.copy()
            bars["first_boundary_delay_ms"] = 299_000
            output[timeframe] = replace(midpoint, bars=bars)
        return output

    with pytest.raises(ValueError, match="development path is unresolved"):
        _MODULE.run_command(
            args,
            midpoint_builder=lambda *_args, **kwargs: _midpoint(kwargs["bar_minutes"]),
            funding_fetcher=lambda *_args, **_kwargs: _funding(),
            venue_path_loader=outage_venue_paths,
            swing_configs=(SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),),
            breakout_configs=(Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),),
        )

    assert not args.output.exists()
    assert not args.trades_output.exists()
    assert not args.sources_output.exists()


def test_full_window_missing_leading_marks_fails_before_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    qualification, liquidity, audit = _write_paired_inputs(tmp_path)
    args = _MODULE.build_parser().parse_args(
        [
            "--qualification-report",
            str(qualification),
            "--liquidity-report",
            str(liquidity),
            "--archive-audit-report",
            str(audit),
            "--output",
            str(tmp_path / "full_window.json"),
            "--trades-output",
            str(tmp_path / "full_window.trades.parquet"),
            "--sources-output",
            str(tmp_path / "full_window.sources.parquet"),
        ]
    )

    def leading_missing_marks(
        loader_args: argparse.Namespace,
        midpoints: dict[str, Hip3MidpointBars],
        audit_payload: dict[str, object],
    ) -> dict[str, Hip3MidpointBars]:
        output = _resolved_venue_paths(loader_args, midpoints, audit_payload)
        for timeframe, midpoint in output.items():
            bars = midpoint.bars.copy()
            leading = bars.index[: len(bars) // 2]
            bars.loc[leading, "mark_path_complete"] = False
            bars.loc[leading, "entry_mark_path_complete"] = False
            bars.loc[leading, "mark_snapshot_count"] = 0
            bars.loc[leading, "entry_mark_snapshot_count"] = 0
            bars.loc[leading, "maximum_mark_interval_ms"] = float("inf")
            bars.loc[leading, "entry_maximum_mark_interval_ms"] = float("inf")
            output[timeframe] = replace(midpoint, bars=bars)
        return output

    monkeypatch.setattr(
        _MODULE,
        "_evaluate_timeframes",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("evaluation must not start")
        ),
    )

    with pytest.raises(ValueError, match="starts before first observed mark-risk bar"):
        _MODULE.run_command(
            args,
            midpoint_builder=lambda *_args, **kwargs: _midpoint(kwargs["bar_minutes"]),
            funding_fetcher=lambda *_args, **_kwargs: _funding(),
            venue_path_loader=leading_missing_marks,
        )

    assert not args.output.exists()
    assert not args.trades_output.exists()
    assert not args.sources_output.exists()


def test_mark_scope_start_accepts_observed_but_interval_incomplete_bar() -> None:
    midpoints = {"15m": _midpoint(15), "5m": _midpoint(5)}
    resolved = _resolved_venue_paths(
        _MODULE.build_parser().parse_args([]),
        midpoints,
        {},
    )
    for timeframe, midpoint in resolved.items():
        bars = midpoint.bars.copy()
        bars.loc[bars.index[0], "mark_path_complete"] = False
        bars.loc[bars.index[0], "maximum_mark_interval_ms"] = 60_000.0
        resolved[timeframe] = replace(midpoint, bars=bars)

    _MODULE._require_qualification_mark_start(resolved)


def test_exact_mark_window_report_retains_internal_gap_ranges(tmp_path: Path) -> None:
    qualification, liquidity, audit = _write_paired_inputs(tmp_path)
    args = _MODULE.build_parser().parse_args(
        [
            "--qualification-report",
            str(qualification),
            "--liquidity-report",
            str(liquidity),
            "--archive-audit-report",
            str(audit),
            "--output",
            str(tmp_path / "gap.json"),
            "--trades-output",
            str(tmp_path / "gap.trades.parquet"),
            "--sources-output",
            str(tmp_path / "gap.sources.parquet"),
        ]
    )

    def internal_gap(
        loader_args: argparse.Namespace,
        midpoints: dict[str, Hip3MidpointBars],
        audit_payload: dict[str, object],
    ) -> dict[str, Hip3MidpointBars]:
        output = _resolved_venue_paths(loader_args, midpoints, audit_payload)
        for timeframe, midpoint in output.items():
            bars = midpoint.bars.copy()
            gap = bars.index[-2:-1]
            bars.loc[gap, "mark_path_complete"] = False
            bars.loc[gap, "maximum_mark_interval_ms"] = 60_000.0
            output[timeframe] = replace(midpoint, bars=bars)
        return output

    report = _MODULE.run_command(
        args,
        midpoint_builder=lambda *_args, **kwargs: _midpoint(kwargs["bar_minutes"]),
        funding_fetcher=lambda *_args, **_kwargs: _funding(),
        venue_path_loader=internal_gap,
        swing_configs=(SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),),
        breakout_configs=(Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),),
    )

    window = report["qualification_window"]
    assert window["mark_incomplete_bar_count"] == {"15m": 1, "5m": 1}
    assert len(window["mark_incomplete_ranges_utc"]["15m"]) == 1
    assert len(window["mark_incomplete_ranges_utc"]["5m"]) == 1


def test_unresolved_entry_mark_slice_aborts_before_validation(
    tmp_path: Path,
) -> None:
    qualification, liquidity, audit = _write_paired_inputs(tmp_path)
    args = _MODULE.build_parser().parse_args(
        [
            "--qualification-report",
            str(qualification),
            "--liquidity-report",
            str(liquidity),
            "--archive-audit-report",
            str(audit),
            "--output",
            str(tmp_path / "entry_gap.json"),
            "--trades-output",
            str(tmp_path / "entry_gap.trades.parquet"),
            "--sources-output",
            str(tmp_path / "entry_gap.sources.parquet"),
        ]
    )

    def unresolved_entry_paths(
        loader_args: argparse.Namespace,
        midpoints: dict[str, Hip3MidpointBars],
        audit_payload: dict[str, object],
    ) -> dict[str, Hip3MidpointBars]:
        output = _resolved_venue_paths(loader_args, midpoints, audit_payload)
        for timeframe, midpoint in output.items():
            bars = midpoint.bars.copy()
            bars.loc[bars.index[0], "mark_path_complete"] = False
            bars.loc[bars.index[0], "maximum_mark_interval_ms"] = 60_000.0
            bars["entry_mark_path_complete"] = False
            bars["entry_maximum_mark_interval_ms"] = float("inf")
            output[timeframe] = replace(midpoint, bars=bars)
        return output

    with pytest.raises(ValueError, match="development path is unresolved"):
        _MODULE.run_command(
            args,
            midpoint_builder=lambda *_args, **kwargs: _midpoint(kwargs["bar_minutes"]),
            funding_fetcher=lambda *_args, **_kwargs: _funding(),
            venue_path_loader=unresolved_entry_paths,
            swing_configs=(SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),),
            breakout_configs=(Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),),
        )

    assert not args.output.exists()
    assert not args.trades_output.exists()
    assert not args.sources_output.exists()


def test_complete_audit_rejects_empty_window_contradicted_by_midpoint_rows(
    tmp_path: Path,
) -> None:
    qualification, liquidity, audit = _write_paired_inputs(tmp_path)
    audit_payload = json.loads(audit.read_text(encoding="utf-8"))
    audit_payload["empty_book_windows"] = 1
    audit_payload["empty_book_ranges_utc"] = [
        ["2026-03-01T00:00:00+00:00", "2026-03-01T01:00:00+00:00"]
    ]
    audit.write_text(json.dumps(audit_payload), encoding="utf-8")
    args = _MODULE.build_parser().parse_args(
        [
            "--database",
            str(tmp_path / "unused.duckdb"),
            "--qualification-report",
            str(qualification),
            "--liquidity-report",
            str(liquidity),
            "--archive-audit-report",
            str(audit),
            "--output",
            str(tmp_path / "gap_report.json"),
            "--trades-output",
            str(tmp_path / "gap_trades.parquet"),
            "--sources-output",
            str(tmp_path / "gap_sources.parquet"),
        ]
    )

    with pytest.raises(ValueError, match="empty book range contains midpoint rows"):
        _MODULE.run_command(
            args,
            midpoint_builder=lambda *_args, **kwargs: _midpoint(kwargs["bar_minutes"]),
            funding_fetcher=lambda *_args, **_kwargs: _funding(),
            swing_configs=(SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),),
            breakout_configs=(Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),),
        )


def test_empty_book_range_must_be_inside_audited_archive_bounds() -> None:
    midpoint = _midpoint()
    audit = {
        "present_bundles": midpoint.archive_bundles,
        "book_snapshots": midpoint.archive_book_rows,
        "empty_book_windows": 1,
        "empty_book_ranges_utc": [
            [
                (midpoint.archive_end_utc + pd.Timedelta(hours=1)).isoformat(),
                (midpoint.archive_end_utc + pd.Timedelta(hours=2)).isoformat(),
            ]
        ],
    }

    with pytest.raises(ValueError, match="archive bounds"):
        _MODULE._reconcile_archive(midpoint, audit)


def test_failed_report_publish_leaves_no_orphans_and_can_rerun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    qualification, liquidity, audit = _write_paired_inputs(tmp_path)
    output = tmp_path / "atomic.json"
    trades = tmp_path / "atomic.trades.parquet"
    sources = tmp_path / "atomic.sources.parquet"
    args = _MODULE.build_parser().parse_args(
        [
            "--qualification-report",
            str(qualification),
            "--liquidity-report",
            str(liquidity),
            "--archive-audit-report",
            str(audit),
            "--output",
            str(output),
            "--trades-output",
            str(trades),
            "--sources-output",
            str(sources),
        ]
    )
    original = _MODULE._report
    monkeypatch.setattr(
        _MODULE,
        "_report",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("injected")),
    )

    with pytest.raises(RuntimeError, match="injected"):
        _MODULE.run_command(
            args,
            midpoint_builder=lambda *_args, **kwargs: _midpoint(kwargs["bar_minutes"]),
            funding_fetcher=lambda *_args, **_kwargs: _funding(),
            venue_path_loader=_resolved_venue_paths,
            swing_configs=(SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),),
            breakout_configs=(Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),),
        )
    assert not output.exists() and not trades.exists() and not sources.exists()
    assert not list(tmp_path.glob("*.mu-stage-*"))

    monkeypatch.setattr(_MODULE, "_report", original)
    report = _MODULE.run_command(
        args,
        midpoint_builder=lambda *_args, **kwargs: _midpoint(kwargs["bar_minutes"]),
        funding_fetcher=lambda *_args, **_kwargs: _funding(),
        venue_path_loader=_resolved_venue_paths,
        swing_configs=(SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),),
        breakout_configs=(Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),),
    )
    assert report["symbol"] == "xyz:MU"


def test_command_rejects_duplicate_output_paths(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"

    with pytest.raises(ValueError, match="distinct"):
        _MODULE._require_new(duplicate, duplicate, tmp_path / "source.parquet")


def test_generator_identity_changes_when_any_source_dependency_changes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src/hypervector/research"
    source.mkdir(parents=True)
    dependency = source / "previously_omitted.py"
    dependency.write_text("VALUE = 1\n", encoding="utf-8")
    script = tmp_path / "scripts/research.py"
    script.parent.mkdir()
    script.write_text("pass\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='probe'\n")
    (tmp_path / "uv.lock").write_text("version = 1\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    first = source_tree_identity(tmp_path, script)
    dependency.write_text("VALUE = 2\n", encoding="utf-8")
    second = source_tree_identity(tmp_path, script)

    assert first["tree_sha256"] != second["tree_sha256"]
