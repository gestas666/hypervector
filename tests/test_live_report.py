"""live-report: pure summary + CLI over live decisions JSONL."""

from __future__ import annotations

import json
from pathlib import Path

from hypervector.cli import main
from hypervector.infra import ensure_data_layout
from hypervector.live.ledger import DECISIONS_FILENAME, append_live_decision
from hypervector.live.report import (
    default_live_decisions_path,
    report_from_data_root,
    summarize_live_decisions,
)


def _live_row(**overrides):
    base = {
        "feed_ts": "2026-07-23T12:00:00+00:00",
        "execution_mode": "live",
        "submitted": True,
        "place_attempted": True,
        "live_phase": True,
        "network": "mainnet",
        "action": "enter_short",
        "fill_model_id": "live_venue_v1",
        "venue_order_id": "oid-1",
        "order_intent": {
            "schema": "hv_order_intent_v1",
            "submit_enabled": True,
        },
    }
    base.update(overrides)
    return base


def test_summarize_live_decisions_counters():
    rows = [
        _live_row(feed_ts="t1"),
        _live_row(
            feed_ts="t2",
            action="close",
            submitted=False,
            submit_error="reject",
            venue_order_id=None,
        ),
        {
            "feed_ts": "t3",
            "execution_mode": "live",
            "submitted": False,
            "place_attempted": False,
            "live_phase": False,
            "network": "mainnet",
            "action": "session_start",
        },
    ]
    rep = summarize_live_decisions(rows, last_n=2)
    assert rep["ok"] is True
    assert rep["ledger"] == "live"
    assert rep["rows"] == 3
    assert rep["market_fills"] == 2
    assert rep["session_start_rows"] == 1
    assert rep["execution_mode"] == {"live": 3}
    assert rep["submitted"]["True"] == 1
    assert rep["place_attempted"]["True"] == 2
    assert rep["honesty"]["all_execution_mode_live"] is True
    assert rep["live_submit_implemented"] is True
    assert rep["command"] == "live-run"
    assert len(rep["last_market"]) == 2


def test_report_from_data_root_reads_live_ledger(tmp_path: Path):
    root = tmp_path / "data"
    ensure_data_layout(root)
    append_live_decision(root, _live_row())
    append_live_decision(root, _live_row(feed_ts="t2", action="close"))

    rep = report_from_data_root(root, last_n=1)
    assert rep["rows"] == 2
    assert rep["market_fills"] == 2
    assert Path(rep["decisions_path"]).name == DECISIONS_FILENAME
    assert rep["decisions_path"] == str(default_live_decisions_path(root))


def test_live_report_refuses_paper_path(tmp_path: Path):
    root = tmp_path / "data"
    ensure_data_layout(root)
    paper_dec = root / "paper" / "decisions" / "decisions.jsonl"
    paper_dec.parent.mkdir(parents=True, exist_ok=True)
    paper_dec.write_text("{}\n", encoding="utf-8")
    try:
        report_from_data_root(root, decisions_path=paper_dec)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "paper" in str(exc).lower()


def test_cli_live_report(tmp_path: Path, capsys):
    root = tmp_path / "data"
    ensure_data_layout(root)
    append_live_decision(root, _live_row())
    rc = main(["--data-root", str(root), "live-report", "--last", "1"])
    assert rc == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["ok"] is True
    assert rep["ledger"] == "live"
    assert rep["rows"] == 1
