"""Shadow resume memory must not grow with telemetry-only ledger history."""

from __future__ import annotations

import json
import tracemalloc
from pathlib import Path

import pytest

from paper_fix_fixtures import write_strict_export

from hypervector.paper.maker_execution import PostOnlyLimitFillModel
from hypervector.paper.resume import ShadowResumeError, load_shadow_portfolio_resume
from hypervector.paper.session import PaperSession


def _seed_filled_shadow_run(tmp_path: Path) -> tuple[Path, str]:
    export = write_strict_export(tmp_path, strategy="hypervelocity_1m_scalper_long")
    root = tmp_path / "data"
    session = PaperSession(export_dir=export, data_root=root, execution_mode="shadow")
    session.ensure_session_identity()
    session.engine.apply_market_fill(
        feed_ts="2026-07-26T20:58:00Z",
        action="enter_long",
        side="buy",
        qty=0.01,
        mark_px=100.0,
        fill_model=PostOnlyLimitFillModel(),
    )
    return session.decisions_path, session.run_id


def _telemetry(run_id: str, action: str, index: int) -> str:
    levels = [{"price": 100.0 + i, "size": 1.0 + i} for i in range(20)]
    row = {
        "feed_ts": f"2026-07-26T21:{index % 60:02d}:00+00:00",
        "run_id": run_id,
        "strategy_name": "hypervelocity_1m_scalper_long",
        "symbol": "BTC",
        "timeframe": "1m",
        "action": action,
        "bids": levels,
        "asks": levels,
        "execution_mode": "shadow",
        "submitted": False,
    }
    return json.dumps(row, separators=(",", ":")) + "\n"


def test_resume_ignores_and_does_not_retain_telemetry_rows(tmp_path: Path) -> None:
    path, run_id = _seed_filled_shadow_run(tmp_path)
    baseline = load_shadow_portfolio_resume(path, symbol="BTC", timeframe="1m")
    with path.open("a", encoding="utf-8") as handle:
        for index in range(4000):
            action = "book_observation" if index % 2 else "entry_execution_observation"
            handle.write(_telemetry(run_id, action, index))

    tracemalloc.start()
    try:
        resumed = load_shadow_portfolio_resume(path, symbol="BTC", timeframe="1m")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert resumed == baseline
    # 4000 retained telemetry dicts cost tens of MB; streaming keeps it bounded.
    assert peak < 2_000_000


def test_malformed_telemetry_line_still_fails_closed(tmp_path: Path) -> None:
    path, run_id = _seed_filled_shadow_run(tmp_path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_telemetry(run_id, "book_observation", 0)[:-20] + "\n")
        handle.write(_telemetry(run_id, "book_observation", 1))

    with pytest.raises(ShadowResumeError, match="line 3"):
        load_shadow_portfolio_resume(path, symbol="BTC", timeframe="1m")
