#!/usr/bin/env python3
"""Independently validate one Swing/HA experiment artifact and trade sidecar."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence

_SCHEMA = "swing_ha_order_block_15m_v1"
_SCENARIOS = {
    "validation:nominal",
    "validation:cost_stress_20bps",
    "validation:entry_delay_1bar",
    "pseudo_holdout:nominal",
    "pseudo_holdout:cost_stress_20bps",
    "pseudo_holdout:entry_delay_1bar",
}


def build_parser() -> argparse.ArgumentParser:
    """Return the explicit artifact-validation parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--trades", type=Path, required=True)
    return parser


def validate_artifact(artifact_path: Path, trades_path: Path) -> dict[str, object]:
    """Validate authority, provenance, completeness, and trade arithmetic."""
    report = _load_report(artifact_path)
    _validate_contract(report)
    _validate_files(report, trades_path)
    _validate_trials(report)
    _validate_scenarios(report)
    trades = pd.read_parquet(trades_path)
    _validate_trades(report, trades)
    return {
        "valid": True,
        "schema_version": report["schema_version"],
        "base_trials": report["base_trial_count"],
        "order_block_trials": report["order_block_trial_count"],
        "scenario_count": len(report["out_of_sample_scenarios"]),
        "trade_rows": len(trades),
        "execution_authority": "none",
    }


def _load_report(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"Swing/HA artifact does not exist: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Swing/HA artifact root must be an object")
    return value


def _validate_contract(report: dict[str, object]) -> None:
    if report.get("schema_version") != _SCHEMA:
        raise ValueError("Swing/HA artifact schema is unsupported")
    if report.get("report_only") is not True:
        raise ValueError("Swing/HA artifact must be report-only")
    if report.get("execution_authority") != "none":
        raise ValueError("Swing/HA artifact has execution authority")
    if report.get("model_authority") != "none":
        raise ValueError("Swing/HA artifact has model authority")
    if report.get("place_attempted") is not False:
        raise ValueError("Swing/HA artifact attempted placement")
    if report.get("promotion") is not None:
        raise ValueError("Swing/HA artifact must not self-promote")


def _validate_files(report: dict[str, object], trades_path: Path) -> None:
    sidecar = _mapping(report.get("trade_sidecar"), "trade_sidecar")
    evidence = file_evidence(trades_path)
    if sidecar.get("sha256") != evidence["sha256"]:
        raise ValueError("Swing/HA trade sidecar checksum mismatch")
    if sidecar.get("bytes") != evidence["bytes"]:
        raise ValueError("Swing/HA trade sidecar byte count mismatch")
    for identity in _list(report.get("source_identity"), "source_identity"):
        source = _mapping(identity, "source identity")
        _validate_file_hash(source, "bars_path", "bars_sha256")
        _validate_file_hash(source, "funding_path", "funding_sha256")
    generators = _mapping(report.get("generator_identity"), "generator_identity")
    root = Path(__file__).resolve().parents[1]
    for relative, expected in generators.items():
        path = root / str(relative)
        if _file_sha256(path) != expected:
            raise ValueError(f"Swing/HA generator checksum mismatch: {relative}")


def _validate_trials(report: dict[str, object]) -> None:
    base = _list(report.get("base_trials"), "base_trials")
    blocks = _list(report.get("order_block_trials"), "order_block_trials")
    if report.get("base_trial_count") != 72 or len(base) != 72:
        raise ValueError("Swing/HA base trial retention is incomplete")
    if report.get("order_block_trial_count") != 13 or len(blocks) != 13:
        raise ValueError("Swing/HA order-block trial retention is incomplete")
    _validate_cell_shapes(base)
    _validate_cell_shapes(blocks)
    base_config = report.get("selected_base_config")
    final_config = report.get("selected_frozen_config")
    if not any(trial.get("config") == base_config for trial in base):
        raise ValueError("selected Swing/HA base config is absent from trials")
    if not any(trial.get("config") == final_config for trial in blocks):
        raise ValueError("selected Swing/HA final config is absent from trials")


def _validate_cell_shapes(trials: list[object]) -> None:
    for raw in trials:
        trial = _mapping(raw, "trial")
        if len(_list(trial.get("asset_cells"), "asset_cells")) != 4:
            raise ValueError("Swing/HA trial must retain four asset cells")
        if len(_list(trial.get("fold_cells"), "fold_cells")) != 12:
            raise ValueError("Swing/HA trial must retain twelve fold cells")
        if trial.get("execution_authority") != "none":
            raise ValueError("Swing/HA trial has execution authority")


def _validate_scenarios(report: dict[str, object]) -> None:
    scenarios = _mapping(
        report.get("out_of_sample_scenarios"), "out_of_sample_scenarios"
    )
    if set(scenarios) != _SCENARIOS:
        raise ValueError("Swing/HA scenario set is incomplete")
    for raw in scenarios.values():
        scenario = _mapping(raw, "scenario")
        cells = _list(scenario.get("asset_cells"), "scenario asset_cells")
        if len(cells) != 4:
            raise ValueError("Swing/HA scenario must retain four assets")
        total = sum(float(_mapping(cell, "cell")["net_pnl_usd"]) for cell in cells)
        observed = float(scenario["total_net_pnl_usd_independent_accounts"])
        if not math.isclose(total, observed, abs_tol=1e-8):
            raise ValueError("Swing/HA scenario aggregate PnL mismatch")


def _validate_trades(report: dict[str, object], trades: pd.DataFrame) -> None:
    required = {
        "symbol",
        "segment",
        "scenario",
        "signal_time_utc",
        "entry_time_utc",
        "exit_time_utc",
        "gross_pnl_usd",
        "fees_usd",
        "funding_cashflow_usd",
        "net_pnl_usd",
        "equity_before_usd",
        "equity_after_usd",
        "execution_authority",
    }
    missing = sorted(required.difference(trades.columns))
    if missing:
        raise ValueError(f"Swing/HA trade sidecar missing columns: {missing}")
    sidecar = _mapping(report.get("trade_sidecar"), "trade_sidecar")
    if sidecar.get("rows") != len(trades):
        raise ValueError("Swing/HA trade sidecar row count mismatch")
    if not trades["execution_authority"].eq("none").all():
        raise ValueError("Swing/HA trade row has execution authority")
    expected = (
        trades["gross_pnl_usd"] - trades["fees_usd"] + trades["funding_cashflow_usd"]
    )
    if not _close_series(expected, trades["net_pnl_usd"]):
        raise ValueError("Swing/HA trade net PnL arithmetic mismatch")
    equity = trades["equity_before_usd"] + trades["net_pnl_usd"]
    if not _close_series(equity, trades["equity_after_usd"]):
        raise ValueError("Swing/HA trade equity arithmetic mismatch")
    signal = pd.to_datetime(trades["signal_time_utc"], utc=True)
    entry = pd.to_datetime(trades["entry_time_utc"], utc=True)
    exit_time = pd.to_datetime(trades["exit_time_utc"], utc=True)
    if not ((signal < entry) & (entry <= exit_time)).all():
        raise ValueError("Swing/HA trade timing is non-causal")


def _validate_file_hash(row: dict[str, object], path_key: str, hash_key: str) -> None:
    path = Path(str(row[path_key]))
    if _file_sha256(path) != row.get(hash_key):
        raise ValueError(f"Swing/HA source checksum mismatch: {path}")


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Swing/HA {label} must be an object")
    return value


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"Swing/HA {label} must be a list")
    return value


def _close_series(left: pd.Series, right: pd.Series) -> bool:
    return bool((left.astype(float) - right.astype(float)).abs().le(1e-8).all())


def main() -> int:
    """Validate one explicit immutable artifact pair."""
    args = build_parser().parse_args()
    print(json.dumps(validate_artifact(args.artifact, args.trades), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
