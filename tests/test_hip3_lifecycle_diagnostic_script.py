"""Reproducible command contract for the HIP-3 v25 bar diagnostic."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
import importlib.util
import json
from pathlib import Path
import sys

import duckdb
import pandas as pd

from hypervector.data.oxa_storage import file_evidence
from hypervector.live.hip3_cohort_providers import HIP3_BREAKOUT_INDEX_STRATEGY
from hypervector.live.hip3_provider_recipes import configured_hip3_recipe

_SCRIPT = Path("scripts/hip3_v25_lifecycle_bar_diagnostic.py")
_SPEC = importlib.util.spec_from_file_location("hip3_v25_bar_diagnostic", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def _database(path: Path) -> tuple[pd.DatetimeIndex, list[float]]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    times = pd.date_range(start, periods=240, freq="15min")
    close = [100.0 + (position % 12 - 6) * 0.2 for position in range(len(times))]
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            """
            CREATE TABLE archive_bundles (
                bundle_id VARCHAR, symbol VARCHAR, start_utc TIMESTAMPTZ,
                end_utc TIMESTAMPTZ, book_rows BIGINT
            );
            CREATE TABLE archive_bundle_provenance (
                bundle_id VARCHAR, market_family VARCHAR, book_only BOOLEAN
            );
            CREATE TABLE replay_book_snapshots (
                symbol VARCHAR, ts_exchange_ms BIGINT, ts_utc TIMESTAMPTZ,
                best_bid DOUBLE, best_ask DOUBLE, mid_price DOUBLE,
                micro_price DOUBLE, spread_bps DOUBLE,
                imbalance_5 DOUBLE, imbalance_10 DOUBLE
            );
            """
        )
        connection.execute(
            "INSERT INTO archive_bundles VALUES (?, ?, ?, ?, ?)",
            ["bundle", "xyz:SP500", start, start + timedelta(hours=60), 240],
        )
        connection.execute(
            "INSERT INTO archive_bundle_provenance VALUES ('bundle', 'hip3', true)"
        )
        rows = [
            (
                "xyz:SP500",
                int(time.timestamp() * 1_000),
                time,
                price - 0.01,
                price + 0.01,
                price,
                price,
                2.0,
                0.5,
                0.5 if position % 12 < 6 else -0.5,
            )
            for position, (time, price) in enumerate(zip(times, close, strict=True))
        ]
        connection.executemany(
            "INSERT INTO replay_book_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    return times, close


def _source_report(root: Path, database: Path) -> Path:
    times, _ = _database(database)
    sidecar = root / "sources.parquet"
    funding_times = pd.date_range(times[0], periods=60, freq="h")
    pd.DataFrame(
        {
            "symbol": ["xyz:SP500"] * len(funding_times),
            "record_type": ["official_funding"] * len(funding_times),
            "timestamp": funding_times,
            "funding_rate": [0.00001] * len(funding_times),
            "source": ["hl_funding_history"] * len(funding_times),
        }
    ).to_parquet(sidecar, index=False)
    qualification = root / "qualification.json"
    qualification.write_text(
        json.dumps({"markets": [{"symbol": "xyz:SP500", "max_leverage": 50}]}),
        encoding="utf-8",
    )
    development_end = times[144]
    validation_end = times[192]
    source = root / "source.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": "hip3_breakout_pressure_transfer_v1",
                "symbols": ["xyz:SP500"],
                "selected_config": asdict(
                    configured_hip3_recipe(HIP3_BREAKOUT_INDEX_STRATEGY)
                ),
                "execution_authority": "none",
                "database_path": str(database),
                "source_sidecar": {
                    "path": str(sidecar),
                    **file_evidence(sidecar),
                },
                "qualification_report": {
                    "path": str(qualification),
                    **file_evidence(qualification),
                },
                "source_evidence": [
                    {
                        "symbol": "xyz:SP500",
                        "archive": {
                            "start_utc": times[0].isoformat(),
                            "end_utc": (
                                times[-1] + pd.Timedelta(minutes=15)
                            ).isoformat(),
                            "bundles": 1,
                            "book_rows": 240,
                            "observed_15m_bars": 240,
                        },
                        "friction": {
                            "notional_usd": 75.0,
                            "effective_taker_fee_rate": 0.0000864,
                            "nominal_visible_round_trip_bps": 2.0,
                            "nominal_latency_bps_per_side": 1.0,
                            "stress_visible_round_trip_bps": 5.0,
                            "stress_latency_bps_per_side": 2.0,
                        },
                    }
                ],
                "windows": {
                    "development_start_utc": times[0].isoformat(),
                    "development_end_utc": development_end.isoformat(),
                    "validation_end_utc": validation_end.isoformat(),
                    "holdout_end_utc": (
                        times[-1] + pd.Timedelta(minutes=15)
                    ).isoformat(),
                    "development_folds": [
                        {
                            "start_utc": times[0].isoformat(),
                            "end_utc": development_end.isoformat(),
                        }
                    ],
                },
                "validation": {
                    friction: [
                        {
                            "symbol": "xyz:SP500",
                            "completed_trades": 0,
                            "net_pnl_usd": 0.0,
                            "profit_factor": None,
                        }
                    ]
                    for friction in ("nominal", "stress")
                },
                "holdout": {
                    "status": "sealed_not_evaluated",
                    "metrics_accessed": False,
                },
            }
        ),
        encoding="utf-8",
    )
    return source


def test_command_writes_report_and_trade_sidecar_without_opening_holdout(
    tmp_path: Path,
) -> None:
    database = tmp_path / "hip3.duckdb"
    source = _source_report(tmp_path, database)
    output = tmp_path / "diagnostic.json"
    trades = tmp_path / "diagnostic.trades.parquet"
    args = _MODULE.build_parser().parse_args(
        [
            "--case",
            f"{HIP3_BREAKOUT_INDEX_STRATEGY}={source}",
            "--signal-exit-policy",
            "honor",
            "--output",
            str(output),
            "--trades-output",
            str(trades),
        ]
    )

    report = _MODULE.run_command(args)

    assert output.is_file() and trades.is_file()
    assert report["schema_version"] == "hip3_v25_lifecycle_bar_diagnostic_v1"
    assert report["execution_authority"] == "none"
    assert report["runtime_strategy_changed"] is False
    case = report["cases"][HIP3_BREAKOUT_INDEX_STRATEGY]
    assert case["recipe_parity"]["exact_match"] is True
    assert case["holdout"]["metrics_accessed"] is False
    assert case["bar_diagnostic_contract"]["scope"].endswith("approximation")
    assert case["bar_diagnostic_contract"]["signal_exit_policy"] == "honor"
    assert case["bar_diagnostic_contract"]["signal_exit_columns_ignored"] is False
