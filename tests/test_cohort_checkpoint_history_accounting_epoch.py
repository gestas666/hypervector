"""Accounting-epoch reconciliation for rolling live checkpoints."""

from __future__ import annotations

import pytest

from hypervector.research import cohort_checkpoint_history


def _audit(*, archive_closed: int, reflected_closed: int) -> dict[str, object]:
    return {
        "portfolio_archive": {
            "accounting_epoch": {
                "epoch_id": "first_live",
                "profile_fingerprint": "a" * 64,
                "start_venue_timestamp_ms": 1_786_653_167_380,
            },
            "performance": {
                "total": {
                    "closed_trades": archive_closed,
                    "net_pnl_usd": -49.60,
                    "maximum_closed_sequence_drawdown_usd": 49.60,
                }
            },
        },
        "trade_reflections": {
            "all_time_live": {
                "history_schema_version": 1,
                "closed_trades": reflected_closed,
                "performance": {
                    "total": {
                        "closed_trades": reflected_closed,
                        "net_pnl_usd": -45.36,
                        "maximum_closed_sequence_drawdown_usd": 49.60,
                    }
                },
            }
        },
    }


def test_epoch_archive_does_not_require_equal_all_history_count() -> None:
    """A reset epoch may coexist with separately labeled older history."""
    bounded = _audit(archive_closed=1, reflected_closed=1)
    complete = _audit(archive_closed=1, reflected_closed=74)

    closed = cohort_checkpoint_history._require_matching_archive_history(
        bounded,
        complete,
    )

    assert closed == 1


def test_epoch_archive_change_still_forces_complete_refresh() -> None:
    """A new epoch close must invalidate the cached historical projection."""
    bounded = _audit(archive_closed=2, reflected_closed=2)
    complete = _audit(archive_closed=1, reflected_closed=74)

    with pytest.raises(
        cohort_checkpoint_history.HistoricalProjectionStale,
        match="archive closed lifecycle count",
    ):
        cohort_checkpoint_history._require_matching_archive_history(
            bounded,
            complete,
        )


def test_new_epoch_archive_forces_refresh_when_cached_checkpoint_has_none() -> None:
    """The first post-sync archive must rebuild a pre-sync cached checkpoint."""
    bounded = _audit(archive_closed=0, reflected_closed=0)
    complete = _audit(archive_closed=0, reflected_closed=0)
    del complete["portfolio_archive"]

    with pytest.raises(
        cohort_checkpoint_history.HistoricalProjectionStale,
        match="complete portfolio archive is unavailable",
    ):
        cohort_checkpoint_history._require_matching_archive_history(
            bounded,
            complete,
        )


def test_historical_merge_copies_closed_history_and_keeps_current_sections() -> None:
    """Cached closed history replaces only the all-time sections."""
    bounded = _historical_sections("bounded")
    complete = _historical_sections("complete")

    cohort_checkpoint_history._copy_historical_sections(bounded, complete)

    reflections = bounded["trade_reflections"]
    assert reflections["all_time_live"] == {"marker": "complete"}
    assert reflections["provider_contract_history"] == {"marker": "complete"}
    assert reflections["performance"]["all_time_live"] == {"marker": "complete"}
    assert reflections["current_run"] == {"marker": "bounded"}
    assert bounded["side_composition"]["marker"] == "bounded"


def _historical_sections(label: str) -> dict[str, object]:
    return {
        "side_composition": {"marker": label},
        "trade_reflections": {
            "all_time_live": {"marker": label},
            "provider_contract_history": {"marker": label},
            "current_run": {"marker": label},
            "performance": {"all_time_live": {"marker": label}},
        },
    }
