"""Immutable route-scoped stop-recovery command tests."""

from __future__ import annotations

import argparse
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType


def _script() -> ModuleType:
    path = Path("scripts/route_stop_recovery_sensitivity.py")
    spec = spec_from_file_location("route_stop_recovery_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("route stop-recovery script is unavailable")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_command_filters_exact_route_and_publishes_authority_none(
    tmp_path: Path,
) -> None:
    """Exclude other strategies while embedding the exact consumed trade."""
    script = _script()
    checkpoint = tmp_path / "checkpoint.json"
    output = tmp_path / "report.json"
    selected = _trade("ETH", "eth_route")
    checkpoint.write_text(
        json.dumps(
            {
                "generated_at_utc": "2026-08-25T00:00:00Z",
                "audit": {
                    "run": {"run_id": "live-1", "profile_id": "v61"},
                    "trade_reflections": {
                        "all_time_live": {
                            "trades": [selected, _trade("BTC", "btc_route")]
                        }
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        checkpoint=checkpoint,
        strategy_id="eth_route",
        symbol="ETH",
        assessment_horizon_minutes=720,
        stop_widths=[60.0, 80.0, 100.0, 120.0],
        out=output,
    )

    report = script.run_report(args)

    assert report["contract"]["execution_authority"] == "none"
    assert report["route"] == {"strategy_id": "eth_route", "symbol": "ETH"}
    assert report["summary"]["protective_stop_trades"] == 1
    assert report["trades"][0]["lifecycle_id"] == "ETH:1"
    assert json.loads(output.read_text()) == report


def _trade(symbol: str, strategy: str) -> dict[str, object]:
    return {
        "lifecycle_id": f"{symbol}:1",
        "source_run_id": "run-v61",
        "source_profile_fingerprint": "fingerprint-v61",
        "strategy_id": strategy,
        "symbol": symbol,
        "side": "long",
        "exit_reason": "protective_stop",
        "entry": {"price": 100.0, "size": 10.0},
        "protective_stop": {"trigger_price": 99.4},
        "entry_followthrough_path": {
            "720": {
                "status": "resolved",
                "adverse_excursion_bps": 130.0,
                "favorable_excursion_bps": 100.0,
                "directional_close_return_bps": 20.0,
            }
        },
    }
