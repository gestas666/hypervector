"""Reproducible report-only HIP-3 Swing/HA command contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import importlib.util
import json
from pathlib import Path
import sys

import duckdb
import pandas as pd

from hypervector.research.swing_ha_signals import SwingHaSignalConfig

_SCRIPT = Path("scripts/hip3_swing_ha_transfer.py")
_SPEC = importlib.util.spec_from_file_location("hip3_swing_ha_transfer_script", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def _database(path: Path) -> pd.DataFrame:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    times = pd.date_range(start, periods=120, freq="15min")
    pattern = [100.0, 102.0, 105.0, 103.0, 99.0, 101.0, 106.0, 104.0]
    close = [
        pattern[position % len(pattern)] + position * 0.02 for position in range(120)
    ]
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
            ["bundle", "xyz:SP500", start, start + timedelta(hours=30), 120],
        )
        connection.execute(
            "INSERT INTO archive_bundle_provenance VALUES ('bundle', 'hip3', true)"
        )
        rows = [
            (
                "xyz:SP500",
                int((time + timedelta(seconds=1)).timestamp() * 1_000),
                time + timedelta(seconds=1),
                price - 0.01,
                price + 0.01,
                price,
                price,
                2.0,
                0.1,
                0.1,
            )
            for time, price in zip(times, close, strict=True)
        ]
        connection.executemany(
            "INSERT INTO replay_book_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    return pd.DataFrame(
        {
            "timestamp": times,
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": [1.0] * len(times),
            "source": ["hl"] * len(times),
        }
    )


def _funding() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01T01:00:00Z", periods=29, freq="h"),
            "funding_rate": [0.00001] * 29,
            "source": ["hl_funding_history"] * 29,
        }
    )


def _write_inputs(root: Path) -> tuple[Path, Path, Path]:
    audit = root / "audit.json"
    liquidity = root / "liquidity.json"
    qualification = root / "qualification.json"
    audit.write_text(json.dumps({"complete": True, "symbol": "xyz:SP500"}))
    liquidity.write_text(
        json.dumps(
            {
                "profile": {
                    "symbol": "xyz:SP500",
                    "fee_status": "modeled_current_inputs",
                    "fees": {"effective_taker_rate": 0.0000864},
                    "notionals": [
                        {
                            "notional_usd": 75.0,
                            "round_trip_visible_cost_bps": {
                                "p90": 0.8,
                                "p99": 2.1,
                            },
                        }
                    ],
                }
            }
        )
    )
    qualification.write_text(
        json.dumps({"markets": [{"symbol": "xyz:SP500", "max_leverage": 50}]})
    )
    return audit, liquidity, qualification


def test_command_writes_immutable_report_trades_and_sources(tmp_path: Path) -> None:
    database = tmp_path / "hip3.duckdb"
    official = _database(database)
    audit, liquidity, qualification = _write_inputs(tmp_path)
    output = tmp_path / "report.json"
    trades = tmp_path / "trades.parquet"
    sources = tmp_path / "sources.parquet"
    args = _MODULE.build_parser().parse_args(
        [
            "--database",
            str(database),
            "--symbol",
            "xyz:SP500",
            "--audit-report",
            f"xyz:SP500={audit}",
            "--liquidity-report",
            f"xyz:SP500={liquidity}",
            "--qualification-report",
            str(qualification),
            "--output",
            str(output),
            "--trades-output",
            str(trades),
            "--sources-output",
            str(sources),
        ]
    )
    base = SwingHaSignalConfig(fast_ema=2, slow_ema=3, pivot_length=1)

    report = _MODULE.run_command(
        args,
        funding_fetcher=lambda *_args, **_kwargs: _funding(),
        candle_fetcher=lambda *_args, **_kwargs: official,
        base_configs=(base,),
        order_block_configs=(base,),
    )

    assert output.is_file() and trades.is_file() and sources.is_file()
    assert report["execution_authority"] == "none"
    assert report["place_attempted"] is False
    assert report["schema_version"] == "hip3_swing_ha_transfer_v2"
    assert report["searched_trial_count"] == 2
    assert report["holdout"]["status"] == "sealed_not_evaluated"
    assert report["source_evidence"][0]["audit_report"]["sha256"]
    assert report["source_sidecar"]["sha256"]
    assert report["validation"]["nominal"][0]["direction_trades"]
    assert report["literal_control_config"]["fast_ema"] == 9
    assert report["literal_control_config"]["slow_ema"] == 21
    assert report["validation"]["literal_9x21_control_nominal"][0]["direction_trades"]
    scenarios = set(pd.read_parquet(trades)["scenario"])
    assert scenarios == {
        "validation_nominal",
        "validation_stress",
        "literal_9x21_control_nominal",
        "literal_9x21_control_stress",
    }
