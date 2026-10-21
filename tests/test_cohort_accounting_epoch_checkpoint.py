"""Fail-closed checkpoint cache tests for a clean cohort accounting epoch."""

from __future__ import annotations

import json
from pathlib import Path

from hypervector.research.cohort_live_portfolio_archive import (
    PORTFOLIO_ARCHIVE_PROJECTION_REVISION,
    CohortAccountingEpoch,
)
from hypervector.research.cohort_checkpoint_accounting import (
    accounting_epoch_worker_args,
)
from hypervector.research.cohort_rolling_checkpoint import (
    load_cached_portfolio_archive,
    publish_rolling_checkpoint,
)

_EPOCH = CohortAccountingEpoch("growth_5000_a", "a" * 64, 1_786_579_200_000)
_LINEAGE_EPOCH = CohortAccountingEpoch(
    "growth_5000_a_b",
    "b" * 64,
    1_786_164_729_837,
    included_profile_fingerprints=("a" * 64, "b" * 64),
)


def _checkpoint(path: Path, epoch: dict[str, object] | None) -> None:
    archive: dict[str, object] = {
        "schema_version": 1,
        "mode": "cohort_live_portfolio_archive_v1",
        "projection_revision": PORTFOLIO_ARCHIVE_PROJECTION_REVISION,
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


def test_epoch_cache_rejects_an_archive_without_preserved_history_revision(
    tmp_path: Path,
) -> None:
    checkpoint = tmp_path / "latest.json"
    _checkpoint(checkpoint, _EPOCH.to_dict())
    document = json.loads(checkpoint.read_text(encoding="utf-8"))
    document["audit"]["portfolio_archive"]["projection_revision"] = 2
    checkpoint.write_text(json.dumps(document), encoding="utf-8")

    assert load_cached_portfolio_archive(checkpoint, accounting_epoch=_EPOCH) is None


def test_accounting_epoch_worker_args_preserve_profile_lineage() -> None:
    """The isolated worker must receive every exact campaign fingerprint."""
    assert accounting_epoch_worker_args(_LINEAGE_EPOCH) == [
        "--accounting-epoch-id",
        "growth_5000_a_b",
        "--accounting-epoch-profile-fingerprint",
        "b" * 64,
        "--accounting-epoch-start-ms",
        "1786164729837",
        "--accounting-epoch-included-profile-fingerprint",
        "a" * 64,
        "--accounting-epoch-included-profile-fingerprint",
        "b" * 64,
    ]


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
        requested_run_id="run-a",
        config_path=Path("profile_a.toml"),
        once=True,
        venue_portfolio=None,
        portfolio_archive=None,
        accounting_epoch=_EPOCH,
    )

    assert forwarded == [None]
