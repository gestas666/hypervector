"""Source-bound IO for the live V58 BRENTOIL lifecycle watcher."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module, util
import json
from pathlib import Path

import pytest

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from test_v58_brentoil_live_lifecycle import _checkpoint, _venue
from test_v58_live_close_ledger import _ledger_rows


def test_bootstrap_freezes_exact_open_sources_and_builds_open_report(
    tmp_path: Path,
) -> None:
    """Bootstrap must freeze current source bytes only after open validation."""
    module_name = "hypervector.research.v58_brentoil_live_lifecycle_io"
    assert util.find_spec(module_name) is not None, "BRENTOIL lifecycle IO is missing"
    module = import_module(module_name)
    paths = _paths(tmp_path)

    preregistration = module.bootstrap_v58_brentoil_preregistration(
        _checkpoint(),
        _venue(),
        ledger_path=paths["ledger"],
        config_path=paths["config"],
        prestart_manifest_path=paths["manifest"],
        generated_at=datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
    )

    identity = preregistration["frozen_identity"]
    assert identity["lifecycle_id"] == "xyz:BRENTOIL:520642502465"
    assert identity["asset_profile_fingerprint"] == "c" * 64
    assert preregistration["ledger_prefix"]["rows"] == 2
    assert preregistration["sources"]["config"] == {
        "path": str(paths["config"].resolve()),
        **file_evidence(paths["config"]),
    }
    assert preregistration["contract"]["execution_authority"] == "none"


def test_loader_verifies_frozen_prefix_and_attaches_current_sources(
    tmp_path: Path,
) -> None:
    """Each cycle must authenticate the frozen prefix and current complete bytes."""
    module = import_module("hypervector.research.v58_brentoil_live_lifecycle_io")
    paths = _paths(tmp_path)
    preregistration = module.bootstrap_v58_brentoil_preregistration(
        _checkpoint(),
        _venue(),
        ledger_path=paths["ledger"],
        config_path=paths["config"],
        prestart_manifest_path=paths["manifest"],
        generated_at=datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
    )
    write_immutable_json(paths["preregistration"], preregistration)
    paths["checkpoint"].write_text(json.dumps(_checkpoint()), encoding="utf-8")
    paths["venue"].write_text(json.dumps(_venue()), encoding="utf-8")

    report = module.load_v58_brentoil_lifecycle_cycle(
        paths["preregistration"],
        expected_preregistration_sha256=file_evidence(paths["preregistration"])[
            "sha256"
        ],
        checkpoint_path=paths["checkpoint"],
        venue_path=paths["venue"],
        ledger_path=paths["ledger"],
        generated_at=datetime(2026, 8, 20, 10, 1, tzinfo=UTC),
    )

    assert report["state"] == "open_protected"
    assert report["source_evidence"]["asset_ledger"]["frozen_prefix_verified"] is True
    assert report["source_evidence"]["checkpoint"]["path"] == str(
        paths["checkpoint"].resolve()
    )


def test_loader_rejects_changed_frozen_entry_prefix(tmp_path: Path) -> None:
    """Mutation of entry-era bytes must fail even if later JSONL remains valid."""
    module = import_module("hypervector.research.v58_brentoil_live_lifecycle_io")
    paths = _paths(tmp_path)
    preregistration = module.bootstrap_v58_brentoil_preregistration(
        _checkpoint(),
        _venue(),
        ledger_path=paths["ledger"],
        config_path=paths["config"],
        prestart_manifest_path=paths["manifest"],
        generated_at=datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
    )
    write_immutable_json(paths["preregistration"], preregistration)
    paths["checkpoint"].write_text(json.dumps(_checkpoint()), encoding="utf-8")
    paths["venue"].write_text(json.dumps(_venue()), encoding="utf-8")
    raw = paths["ledger"].read_bytes()
    paths["ledger"].write_bytes(b"X" + raw[1:])

    with pytest.raises(ValueError, match="authenticated prefix"):
        module.load_v58_brentoil_lifecycle_cycle(
            paths["preregistration"],
            expected_preregistration_sha256=file_evidence(paths["preregistration"])[
                "sha256"
            ],
            checkpoint_path=paths["checkpoint"],
            venue_path=paths["venue"],
            ledger_path=paths["ledger"],
            generated_at=datetime(2026, 8, 20, 10, 1, tzinfo=UTC),
        )


def test_bootstrap_preserves_entry_provenance_after_runtime_adoption(
    tmp_path: Path,
) -> None:
    """A restarted runtime must not relabel the inherited entry as its own."""
    module = import_module("hypervector.research.v58_brentoil_live_lifecycle_io")
    paths = _paths(tmp_path)
    checkpoint = _checkpoint()
    successor_run = "bidirectional-live-1787272893887"
    successor_asset = (
        "multi_asset_growth_first_5000_eight_asset_incremental_v58_"
        "xyz:brentoil_successor"
    )
    successor_fingerprint = "d" * 64
    checkpoint["audit"]["run"]["run_id"] = successor_run
    rows = _ledger_rows()[:2]
    rows.append(
        {
            "sequence": 3,
            "event_type": "heartbeat",
            "observed_at_utc": "2026-08-21T00:46:33+00:00",
            "profile_id": successor_asset,
            "profile_fingerprint": successor_fingerprint,
            "run_id": successor_run,
            "payload": {},
        }
    )
    paths["ledger"].write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )

    preregistration = module.bootstrap_v58_brentoil_preregistration(
        checkpoint,
        _venue(),
        ledger_path=paths["ledger"],
        config_path=paths["config"],
        prestart_manifest_path=paths["manifest"],
        generated_at=datetime(2026, 8, 21, 1, 0, tzinfo=UTC),
    )

    identity = preregistration["frozen_identity"]
    assert identity["run_id"] == successor_run
    assert identity["source_run_id"] == "bidirectional-live-1787166474078"
    assert identity["asset_profile_fingerprint"] == "c" * 64
    assert identity["runtime_asset_profile_id"] == successor_asset
    assert identity["runtime_asset_profile_fingerprint"] == successor_fingerprint


def _paths(tmp_path: Path) -> dict[str, Path]:
    """Create exact compact source files for one lifecycle cycle."""
    paths = {
        name: tmp_path / filename
        for name, filename in {
            "ledger": "xyz:brentoil.jsonl",
            "config": "v58.toml",
            "manifest": "manifest.json",
            "preregistration": "preregistration.json",
            "checkpoint": "checkpoint.json",
            "venue": "venue.json",
        }.items()
    }
    paths["ledger"].write_text(
        "".join(json.dumps(row) + "\n" for row in _ledger_rows()[:2]),
        encoding="utf-8",
    )
    paths["config"].write_text("profile_id = 'v58'\n", encoding="utf-8")
    paths["manifest"].write_text('{"status":"verified"}\n', encoding="utf-8")
    return paths
