"""Tests for immutable BTC option-flow experiment publication."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd
import pytest

from hypervector.data.oxa_storage import file_evidence, write_json


_SCRIPT = Path("scripts/v58_btc_deribit_option_flow_experiment.py")


def test_registered_source_loader_binds_protocol_and_remains_outcome_blind(
    tmp_path: Path,
) -> None:
    """Signal generation may begin only from the exact registered source boundary."""
    module = _load_module()
    preregistration = tmp_path / "v3.json"
    protocol = tmp_path / "protocol.json"
    preregistration.write_text("{}\n", encoding="utf-8")
    protocol.write_text("{}\n", encoding="utf-8")
    bundle = tmp_path / "registered"
    bundle.mkdir()
    hourly = pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-08-01", periods=2, freq="1h", tz="UTC"),
            "eligible_trade_count": [20, 20],
            "weight_usd": [1.0, 1.0],
            "signed_weight_usd": [0.5, -0.5],
            "directional_imbalance": [0.5, -0.5],
        }
    )
    hourly.to_parquet(bundle / "hourly_flow.parquet", index=False)
    manifest = _registered_manifest(bundle, preregistration, protocol)
    write_json(bundle / "manifest.json", manifest)

    loaded, evidence = module.load_registered_hourly_source(
        bundle, preregistration, protocol
    )

    assert loaded.equals(hourly)
    assert evidence["candidate_outcomes_computed"] is False
    manifest["candidate_outcomes_computed"] = True
    write_json(bundle / "replacement.json", manifest)
    (bundle / "manifest.json").write_text(
        (bundle / "replacement.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="identity or authority"):
        module.load_registered_hourly_source(bundle, preregistration, protocol)


def test_actual_protocol_builds_exact_three_partitions_and_five_folds() -> None:
    """Runtime partition construction must equal the frozen protocol."""
    module = _load_module()
    preregistration = json.loads(
        Path(
            "docs/research-journal/"
            "v58-btc-deribit-option-flow-long-preregistration-20260822-v4.json"
        ).read_text(encoding="utf-8")
    )
    protocol = json.loads(
        Path(
            "docs/research-journal/"
            "v58-btc-deribit-option-flow-experiment-protocol-20260822-v1.json"
        ).read_text(encoding="utf-8")
    )

    partitions, folds = module.experiment_partitions(preregistration, protocol)

    assert [value.name for value in partitions] == [
        "development",
        "validation",
        "pseudo_holdout",
    ]
    assert len(folds) == 5
    assert folds[0].start == partitions[0].start
    assert folds[-1].end == partitions[0].end


def _registered_manifest(
    bundle: Path, preregistration: Path, protocol: Path
) -> dict[str, object]:
    return {
        "schema_version": "v58_btc_deribit_option_flow_registered_source_v2",
        "hypothesis_id": "V58_BTC_DERIBIT_OTM_DIRECTIONAL_FLOW_LONG_V1",
        "status": "registered_before_candidate_signals_or_outcomes",
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "live_change_authorized": False,
        "candidate_signals_computed": False,
        "candidate_outcomes_computed": False,
        "instrument_preregistration": {
            "path": str(preregistration),
            **file_evidence(preregistration),
        },
        "experiment_protocol": {
            "path": str(protocol),
            **file_evidence(protocol),
        },
        "files": {"hourly_flow.parquet": file_evidence(bundle / "hourly_flow.parquet")},
    }


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "option_flow_experiment_script", _SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script: {_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
