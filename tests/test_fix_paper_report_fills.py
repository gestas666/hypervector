"""`paper report` counts only real fills and reports the live tree honestly."""

from __future__ import annotations

from pathlib import Path

from hypervector.infra import ensure_data_layout
from hypervector.paper.costs import CostProvider
from hypervector.paper.fills import ExplicitFillEngine
from hypervector.paper.ledger import append_paper_decision
from hypervector.paper.report import report_from_data_root, summarize_paper_decisions


def _engine(root: Path, *, run_id: str = "run-a") -> ExplicitFillEngine:
    return ExplicitFillEngine(
        root,
        cost_provider=CostProvider(fee_tier=0),
        run_id=run_id,
        export_id="exp",
        strategy_name="test_managed_long",
        symbol="BTC",
        timeframe="1m",
        conviction=0.5,
        execution_mode="shadow",
    )


def test_order_lifecycle_and_skipped_rows_are_not_market_fills(tmp_path: Path) -> None:
    root = tmp_path / "data"
    engine = _engine(root)
    for action, status in (
        ("submit_entry", "pending"),
        ("accepted_entry", "accepted"),
        ("cancel_entry", "canceled"),
        ("submit_target", "pending"),
    ):
        engine.record_order_event(
            feed_ts="2026-07-23T00:00:00+00:00",
            action=action,
            side="buy",
            qty=0.01,
            limit_px=50_000.0,
            status=status,
        )
    append_paper_decision(
        root,
        {
            "feed_ts": "2026-07-23T00:01:00+00:00",
            "action": "enter_long",
            "side": "buy",
            "qty": 0.0,
            "fill_qty": 0.0,
            "skipped": True,
            "skip_reason": "book_gate",
            "fill_model_id": "l2_walk_v1",
            "execution_mode": "shadow",
        },
    )
    engine.apply_market_fill(
        feed_ts="2026-07-23T00:02:00+00:00",
        action="enter_long",
        side="buy",
        qty=0.01,
        mark_px=50_000.0,
    )

    report = report_from_data_root(root)

    assert report["rows"] == 6
    assert report["market_fills"] == 1
    assert report["action"] == {"enter_long": 1}
    assert sum(report["fill_model_id"].values()) == 1
    assert report["order_events"]["count"] == 4
    assert report["order_events"]["action"] == {
        "accepted_entry": 1,
        "cancel_entry": 1,
        "submit_entry": 1,
        "submit_target": 1,
    }
    assert report["skipped_fills"] == 1
    assert report["order_intent"]["missing_on_market_fills"] == 0
    assert [row["action"] for row in report["last_market"]] == ["enter_long"]


def test_fill_predicate_keeps_liquidations_and_legacy_rows() -> None:
    rows = [
        {"action": "partial_liquidation", "fill_model_id": "liq", "fill_qty": 0.2},
        {"action": "backstop_liquidation", "fill_model_id": "liq", "qty": 1.0},
        {"action": "close", "fill_model_id": "legacy"},  # legacy row without qty
        {"action": "funding", "fill_model_id": "bar_close_slippage_v1", "qty": 1.0},
    ]
    report = summarize_paper_decisions(rows)
    assert report["market_fills"] == 3
    assert report["funding_rows"] == 1


def test_live_bot_files_do_not_fail_paper_honesty(tmp_path: Path) -> None:
    """A co-hosted live runtime's own files say nothing about paper behaviour."""
    root = tmp_path / "data"
    ensure_data_layout(root)
    append_paper_decision(
        root, {"feed_ts": "t0", "action": "close", "execution_mode": "shadow"}
    )
    live_ledger = root / "live" / "decisions" / "decisions.jsonl"
    live_ledger.write_text('{"execution_mode":"live","action":"close"}\n')
    (root / "live" / "bot.log").write_text("live runtime output\n")

    report = report_from_data_root(root)

    assert report["honesty"]["live_files"] == 0
    assert report["honesty"]["no_live_files"] is True


def test_paper_stamped_artifact_under_live_fails_honesty(tmp_path: Path) -> None:
    """A paper/shadow decision ledger misrouted under live/ is a real violation."""
    root = tmp_path / "data"
    ensure_data_layout(root)
    append_paper_decision(
        root, {"feed_ts": "t0", "action": "close", "execution_mode": "shadow"}
    )
    misrouted = root / "live" / "paper" / "decisions" / "decisions.jsonl"
    misrouted.parent.mkdir(parents=True)
    misrouted.write_text('{"execution_mode":"shadow","action":"close"}\n')

    report = report_from_data_root(root)

    assert report["honesty"]["live_files"] == 1
    assert report["honesty"]["no_live_files"] is False


def test_report_filters_by_run_and_strategy(tmp_path: Path) -> None:
    root = tmp_path / "data"
    _engine(root, run_id="run-a").apply_market_fill(
        feed_ts="t1", action="enter_long", side="buy", qty=0.01, mark_px=50_000.0
    )
    _engine(root, run_id="run-b").apply_market_fill(
        feed_ts="t2", action="enter_long", side="buy", qty=0.01, mark_px=50_000.0
    )

    report = report_from_data_root(root, run_id="run-b")
    assert report["rows"] == 1
    assert report["market_fills"] == 1
    assert report["filters"] == {"run_id": "run-b", "strategy": None}
    none = report_from_data_root(root, strategy="test_sma_cross_short")
    assert none["rows"] == 0
