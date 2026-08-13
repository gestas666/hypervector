"""Tests for the recoverable v39-to-growth accounting boundary."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

import pytest

from hypervector.live.cohort_accounting_rollover import (
    build_accounting_rollover_manifest,
    load_accounting_rollover_manifest,
    load_required_accounting_epoch,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)

_PRIOR_PATH = Path(
    "configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml"
)
_NEXT_PATH = Path("configs/multi_asset_growth_first_5000_repaired_candidate_v49.toml")
_SIX_ASSET_PATH = Path(
    "configs/multi_asset_growth_first_5000_six_asset_candidate_v50.toml"
)
_PROFIT_PROTECTED_PATH = Path(
    "configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml"
)
_NOW = datetime(2026, 8, 12, 23, 0, tzinfo=UTC)


def _configs() -> tuple[MultiAssetLiveConfig, MultiAssetLiveConfig]:
    return (
        load_multi_asset_live_config(_PRIOR_PATH, mode="observe"),
        load_multi_asset_live_config(_NEXT_PATH, mode="observe"),
    )


def _checkpoint(prior) -> dict[str, object]:
    assets = {
        symbol: {
            "final_state": "FLAT",
            "position_size_signed": 0.0,
            "open_order_ids": [],
        }
        for symbol in prior.symbols
    }
    return {
        "generated_at_utc": "2026-08-12T22:59:00+00:00",
        "audit": {
            "run": {
                "run_id": "bidirectional-live-prior",
                "profile_id": prior.profile_id,
                "profile_fingerprint": prior.profile_fingerprint,
            },
            "health": {"assets": assets},
            "open_trade_reflections": {"open_lifecycles": 0, "trades": []},
        },
    }


def _preflight(prior, successor) -> dict[str, object]:
    return {
        "observed_at_utc": "2026-08-12T22:59:30+00:00",
        "identity": {
            "active_profile_id": prior.profile_id,
            "active_profile_fingerprint": prior.profile_fingerprint,
            "candidate_profile_id": successor.profile_id,
            "candidate_profile_fingerprint": successor.profile_fingerprint,
        },
        "portfolio": {
            "flat_no_orders": True,
            "ledger_reconciled": True,
            "open_positions": 0,
            "open_orders": 0,
            "sizing_reference_equity_usd": 5_000.0,
            "technically_ready_for_profile_transition": True,
            "transition_blocking_assets": [],
        },
    }


def _backup(prior, successor) -> dict[str, object]:
    return {
        "schema_version": 1,
        "bundle_type": "cohort_prestart_backup",
        "target_identity": {
            "profile_id": successor.profile_id,
            "profile_fingerprint": successor.profile_fingerprint,
        },
        "previous_identity": {
            "profile_id": prior.profile_id,
            "profile_fingerprint": prior.profile_fingerprint,
            "run_id": "bidirectional-live-prior",
        },
    }


def test_rollover_manifest_binds_zero_state_equity_and_preserved_history() -> None:
    prior, successor = _configs()

    report = build_accounting_rollover_manifest(
        prior,
        successor,
        _checkpoint(prior),
        _preflight(prior, successor),
        _backup(prior, successor),
        epoch_id="growth_5000_v49",
        backup_bundle_evidence={"path": "backup", "sha256": "a" * 64, "bytes": 1},
        checkpoint_evidence={"path": "checkpoint", "sha256": "b" * 64, "bytes": 2},
        preflight_evidence={"path": "preflight", "sha256": "c" * 64, "bytes": 3},
        now=_NOW,
    )

    epoch = report["accounting_epoch"]
    assert epoch["epoch_id"] == "growth_5000_v49"
    assert epoch["profile_fingerprint"] == successor.profile_fingerprint
    assert epoch["start_venue_timestamp_ms"] == int(_NOW.timestamp() * 1_000)
    assert report["acceptance"] == {
        "all_time_closed_trades": 0,
        "current_run_closed_trades": 0,
        "open_lifecycles": 0,
        "venue_equity_usd": 5_000.0,
    }
    assert report["preserved_prior_history"]["prestart_backup"]["sha256"] == "a" * 64
    assert report["preserved_prior_history"]["final_preflight"]["sha256"] == "c" * 64
    assert report["execution_authority"] == "none"


def test_rollover_rejects_nonflat_checkpoint() -> None:
    prior, successor = _configs()
    checkpoint = _checkpoint(prior)
    checkpoint["audit"]["health"]["assets"]["ETH"]["final_state"] = "OPEN"

    with pytest.raises(ValueError, match="checkpoint is not flat"):
        build_accounting_rollover_manifest(
            prior,
            successor,
            checkpoint,
            _preflight(prior, successor),
            _backup(prior, successor),
            epoch_id="growth_5000_v49",
            backup_bundle_evidence={"path": "backup", "sha256": "a" * 64, "bytes": 1},
            checkpoint_evidence={"path": "checkpoint", "sha256": "b" * 64, "bytes": 2},
            preflight_evidence={"path": "preflight", "sha256": "c" * 64, "bytes": 3},
            now=_NOW,
        )


def test_rollover_rejects_open_or_unreconciled_preflight() -> None:
    prior, successor = _configs()
    preflight = _preflight(prior, successor)
    preflight["portfolio"]["open_orders"] = 1
    preflight["portfolio"]["flat_no_orders"] = False

    with pytest.raises(ValueError, match="preflight is not flat and order-free"):
        build_accounting_rollover_manifest(
            prior,
            successor,
            _checkpoint(prior),
            preflight,
            _backup(prior, successor),
            epoch_id="growth_5000_v49",
            backup_bundle_evidence={"path": "backup", "sha256": "a" * 64, "bytes": 1},
            checkpoint_evidence={"path": "checkpoint", "sha256": "b" * 64, "bytes": 2},
            preflight_evidence={"path": "preflight", "sha256": "c" * 64, "bytes": 3},
            now=_NOW,
        )


def test_rollover_rejects_wrong_preserved_profile_identity() -> None:
    prior, successor = _configs()
    backup = _backup(prior, successor)
    backup["previous_identity"]["profile_fingerprint"] = "c" * 64

    with pytest.raises(ValueError, match="backup previous identity"):
        build_accounting_rollover_manifest(
            prior,
            successor,
            _checkpoint(prior),
            _preflight(prior, successor),
            backup,
            epoch_id="growth_5000_v49",
            backup_bundle_evidence={"path": "backup", "sha256": "a" * 64, "bytes": 1},
            checkpoint_evidence={"path": "checkpoint", "sha256": "b" * 64, "bytes": 2},
            preflight_evidence={"path": "preflight", "sha256": "c" * 64, "bytes": 3},
            now=_NOW,
        )


def _published_rollover(tmp_path: Path) -> tuple[Path, MultiAssetLiveConfig]:
    prior, successor = _configs()
    bundle = tmp_path / "epoch"
    bundle.mkdir()
    checkpoint = b'{"checkpoint":true}\n'
    preflight = b'{"preflight":true}\n'
    backup = tmp_path / "backup_manifest.json"
    backup.write_bytes(b'{"backup":true}\n')
    (bundle / "final_checkpoint.json").write_bytes(checkpoint)
    (bundle / "final_preflight.json").write_bytes(preflight)
    report = build_accounting_rollover_manifest(
        prior,
        successor,
        _checkpoint(prior),
        _preflight(prior, successor),
        _backup(prior, successor),
        epoch_id="growth_5000_v49",
        backup_bundle_evidence=_raw_evidence(str(backup), backup.read_bytes()),
        checkpoint_evidence=_raw_evidence("final_checkpoint.json", checkpoint),
        preflight_evidence=_raw_evidence("final_preflight.json", preflight),
        now=_NOW,
    )
    (bundle / "manifest.json").write_text(
        json.dumps(report, sort_keys=True) + "\n", encoding="utf-8"
    )
    return bundle, successor


def _raw_evidence(path: str, raw: bytes) -> dict[str, object]:
    return {"path": path, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def test_rollover_loader_returns_exact_successor_accounting_epoch(
    tmp_path: Path,
) -> None:
    bundle, successor = _published_rollover(tmp_path)

    epoch = load_accounting_rollover_manifest(bundle, successor)

    assert epoch.epoch_id == "growth_5000_v49"
    assert epoch.profile_fingerprint == successor.profile_fingerprint
    assert epoch.start_venue_timestamp_ms == int(_NOW.timestamp() * 1_000)


def test_rollover_loader_rejects_changed_preserved_checkpoint(tmp_path: Path) -> None:
    bundle, successor = _published_rollover(tmp_path)
    (bundle / "final_checkpoint.json").write_text("changed\n", encoding="utf-8")

    with pytest.raises(ValueError, match="final checkpoint evidence differs"):
        load_accounting_rollover_manifest(bundle, successor)


def test_rollover_loader_rejects_a_different_successor(tmp_path: Path) -> None:
    bundle, _ = _published_rollover(tmp_path)
    prior, _ = _configs()

    with pytest.raises(ValueError, match="successor identity differs"):
        load_accounting_rollover_manifest(bundle, prior)


def test_v49_live_boundary_requires_the_clean_epoch_bundle() -> None:
    _, successor = _configs()

    with pytest.raises(ValueError, match="requires --accounting-epoch-bundle"):
        load_required_accounting_epoch(None, successor)


def test_v50_live_boundary_requires_its_own_clean_epoch_bundle() -> None:
    """The six-asset first-live profile cannot inherit v49 or legacy history."""
    successor = load_multi_asset_live_config(_SIX_ASSET_PATH, mode="observe")

    with pytest.raises(ValueError, match="requires --accounting-epoch-bundle"):
        load_required_accounting_epoch(None, successor)


def test_v51_live_boundary_requires_its_own_clean_epoch_bundle() -> None:
    """The profit-protected successor cannot inherit any prior reporting epoch."""
    successor = load_multi_asset_live_config(_PROFIT_PROTECTED_PATH, mode="observe")

    with pytest.raises(ValueError, match="requires --accounting-epoch-bundle"):
        load_required_accounting_epoch(None, successor)


def test_prior_profile_does_not_require_a_clean_epoch_bundle() -> None:
    prior, _ = _configs()

    assert load_required_accounting_epoch(None, prior) is None
