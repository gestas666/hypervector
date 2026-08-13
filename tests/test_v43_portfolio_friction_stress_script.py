"""Immutable CLI evidence for full-roster v43 friction stress."""

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

import duckdb
import pytest

_SCRIPT = Path("scripts/v43_portfolio_friction_stress.py")


def _module() -> ModuleType:
    spec = spec_from_file_location("v43_portfolio_friction_stress_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _database(path: Path) -> None:
    connection = duckdb.connect(str(path))
    connection.execute(
        """
        create table cohort_live_attributed_fills (
          snapshot_observed_at_utc varchar,
          trade_id ubigint,
          symbol varchar,
          strategy_id varchar,
          operation varchar,
          slippage_bps double,
          acknowledgement_latency_ms ubigint
        )
        """
    )
    rows = [
        ("2026-08-01T00:00:00Z", 1, "BTC", "x", "entry", 2.0, 10),
        ("2026-08-01T00:01:00Z", 2, "BTC", "x", "protective_stop", 4.0, 11),
        ("2026-08-01T00:02:00Z", 3, "BTC", "x", "target", 0.1, 12),
        ("2026-08-01T00:03:00Z", 4, "HYPE", "x", "entry", 3.0, 13),
        ("2026-08-01T00:04:00Z", 5, "HYPE", "x", "reduce_only_close", 5.0, 14),
        (
            "2026-08-01T00:05:00Z",
            6,
            "xyz:SP500",
            "hip3_breakout_pressure_sp500_spcx_bidirectional_v1",
            "entry",
            0.5,
            15,
        ),
        (
            "2026-08-01T00:06:00Z",
            7,
            "xyz:SPCX",
            "hip3_breakout_pressure_sp500_spcx_bidirectional_v1",
            "protective_stop",
            6.0,
            16,
        ),
        ("2026-08-01T00:07:00Z", 8, "ETH", "x", "entry", 1.0, 17),
        ("2026-08-01T00:08:00Z", 9, "ETH", "x", "protective_stop", 2.0, 18),
        ("2026-08-01T00:09:00Z", 10, "SOL", "x", "entry", 1.5, 19),
        ("2026-08-01T00:10:00Z", 11, "SOL", "x", "reduce_only_close", 2.5, 20),
    ]
    connection.executemany(
        "insert into cohort_live_attributed_fills values (?,?,?,?,?,?,?)", rows
    )
    connection.close()


def _checkpoint(path: Path, fills: int) -> None:
    path.write_text(
        json.dumps(
            {
                "audit": {
                    "portfolio_archive": {
                        "source_execution": {
                            "fill_events": fills,
                            "sha256": "a" * 64,
                        }
                    }
                }
            }
        )
    )


def test_extracts_exact_assets_and_explicit_spcx_exit_proxy(tmp_path: Path) -> None:
    """Exact entry rows and same-provider exit proxy remain distinguishable."""
    module = _module()
    database = tmp_path / "fills.duckdb"
    checkpoint = tmp_path / "checkpoint.json"
    _database(database)
    _checkpoint(checkpoint, 11)

    friction, evidence = module.collect_execution_friction(
        database,
        checkpoint,
        symbols=("BTC", "ETH", "SOL", "HYPE", "xyz:SP500"),
    )

    assert friction["BTC"]["adverse_exit"]["p99_bps"] == pytest.approx(4.0)
    assert friction["xyz:SP500"]["entry"]["sample_count"] == 1
    assert friction["xyz:SP500"]["adverse_exit"]["p99_bps"] == pytest.approx(6.0)
    assert friction["xyz:SP500"]["exit_evidence_scope"].endswith("proxy")
    assert friction["ETH"]["adverse_exit"]["p99_bps"] == pytest.approx(2.0)
    assert friction["SOL"]["entry"]["p99_bps"] == pytest.approx(1.5)
    assert evidence["canonical_fill_rows"] == 11
    assert len(evidence["canonical_rows_sha256"]) == 64


def test_rejects_checkpoint_database_fill_count_mismatch(tmp_path: Path) -> None:
    """A partially ingested execution database cannot support the report."""
    module = _module()
    database = tmp_path / "fills.duckdb"
    checkpoint = tmp_path / "checkpoint.json"
    _database(database)
    _checkpoint(checkpoint, 12)

    with pytest.raises(ValueError, match="fill count"):
        module.collect_execution_friction(database, checkpoint)


def test_parser_has_no_live_authority_surface() -> None:
    """The command cannot arm or mutate the live backend."""
    help_text = _module().build_parser().format_help()
    assert "--enabled" not in help_text
    assert "--i-accept-live-risk" not in help_text
    assert "--schema-version" in help_text
