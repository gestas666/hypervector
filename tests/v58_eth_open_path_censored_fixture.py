"""Fixture mutation for one technically censored V58 ETH lifecycle."""

from __future__ import annotations

import json
from pathlib import Path


def write_censored_status(status: Path) -> None:
    """Replace one pending fixture attempt with active-book-gap evidence."""
    payload = json.loads(status.read_text(encoding="utf-8"))
    attempt = payload["latest_attempts"][0]
    fields = (
        "available_time_ms",
        "candidate_strategy_id",
        "decision_time_ms",
        "entry_notional_usd",
        "entry_price",
        "entry_time_ms",
        "position_quantity",
        "side",
        "source_run_id",
        "strategy_id",
        "symbol",
    )
    keep = {key: attempt[key] for key in fields}
    payload["latest_attempts"] = [
        keep
        | {
            "status": "active_book_path_gap",
            "current_exit_time_ms": 4_000,
            "deadline_time_ms": 5_000,
            "active_book_gap_start_ms": 1_000,
            "active_book_gap_end_ms": 3_000,
            "maximum_active_book_gap_ms": 2_000,
            "maximum_allowed_active_book_gap_ms": 1_000,
        }
    ]
    payload["summary"].update({"pending": 0, "technical_incomplete": 1})
    status.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def write_censored_then_pending_status(status: Path) -> None:
    """Prepend one censored lifecycle to the current pending fixture."""
    payload = json.loads(status.read_text(encoding="utf-8"))
    pending = payload["latest_attempts"][0]
    censored = {
        **pending,
        "status": "active_book_path_gap",
        "decision_time_ms": 350,
        "available_time_ms": 400,
        "entry_time_ms": 500,
        "current_exit_time_ms": 800,
        "deadline_time_ms": 900,
        "active_book_gap_start_ms": 600,
        "active_book_gap_end_ms": 800,
        "maximum_active_book_gap_ms": 200,
        "maximum_allowed_active_book_gap_ms": 100,
    }
    payload["latest_attempts"] = [censored, pending]
    payload["summary"].update(
        {"pending": 1, "technical_incomplete": 1, "selected_non_overlapping": 2}
    )
    status.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
