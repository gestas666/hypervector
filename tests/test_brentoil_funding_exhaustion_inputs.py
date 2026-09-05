"""Exact local inputs for the BRENTOIL funding-exhaustion screen."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.brentoil_funding_exhaustion_inputs import (
    load_brentoil_funding_exhaustion_inputs,
    require_brentoil_inputs_unchanged,
)


def _database(path: Path) -> None:
    connection = duckdb.connect(str(path))
    connection.execute(
        """
        CREATE TABLE canonical_trade_5m_bars (
            symbol VARCHAR, bar_open_at TIMESTAMPTZ, open DOUBLE, high DOUBLE,
            low DOUBLE, close DOUBLE, volume DOUBLE, trade_count BIGINT
        )
        """
    )
    times = pd.to_datetime(
        [
            "2026-01-01T00:00Z",
            "2026-01-01T00:05Z",
            "2026-01-01T00:15Z",
            "2026-01-01T00:20Z",
        ]
    )
    connection.executemany(
        "INSERT INTO canonical_trade_5m_bars VALUES (?, ?, 100, 101, 99, 100, 5, 2)",
        [("xyz:BRENTOIL", value.to_pydatetime()) for value in times],
    )
    connection.close()


def _funding(path: Path) -> None:
    timestamp = pd.Timestamp("2026-01-01T00:00Z")
    pd.DataFrame(
        {
            "timestamp": [timestamp],
            "funding_rate": [0.0001],
            "source": ["hl_funding_history"],
            "event_ts_ms": [int(timestamp.timestamp() * 1_000) + 1],
        }
    ).to_parquet(path, index=False)


def _preregistration(path: Path, database: Path, funding: Path) -> None:
    sources = []
    for role, source in (("database", database), ("funding", funding)):
        sources.append({"role": role, "path": str(source), **file_evidence(source)})
    payload = {
        "hypothesis_id": "V58_BRENTOIL_FUNDING_PRICE_EXHAUSTION_DEVELOPMENT_V1",
        "status": "proposed",
        "symbol": "xyz:BRENTOIL",
        "mode": "development_only_report_only",
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
        "frozen_window": {
            "start_utc": "2026-01-01T00:00:00Z",
            "end_exclusive_utc": "2026-01-01T00:25:00Z",
        },
        "frozen_mechanism": {
            "funding_lookback_events": 4,
            "minimum_funding_history_events": 4,
            "lower_funding_quantile": 0.25,
            "upper_funding_quantile": 0.75,
            "minimum_previous_extension_bps_from_ema21": 60.0,
            "clean_history_bars": 21,
            "fixed_horizons": ["15m"],
        },
        "frozen_cost_contract": {
            "nominal_round_trip_bps_before_funding": 4.0,
            "stress_round_trip_bps_before_funding": 8.0,
        },
        "success_criteria": {
            "minimum_non_overlapping_observations": 10,
        },
        "source_evidence": sources,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_loads_exact_bounds_and_preserves_internal_gap(tmp_path: Path) -> None:
    database = tmp_path / "brent.duckdb"
    funding = tmp_path / "funding.parquet"
    preregistration = tmp_path / "prereg.json"
    _database(database)
    _funding(funding)
    _preregistration(preregistration, database, funding)

    inputs = load_brentoil_funding_exhaustion_inputs(preregistration, database, funding)

    assert len(inputs.bars) == 4
    assert inputs.bars["timestamp"].diff().max() == pd.Timedelta(minutes=10)
    assert len(inputs.funding) == 1
    assert inputs.spec.horizons_minutes == (15,)
    assert inputs.source_references[0].report()["sha256"]
    require_brentoil_inputs_unchanged(inputs)


def test_rejects_database_changed_after_preregistration(tmp_path: Path) -> None:
    database = tmp_path / "brent.duckdb"
    funding = tmp_path / "funding.parquet"
    preregistration = tmp_path / "prereg.json"
    _database(database)
    _funding(funding)
    _preregistration(preregistration, database, funding)
    with database.open("ab") as stream:
        stream.write(b"drift")

    with pytest.raises(ValueError, match="input changed"):
        load_brentoil_funding_exhaustion_inputs(preregistration, database, funding)


def test_rejects_non_report_only_preregistration(tmp_path: Path) -> None:
    database = tmp_path / "brent.duckdb"
    funding = tmp_path / "funding.parquet"
    preregistration = tmp_path / "prereg.json"
    _database(database)
    _funding(funding)
    _preregistration(preregistration, database, funding)
    payload = json.loads(preregistration.read_text(encoding="utf-8"))
    payload["mode"] = "live"
    preregistration.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid mode"):
        load_brentoil_funding_exhaustion_inputs(preregistration, database, funding)


def test_rejects_database_path_not_bound_by_preregistration(tmp_path: Path) -> None:
    database = tmp_path / "brent.duckdb"
    other_database = tmp_path / "other.duckdb"
    funding = tmp_path / "funding.parquet"
    preregistration = tmp_path / "prereg.json"
    _database(database)
    _database(other_database)
    _funding(funding)
    _preregistration(preregistration, database, funding)

    with pytest.raises(ValueError, match="database path is not preregistered"):
        load_brentoil_funding_exhaustion_inputs(
            preregistration, other_database, funding
        )
