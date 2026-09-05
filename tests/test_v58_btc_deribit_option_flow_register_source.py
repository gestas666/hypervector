"""Tests for frozen BTC Deribit option-flow source registration."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest

from hypervector.data.oxa_storage import file_evidence


_SCRIPT = Path("scripts/v58_btc_deribit_option_flow_register_source.py")


def test_source_registration_script_exists() -> None:
    """The acquired source needs an independently reproducible registrar."""
    assert _SCRIPT.is_file()


def test_registration_publishes_report_only_hourly_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Registration must bind both preregistrations without computing signals."""
    module = _load_module()
    original, revised, horizon, protocol, instrument, audit = _preregistrations(
        tmp_path
    )
    source = tmp_path / "raw-source"
    source.mkdir()
    supplement = tmp_path / "instrument-supplement"
    supplement.mkdir()
    pd.DataFrame(
        {
            "instrument_name": [],
            "creation_timestamp_ms": [],
            "expiration_timestamp_ms": [],
            "strike": [],
            "option_type": [],
            "contract_size": [],
        }
    ).to_parquet(supplement / "instruments.parquet", index=False)
    output = tmp_path / "registered"
    hourly = pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-08-01", periods=24, freq="1h", tz="UTC"),
            "eligible_trade_count": [0] * 24,
            "weight_usd": [0.0] * 24,
            "signed_weight_usd": [0.0] * 24,
            "directional_imbalance": [float("nan")] * 24,
        }
    )
    reproduction = SimpleNamespace(to_dict=lambda: {"trade_rows_match": True})
    supplement_reproduction = SimpleNamespace(
        to_dict=lambda: {"rows_match": True, "instrument_rows": 0}
    )
    source_audit = SimpleNamespace(to_dict=lambda: {"trade_rows": 100})
    monkeypatch.setattr(
        module, "reproduce_deribit_option_bundle", lambda _: reproduction
    )
    monkeypatch.setattr(
        module,
        "reproduce_deribit_instrument_supplement",
        lambda _: supplement_reproduction,
    )
    monkeypatch.setattr(
        module,
        "materialize_registered_hourly_flow",
        lambda *args, **kwargs: (hourly, source_audit),
    )
    args = module.build_parser().parse_args(
        [
            "--source-bundle",
            str(source),
            "--original-preregistration",
            str(original),
            "--revised-preregistration",
            str(revised),
            "--execution-preregistration",
            str(horizon),
            "--experiment-protocol",
            str(protocol),
            "--instrument-preregistration",
            str(instrument),
            "--completeness-audit",
            str(audit),
            "--instrument-supplement",
            str(supplement),
            "--output",
            str(output),
            "--recorded-at-utc",
            "2026-08-22T09:00:00Z",
        ]
    )

    published = module.run_command(args)

    manifest = json.loads((published / "manifest.json").read_text(encoding="utf-8"))
    stored = pd.read_parquet(published / "hourly_flow.parquet")
    assert len(stored) == 24
    assert manifest["execution_authority"] == "none"
    assert manifest["candidate_signals_computed"] is False
    assert manifest["candidate_outcomes_computed"] is False
    assert manifest["runtime_strategy_changed"] is False
    assert manifest["live_change_authorized"] is False
    assert manifest["raw_reproduction"]["trade_rows_match"] is True
    assert manifest["source_audit"]["trade_rows"] == 100
    assert manifest["execution_preregistration"]["path"] == str(horizon.resolve())
    assert manifest["experiment_protocol"]["path"] == str(protocol.resolve())
    assert manifest["instrument_preregistration"]["path"] == str(instrument.resolve())
    assert manifest["instrument_supplement_reproduction"]["rows_match"] is True
    with pytest.raises(FileExistsError, match="already exists"):
        module.run_command(args)


def _preregistrations(
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path, Path, Path]:
    original = tmp_path / "v1.json"
    original.write_text(
        json.dumps(
            {
                "schema_version": (
                    "v58_btc_deribit_option_flow_long_preregistration_v1"
                ),
                "hypothesis_id": "V58_BTC_DERIBIT_OTM_DIRECTIONAL_FLOW_LONG_V1",
            }
        ),
        encoding="utf-8",
    )
    revised = tmp_path / "v2.json"
    revised.write_text(
        json.dumps(
            {
                "schema_version": (
                    "v58_btc_deribit_option_flow_long_preregistration_v2"
                ),
                "hypothesis_id": "V58_BTC_DERIBIT_OTM_DIRECTIONAL_FLOW_LONG_V1",
                "status": "source_revision_preregistered_before_candidate_outcomes",
                "execution_authority": "none",
                "automatic_promotion": False,
                "runtime_strategy_changed": False,
                "orders_supported": False,
                "live_change_authorized": False,
                "outcomes_inspected_before_preregistration": False,
                "candidate_signal_counts_inspected": False,
                "candidate_forward_returns_inspected": False,
                "candidate_trade_outcomes_inspected": False,
                "source_contract": {
                    "deribit_trades": {
                        "start_utc": "2025-08-01T00:00:00Z",
                        "end_utc": "2025-08-02T00:00:00Z",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    horizon = tmp_path / "v3.json"
    payload = json.loads(revised.read_text(encoding="utf-8"))
    payload["schema_version"] = "v58_btc_deribit_option_flow_long_preregistration_v3"
    payload["status"] = (
        "execution_horizon_revision_preregistered_before_candidate_outcomes"
    )
    horizon.write_text(json.dumps(payload), encoding="utf-8")
    protocol = tmp_path / "protocol.json"
    protocol.write_text(
        json.dumps(
            {
                "schema_version": (
                    "v58_btc_deribit_option_flow_experiment_protocol_v1"
                ),
                "hypothesis_id": "V58_BTC_DERIBIT_OTM_DIRECTIONAL_FLOW_LONG_V1",
                "status": "evaluation_semantics_frozen_before_signals_or_outcomes",
                "authority": {
                    "execution_authority": "none",
                    "live_change_authorized": False,
                    "automatic_promotion": False,
                },
                "outcome_blindness": {
                    "candidate_signals_computed": False,
                    "candidate_signal_counts_inspected": False,
                    "candidate_forward_returns_inspected": False,
                    "candidate_trade_outcomes_inspected": False,
                    "parameters_changed": False,
                },
            }
        ),
        encoding="utf-8",
    )
    audit = tmp_path / "audit.json"
    audit.write_text(
        json.dumps(
            {
                "status": (
                    "instrument_dictionary_gap_identified_before_candidate_signals"
                ),
                "unmatched_instrument_count": 0,
                "unmatched_instrument_names": [],
                "outcome_blindness": {
                    "candidate_signals_computed": False,
                    "candidate_signal_counts_inspected": False,
                    "candidate_forward_returns_inspected": False,
                    "candidate_trade_outcomes_inspected": False,
                },
            }
        ),
        encoding="utf-8",
    )
    instrument = tmp_path / "v4.json"
    payload = json.loads(horizon.read_text(encoding="utf-8"))
    payload["schema_version"] = "v58_btc_deribit_option_flow_long_preregistration_v4"
    payload["status"] = (
        "instrument_dictionary_revision_preregistered_before_candidate_signals"
    )
    payload["instrument_dictionary_revision"] = {
        "completeness_audit": {
            "path": str(audit),
            **file_evidence(audit),
        },
        "candidate_signals_opened": False,
        "candidate_outcomes_opened": False,
        "candidate_parameters_changed": False,
    }
    instrument.write_text(json.dumps(payload), encoding="utf-8")
    return original, revised, horizon, protocol, instrument, audit


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("btc_option_register_source", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script: {_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
