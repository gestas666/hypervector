"""Integrity tests for frozen cross-asset impulse evidence."""

from __future__ import annotations

from dataclasses import fields
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.research.cross_asset_impulse_artifact_validation import (
    validate_cross_asset_impulse_artifact,
)
from hypervector.research.cross_asset_impulse_models import (
    CrossAssetImpulseConfig,
    CrossAssetImpulseLabel,
)
from hypervector.research.cross_asset_impulse_screen import summarize_impulse_labels


def _evidence(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def _write_fixture(root: Path) -> tuple[Path, Path, dict[str, object]]:
    prior_path = root / "residual-v2.json"
    prior_path.write_text(
        json.dumps(
            {
                "schema_version": "cross_asset_residual_exit_surface_v2",
                "trial_count": 90,
                "report_only": True,
                "execution_authority": "none",
            }
        ),
        encoding="utf-8",
    )
    prior = {
        "artifact": str(prior_path),
        "sha256": _evidence(prior_path)["sha256"],
        "bytes": _evidence(prior_path)["bytes"],
        "selectable_cells": 90,
        "schema_version": "cross_asset_residual_exit_surface_v2",
        "trial_count": 90,
    }
    source_identity: dict[str, dict[str, object]] = {}
    for symbol in ("BTC", "ETH", "SOL", "HYPE"):
        bars = root / f"{symbol}.parquet"
        bars.write_bytes(symbol.encode())
        source_identity[symbol] = {
            "bars_path": str(bars),
            "bars": _evidence(bars),
            "selected_rows": 1,
            "selected_frame_sha256": symbol.lower(),
            "native_rows": 1,
            "gap_fill_rows": 0,
        }
    config = CrossAssetImpulseConfig()
    artifact = summarize_impulse_labels(
        labels=(),
        config=config,
        run_id="fixture",
        source_identity=source_identity,
        prior_search_identity=prior,
    )
    rows = pd.DataFrame(
        columns=[field.name for field in fields(CrossAssetImpulseLabel)]
    )
    sidecar = root / "events.parquet"
    rows.to_parquet(sidecar, index=False)
    generator = root / "generator.py"
    generator.write_text("VALUE = 1\n", encoding="utf-8")
    artifact.update(
        event_storage={"path": str(sidecar), **_evidence(sidecar), "rows": 0},
        generator_identity={
            "generator_modules": {str(generator): _evidence(generator)}
        },
        prior_cross_asset_search=prior,
        contract_identity={
            "warmup_start_utc": config.warmup_start.isoformat(),
            "development_start_utc": config.development_start.isoformat(),
            "development_end_utc": config.development_end.isoformat(),
            "report_only": True,
            "execution_authority": "none",
        },
    )
    artifact_path = root / "impulse.json"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    return artifact_path, sidecar, artifact


def _rewrite(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_validates_complete_report_only_artifact(tmp_path: Path) -> None:
    artifact, _, _ = _write_fixture(tmp_path)

    result = validate_cross_asset_impulse_artifact(artifact)

    assert result.valid is True
    assert result.primary_cells_verified == 15
    assert result.control_cells_verified == 45
    assert result.event_rows_verified == 0
    assert result.source_files_verified == 4
    assert result.generator_modules_verified == 1
    assert result.execution_authority == "none"


def test_accepts_canonical_json_symbol_key_order(tmp_path: Path) -> None:
    artifact, _, payload = _write_fixture(tmp_path)
    artifact.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    result = validate_cross_asset_impulse_artifact(artifact)

    assert result.source_files_verified == 4


def test_rejects_sidecar_hash_or_missing_authority_columns(tmp_path: Path) -> None:
    artifact, sidecar, payload = _write_fixture(tmp_path)
    pd.DataFrame({"signal_variant": ["primary"]}).to_parquet(sidecar, index=False)

    with pytest.raises(ValueError, match="sidecar evidence differs"):
        validate_cross_asset_impulse_artifact(artifact)

    payload["event_storage"].update(_evidence(sidecar))
    payload["event_storage"]["rows"] = 1
    _rewrite(artifact, payload)
    with pytest.raises(ValueError, match="missing columns"):
        validate_cross_asset_impulse_artifact(artifact)


@pytest.mark.parametrize("location", ("top", "cell"))
def test_rejects_execution_authority_inheritance(tmp_path: Path, location: str) -> None:
    artifact, _, payload = _write_fixture(tmp_path)
    if location == "top":
        payload["execution_authority"] = "orders"
    else:
        payload["primary_cells"][0]["execution_authority"] = "orders"
    _rewrite(artifact, payload)

    with pytest.raises(ValueError, match="execution authority"):
        validate_cross_asset_impulse_artifact(artifact)


@pytest.mark.parametrize("change", ("duplicate", "control_selectable"))
def test_rejects_cell_identity_or_role_mismatch(tmp_path: Path, change: str) -> None:
    artifact, _, payload = _write_fixture(tmp_path)
    if change == "duplicate":
        payload["primary_cells"][1] = payload["primary_cells"][0]
    else:
        payload["control_cells"][0]["selectable"] = True
    _rewrite(artifact, payload)

    with pytest.raises(ValueError, match="cell"):
        validate_cross_asset_impulse_artifact(artifact)


def test_rejects_selected_candidate_inconsistency(tmp_path: Path) -> None:
    artifact, _, payload = _write_fixture(tmp_path)
    payload["selected_candidate"] = {
        "leader_symbol": "BTC",
        "follower_symbol": "ETH",
        "horizon_minutes": 5,
    }
    _rewrite(artifact, payload)

    with pytest.raises(ValueError, match="selected candidate"):
        validate_cross_asset_impulse_artifact(artifact)


@pytest.mark.parametrize("location", ("config", "fold"))
def test_rejects_changed_frozen_contract(tmp_path: Path, location: str) -> None:
    artifact, _, payload = _write_fixture(tmp_path)
    if location == "config":
        payload["config"]["leader_z_threshold"] = 2.4
    else:
        payload["folds"][0]["end_utc"] = "2025-09-29T00:00:00+00:00"
    _rewrite(artifact, payload)

    with pytest.raises(ValueError, match="frozen contract"):
        validate_cross_asset_impulse_artifact(artifact)


@pytest.mark.parametrize("identity", ("source", "generator", "prior"))
def test_rejects_changed_bound_evidence(tmp_path: Path, identity: str) -> None:
    artifact, _, payload = _write_fixture(tmp_path)
    if identity == "source":
        Path(payload["source_identity"]["BTC"]["bars_path"]).write_text("changed")
        message = "source file evidence differs"
    elif identity == "generator":
        path = next(iter(payload["generator_identity"]["generator_modules"]))
        Path(path).write_text("changed")
        message = "generator module evidence differs"
    else:
        Path(payload["prior_cross_asset_search"]["artifact"]).write_text("changed")
        message = "prior residual evidence differs"

    with pytest.raises(ValueError, match=message):
        validate_cross_asset_impulse_artifact(artifact)


def test_validates_and_rejects_bound_warmup_components(tmp_path: Path) -> None:
    artifact, _, payload = _write_fixture(tmp_path)
    warmup = tmp_path / "BTC-warmup.parquet"
    warmup.write_bytes(b"warmup")
    payload["source_identity"]["BTC"]["warmup_source_files"] = [
        {"path": str(warmup), **_evidence(warmup)}
    ]
    _rewrite(artifact, payload)

    result = validate_cross_asset_impulse_artifact(artifact)
    assert result.source_files_verified == 5

    warmup.write_bytes(b"changed")
    with pytest.raises(ValueError, match="source file evidence differs"):
        validate_cross_asset_impulse_artifact(artifact)


def test_treats_historical_validator_hash_as_declared_snapshot(tmp_path: Path) -> None:
    artifact, _, payload = _write_fixture(tmp_path)
    validator = Path(
        "src/hypervector/research/cross_asset_impulse_artifact_validation.py"
    )
    payload["generator_identity"]["generator_modules"][str(validator)] = {
        "bytes": 1,
        "sha256": "0" * 64,
    }
    _rewrite(artifact, payload)

    result = validate_cross_asset_impulse_artifact(artifact)

    assert result.generator_modules_verified == 2


def test_rejects_fold_aggregate_not_supported_by_rows(tmp_path: Path) -> None:
    artifact, _, payload = _write_fixture(tmp_path)
    payload["primary_cells"][0]["folds"][0]["base"]["resolved_events"] = 1
    _rewrite(artifact, payload)

    with pytest.raises(ValueError, match="fold resolved_events differs"):
        validate_cross_asset_impulse_artifact(artifact)


def test_enforces_explicit_cell_and_event_bounds(tmp_path: Path) -> None:
    artifact, _, _ = _write_fixture(tmp_path)

    with pytest.raises(ValueError, match="cell bound exceeded"):
        validate_cross_asset_impulse_artifact(artifact, max_cells=50)
    with pytest.raises(ValueError, match="event row bound exceeded"):
        validate_cross_asset_impulse_artifact(artifact, max_event_rows=-1)
