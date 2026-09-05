"""Tests for the frozen BTC spot-lead experiment publisher."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from hypervector.data.oxa_storage import file_evidence

from btc_spot_lead_catchup_fixtures import spot_lead_signal_bars


def test_btc_spot_lead_experiment_script_exists() -> None:
    """The exact replay must have a reproducible immutable publisher."""
    assert Path("scripts/v58_btc_binance_spot_lead_experiment.py").is_file()


def test_command_publishes_source_bound_complete_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bind all inputs and generators before publishing every frozen cell."""
    module = _load_module()
    assert hasattr(module, "build_parser")
    assert hasattr(module, "run_command")
    assert hasattr(module, "BtcSpotLeadCatchupPartition")
    registration = _write_inputs_and_registration(tmp_path)
    perpetual, _, _, _, _ = spot_lead_signal_bars()
    start = perpetual.index[0]
    bounds = (
        start,
        start + pd.Timedelta(hours=58),
        start + pd.Timedelta(hours=61),
        start + pd.Timedelta(hours=64),
    )
    partitions = tuple(
        module.BtcSpotLeadCatchupPartition(name, bounds[offset], bounds[offset + 1])
        for offset, name in enumerate(("development", "validation", "pseudo_holdout"))
    )
    monkeypatch.setattr(
        module,
        "frozen_btc_spot_lead_catchup_partitions",
        lambda: partitions,
    )
    output = tmp_path / "result"
    args = module.build_parser().parse_args(
        ["--input-registration", str(registration), "--output", str(output)]
    )

    published = module.run_command(args)

    assert published == output
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert report["hypothesis_id"] == (
        "V58_BTC_BINANCE_SPOT_LEAD_HL_PERP_CATCHUP_LONG_V1"
    )
    assert report["authority"]["execution_authority"] == "none"
    assert len(report["summary_rows"]) == 36
    assert set(manifest["files"]) == {"report.json", "trades.parquet"}
    assert report["generator_identity"]["aggregate_sha256"]
    with pytest.raises(FileExistsError, match="already exists"):
        module.run_command(args)


def _write_inputs_and_registration(tmp_path: Path) -> Path:
    perpetual, spot, _, _, _ = spot_lead_signal_bars()
    bars_path = tmp_path / "perpetual.parquet"
    perpetual.drop(columns="funding_rate").reset_index(names="timestamp").to_parquet(
        bars_path,
        index=False,
    )
    spot_path = tmp_path / "spot.parquet"
    spot.reset_index(names="timestamp").to_parquet(spot_path, index=False)
    funding_path = tmp_path / "funding.parquet"
    funding_index = pd.date_range(
        perpetual.index[0],
        perpetual.index[-1].ceil("h"),
        freq="1h",
    )
    pd.DataFrame(
        {
            "timestamp": funding_index,
            "funding_rate": 0.0,
            "source": "hl_funding_history",
        }
    ).to_parquet(funding_path, index=False)
    vendor_manifest = tmp_path / "vendor_manifest.json"
    vendor_manifest.write_text("{}", encoding="utf-8")
    normalized_manifest = tmp_path / "normalized_manifest.json"
    normalized_manifest.write_text("{}", encoding="utf-8")
    preregistration = tmp_path / "preregistration.json"
    preregistration.write_text("{}", encoding="utf-8")
    registration = tmp_path / "registration.json"
    payload = {
        "schema_version": "v58_btc_binance_spot_lead_input_registration_v1",
        "hypothesis_id": "V58_BTC_BINANCE_SPOT_LEAD_HL_PERP_CATCHUP_LONG_V1",
        "status": "inputs_hash_bound_before_candidate_signal_or_return_results",
        "authority": {"execution_authority": "none"},
        "change_scope": {
            "candidate_signal_count_inspected": False,
            "candidate_returns_inspected": False,
            "candidate_pnl_inspected": False,
        },
        "preregistration": {
            "path": str(preregistration.resolve()),
            **file_evidence(preregistration),
        },
        "source_evidence": {
            "hyperliquid_btc_1m_bars": _evidence(bars_path),
            "hyperliquid_btc_hourly_funding": _evidence(funding_path),
            "binance_spot_vendor_manifest": _evidence(vendor_manifest),
            "binance_spot_normalized_manifest": _evidence(normalized_manifest),
            "binance_spot_normalized_bars": _evidence(spot_path),
        },
    }
    registration.write_text(json.dumps(payload), encoding="utf-8")
    return registration


def _evidence(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _load_module() -> ModuleType:
    path = Path("scripts/v58_btc_binance_spot_lead_experiment.py")
    spec = importlib.util.spec_from_file_location("btc_spot_lead_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
