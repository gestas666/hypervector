"""Bounded checkpoint projections for high-frequency live ledgers."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from hypervector.research.checkpoint_ledger_projection import (
    compact_asset_ledger_rows,
    compact_cohort_ledger_rows,
)

_RUN_ID = "run-current"


def test_cohort_projection_retains_events_and_compacts_repeated_snapshots(
    tmp_path: Path,
) -> None:
    """Portfolio extrema, material changes, and the latest state remain exact."""
    rows = [_row(1, "configuration_identity", {"symbol": "MULTI"})]
    sequence = 2
    for cycle in range(50):
        recent_fills = [] if cycle < 25 else [{"symbol": "BTC", "trade_id": 7}]
        rows.append(
            _row(
                sequence,
                "cohort_snapshot",
                {
                    "account_value_usd": 5_000.0 + min(cycle, 10),
                    "open_position_count": int(cycle >= 25),
                    "total_margin_used_usd": float(cycle >= 25) * 50.0,
                    "total_notional_position_usd": float(cycle >= 25) * 250.0,
                    "recent_fills": recent_fills,
                    "assets": [
                        {
                            "symbol": "BTC",
                            "position_size_signed": float(cycle >= 25),
                            "protective_stop_oid": 11 if cycle >= 25 else None,
                            "target_oid": None,
                        }
                    ],
                },
            )
        )
        sequence += 1
        rows.append(_row(sequence, "heartbeat", {"status": "running"}))
        sequence += 1
    path = _write_rows(tmp_path / "cohort.jsonl", rows)

    projected = compact_cohort_ledger_rows(path)

    snapshots = [
        row for row in projected.rows if row["event_type"] == "cohort_snapshot"
    ]
    assert len(snapshots) < 20
    assert (
        len([row for row in projected.rows if row["event_type"] == "heartbeat"]) == 50
    )
    assert snapshots[-1]["sequence"] == rows[-2]["sequence"]
    assert snapshots[-1]["payload"]["open_position_count"] == 1
    assert projected.source_sequence_start == 1
    assert projected.source_sequence_end == rows[-1]["sequence"]


def test_asset_projection_retains_execution_and_only_required_cycle_samples(
    tmp_path: Path,
) -> None:
    """Execution lifecycles remain attributable without every flat poll sample."""
    rows = [_row(1, "configuration_identity", {"symbol": "BTC"})]
    sequence = 2
    for cycle in range(20):
        rows.extend(
            (
                _row(
                    sequence,
                    "reconciliation",
                    {"account_value_usd": 5_000.0, "open_order_ids": []},
                ),
                _row(sequence + 1, "position", {"size_signed": 0.0}),
                _row(sequence + 2, "liquidation_price", {"value": None}),
                _row(
                    sequence + 3,
                    "book_observation",
                    {"exchange_ts_ms": cycle * 1_000, "mid_px": 100.0 + cycle},
                ),
            )
        )
        sequence += 4
    rows.extend(
        (
            _row(sequence, "order_intent", {"operation": "entry", "oid": 71}),
            _row(
                sequence + 1,
                "order_acknowledgement",
                {"operation": "entry", "accepted": True, "oid": 71},
            ),
            _row(
                sequence + 2,
                "fill",
                {"oid": 71, "venue_timestamp_ms": 20_000, "size": 1.0},
            ),
            _row(
                sequence + 3,
                "book_observation",
                {"exchange_ts_ms": 24_000, "mid_px": 120.0},
            ),
            _row(
                sequence + 4,
                "book_observation",
                {"exchange_ts_ms": 25_000, "mid_px": 121.0},
            ),
            _row(
                sequence + 5,
                "book_observation",
                {"exchange_ts_ms": 26_000, "mid_px": 122.0},
            ),
        )
    )
    path = _write_rows(tmp_path / "asset.jsonl", rows)

    projected = compact_asset_ledger_rows(path, current_run_id=_RUN_ID)

    event_types = [row["event_type"] for row in projected.rows]
    books = [row for row in projected.rows if row["event_type"] == "book_observation"]
    assert "order_intent" in event_types
    assert "order_acknowledgement" in event_types
    assert "fill" in event_types
    assert [row["payload"]["exchange_ts_ms"] for row in books] == [25_000, 26_000]
    assert event_types.count("reconciliation") < 5
    assert event_types.count("position") < 5
    assert projected.source_sequence_end == rows[-1]["sequence"]


def test_asset_projection_retains_latest_cycle_state_before_cohort_cutoff(
    tmp_path: Path,
) -> None:
    """A later asset poll cannot erase the state aligned to a cohort snapshot."""
    rows = [
        _row(1, "configuration_identity", {"symbol": "BTC"}),
        _row(2, "reconciliation", {"open_order_ids": [11]}),
        _row(3, "position", {"size_signed": 1.0}),
        _row(4, "reconciliation", {"open_order_ids": []}),
        _row(5, "position", {"size_signed": 0.0}),
    ]
    rows[1]["observed_at_utc"] = "2026-08-20T12:00:10+00:00"
    rows[2]["observed_at_utc"] = "2026-08-20T12:00:11+00:00"
    rows[3]["observed_at_utc"] = "2026-08-20T12:00:20+00:00"
    rows[4]["observed_at_utc"] = "2026-08-20T12:00:21+00:00"
    path = _write_rows(tmp_path / "asset.jsonl", rows)

    projected = compact_asset_ledger_rows(
        path,
        current_run_id=_RUN_ID,
        as_of=datetime(2026, 8, 20, 12, 0, 15, tzinfo=timezone.utc),
    )

    reconciliations = [
        row for row in projected.rows if row["event_type"] == "reconciliation"
    ]
    positions = [row for row in projected.rows if row["event_type"] == "position"]
    assert reconciliations[-1]["payload"]["open_order_ids"] == [11]
    assert positions[-1]["payload"]["size_signed"] == 1.0


def _row(
    sequence: int, event_type: str, payload: dict[str, object]
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "sequence": sequence,
        "event_type": event_type,
        "observed_at_utc": f"2026-08-20T12:00:{sequence % 60:02d}+00:00",
        "execution_mode": "live",
        "effective_mode": "LIVE ARMED",
        "live_armed": True,
        "execution_authority": "hyperliquid_mainnet",
        "profile_id": "profile",
        "profile_fingerprint": "profile-fingerprint",
        "run_fingerprint": "run-fingerprint",
        "run_id": _RUN_ID,
        "payload": payload,
    }


def _write_rows(path: Path, rows: list[dict[str, object]]) -> Path:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path
