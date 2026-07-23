"""Live ledger: writes under data/live/decisions; refuses paper paths."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.infra import ensure_data_layout
from hypervector.live.ledger import LiveLedgerError, append_live_decision
from hypervector.paper.ledger import PaperLedgerError, append_paper_decision


def test_append_live_decision_writes_under_live_decisions(tmp_path: Path):
    root = tmp_path / "data"
    ensure_data_layout(root)
    out = append_live_decision(
        root,
        {
            "feed_ts": "2026-07-23T00:00:00+00:00",
            "action": "enter_short",
            "submitted": False,
            "symbol": "BTC",
        },
    )
    assert out == root / "live" / "decisions" / "decisions.jsonl"
    assert out.is_file()
    row = json.loads(out.read_text(encoding="utf-8").strip())
    assert row["execution_mode"] == "live"
    assert row["network"] == "mainnet"
    assert row["action"] == "enter_short"
    # Must not appear under paper
    paper = root / "paper" / "decisions" / "decisions.jsonl"
    assert not paper.is_file() or paper.read_text(encoding="utf-8").strip() == ""


def test_live_ledger_requires_feed_ts(tmp_path: Path):
    root = tmp_path / "data"
    with pytest.raises(LiveLedgerError, match="feed timestamp"):
        append_live_decision(root, {"action": "enter_long"})


def test_paper_still_refuses_live_root(tmp_path: Path):
    """Regression: paper ledger must not write under live/."""
    root = tmp_path / "data"
    ensure_data_layout(root)
    # Paper refuses when data_root itself is under a live path component
    live_root = root / "live" / "nested"
    live_root.mkdir(parents=True, exist_ok=True)
    with pytest.raises(PaperLedgerError, match="live"):
        append_paper_decision(
            live_root,
            {"feed_ts": "t0", "action": "enter_long"},
        )


def test_live_and_paper_ledgers_separated(tmp_path: Path):
    root = tmp_path / "data"
    append_paper_decision(
        root,
        {
            "feed_ts": "t0",
            "action": "enter_short",
            "execution_mode": "shadow",
            "submitted": False,
        },
    )
    append_live_decision(
        root,
        {
            "feed_ts": "t1",
            "action": "enter_short",
            "submitted": False,
        },
    )
    paper_lines = (
        root / "paper" / "decisions" / "decisions.jsonl"
    ).read_text(encoding="utf-8").strip().splitlines()
    live_lines = (
        root / "live" / "decisions" / "decisions.jsonl"
    ).read_text(encoding="utf-8").strip().splitlines()
    assert len(paper_lines) == 1
    assert len(live_lines) == 1
    assert json.loads(paper_lines[0])["execution_mode"] == "shadow"
    assert json.loads(live_lines[0])["execution_mode"] == "live"
