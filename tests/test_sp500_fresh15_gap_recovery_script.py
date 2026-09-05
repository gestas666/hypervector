"""Command tests for immutable SP500 outage mark recovery evidence."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

from hypervector.data.oxa_prices import (
    OxaPriceFetch,
    OxaPriceRequest,
    OxaPriceSnapshot,
    price_output_directory,
    store_price_history,
)

_ROOT = Path(__file__).parents[1]
_SCRIPT = _ROOT / "scripts" / "sp500_fresh15_gap_recovery.py"
_START = datetime(2026, 8, 19, 7, 40, tzinfo=UTC)
_END = _START + timedelta(minutes=16)
_GAP_START = int((_START + timedelta(minutes=1)).timestamp() * 1_000)


def test_command_publishes_source_bound_report_without_authority(
    tmp_path: Path,
) -> None:
    module = _load_script()
    paths = _inputs(tmp_path)
    output = tmp_path / "recovery.json"
    args = argparse.Namespace(**paths, output=output)

    report = module.run_command(args)

    assert output.is_file()
    assert report["disposition"] == "OPEN_LIFECYCLE_CENSORED_DECISION_GAP"
    assert report["execution_authority"] == "none"
    evidence = report["input_evidence"]
    assert evidence["price_manifest"]["sha256"]
    assert evidence["prices"]["sha256"]
    assert evidence["decision_journal_prefix"]["rows"] == 2
    assert evidence["candle_journal_prefix"]["rows"] == 13


def _load_script() -> object:
    spec = spec_from_file_location("sp500_fresh15_gap_recovery_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _inputs(root: Path) -> dict[str, Path]:
    preregistration = root / "preregistration.json"
    status = root / "status.json"
    decisions = root / "decisions.jsonl"
    candles = root / "candles.jsonl"
    preregistration.write_text(json.dumps(_preregistration()) + "\n")
    status.write_text(json.dumps(_status()) + "\n")
    _write_jsonl(decisions, _decisions())
    _write_jsonl(candles, _candles())
    archive = _archive(root)
    return {
        "preregistration": preregistration,
        "watcher_status": status,
        "decision_journal": decisions,
        "candle_journal": candles,
        "price_archive": archive,
    }


def _archive(root: Path) -> Path:
    request = OxaPriceRequest("xyz:SP500", _START, _END, market_family="hip3")
    timestamps = range(
        int(_START.timestamp() * 1_000), int(_END.timestamp() * 1_000), 3_000
    )
    snapshots = tuple(
        OxaPriceSnapshot(
            datetime.fromtimestamp(timestamp / 1_000, tz=UTC).isoformat(),
            timestamp,
            "7692.0",
            "7692.0",
            "7692.0",
        )
        for timestamp in timestamps
    )
    store_price_history(root, request, OxaPriceFetch((), snapshots, True, None))
    return price_output_directory(root, request)


def _preregistration() -> dict[str, object]:
    return {
        "schema_version": "v58_sp500_fresh15_lifecycle_watch_preregistration_v1",
        "symbol": "xyz:SP500",
        "provider_id": "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3",
        "profile_id": "sp500_fresh15_pressure_shadow_research_v3",
        "event": {
            "decision_time_ms": 1_787_120_100_000,
            "entry_time_ms": 1_787_120_101_436,
            "side": "short",
            "entry_price": 7675.6,
            "stop_price": 7737.0048,
        },
        "profit_lock": {
            "policy_id": "v58_hip3_sp500_100_40_80",
            "activation_bps": 100.0,
            "floor_bps": 40.0,
            "trailing_giveback_bps": 80.0,
        },
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }


def _status() -> dict[str, object]:
    return {
        "schema_version": "sp500_fresh15_lifecycle_watch_status_v1",
        "symbol": "xyz:SP500",
        "execution_authority": "none",
        "lifecycle": dict(_preregistration()["event"]),
        "trigger_reasons": ["profit_lock_source_gap", "profit_lock_source_stale"],
        "path": {
            "last_bar_close_ms": _GAP_START,
            "profit_lock_activated": False,
            "source_gap": True,
        },
    }


def _decisions() -> list[dict[str, object]]:
    return [
        {"decision": {"decision_time_ms": 1_787_124_600_000}},
        {"decision": {"decision_time_ms": 1_787_126_400_000}},
    ]


def _candles() -> list[dict[str, object]]:
    end = _GAP_START + 13 * 60_000
    return [
        {
            "event_type": "sp500_hip3_breakout_shadow_profit_lock_candle_observation",
            "symbol": "xyz:SP500",
            "source": "hyperliquid_public_candleSnapshot_1m",
            "prospective": False,
            "execution_authority": "none",
            "bar_open_ms": timestamp,
            "bar_close_ms": timestamp + 60_000,
            "observed_at_ms": end + 1_000,
            "open": 7692.0,
            "high": 7694.0,
            "low": 7690.0,
            "close": 7692.0,
        }
        for timestamp in range(_GAP_START, end, 60_000)
    ]


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
