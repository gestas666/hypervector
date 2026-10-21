"""Tests for the recoverable accounting-epoch rollover boundary."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

import pytest

from hypervector.live import cohort_accounting_rollover
from hypervector.live.cohort_accounting_rollover import (
    build_accounting_rollover_manifest,
    load_accounting_rollover_manifest,
    load_required_accounting_epoch,
)
from hypervector.live.cohort_accounting_continuation import (
    build_accounting_continuation_manifest,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)

_PRIOR_PATH = Path(
    "tests/fixtures/profiles/ten_asset_base.toml"
)
_NEXT_PATH = Path("tests/fixtures/profiles/four_asset_mixed_sides.toml")
_PARENT_EPOCH_PATH = Path(
    "tests/fixtures/profiles/eight_asset_base.toml"
)
_CONTINUED_PATH = Path(
    "tests/fixtures/profiles/eight_asset_short_only_override.toml"
)
_NOW = datetime(2026, 8, 12, 23, 0, tzinfo=UTC)
_PARENT_EPOCH_START_MS = 1_787_164_729_837


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
        "assets": [
            {
                "symbol": symbol,
                "sizing": {"actual_account_value_usd": 4_875.84},
            }
            for symbol in successor.symbols
        ],
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
        epoch_id="fixture_epoch_2",
        backup_bundle_evidence={"path": "backup", "sha256": "a" * 64, "bytes": 1},
        checkpoint_evidence={"path": "checkpoint", "sha256": "b" * 64, "bytes": 2},
        preflight_evidence={"path": "preflight", "sha256": "c" * 64, "bytes": 3},
        now=_NOW,
    )

    epoch = report["accounting_epoch"]
    assert epoch["epoch_id"] == "fixture_epoch_2"
    assert epoch["profile_fingerprint"] == successor.profile_fingerprint
    assert epoch["start_venue_timestamp_ms"] == int(_NOW.timestamp() * 1_000)
    assert report["acceptance"] == {
        "all_time_closed_trades": 0,
        "current_run_closed_trades": 0,
        "open_lifecycles": 0,
        "venue_equity_usd": 4_875.84,
        "sizing_reference_equity_usd": 5_000.0,
    }
    assert report["preserved_prior_history"]["prestart_backup"]["sha256"] == "a" * 64
    assert report["preserved_prior_history"]["final_preflight"]["sha256"] == "c" * 64
    assert report["execution_authority"] == "none"


def test_rollover_rejects_inconsistent_observed_venue_equity() -> None:
    """Every asset preflight row must report one observed account value."""
    prior, successor = _configs()
    preflight = _preflight(prior, successor)
    preflight["assets"][0]["sizing"]["actual_account_value_usd"] = 4_800.0

    with pytest.raises(ValueError, match="observed venue equity differs"):
        build_accounting_rollover_manifest(
            prior,
            successor,
            _checkpoint(prior),
            preflight,
            _backup(prior, successor),
            epoch_id="fixture_epoch_2",
            backup_bundle_evidence={"path": "backup", "sha256": "a" * 64, "bytes": 1},
            checkpoint_evidence={"path": "checkpoint", "sha256": "b" * 64, "bytes": 2},
            preflight_evidence={"path": "preflight", "sha256": "c" * 64, "bytes": 3},
            now=_NOW,
        )


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
            epoch_id="fixture_epoch_2",
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
            epoch_id="fixture_epoch_2",
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
            epoch_id="fixture_epoch_2",
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
        epoch_id="fixture_epoch_2",
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


def _published_continuation(
    tmp_path: Path,
) -> tuple[Path, MultiAssetLiveConfig, MultiAssetLiveConfig]:
    prior = load_multi_asset_live_config(_PARENT_EPOCH_PATH, mode="observe")
    successor = load_multi_asset_live_config(_CONTINUED_PATH, mode="observe")
    bundle = tmp_path / "continuation"
    bundle.mkdir()
    checkpoint = _checkpoint(prior)
    parent_epoch = {
        "epoch_id": "eight_asset_incremental_parent",
        "profile_fingerprint": prior.profile_fingerprint,
        "start_venue_timestamp_ms": _PARENT_EPOCH_START_MS,
    }
    checkpoint["audit"]["portfolio_archive"] = {
        "accounting_epoch": parent_epoch,
        "performance": {"total": {"closed_trades": 8}},
    }
    final_checkpoint = json.dumps(checkpoint, sort_keys=True).encode()
    final_preflight = b'{"preflight":true}\n'
    backup = tmp_path / "backup_manifest.json"
    backup.write_bytes(b'{"backup":true}\n')
    (bundle / "final_checkpoint.json").write_bytes(final_checkpoint)
    (bundle / "final_preflight.json").write_bytes(final_preflight)
    base = build_accounting_rollover_manifest(
        prior,
        successor,
        checkpoint,
        _preflight(prior, successor),
        _backup(prior, successor),
        epoch_id="aaa_short_containment_continued",
        backup_bundle_evidence=_raw_evidence(str(backup), backup.read_bytes()),
        checkpoint_evidence=_raw_evidence("final_checkpoint.json", final_checkpoint),
        preflight_evidence=_raw_evidence("final_preflight.json", final_preflight),
        now=_NOW,
    )
    parent = {
        "schema_version": 1,
        "mode": "cohort_accounting_epoch_rollover_v1",
        "successor_identity": {
            "profile_id": prior.profile_id,
            "profile_fingerprint": prior.profile_fingerprint,
        },
        "accounting_epoch": parent_epoch,
    }
    parent_raw = (json.dumps(parent, sort_keys=True) + "\n").encode()
    (bundle / "parent_accounting_epoch_manifest.json").write_bytes(parent_raw)
    report = build_accounting_continuation_manifest(
        base,
        parent,
        checkpoint,
        parent_manifest_evidence=_raw_evidence(
            "parent_accounting_epoch_manifest.json", parent_raw
        ),
    )
    (bundle / "manifest.json").write_text(
        json.dumps(report, sort_keys=True) + "\n", encoding="utf-8"
    )
    return bundle, prior, successor


def test_rollover_loader_returns_exact_successor_accounting_epoch(
    tmp_path: Path,
) -> None:
    bundle, successor = _published_rollover(tmp_path)

    epoch = load_accounting_rollover_manifest(bundle, successor)

    assert epoch.epoch_id == "fixture_epoch_2"
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


def test_rollover_loader_rejects_invalid_sizing_reference(tmp_path: Path) -> None:
    """A published sizing scenario cannot masquerade as valid evidence."""
    bundle, successor = _published_rollover(tmp_path)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["acceptance"]["sizing_reference_equity_usd"] = 0.0
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="sizing reference equity must be positive"):
        load_accounting_rollover_manifest(bundle, successor)


def test_rollover_loader_returns_exact_continued_profile_lineage(
    tmp_path: Path,
) -> None:
    bundle, prior, successor = _published_continuation(tmp_path)

    epoch = load_accounting_rollover_manifest(bundle, successor)

    assert epoch.profile_fingerprint == successor.profile_fingerprint
    assert epoch.start_venue_timestamp_ms == _PARENT_EPOCH_START_MS
    assert epoch.included_profile_fingerprints == (
        prior.profile_fingerprint,
        successor.profile_fingerprint,
    )


def test_rollover_loader_rejects_changed_parent_epoch_evidence(tmp_path: Path) -> None:
    bundle, _, successor = _published_continuation(tmp_path)
    (bundle / "parent_accounting_epoch_manifest.json").write_text(
        "changed\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="parent accounting epoch evidence differs"):
        load_accounting_rollover_manifest(bundle, successor)


def test_declared_live_boundary_requires_the_clean_epoch_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A profile that declares the rollover cannot inherit prior counters."""
    _, successor = _configs()
    monkeypatch.setattr(
        cohort_accounting_rollover,
        "_CLEAN_ACCOUNTING_REQUIRED_PROFILE_FINGERPRINTS",
        frozenset({successor.profile_fingerprint}),
    )

    with pytest.raises(ValueError, match="requires --accounting-epoch-bundle"):
        load_required_accounting_epoch(None, successor)


def test_prior_profile_does_not_require_a_clean_epoch_bundle() -> None:
    prior, _ = _configs()

    assert load_required_accounting_epoch(None, prior) is None
