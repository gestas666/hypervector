"""Fail-closed checkpoint cache tests for a clean cohort accounting epoch."""

from __future__ import annotations

import json
from pathlib import Path

from hypervector.research.cohort_live_portfolio_archive import CohortAccountingEpoch
from hypervector.research.cohort_rolling_checkpoint import (
    load_cached_portfolio_archive,
    publish_rolling_checkpoint,
)

_EPOCH = CohortAccountingEpoch("growth_5000_v49", "a" * 64, 1_786_579_200_000)


def _checkpoint(path: Path, epoch: dict[str, object] | None) -> None:
    archive: dict[str, object] = {
        "schema_version": 1,
        "mode": "cohort_live_portfolio_archive_v1",
    }
    if epoch is not None:
        archive["accounting_epoch"] = epoch
    path.write_text(
        json.dumps({"audit": {"portfolio_archive": archive}}), encoding="utf-8"
    )


def test_epoch_cache_refuses_an_unscoped_prior_archive(tmp_path: Path) -> None:
    checkpoint = tmp_path / "latest.json"
    _checkpoint(checkpoint, None)

    assert load_cached_portfolio_archive(checkpoint, accounting_epoch=_EPOCH) is None


def test_epoch_cache_accepts_only_the_exact_epoch(tmp_path: Path) -> None:
    checkpoint = tmp_path / "latest.json"
    _checkpoint(checkpoint, _EPOCH.to_dict())

    archive = load_cached_portfolio_archive(checkpoint, accounting_epoch=_EPOCH)

    assert archive is not None
    assert archive["accounting_epoch"] == _EPOCH.to_dict()


def test_rolling_publish_does_not_fall_back_to_unscoped_history(
    tmp_path: Path,
) -> None:
    checkpoint = tmp_path / "latest.json"
    _checkpoint(checkpoint, None)
    forwarded: list[object] = []

    def publish(_root: Path, _out: Path, **kwargs: object) -> dict[str, object]:
        forwarded.append(kwargs["portfolio_archive"])
        return {"status": "ready"}

    publish_rolling_checkpoint(
        publish,
        tmp_path / "ledger",
        checkpoint,
        requested_run_id="run-v49",
        config_path=Path("v49.toml"),
        once=True,
        venue_portfolio=None,
        opportunity_matrix_path=None,
        supplemental_opportunity_matrix_paths=(),
        eligible_policy_forward=False,
        funding_evidence_fn=None,
        portfolio_archive=None,
        accounting_epoch=_EPOCH,
        asymmetric_forward_journal_path=None,
    )

    assert forwarded == [None]
