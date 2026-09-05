"""Point-in-time integration coverage for live cohort checkpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from cohort_trade_reflection_fixtures import (
    open_reflection_cohort_rows,
    reflection_asset_rows,
)
from test_multi_asset_live_audit import _RUN_ID, _SYMBOLS, _asset_rows

from hypervector.research.cohort_live_audit import audit_multi_asset_live_run


def test_later_generic_cohort_event_cannot_mix_with_post_snapshot_close() -> None:
    """A checkpoint must keep portfolio state and asset lifecycles co-temporal."""
    cohort = open_reflection_cohort_rows()
    latest_snapshot = next(
        row for row in reversed(cohort) if row["event_type"] == "cohort_snapshot"
    )
    latest_snapshot["observed_at_utc"] = _utc(1_785_600_005)
    cohort[-1]["observed_at_utc"] = _utc(1_785_600_032)
    report = audit_multi_asset_live_run(
        cohort,
        {
            "BTC": reflection_asset_rows(),
            **{symbol: _asset_rows(symbol) for symbol in _SYMBOLS if symbol != "BTC"},
        },
        run_id=_RUN_ID,
    )

    open_trades = report["open_trade_reflections"]["trades"]
    assert [trade["lifecycle_id"] for trade in open_trades] == ["BTC:11"]
    assert report["trade_reflections"]["trades"] == []


def _utc(seconds: int) -> str:
    """Return one stable UTC fixture timestamp."""
    return datetime.fromtimestamp(seconds, tz=UTC).isoformat()
