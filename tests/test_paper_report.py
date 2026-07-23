"""paper-report: pure summary + CLI over real decisions JSONL."""

from __future__ import annotations

import json
from pathlib import Path

from hypervector.cli import main
from hypervector.infra import ensure_data_layout
from hypervector.paper.ledger import DECISIONS_FILENAME, append_paper_decision
from hypervector.paper.report import (
    default_decisions_path,
    report_from_data_root,
    summarize_paper_decisions,
)


def _market_row(**overrides):
    base = {
        "feed_ts": "2026-07-23T00:00:00+00:00",
        "execution_mode": "shadow",
        "submitted": False,
        "network": "mainnet",
        "action": "enter_short",
        "fill_model_id": "bar_close_slippage_v1",
        "fill_fallback_reason": "book_missing",
        "order_intent": {
            "schema": "hv_order_intent_v1",
            "submit_enabled": False,
        },
    }
    base.update(overrides)
    return base


def test_summarize_paper_decisions_counters():
    rows = [
        _market_row(feed_ts="t1"),
        _market_row(
            feed_ts="t2",
            action="close",
            fill_model_id="l2_walk_v1",
            fill_fallback_reason=None,
        ),
        {
            "feed_ts": "t3",
            "execution_mode": "shadow",
            "submitted": False,
            "network": "mainnet",
            "action": "funding",
            "fill_model_id": "bar_close_slippage_v1",
        },
    ]
    rep = summarize_paper_decisions(rows, last_n=2)
    assert rep["ok"] is True
    assert rep["rows"] == 3
    assert rep["market_fills"] == 2
    assert rep["funding_rows"] == 1
    assert rep["execution_mode"] == {"shadow": 3}
    assert rep["submitted"] == {"False": 3}
    assert rep["fill_model_id"]["bar_close_slippage_v1"] == 1
    assert rep["fill_model_id"]["l2_walk_v1"] == 1
    assert rep["order_intent"]["count"] == 2
    assert rep["order_intent"]["submit_enabled"] == {"False": 2}
    assert rep["honesty"]["all_submitted_false_or_absent"] is True
    assert rep["honesty"]["all_intent_submit_enabled_false"] is True
    assert rep["no_submit"] is True
    assert rep["live_submit_implemented"] is True
    assert rep["live_submit_command"] == "live-run"
    assert len(rep["last_market"]) == 2


def test_report_from_data_root_reads_ledger(tmp_path: Path):
    root = tmp_path / "data"
    ensure_data_layout(root)
    append_paper_decision(root, _market_row())
    append_paper_decision(
        root,
        _market_row(feed_ts="t2", action="close", fill_model_id="l2_walk_v1"),
    )
    # touch empty live tree only
    (root / "live").mkdir(exist_ok=True)

    rep = report_from_data_root(root, last_n=1)
    assert rep["rows"] == 2
    assert rep["market_fills"] == 2
    assert rep["honesty"]["no_live_files"] is True
    assert Path(rep["decisions_path"]).name == DECISIONS_FILENAME
    assert rep["decisions_path"] == str(default_decisions_path(root))


def test_report_refuses_live_path(tmp_path: Path):
    root = tmp_path / "data"
    ensure_data_layout(root)
    live_dec = root / "live" / "decisions.jsonl"
    live_dec.parent.mkdir(parents=True, exist_ok=True)
    live_dec.write_text("{}\n", encoding="utf-8")
    try:
        report_from_data_root(root, decisions_path=live_dec)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "live" in str(exc).lower()


def test_cli_paper_report(tmp_path: Path, capsys):
    root = tmp_path / "data"
    ensure_data_layout(root)
    append_paper_decision(root, _market_row())
    rc = main(["--data-root", str(root), "paper-report", "--last", "1"])
    assert rc == 0
    out = capsys.readouterr().out
    rep = json.loads(out)
    assert rep["ok"] is True
    assert rep["market_fills"] == 1
    assert rep["honesty"]["all_intent_submit_enabled_false"] is True
