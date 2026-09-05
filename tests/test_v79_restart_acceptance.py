"""V79 restart-spanning fill and lifecycle acceptance contracts."""

from __future__ import annotations

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.research.v79_poststart_acceptance import (
    build_v79_poststart_acceptance,
)
from test_v79_poststart_acceptance import (
    _CONFIG,
    _NOW,
    _checkpoint,
    _epoch,
)


def test_v79_accepts_complete_compatible_history_after_restart() -> None:
    """A process restart must retain exact prior V79 lifecycle monitoring."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    checkpoint = _checkpoint(config)
    audit = checkpoint["audit"]
    run = audit["run"]
    execution = audit["execution"]
    prior_run = "bidirectional-live-v79-prior"
    run["run_id"] = "bidirectional-live-v79-restart"
    execution["history_run_ids"] = [prior_run, run["run_id"]]
    execution["current_run_fills"] = 1
    for fill in execution["fill_details"]:
        fill["origin_run_id"] = (
            prior_run if fill["operation"] == "entry" else run["run_id"]
        )
    audit["trade_reflections"]["trades"][0]["source_run_id"] = prior_run

    report = _report(checkpoint)

    assert report["accepted"] is True
    assert report["reasons"] == []


def test_v79_rejects_fill_origin_outside_compatible_history() -> None:
    """A stale fill from another execution history cannot pass attribution."""
    checkpoint = _checkpoint(_config())
    checkpoint["audit"]["execution"]["fill_details"][0]["origin_run_id"] = (
        "unrelated-run"
    )

    report = _report(checkpoint)

    assert report["accepted"] is False
    assert "execution_fill_run_provenance_mismatch" in report["reasons"]


def test_v79_rejects_incorrect_current_run_fill_count() -> None:
    """The current-process counter must reconcile to exact fill provenance."""
    checkpoint = _checkpoint(_config())
    checkpoint["audit"]["execution"]["current_run_fills"] = 1

    report = _report(checkpoint)

    assert report["accepted"] is False
    assert "execution_fill_run_provenance_mismatch" in report["reasons"]


def test_v79_rejects_missing_fill_history_provenance() -> None:
    """Missing history identity must produce a visible rejection, not abort."""
    checkpoint = _checkpoint(_config())
    checkpoint["audit"]["execution"].pop("history_run_ids")

    report = _report(checkpoint)

    assert report["accepted"] is False
    assert "execution_fill_run_provenance_mismatch" in report["reasons"]


def _config() -> MultiAssetLiveConfig:
    return load_multi_asset_live_config(_CONFIG, mode="observe")


def _report(checkpoint: dict[str, object]) -> dict[str, object]:
    return build_v79_poststart_acceptance(
        checkpoint,
        _config(),
        _epoch(),
        now_utc=_NOW,
    )
