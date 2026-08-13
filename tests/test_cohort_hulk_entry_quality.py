"""Report-only live attribution for Hulk money-flow and volume context."""

from __future__ import annotations

from hypervector.research.cohort_hulk_entry_quality import (
    build_hulk_entry_quality_mechanism,
)

HULK = "hulk_expansion_bidirectional_tuned_v2"


def _context(flow: int | None, volume: float | None) -> dict[str, object]:
    metrics: dict[str, object] = {}
    if flow is not None:
        metrics["money_flow_direction"] = flow
    if volume is not None:
        metrics["volume_ratio"] = volume
    return {
        "signal_provider": {
            "status": "observed",
            "readiness": {"metrics": metrics},
        }
    }


def _closed(
    *,
    side: str,
    flow: int | None,
    volume: float | None,
    pnl: float,
    return_pct: float,
    symbol: str = "BTC",
) -> dict[str, object]:
    return {
        "strategy_id": HULK,
        "symbol": symbol,
        "side": side,
        "net_pnl_usd": pnl,
        "net_return_on_margin_pct": return_pct,
        "entry_context": _context(flow, volume),
    }


def test_hulk_entry_quality_stratifies_symmetric_completed_outcomes() -> None:
    """Flow uses trade direction and volume uses one untuned 1.0x baseline."""
    report = build_hulk_entry_quality_mechanism(
        [
            _closed(side="long", flow=1, volume=1.2, pnl=2.0, return_pct=4.0),
            _closed(side="short", flow=-1, volume=0.7, pnl=1.0, return_pct=2.0),
            _closed(side="short", flow=1, volume=0.5, pnl=-1.0, return_pct=-2.0),
        ]
    )

    assert report["closed_trades"] == 3
    assert report["attributable_closed_trades"] == 3
    groups = report["closed_by_quality"]
    assert groups["flow_and_volume"]["trades"] == 1
    assert groups["one_of_two"]["trades"] == 1
    assert groups["neither"]["trades"] == 1
    assert groups["flow_and_volume"]["net_pnl_usd"] == 2.0
    assert groups["neither"]["normalized_profit_factor"] == 0.0
    assert report["by_side"]["short"]["closed_trades"] == 2


def test_hulk_entry_quality_keeps_open_marks_out_of_realized_results() -> None:
    """An active lifecycle is visible but cannot masquerade as a closed result."""
    open_trade = {
        "strategy_id": HULK,
        "symbol": "SOL",
        "side": "long",
        "entry_context": _context(-1, 0.09),
        "marked_economics": {
            "active_lifecycle_marked_net_pnl_usd": -0.04,
        },
    }

    report = build_hulk_entry_quality_mechanism([], [open_trade])

    assert report["closed_trades"] == 0
    assert report["open_trades"] == 1
    assert report["closed_by_quality"]["neither"]["trades"] == 0
    assert report["open_observations"] == [
        {
            "symbol": "SOL",
            "side": "long",
            "flow_direction": -1,
            "volume_ratio": 0.09,
            "quality": "neither",
            "marked_net_pnl_usd": -0.04,
            "status": "unresolved",
        }
    ]


def test_hulk_entry_quality_reports_unavailable_and_ignores_other_providers() -> None:
    """Missing legacy context stays unavailable and other strategies stay out."""
    legacy = _closed(
        side="long",
        flow=None,
        volume=None,
        pnl=0.5,
        return_pct=1.0,
    )
    other = dict(legacy, strategy_id="another_strategy")

    report = build_hulk_entry_quality_mechanism([legacy, other])

    assert report["closed_trades"] == 1
    assert report["attributable_closed_trades"] == 0
    assert report["closed_by_quality"]["unavailable"]["trades"] == 1
    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "automatic_strategy_changes": False,
        "runtime_strategy_changed": False,
        "execution_gate": False,
        "position_sizing_authority": False,
    }
