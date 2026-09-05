"""Command contracts for the V58 BTC absorption experiment."""

from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd
import pytest


def _load_module() -> ModuleType:
    """Load the command script without requiring scripts to be a package."""
    path = Path("scripts/v58_btc_subminute_absorption.py")
    spec = importlib.util.spec_from_file_location("v58_btc_subminute_absorption", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load BTC absorption command")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_command_defaults_bind_registered_sources_and_authority_none() -> None:
    """The command must expose only the frozen report-only experiment."""
    module = _load_module()
    args = module.build_parser().parse_args([])
    partitions = module.frozen_partitions()
    configs = module.frozen_replay_configs()

    assert args.database == Path("data/research/market.duckdb")
    assert args.preregistration.name.endswith("20260821-v1.json")
    assert [
        (row.start_utc.isoformat(), row.end_utc.isoformat()) for row in partitions
    ] == [
        ("2025-04-25T00:00:00+00:00", "2026-01-29T00:00:00+00:00"),
        ("2026-01-29T00:00:00+00:00", "2026-04-29T00:00:00+00:00"),
        ("2026-04-29T00:00:00+00:00", "2026-07-28T00:00:00+00:00"),
    ]
    assert [row.scenario for row in configs] == [
        "nominal_midpoint_stop_proxy",
        "latency_and_slippage_stress",
        "public_trade_stop_proxy",
    ]


def test_preregistration_validation_rejects_execution_authority() -> None:
    """A mutated preregistration must fail before any market query."""
    payload = {
        "schema_version": "v58_btc_subminute_sell_flow_absorption_preregistration_v1",
        "hypothesis_id": "V58_BTC_SUBMINUTE_SELL_FLOW_ABSORPTION_LONG_V1",
        "authority": {"execution_authority": "live"},
    }
    module = _load_module()

    with pytest.raises(ValueError, match="authority"):
        module.validate_preregistration_payload(payload)


def test_result_bundle_is_immutable_and_manifest_bound(tmp_path: Path) -> None:
    """Published report and sidecars must be hashed and non-overwritable."""
    output = tmp_path / "result"
    report = {
        "hypothesis_id": "V58_BTC_SUBMINUTE_SELL_FLOW_ABSORPTION_LONG_V1",
        "execution_authority": "none",
        "orders_attempted": False,
    }
    trades = pd.DataFrame([{"event_id": "event", "net_pnl_usd": 1.0}])
    signals = pd.DataFrame([{"event_id": "event"}])
    module = _load_module()

    module.publish_result_bundle(output, report, trades, signals)

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["files"]) == {
        "report.json",
        "signals.parquet",
        "trades.parquet",
    }
    with pytest.raises(FileExistsError):
        module.publish_result_bundle(output, report, trades, signals)
