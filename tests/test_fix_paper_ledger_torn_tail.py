"""A torn final ledger line is preserved, repaired and never merged into a record."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from paper_fix_fixtures import write_strict_export

from hypervector.paper import ledger as ledger_module
from hypervector.paper.ledger import (
    QUARANTINE_ACTION,
    PaperLedgerError,
    append_paper_decision,
)
from hypervector.paper.maker_execution import PostOnlyLimitFillModel
from hypervector.paper.peak_observer_persistence import load_peak_observer_state
from hypervector.paper.report import report_from_data_root
from hypervector.paper.resume import ShadowResumeError, load_shadow_portfolio_resume
from hypervector.paper.session import PaperSession
from hypervector.shadow_reset import reset_shadow_state

FRAGMENT = b'{"feed_ts":"2026-07-26T21:00:00Z","action":"regime_observ'


def _ledger(root: Path) -> Path:
    return root / "paper" / "decisions" / "decisions.jsonl"


def _rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_next_append_quarantines_fragment_instead_of_merging(tmp_path: Path) -> None:
    root = tmp_path / "data"
    path = append_paper_decision(root, {"feed_ts": "t0", "action": "close"})
    with path.open("ab") as handle:
        handle.write(FRAGMENT)

    append_paper_decision(root, {"feed_ts": "t1", "action": "enter_long"})

    rows = _rows(path)  # every line parses: nothing was merged into the fragment
    assert [row["action"] for row in rows] == ["close", QUARANTINE_ACTION, "enter_long"]
    audit = rows[1]
    assert audit["torn_bytes"] == len(FRAGMENT)
    sidecar = Path(str(audit["sidecar"]))
    assert sidecar.parent == path.parent
    assert sidecar.name.startswith("decisions.jsonl.torn-")
    assert sidecar.read_bytes() == FRAGMENT


def test_complete_unterminated_record_is_kept_not_quarantined(tmp_path: Path) -> None:
    root = tmp_path / "data"
    path = append_paper_decision(root, {"feed_ts": "t0", "action": "close"})
    with path.open("ab") as handle:
        handle.write(b'{"feed_ts":"t1","action":"funding"}')

    append_paper_decision(root, {"feed_ts": "t2", "action": "close"})

    assert [row["action"] for row in _rows(path)] == ["close", "funding", "close"]
    assert list(path.parent.glob("decisions.jsonl.torn-*")) == []


def test_short_write_is_rolled_back(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "data"
    path = append_paper_decision(root, {"feed_ts": "t0", "action": "close"})
    before = path.read_bytes()
    monkeypatch.setattr(ledger_module, "_write", lambda fd, data: 7)

    with pytest.raises(OSError):
        append_paper_decision(root, {"feed_ts": "t1", "action": "close"})

    assert path.read_bytes() == before


def test_append_creates_no_live_tree_and_refuses_symlinked_ledger(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    append_paper_decision(root, {"feed_ts": "t0", "action": "close"})
    assert not (root / "live").exists()

    other = tmp_path / "other"
    other_live = other / "live" / "decisions.jsonl"
    other_live.parent.mkdir(parents=True)
    other_live.write_text("")
    hijacked = tmp_path / "hijacked"
    target = _ledger(hijacked)
    target.parent.mkdir(parents=True)
    target.symlink_to(other_live)
    with pytest.raises(PaperLedgerError, match="live"):
        append_paper_decision(hijacked, {"feed_ts": "t0"})
    assert other_live.read_text() == ""

    # A symlinked parent directory that lands in a live tree is refused too.
    linked_root = tmp_path / "linked"
    linked_root.mkdir()
    (linked_root / "paper").symlink_to(other / "live", target_is_directory=True)
    with pytest.raises(PaperLedgerError, match="live"):
        append_paper_decision(linked_root, {"feed_ts": "t0"})
    assert not (other / "live" / "decisions").exists()


def test_readers_tolerate_only_a_torn_final_line(tmp_path: Path) -> None:
    export = write_strict_export(tmp_path, strategy="hypervelocity_1m_scalper_long")
    root = tmp_path / "data"
    original = PaperSession(export_dir=export, data_root=root, execution_mode="shadow")
    original.ensure_session_identity()
    original.engine.apply_market_fill(
        feed_ts="2026-07-26T20:58:00Z",
        action="enter_long",
        side="buy",
        qty=0.01,
        mark_px=100.0,
        fill_model=PostOnlyLimitFillModel(),
    )
    path = _ledger(root)
    with path.open("ab") as handle:
        handle.write(FRAGMENT)

    resumed = load_shadow_portfolio_resume(
        path, symbol="BTC", timeframe="1m", expected_spec=None
    )
    assert resumed is not None and resumed.position_qty == pytest.approx(0.01)
    report = report_from_data_root(root)
    assert report["market_fills"] == 1
    assert report["torn_tail_skipped"] is True
    assert (
        load_peak_observer_state(path, run_id=original.run_id, candidate_id="x")
        is None
    )

    # Interior corruption stays fail-closed.
    lines = path.read_bytes().split(b"\n")
    path.write_bytes(lines[0] + b"\n" + FRAGMENT + b"\n" + lines[1] + b"\n")
    with pytest.raises(ShadowResumeError, match="line 2"):
        load_shadow_portfolio_resume(
            path, symbol="BTC", timeframe="1m", expected_spec=None
        )
    with pytest.raises(ValueError, match="invalid JSONL"):
        report_from_data_root(root)


def test_shadow_reset_waits_for_the_ledger_append_lock(tmp_path: Path) -> None:
    import fcntl
    import os

    root = tmp_path / "data"
    path = append_paper_decision(root, {"feed_ts": "t0", "action": "close"})
    fd = os.open(path, os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX)
    done = threading.Event()

    def reset() -> None:
        reset_shadow_state(root, confirmed=True)
        done.set()

    worker = threading.Thread(target=reset)
    worker.start()
    try:
        assert not done.wait(0.3)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    worker.join(5.0)
    assert done.is_set()
    assert path.read_text() == ""
