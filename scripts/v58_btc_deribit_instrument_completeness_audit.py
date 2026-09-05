#!/usr/bin/env python3
"""Audit exact instrument metadata coverage before option-flow features."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json


_SOURCE = Path(
    "data/cache/vendor/deribit/BTC_OPTIONS/"
    "20250401T000000Z_20260801T000000Z_directional_flow_v1"
)
_OUTPUT = Path(
    "docs/research-journal/"
    "v58-btc-deribit-instrument-completeness-audit-20260822-v1.json"
)


def build_parser() -> argparse.ArgumentParser:
    """Return the source-only completeness-audit parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-bundle", type=Path, default=_SOURCE)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    parser.add_argument("--recorded-at-utc", required=True)
    return parser


def instrument_completeness(
    trades_path: Path, instruments_path: Path
) -> dict[str, object]:
    """Return exact left-anti-join counts and missing instrument identities."""
    connection = duckdb.connect(":memory:")
    try:
        counts = connection.execute(
            """WITH unmatched AS (
                SELECT t.instrument_name, t.timestamp_ms
                FROM read_parquet(?) AS t
                LEFT JOIN read_parquet(?) AS i USING (instrument_name)
                WHERE i.instrument_name IS NULL
            )
            SELECT
                (SELECT count(*) FROM read_parquet(?)),
                count(*), count(DISTINCT instrument_name),
                min(timestamp_ms), max(timestamp_ms)
            FROM unmatched""",
            [str(trades_path), str(instruments_path), str(trades_path)],
        ).fetchone()
        names = connection.execute(
            """SELECT DISTINCT t.instrument_name
            FROM read_parquet(?) AS t
            LEFT JOIN read_parquet(?) AS i USING (instrument_name)
            WHERE i.instrument_name IS NULL ORDER BY t.instrument_name""",
            [str(trades_path), str(instruments_path)],
        ).fetchall()
    finally:
        connection.close()
    if counts is None:
        raise ValueError("Deribit instrument completeness query returned no row")
    return {
        "trade_rows": _integer(counts[0], "trade rows"),
        "unmatched_trade_rows": _integer(counts[1], "unmatched trade rows"),
        "unmatched_instrument_count": _integer(counts[2], "unmatched instrument count"),
        "first_unmatched_timestamp_ms": _optional_integer(counts[3]),
        "last_unmatched_timestamp_ms": _optional_integer(counts[4]),
        "unmatched_instrument_names": [str(row[0]) for row in names],
    }


def run_command(args: argparse.Namespace) -> Path:
    """Validate source authority and publish the immutable anti-join audit."""
    manifest_path = args.source_bundle / "manifest.json"
    manifest = _load_mapping(manifest_path)
    expected = {
        "schema_version": "deribit_btc_option_flow_source_bundle_v1",
        "execution_authority": "none",
        "candidate_outcomes_computed": False,
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("Deribit instrument audit source authority drifted")
    result = instrument_completeness(
        args.source_bundle / "trades.parquet",
        args.source_bundle / "instruments.parquet",
    )
    result.update(
        {
            "schema_version": ("v58_btc_deribit_instrument_completeness_audit_v1"),
            "hypothesis_id": "V58_BTC_DERIBIT_OTM_DIRECTIONAL_FLOW_LONG_V1",
            "recorded_at_utc": _utc_text(args.recorded_at_utc),
            "status": "instrument_dictionary_gap_identified_before_candidate_signals",
            "source_bundle": str(args.source_bundle.resolve()),
            "source_manifest": file_evidence(manifest_path),
            "trades": file_evidence(args.source_bundle / "trades.parquet"),
            "instruments": file_evidence(args.source_bundle / "instruments.parquet"),
            "supplement_contract": {
                "endpoint": (
                    "https://history.deribit.com/api/v2/public/get_instrument"
                ),
                "selection": "exact left-anti-join instrument names in this artifact",
                "required_exact_name_match": True,
                "inference_permitted": False,
            },
            "outcome_blindness": {
                "candidate_signals_computed": False,
                "candidate_signal_counts_inspected": False,
                "candidate_forward_returns_inspected": False,
                "candidate_trade_outcomes_inspected": False,
            },
            "authority": {
                "execution_authority": "none",
                "live_change_authorized": False,
            },
        }
    )
    write_immutable_json(args.output, result)
    return args.output


def _load_mapping(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Deribit instrument source manifest must be an object")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Deribit instrument {label} is invalid")
    return value


def _optional_integer(value: object) -> int | None:
    return None if value is None else _integer(value, "timestamp")


def _utc_text(value: str) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("recorded_at_utc must be timezone-aware")
    return timestamp.tz_convert("UTC").isoformat().replace("+00:00", "Z")


def main() -> int:
    """Publish the audit and print its path."""
    print(run_command(build_parser().parse_args()).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
