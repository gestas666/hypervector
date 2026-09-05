from __future__ import annotations

import argparse
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pandas as pd

from hypervector.data.hip3_public_candles import Hip3CandleSourceProtocol
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_CONFIG = Path(
    "configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml"
)
_SCRIPT = Path(__file__).parents[1] / "scripts/hip3_index_live_condition_diagnostic.py"
_BAR_MS = 900_000


class _CandleSource(Hip3CandleSourceProtocol):
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def completed_candles(
        self,
        *,
        symbol: str,
        start_ms: int,
        end_ms: int,
        observed_at_ms: int,
    ) -> pd.DataFrame:
        del symbol, start_ms, end_ms, observed_at_ms
        return self._frame.copy()


def _candles() -> pd.DataFrame:
    timestamps = pd.date_range("2026-08-01", periods=64, freq="15min", tz="UTC")
    close = [100.0 + index * 0.1 for index in range(64)]
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": close,
            "high": [value + 0.2 for value in close],
            "low": [value - 0.2 for value in close],
            "close": close,
        }
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_command_publishes_exact_report_only_current_run(tmp_path: Path) -> None:
    module = _module()
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    candles = _candles()
    boundary = int(candles.loc[62, "timestamp"].timestamp() * 1_000) + _BAR_MS
    checkpoint = tmp_path / "checkpoint.json"
    frozen = tmp_path / "frozen.json"
    journal = tmp_path / "observer.jsonl"
    output = tmp_path / "report.json"
    _write_json(
        checkpoint,
        {
            "generated_at_utc": "2026-08-01T16:00:05Z",
            "checkpoint_contract": {
                "report_only": True,
                "execution_authority": "none",
                "runtime_strategy_changed": False,
            },
            "configuration_generation": {
                "state": "current_runtime_configuration",
                "matches_runtime": True,
                "current_profile_fingerprint": config.profile_fingerprint,
                "runtime_profile_fingerprint": config.profile_fingerprint,
                "source_path": str(_CONFIG),
            },
            "audit": {
                "run": {
                    "run_id": "v51-run",
                    "profile_fingerprint": config.profile_fingerprint,
                    "first_observed_at_utc": "2026-08-01T15:00:01Z",
                }
            },
        },
    )
    _write_json(
        frozen,
        {
            "schema_version": "v51_index_source_parity_forward_v1",
            "mode": "report_only",
            "execution_authority": "none",
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
            "routes": [
                "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3|xyz:SP500"
            ],
            "frozen_signal_contract": {
                "provider_id": "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3",
                "profile_ids": {
                    "xyz:SP500": "sp500_fresh15_pressure_shadow_research_v3"
                },
                "timeframe": "15m",
                "breakout_lookback_bars": 32,
                "fast_ema": 21,
                "slow_ema": 55,
                "minimum_abs_imbalance": 0.1,
                "signal_maximum_stop_bps": 120.0,
                "execution_stop_bps": 80.0,
            },
        },
    )
    journal.write_text(
        json.dumps(
            {
                "report_only": True,
                "execution_authority": "none",
                "runtime_strategy_changed": False,
                "intents": [],
                "decision": {
                    "decision_time_ms": boundary,
                    "decision_imbalance_10": 0.4,
                    "eligible": False,
                    "execution_authority": "none",
                    "pressure_fresh": True,
                    "pressure_state_history_complete": True,
                    "prospective": True,
                    "provider_id": "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3",
                    "profile_id": "sp500_fresh15_pressure_shadow_research_v3",
                    "side": None,
                    "symbol": "xyz:SP500",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    args = argparse.Namespace(
        symbol="xyz:SP500",
        config=_CONFIG,
        checkpoint=checkpoint,
        frozen_journal=frozen,
        observer_journal=journal,
        output=output,
    )

    report = module.run_command(args, candle_source=_CandleSource(candles))

    assert output.is_file()
    assert report["scope"]["run_id"] == "v51-run"
    assert report["scope"]["profile_fingerprint"] == config.profile_fingerprint
    assert report["scope"]["execution_stop_bps"] == 80.0
    assert report["input_evidence"]["observer_prefix"]["rows"] == 1
    assert report["contract"]["execution_authority"] == "none"


def _module() -> ModuleType:
    spec = spec_from_file_location("hip3_index_live_condition_diagnostic", _SCRIPT)
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
