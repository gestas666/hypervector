"""Phase 3 paper decision ledger scaffold — identity + path separation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.cli import main
from hypervector.paper.ledger import PaperLedgerError, append_paper_decision


def test_append_paper_decision_writes_under_paper_decisions(tmp_path: Path):
    root = tmp_path / "data"
    out = append_paper_decision(
        root,
        {"feed_ts": "2026-07-22T12:00:00Z", "side": "buy", "symbol": "BTC"},
    )
    assert out.is_file()
    assert out.parent == (root / "paper" / "decisions")
    assert out.is_relative_to(root / "paper" / "decisions")
    assert "live" not in out.resolve().parts

    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["execution_mode"] == "paper"
    assert rec["feed_ts"] == "2026-07-22T12:00:00Z"
    assert rec["side"] == "buy"


def test_append_stamps_execution_mode_paper_even_if_caller_lies(tmp_path: Path):
    root = tmp_path / "data"
    out = append_paper_decision(
        root,
        {"execution_mode": "live", "feed_ts": 1_721_644_800, "intent": "enter"},
    )
    rec = json.loads(out.read_text(encoding="utf-8").strip())
    assert rec["execution_mode"] == "paper"


def test_append_preserves_shadow_mode(tmp_path: Path):
    p = append_paper_decision(
        tmp_path / "data",
        {"feed_ts": "t0", "action": "enter_long", "execution_mode": "shadow"},
    )
    line = p.read_text(encoding="utf-8").strip().splitlines()[-1]
    row = json.loads(line)
    assert row["execution_mode"] == "shadow"


def test_append_defaults_paper_when_mode_missing(tmp_path: Path):
    p = append_paper_decision(tmp_path / "data", {"feed_ts": "t0", "action": "x"})
    row = json.loads(p.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert row["execution_mode"] == "paper"


def test_append_still_refuses_live_root(tmp_path: Path):
    with pytest.raises(PaperLedgerError):
        append_paper_decision(tmp_path / "data" / "live", {"feed_ts": "t0"})


def test_append_requires_feed_timestamp(tmp_path: Path):
    root = tmp_path / "data"
    with pytest.raises(PaperLedgerError, match="feed"):
        append_paper_decision(root, {"side": "sell"})


def test_append_accepts_feed_timestamp_alias(tmp_path: Path):
    root = tmp_path / "data"
    out = append_paper_decision(
        root,
        {"feed_timestamp": "2026-07-22T00:00:00+00:00", "note": "alias"},
    )
    rec = json.loads(out.read_text(encoding="utf-8").strip())
    assert rec["execution_mode"] == "paper"
    assert rec["feed_ts"] == "2026-07-22T00:00:00+00:00"
    assert "feed_timestamp" not in rec or rec.get("feed_ts")


def test_append_is_append_only(tmp_path: Path):
    root = tmp_path / "data"
    p1 = append_paper_decision(root, {"feed_ts": "t1", "n": 1})
    p2 = append_paper_decision(root, {"feed_ts": "t2", "n": 2})
    assert p1 == p2
    lines = p1.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["n"] == 1
    assert json.loads(lines[1])["n"] == 2


def test_refuse_write_when_data_root_is_live_tree(tmp_path: Path):
    """Refuse if resolved destination would sit under data/live/."""
    live = tmp_path / "data" / "live"
    live.mkdir(parents=True)
    with pytest.raises(PaperLedgerError, match="live"):
        append_paper_decision(live, {"feed_ts": "t0"})


def test_refuse_write_when_data_root_nested_under_live(tmp_path: Path):
    nested = tmp_path / "data" / "live" / "nested_root"
    nested.mkdir(parents=True)
    with pytest.raises(PaperLedgerError, match="live"):
        append_paper_decision(nested, {"feed_ts": "t0"})


def test_cli_paper_check_prints_layout_and_live_feed_loop(tmp_path: Path, capsys):
    data = tmp_path / "data"
    assert main(["--data-root", str(data), "paper-check"]) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["dirs"]["paper_decisions"]["exists"] is True
    assert report["dirs"]["paper_ledger"]["exists"] is True
    assert report["rules"]["paper_live_separated"] is True
    assert report["paper"]["live_feed_loop"] is True
    assert report["paper"]["execution_mode"] == "shadow"  # 4b default
    assert "secrets_present" in report["paper"]
