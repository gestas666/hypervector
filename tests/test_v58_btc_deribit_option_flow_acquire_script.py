"""Tests for the frozen Deribit BTC option-flow acquisition command."""

from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
from types import ModuleType

import pytest


_SCRIPT = Path("scripts/v58_btc_deribit_option_flow_acquire.py")


def test_option_flow_acquisition_script_exists() -> None:
    """The preregistered source needs a reproducible guarded entry point."""
    assert _SCRIPT.is_file()


def test_command_binds_frozen_preregistration_before_acquisition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The command must bind source identity without inspecting outcomes."""
    module = _load_module()
    preregistration = _write_preregistration(tmp_path)
    output = tmp_path / "bundle"
    captured: dict[str, object] = {}

    def acquire(
        path: Path,
        fetch_bytes: object,
        *,
        window: object,
        max_requests_per_day: int,
        context: dict[str, object],
    ) -> Path:
        captured.update(
            path=path,
            fetch_bytes=fetch_bytes,
            window=window,
            max_requests_per_day=max_requests_per_day,
            context=context,
        )
        return path

    monkeypatch.setattr(module, "acquire_deribit_option_bundle", acquire)
    args = module.build_parser().parse_args(
        ["--preregistration", str(preregistration), "--output", str(output)]
    )

    published = module.run_command(args)

    assert published == output
    window = captured["window"]
    assert window.start_ms == module.START_TIMESTAMP_MS
    assert window.end_ms == module.END_TIMESTAMP_MS
    assert captured["max_requests_per_day"] == 64
    context = captured["context"]
    assert context["execution_authority"] == "none"
    assert context["candidate_outcomes_inspected_before_acquisition"] is False
    assert context["live_change_authorized"] is False
    assert len(context["preregistration"]["sha256"]) == 64


def _write_preregistration(tmp_path: Path) -> Path:
    qualification = tmp_path / "qualification.json"
    qualification.write_text("{}\n", encoding="utf-8")
    qualification_bytes = qualification.read_bytes()
    payload = {
        "schema_version": "v58_btc_deribit_option_flow_long_preregistration_v1",
        "hypothesis_id": "V58_BTC_DERIBIT_OTM_DIRECTIONAL_FLOW_LONG_V1",
        "status": (
            "preregistered_after_schema_preflight_before_full_source_"
            "acquisition_or_candidate_outcomes"
        ),
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "orders_supported": False,
        "live_change_authorized": False,
        "outcomes_inspected_before_preregistration": False,
        "candidate_signal_counts_inspected": False,
        "candidate_forward_returns_inspected": False,
        "candidate_trade_outcomes_inspected": False,
        "source_qualification": {
            "path": qualification.name,
            "sha256": hashlib.sha256(qualification_bytes).hexdigest(),
            "bytes": len(qualification_bytes),
        },
        "source_contract": {
            "deribit_trades": {
                "endpoint": (
                    "https://history.deribit.com/api/v2/public/"
                    "get_last_trades_by_currency_and_time"
                ),
                "currency": "BTC",
                "kind": "option",
                "include_old": True,
                "sorting": "asc",
                "start_utc": "2025-04-01T00:00:00Z",
                "end_utc": "2026-08-01T00:00:00Z",
                "maximum_count": 10_000,
            },
            "deribit_instruments": {
                "endpoint": (
                    "https://history.deribit.com/api/v2/public/get_instruments"
                ),
                "currency": "BTC",
                "kind": "option",
                "expired": True,
            },
        },
    }
    path = tmp_path / "preregistration.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("btc_option_acquire_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script: {_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
