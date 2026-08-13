"""Tests for profile-and-time bounded clean accounting epochs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

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
        ),
        observed_through_utc=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_accounting_epoch_filters_prior_profile_and_pre_epoch_rows(
    tmp_path: Path,
) -> None:
    database = tmp_path / "market.duckdb"
    database.touch()
    epoch = CohortAccountingEpoch("growth_5000_v49", _CURRENT, 1_800)

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


def test_accounting_epoch_can_publish_an_explicit_zero_trade_archive(
    tmp_path: Path,
) -> None:
    database = tmp_path / "market.duckdb"
    database.touch()
    epoch = CohortAccountingEpoch("growth_5000_v49", _CURRENT, 3_000)

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
