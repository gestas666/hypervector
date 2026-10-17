"""CLI surface for report-only shadow/real reconciliation."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from hypervector.cli import main


def test_shadow_compare_cli_writes_report(tmp_path: Path, capsys) -> None:
    ledger = tmp_path / "shadow.jsonl"
    rows = [
        {
            "feed_ts": "2026-07-25T10:00:00Z",
            "run_id": "run-long",
            "action": "regime_observation",
            "primary_regime": "TREND_UP",
            "entry_direction": "long",
            "entry_allowed": True,
        },
        {
            "feed_ts": "2026-07-25T10:00:10Z",
            "run_id": "run-long",
            "action": "enter_long",
            "side": "buy",
            "fill_px": 100.0,
            "fill_qty": 1.0,
        },
        {
            "feed_ts": "2026-07-25T10:01:00Z",
            "run_id": "run-long",
            "action": "regime_observation",
            "primary_regime": "TREND_UP",
            "entry_direction": "long",
            "entry_allowed": True,
        },
    ]
    ledger.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    positions = tmp_path / "positions.csv"
    pd.DataFrame(
        [
            {
                "symbol": "BTC",
                "side": "long",
                "open_time_utc": "2026-07-25T10:00:05Z",
                "close_time_utc": None,
                "entry_price": 100.0,
                "exit_price": None,
                "fill_type": "maker",
            }
        ]
    ).to_csv(positions, index=False)
    output = tmp_path / "report.json"

    rc = main(
        [
            "paper",
            "compare",
            "--shadow-ledger",
            str(ledger),
            "--positions",
            str(positions),
            "--run-id",
            "run-long",
            "--entry-tolerance-seconds",
            "30",
            "--out",
            str(output),
        ]
    )

    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["report_only"] is True
    assert report["summary"]["matched_entries"] == 1
    assert json.loads(output.read_text()) == report
