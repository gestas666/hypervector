"""Command contracts for the BTC OI-expansion count-only preflight."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

import duckdb
import pandas as pd
import pytest


_SCRIPT = Path("scripts/v58_btc_oi_expansion_preflight.py")
_ARMS = (
    "positive_price_shock",
    "positive_price_and_oi_expansion",
    "positive_price_oi_and_trade_flow",
    "full_price_oi_trade_and_book_candidate",
)


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "v58_btc_oi_expansion_preflight_script", _SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("BTC OI-expansion preflight script is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _source_database(path: Path) -> None:
    connection = duckdb.connect(str(path))
    connection.execute(
        "CREATE TABLE live_event_files ("
        "file_id VARCHAR, symbol VARCHAR, utc_date DATE, dataset VARCHAR, "
        "source_path VARCHAR, byte_count BIGINT, row_count BIGINT, "
        "sha256 VARCHAR, ingested_at TIMESTAMPTZ)"
    )
    for table in (
        "live_asset_contexts",
        "replay_live_public_trades",
        "replay_live_book_snapshots",
    ):
        connection.execute(
            f"CREATE TABLE {table} ("
            "file_id VARCHAR, symbol VARCHAR, received_ts_ns BIGINT)"
        )
    received = int(datetime(2026, 8, 1, tzinfo=UTC).timestamp() * 1_000_000_000)
    records = []
    for index, table in enumerate(
        (
            "live_asset_contexts",
            "replay_live_public_trades",
            "replay_live_book_snapshots",
        )
    ):
        file_id = f"file-{index}"
        connection.execute(
            f"INSERT INTO {table} VALUES (?, 'BTC', ?)", [file_id, received]
        )
        records.append(
            (
                file_id,
                "BTC",
                datetime(2026, 8, 1).date(),
                table,
                f"parts/{file_id}.parquet",
                100 + index,
                10 + index,
                str(index) * 64,
                datetime(2026, 8, 1, tzinfo=UTC),
            )
        )
    connection.executemany(
        "INSERT INTO live_event_files VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        records,
    )
    connection.close()


def _arm_rows(
    partition: str,
    quantile: float,
    counts: dict[str, int],
    start: datetime,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for arm, count in counts.items():
        for index in range(count):
            rows.append(
                {
                    "partition": partition,
                    "decision_at": start + timedelta(minutes=65 * index),
                    "segment_id": 1,
                    "quantile": quantile,
                    "arm": arm,
                    "qualifies": True,
                    "onset": True,
                    "shock_bps": 20.0,
                    "oi_change_pct": 0.001,
                    "price_threshold_bps": 15.0,
                    "oi_threshold_pct": 0.0007,
                    "terminal_trade_imbalance": 0.2,
                    "terminal_book_imbalance": 0.1,
                }
            )
    return pd.DataFrame.from_records(rows)


def test_existing_output_is_refused_before_any_source_query(tmp_path: Path) -> None:
    """Fail before touching the database when immutable evidence already exists."""
    module = _module()
    output = tmp_path / "existing"
    output.mkdir()
    args = module.build_parser().parse_args(
        ["--database", str(tmp_path / "missing.duckdb"), "--output", str(output)]
    )

    with pytest.raises(FileExistsError, match="output already exists"):
        module.run_command(args)


def test_source_evidence_opens_read_only_and_binds_every_file_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bind exact immutable part identities without obtaining write access."""
    module = _module()
    database = tmp_path / "market.duckdb"
    _source_database(database)
    calls: list[bool] = []
    original = module.duckdb.connect

    def tracked_connect(path: str, *, read_only: bool = False) -> object:
        calls.append(read_only)
        return original(path, read_only=read_only)

    monkeypatch.setattr(module.duckdb, "connect", tracked_connect)
    evidence = module.source_evidence(
        database,
        datetime(2026, 8, 1, tzinfo=UTC),
        datetime(2026, 8, 2, tzinfo=UTC),
    )

    assert calls == [True]
    assert {row["file_id"] for row in evidence["files"]} == {
        "file-0",
        "file-1",
        "file-2",
    }
    assert evidence["aggregate_sha256"]
    assert evidence["execution_authority"] == "none"


def test_count_report_selects_only_from_development_and_publishes_no_onsets() -> None:
    """Use the strictest qualifying development quantile without leaking timestamps."""
    module = _module()
    starts = {
        "development": datetime(2026, 8, 1, tzinfo=UTC),
        "validation": datetime(2026, 8, 2, tzinfo=UTC),
        "pseudo_holdout": datetime(2026, 8, 3, tzinfo=UTC),
    }
    full_counts = {
        0.75: {"development": 25, "validation": 12, "pseudo_holdout": 11},
        0.8: {"development": 21, "validation": 11, "pseudo_holdout": 10},
        0.9: {"development": 19, "validation": 40, "pseudo_holdout": 40},
    }
    frames: list[pd.DataFrame] = []
    for quantile, partitions in full_counts.items():
        for partition, count in partitions.items():
            counts = {arm: count for arm in _ARMS}
            frames.append(_arm_rows(partition, quantile, counts, starts[partition]))
    rows = pd.concat(frames, ignore_index=True)

    counts = module.summarize_count_only_rows(rows)
    disposition = module.select_cadence_disposition(counts)

    encoded = json.dumps({"counts": counts, "disposition": disposition})
    assert disposition["selected_quantile"] == 0.8
    assert disposition["status"] == "cadence_qualified_requires_outcome_preregistration"
    assert disposition["outcomes_computed"] is False
    assert "decision_at" not in encoded
    assert "signals" not in encoded
    assert "pnl" not in encoded.lower()


def test_count_bundle_is_manifest_bound_and_non_overwritable(tmp_path: Path) -> None:
    """Publish only the count report and its immutable evidence manifest."""
    module = _module()
    output = tmp_path / "count-result"
    report = {
        "hypothesis_id": "V58_BTC_OI_EXPANSION_FLOW_CONTINUATION_LONG_PREFLIGHT_V1",
        "authority": {
            "report_only": True,
            "execution_authority": "none",
            "outcomes_computed": False,
            "live_change": False,
        },
    }

    module.publish_count_bundle(output, report)

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["files"]) == {"report.json"}
    with pytest.raises(FileExistsError):
        module.publish_count_bundle(output, report)


def test_input_bar_counts_are_not_divided_after_timestamp_deduplication() -> None:
    """Report each distinct completed/evaluable bar once across quantile arms."""
    module = _module()
    minute = pd.date_range("2026-07-28T00:00:00Z", periods=10, freq="1min")
    minutes = pd.DataFrame({"minute": minute})
    records: list[dict[str, object]] = []
    for quantile in (0.75, 0.8, 0.9):
        for decision in (minute[5], minute[9]):
            for arm in _ARMS:
                records.append(
                    {
                        "partition": "development",
                        "decision_at": decision,
                        "quantile": quantile,
                        "arm": arm,
                        "price_threshold_bps": 15.0,
                    }
                )
    rows = pd.DataFrame.from_records(records)

    counts = module._input_counts(minutes, rows)

    assert counts[0]["complete_five_minute_bar_count"] == 2
    assert counts[0]["evaluable_five_minute_bar_count"] == 2
