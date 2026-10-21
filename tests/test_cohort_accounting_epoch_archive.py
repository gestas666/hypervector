"""Tests for profile-and-time bounded clean accounting epochs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hypervector.research import cohort_live_portfolio_archive as archive_module
from hypervector.research.cohort_live_portfolio_archive import (
    CohortAccountingEpoch,
    CohortLiveArchiveSource,
    CohortLiveFillIdentity,
    load_cohort_live_portfolio_archive,
)

_CURRENT = "a" * 64
_PRIOR = "b" * 64


def _row(profile: str, exit_ms: int, net: float) -> tuple[object, ...]:
    return (
        "BTC",
        "strategy",
        "run",
        "Open Long",
        net,
        0.1,
        0.0,
        10.0,
        5.0,
        profile,
        exit_ms,
        exit_ms,
    )


def _source(path: Path) -> CohortLiveArchiveSource:
    return CohortLiveArchiveSource(
        database_path=str(path.resolve()),
        identity=CohortLiveFillIdentity(fill_events=6, sha256="c" * 64),
        lifecycle_rows=(
            _row(_PRIOR, 1_000, 3.0),
            _row(_CURRENT, 1_500, 4.0),
            _row(_CURRENT, 2_000, 5.0),
            _row(_PRIOR, 2_500, 2.0),
        ),
        observed_through_utc=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _reflection(
    lifecycle_id: str,
    profile: str,
    exit_ms: int,
    net: float,
) -> dict[str, object]:
    return {
        "lifecycle_id": lifecycle_id,
        "source_run_id": "run",
        "source_profile_fingerprint": profile,
        "symbol": "BTC",
        "strategy_id": "strategy",
        "side": "long",
        "net_pnl_usd": net,
        "entry_margin_used_usd": 100.0,
        "net_return_on_margin_pct": net,
        "fees_usd": 0.1,
        "funding_usd": 0.0,
        "exit": {"venue_timestamp_ms": exit_ms},
    }


def test_accounting_epoch_filters_prior_profile_and_pre_epoch_rows(
    tmp_path: Path,
) -> None:
    database = tmp_path / "market.duckdb"
    database.touch()
    epoch = CohortAccountingEpoch("fixture_epoch_a", _CURRENT, 1_800)

    archive = load_cohort_live_portfolio_archive(
        database,
        source=_source(database),
        accounting_epoch=epoch,
    )

    assert archive["accounting_epoch"] == epoch.to_dict()
    assert archive["coverage"]["closed_orders"] == 1
    assert archive["performance"]["total"]["closed_trades"] == 1
    assert archive["performance"]["total"]["net_pnl_usd"] == pytest.approx(5.0)
    assert archive["source_execution"]["fill_events"] == 6
    preserved = archive["preserved_history"]
    assert preserved["scope"] == "full_backend_history"
    assert preserved["coverage"]["closed_orders"] == 4
    assert preserved["performance"]["total"]["closed_trades"] == 4
    assert preserved["performance"]["total"]["net_pnl_usd"] == pytest.approx(14.0)


def test_accounting_epoch_lineage_includes_each_exact_profile_after_start(
    tmp_path: Path,
) -> None:
    """One funded campaign may continue across an exact profile lineage."""
    database = tmp_path / "market.duckdb"
    database.touch()
    epoch = CohortAccountingEpoch(
        "fixture_epoch_a_b",
        _CURRENT,
        1_800,
        included_profile_fingerprints=(_PRIOR, _CURRENT),
    )

    archive = load_cohort_live_portfolio_archive(
        database,
        source=_source(database),
        accounting_epoch=epoch,
    )

    assert archive["accounting_epoch"] == {
        "epoch_id": "fixture_epoch_a_b",
        "profile_fingerprint": _CURRENT,
        "start_venue_timestamp_ms": 1_800,
        "included_profile_fingerprints": [_PRIOR, _CURRENT],
    }
    assert archive["coverage"]["closed_orders"] == 2
    assert archive["performance"]["total"]["closed_trades"] == 2
    assert archive["performance"]["total"]["net_pnl_usd"] == pytest.approx(7.0)


def test_accounting_epoch_archive_reconciles_new_reflected_close_once(
    tmp_path: Path,
) -> None:
    """A stale database archive must not omit or double-count a newer close."""
    database = tmp_path / "market.duckdb"
    database.touch()
    epoch = CohortAccountingEpoch(
        "fixture_epoch_a_b",
        _CURRENT,
        1_800,
        included_profile_fingerprints=(_PRIOR, _CURRENT),
    )
    stale = load_cohort_live_portfolio_archive(
        database,
        source=_source(database),
        accounting_epoch=epoch,
    )
    all_time_live = {
        "trades": [
            _reflection("before-epoch", _CURRENT, 1_500, 50.0),
            _reflection("already-archived", _PRIOR, 2_500, 2.0),
            _reflection("last-btc-close", _CURRENT, 3_000, 6.0),
        ]
    }

    reconciler = getattr(archive_module, "reconcile_accounting_epoch_archive", None)
    assert callable(reconciler), "accounting epoch reflection reconciliation is missing"
    reconciled = reconciler(stale, all_time_live)

    assert reconciled["coverage"] == {
        "complete": True,
        "closed_orders": 2,
        "leverage_matches": 2,
    }
    total = reconciled["performance"]["total"]
    assert total["closed_trades"] == 2
    assert total["wins"] == 2
    assert total["net_pnl_usd"] == pytest.approx(8.0)
    assert reconciled["performance_source"]["mode"] == (
        "accounting_epoch_trade_reflections_v1"
    )
    assert reconciled["performance_source"]["closed_lifecycles"] == 2
    assert reconciled["preserved_history"] == stale["preserved_history"]
    assert stale["performance"]["total"]["closed_trades"] == 2


def test_accounting_epoch_reconciliation_never_drops_database_lifecycles(
    tmp_path: Path,
) -> None:
    """A bounded reflection window must not erase newer durable DB outcomes."""
    database = tmp_path / "market.duckdb"
    database.touch()
    epoch = CohortAccountingEpoch(
        "fixture_epoch_a_b",
        _CURRENT,
        1_800,
        included_profile_fingerprints=(_PRIOR, _CURRENT),
    )
    archive = load_cohort_live_portfolio_archive(
        database,
        source=_source(database),
        accounting_epoch=epoch,
    )
    incomplete_reflections = {
        "trades": [_reflection("only-one-visible", _CURRENT, 2_000, 5.0)]
    }

    reconciled = archive_module.reconcile_accounting_epoch_archive(
        archive,
        incomplete_reflections,
    )

    assert reconciled["coverage"]["closed_orders"] == 2
    assert reconciled["performance"]["total"]["closed_trades"] == 2
    assert reconciled["performance"]["total"]["net_pnl_usd"] == pytest.approx(7.0)
    assert reconciled.get("performance_source") != {
        "mode": "accounting_epoch_trade_reflections_v1",
        "closed_lifecycles": 1,
    }


@pytest.mark.parametrize(
    "included",
    [
        (_PRIOR, _PRIOR),
        (_PRIOR,),
        (_PRIOR, "bad"),
    ],
)
def test_accounting_epoch_rejects_invalid_profile_lineage(
    included: tuple[str, ...],
) -> None:
    """Lineage scope must be unique, valid, and include the current profile."""
    with pytest.raises(ValueError, match="accounting epoch profile lineage"):
        CohortAccountingEpoch(
            "fixture_epoch_a_b",
            _CURRENT,
            1_800,
            included_profile_fingerprints=included,
        )


def test_accounting_epoch_can_publish_an_explicit_zero_trade_archive(
    tmp_path: Path,
) -> None:
    database = tmp_path / "market.duckdb"
    database.touch()
    epoch = CohortAccountingEpoch("fixture_epoch_a", _CURRENT, 3_000)

    archive = load_cohort_live_portfolio_archive(
        database,
        source=_source(database),
        accounting_epoch=epoch,
    )

    assert archive["coverage"]["closed_orders"] == 0
    assert archive["symbols"] == []
    assert archive["performance"]["total"]["closed_trades"] == 0


@pytest.mark.parametrize(
    ("epoch_id", "fingerprint", "start_ms"),
    [("", _CURRENT, 1), ("epoch", "bad", 1), ("epoch", _CURRENT, -1)],
)
def test_accounting_epoch_rejects_invalid_identity(
    epoch_id: str, fingerprint: str, start_ms: int
) -> None:
    with pytest.raises(ValueError, match="accounting epoch"):
        CohortAccountingEpoch(epoch_id, fingerprint, start_ms)
