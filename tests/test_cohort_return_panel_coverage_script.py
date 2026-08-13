"""Command tests for immutable cohort return-panel coverage evidence."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import duckdb

_SCRIPT = Path(__file__).parents[1] / "scripts" / "cohort_return_panel_coverage.py"


def test_report_binds_candidate_profile_and_database(tmp_path: Path) -> None:
    spec = spec_from_file_location("cohort_return_panel_coverage_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    database = tmp_path / "market.duckdb"
    connection = duckdb.connect(str(database))
    connection.execute(
        """
        CREATE TABLE canonical_trade_5m_bars (
            symbol VARCHAR NOT NULL,
            bar_open_at TIMESTAMPTZ NOT NULL,
            open DOUBLE NOT NULL,
            high DOUBLE NOT NULL,
            low DOUBLE NOT NULL,
            close DOUBLE NOT NULL,
            volume DOUBLE NOT NULL,
            trade_count BIGINT NOT NULL
        )
        """
    )
    connection.execute(
        "INSERT INTO canonical_trade_5m_bars VALUES (?, ?, 1, 1, 1, 1, 1, 1)",
        ["BTC", datetime(2026, 8, 1, tzinfo=UTC)],
    )
    connection.close()
    config = Path(
        "configs/"
        "multi_asset_bidirectional_hype_compression_growth_5000_"
        "risk_normalized_candidate_v41.toml"
    )

    report = module.run_report(
        argparse.Namespace(database=database, config=config, out=tmp_path / "out.json")
    )

    assert report["candidate_profile"]["profile_id"].endswith("v41")
    assert report["status"] == "insufficient_synchronized_coverage"
    assert report["by_symbol"]["BTC"]["bar_count"] == 1
    assert set(report["missing_symbols"]) == {
        "ETH",
        "HYPE",
        "SOL",
        "xyz:BRENTOIL",
        "xyz:SNDK",
        "xyz:SP500",
        "xyz:SPCX",
    }
    assert report["evidence"]["database"]["size_bytes"] > 0
    assert report["generator_identity"]["tree_sha256"]
