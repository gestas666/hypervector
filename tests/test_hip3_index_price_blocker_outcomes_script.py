"""CLI tests for source-bound HIP-3 price-blocker outcome evidence."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pandas as pd

SCRIPT = Path(__file__).parents[1] / "scripts/hip3_index_price_blocker_outcomes.py"


class _Candles:
    def completed_candles(self, **kwargs: object) -> pd.DataFrame:
        assert kwargs["symbol"] == "xyz:SP500"
        return pd.DataFrame(
            {
                "timestamp": pd.to_datetime([900_000, 1_800_000], unit="ms", utc=True),
                "open": [100.0, 100.1],
                "high": [100.2, 100.3],
                "low": [99.9, 99.7],
                "close": [100.1, 99.9],
            }
        )


def test_command_binds_runtime_friction_and_publishes_immutable_report(
    tmp_path: Path,
) -> None:
    """The CLI must source cost sensitivity from the exact active route."""
    module = _load()
    condition = tmp_path / "condition.json"
    checkpoint = tmp_path / "checkpoint.json"
    output = tmp_path / "result.json"
    condition.write_text(json.dumps(_condition_report()))
    checkpoint.write_text(json.dumps(_checkpoint()))
    args = module.build_parser().parse_args(
        [
            "--condition-report",
            str(condition),
            "--checkpoint",
            str(checkpoint),
            "--output",
            str(output),
            "--side",
            "long",
            "--observed-at-utc",
            "1970-01-01T00:45:00Z",
        ]
    )

    report = module.run_command(args, candle_source=_Candles())

    assert report["scope"]["round_trip_friction_bps"] == 5.0
    assert report["cost_evidence"]["entry_fee_bps"] == 1.0
    assert report["cost_evidence"]["entry_slippage_bps"] == 1.5
    assert report["input_evidence"]["condition_report"]["sha256"]
    assert report["market_candle_evidence"]["rows"] == 2
    assert json.loads(output.read_text()) == report


def test_command_censors_a_terminal_forming_candle(tmp_path: Path) -> None:
    """A candle whose close follows observed_at cannot resolve a future path."""
    module = _load()
    condition = tmp_path / "condition.json"
    checkpoint = tmp_path / "checkpoint.json"
    output = tmp_path / "result.json"
    condition.write_text(json.dumps(_condition_report()))
    checkpoint.write_text(json.dumps(_checkpoint()))
    args = module.build_parser().parse_args(
        [
            "--condition-report",
            str(condition),
            "--checkpoint",
            str(checkpoint),
            "--output",
            str(output),
            "--side",
            "long",
            "--observed-at-utc",
            "1970-01-01T00:35:00Z",
        ]
    )

    report = module.run_command(args, candle_source=_Candles())

    assert report["market_candle_evidence"]["rows"] == 1
    assert report["by_horizon"]["15"]["resolved"] == 1
    assert report["by_horizon"]["30"]["censored"] == 1


def _condition_report() -> dict[str, object]:
    return {
        "schema_version": "hip3_index_live_condition_diagnostic_v1",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_change": False,
            "runtime_strategy_changed": False,
        },
        "scope": {
            "symbol": "xyz:SP500",
            "provider_id": "index-v3",
            "profile_id": "profile-v51",
            "profile_fingerprint": "a" * 64,
            "run_id": "run-v51",
            "timeframe": "15m",
            "execution_stop_bps": 80.0,
        },
        "observations": [
            {
                "decision_time_ms": 900_000,
                "close": 100.0,
                "authoritative_eligible": False,
                "long": {
                    "price_breakout": False,
                    "ema_alignment": True,
                    "pressure_confirmation": True,
                },
                "short": {
                    "price_breakout": False,
                    "ema_alignment": False,
                    "pressure_confirmation": False,
                },
            }
        ],
    }


def _checkpoint() -> dict[str, object]:
    return {
        "checkpoint_contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
        },
        "configuration_generation": {
            "state": "current_runtime_configuration",
            "matches_runtime": True,
            "current_profile_fingerprint": "a" * 64,
            "runtime_profile_fingerprint": "a" * 64,
        },
        "audit": {
            "run": {
                "run_id": "run-v51",
                "profile_id": "profile-v51",
                "profile_fingerprint": "a" * 64,
            },
            "execution": {
                "friction_parity": {
                    "by_provider_symbol": {
                        "index-v3|xyz:SP500": {
                            "parity_state": "runtime_shape_aligned",
                            "modeled_contract": {
                                "entry_fee_bps": 1.0,
                                "entry_slippage_bps": 1.5,
                                "stop_bps": 80.0,
                                "evidence_source": "fixture.json",
                            },
                            "runtime_contract": {"stop_bps": 80.0},
                        }
                    }
                }
            },
        },
    }


def _load() -> ModuleType:
    spec = spec_from_file_location("hip3_index_price_blocker_outcomes_script", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load price-blocker script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
