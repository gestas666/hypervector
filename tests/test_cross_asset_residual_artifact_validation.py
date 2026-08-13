"""Integrity tests for frozen cross-asset residual evidence artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.research.cross_asset_residual_artifact_validation import (
    validate_cross_asset_residual_artifact,
)


def _evidence(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def _write_source_identity(root: Path) -> dict[str, dict[str, object]]:
    identity: dict[str, dict[str, object]] = {}
    for symbol in ("BTC", "ETH", "SOL", "HYPE"):
        bars = root / f"{symbol}_bars.parquet"
        funding = root / f"{symbol}_funding.parquet"
        bars.write_bytes(f"{symbol}-bars".encode())
        funding.write_bytes(f"{symbol}-funding".encode())
        identity[symbol] = {
            "bars_path": str(bars),
            "bars": _evidence(bars),
            "funding_path": str(funding),
            "funding": _evidence(funding),
        }
    return identity


def _trade_rows(*, surface: bool) -> pd.DataFrame:
    rows: list[dict[str, object]] = [
        {
            "left_symbol": "BTC",
            "right_symbol": "ETH",
            "signal_time_utc": "2026-01-01T00:00:00+00:00",
            "entry_time_utc": "2026-01-01T00:05:00+00:00",
            "exit_time_utc": "2026-01-01T00:10:00+00:00",
            "gross_pnl_usd": 8.0,
            "fees_usd": 1.0,
            "funding_cashflow_usd": 0.0,
            "liquidation_penalty_usd": 0.0,
            "net_pnl_usd": 7.0,
            "equity_before_usd": 1000.0,
            "equity_after_usd": 1007.0,
            "exit_reason": "mean_reversion",
        },
        {
            "left_symbol": "BTC",
            "right_symbol": "ETH",
            "signal_time_utc": "2026-01-01T01:00:00+00:00",
            "entry_time_utc": "2026-01-01T01:05:00+00:00",
            "exit_time_utc": "2026-01-01T01:10:00+00:00",
            "gross_pnl_usd": -2.0,
            "fees_usd": 0.5,
            "funding_cashflow_usd": 0.5,
            "liquidation_penalty_usd": 0.0,
            "net_pnl_usd": -2.0,
            "equity_before_usd": 1007.0,
            "equity_after_usd": 1005.0,
            "exit_reason": "liquidation",
        },
    ]
    if surface:
        for row in rows:
            row["trial_id"] = "stop4_hold36"
    return pd.DataFrame(rows)


def _cell(*, surface: bool) -> dict[str, object]:
    cell: dict[str, object] = {
        "left_symbol": "BTC",
        "right_symbol": "ETH",
        "completed_trades": 2,
        "wins": 1,
        "losses": 1,
        "initial_equity": 1000.0,
        "final_equity": 1005.0,
        "gross_pnl_usd": 6.0,
        "fees_usd": 1.5,
        "funding_cashflow_usd": 0.5,
        "liquidation_penalties_usd": 0.0,
        "net_pnl_usd": 5.0,
        "profit_factor": 3.5,
        "liquidations": 1,
        "execution_authority": "none",
    }
    if surface:
        cell["trial_id"] = "stop4_hold36"
    return cell


def _write_artifact(root: Path, *, surface: bool = False) -> tuple[Path, Path]:
    trades_path = root / "trades.parquet"
    _trade_rows(surface=surface).to_parquet(trades_path, index=False)
    generator = root / "embedded_generator.py"
    generator.write_text("VALUE = 1\n", encoding="utf-8")
    artifact: dict[str, object] = {
        "schema_version": (
            "cross_asset_residual_exit_surface_v2"
            if surface
            else "cross_asset_residual_development_v2"
        ),
        "run_id": "fixture",
        "report_only": True,
        "execution_authority": "none",
        "generator_identity": {
            "generator_modules": {str(generator): _evidence(generator)}
        },
        "trial_count": 1,
        "source_identity": _write_source_identity(root),
        "cells": [_cell(surface=surface)],
        "trade_storage": {
            "path": str(trades_path),
            **_evidence(trades_path),
            "rows": 2,
        },
    }
    contract_key = "signal_contract" if surface else "config"
    artifact[contract_key] = {"execution_authority": "none"}
    artifact_path = root / "artifact.json"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    return artifact_path, trades_path


def _write_generator_manifest(root: Path) -> tuple[Path, Path]:
    module = root / "generator.py"
    module.write_text("VALUE = 1\n", encoding="utf-8")
    manifest = root / "generator_manifest.json"
    manifest.write_text(
        json.dumps({"generator_modules": {str(module): _evidence(module)}}),
        encoding="utf-8",
    )
    return manifest, module


def test_validates_sidecar_cells_sources_and_authority(tmp_path: Path) -> None:
    artifact, _ = _write_artifact(tmp_path)

    result = validate_cross_asset_residual_artifact(artifact)

    assert result.valid is True
    assert result.cells_verified == 1
    assert result.trades_verified == 2
    assert result.source_files_verified == 8
    assert result.generator_modules_verified == 1
    assert result.execution_authority == "none"


def test_validates_surface_identity_and_generator_manifest(tmp_path: Path) -> None:
    artifact, _ = _write_artifact(tmp_path, surface=True)
    manifest, _ = _write_generator_manifest(tmp_path)

    result = validate_cross_asset_residual_artifact(
        artifact,
        generator_manifest_path=manifest,
    )

    assert result.cells_verified == 1
    assert result.trades_verified == 2
    assert result.generator_modules_verified == 2


def test_v2_requires_and_validates_embedded_generator_identity(tmp_path: Path) -> None:
    artifact, _ = _write_artifact(tmp_path)
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    payload.pop("generator_identity")
    artifact.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="generator identity"):
        validate_cross_asset_residual_artifact(artifact)

    module = tmp_path / "generator.py"
    module.write_text("VALUE = 1\n", encoding="utf-8")
    payload["generator_identity"] = {
        "generator_modules": {str(module): _evidence(module)}
    }
    artifact.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_cross_asset_residual_artifact(artifact)

    assert result.generator_modules_verified == 1


def test_rejects_sidecar_hash_or_row_count_mismatch(tmp_path: Path) -> None:
    artifact, trades = _write_artifact(tmp_path)
    frame = pd.read_parquet(trades)
    pd.concat([frame, frame.iloc[[0]]], ignore_index=True).to_parquet(
        trades,
        index=False,
    )

    with pytest.raises(ValueError, match="trade sidecar evidence differs"):
        validate_cross_asset_residual_artifact(artifact)


@pytest.mark.parametrize(
    ("field", "value"),
    (("fees_usd", 99.0), ("completed_trades", 3), ("profit_factor", 2.0)),
)
def test_rejects_cell_trade_aggregate_mismatch(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    artifact, _ = _write_artifact(tmp_path)
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    payload["cells"][0][field] = value
    artifact.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=f"cell {field} differs"):
        validate_cross_asset_residual_artifact(artifact)


def test_rejects_undeclared_trade_cell_identity(tmp_path: Path) -> None:
    artifact, trades = _write_artifact(tmp_path)
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    frame = pd.read_parquet(trades)
    frame.loc[:, "right_symbol"] = "SOL"
    frame.to_parquet(trades, index=False)
    payload["trade_storage"].update(_evidence(trades))
    artifact.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="undeclared cell identity"):
        validate_cross_asset_residual_artifact(artifact)


def test_rejects_changed_source_or_generator_module(tmp_path: Path) -> None:
    artifact, _ = _write_artifact(tmp_path)
    manifest, module = _write_generator_manifest(tmp_path)
    module.write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(ValueError, match="generator module evidence differs"):
        validate_cross_asset_residual_artifact(
            artifact,
            generator_manifest_path=manifest,
        )

    source = tmp_path / "BTC_bars.parquet"
    source.write_bytes(b"changed")
    with pytest.raises(ValueError, match="source file evidence differs"):
        validate_cross_asset_residual_artifact(artifact)


@pytest.mark.parametrize(
    ("location", "value"),
    (("top", "live"), ("contract", "live"), ("cell", "live")),
)
def test_rejects_authority_inheritance_violation(
    tmp_path: Path,
    location: str,
    value: str,
) -> None:
    artifact, _ = _write_artifact(tmp_path)
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    if location == "top":
        payload["execution_authority"] = value
    elif location == "contract":
        payload["config"]["execution_authority"] = value
    else:
        payload["cells"][0]["execution_authority"] = value
    artifact.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="execution authority"):
        validate_cross_asset_residual_artifact(artifact)


def test_enforces_explicit_cell_and_trade_bounds(tmp_path: Path) -> None:
    artifact, _ = _write_artifact(tmp_path)

    with pytest.raises(ValueError, match="cell bound exceeded"):
        validate_cross_asset_residual_artifact(artifact, max_cells=0)
    with pytest.raises(ValueError, match="trade row bound exceeded"):
        validate_cross_asset_residual_artifact(artifact, max_trade_rows=1)
