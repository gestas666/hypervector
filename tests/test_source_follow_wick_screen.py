"""Frozen current-lead consolidation-wick screen command contract."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest


def _module() -> ModuleType:
    path = Path("scripts/hypervelocity_source_wick_screen.py")
    spec = importlib.util.spec_from_file_location("source_wick_screen", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load source wick screen: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_wick_screen_command_exists() -> None:
    """The frozen report-only screen must have a direct reproducible command."""
    assert Path("scripts/hypervelocity_source_wick_screen.py").is_file()


def test_wick_screen_contract_is_frozen_and_report_only() -> None:
    """The first current-lead screen must not expose a tuning grid."""
    contract = _module().experiment_contract()

    assert contract == {
        "candidate": "source_follow_minrange12_consolidation_wick_screen_v1",
        "report_only": True,
        "runtime_strategy_changed": False,
        "execution_authority": "none",
        "model_authority": "observe",
        "stateful_replay_performed": False,
        "bbwp_length": 20,
        "bbwp_lookback": 240,
        "bbwp_threshold": 25.0,
        "maximum_gap_fill_minutes": 30,
        "stop_buffer_bps": 0.0,
        "trigger_reference": "hyperliquid_mark_price",
    }


def test_wick_screen_rejects_noncontinuous_or_wrong_risk_artifact() -> None:
    """An older source-follow artifact cannot masquerade as the current lead."""
    module = _module()
    payload = _source_payload()
    module._validate_source_payload(payload)

    with pytest.raises(ValueError, match="continuous production replay"):
        module._validate_source_payload({**payload, "schema": "older_schema"})
    altered = dict(payload)
    altered["experiment_contract"] = {
        **payload["experiment_contract"],
        "leverage": 40.0,
    }
    with pytest.raises(ValueError, match="frozen current lead"):
        module._validate_source_payload(altered)


def test_wick_screen_qualification_requires_pnl_and_liquidation_improvement() -> None:
    """Lower PnL or zero avoided liquidations cannot launch stateful work."""
    module = _module()
    qualified = {
        "net_pnl_delta_usd": 10.0,
        "liquidations_avoided": 1,
    }

    assert module._qualification(qualified)["qualified"] is True
    assert (
        module._qualification({**qualified, "net_pnl_delta_usd": 0.0})["qualified"]
        is False
    )
    assert (
        module._qualification({**qualified, "liquidations_avoided": 0})["qualified"]
        is False
    )


def test_wick_screen_repairs_bounded_no_trade_minutes(tmp_path: Path) -> None:
    """Missing no-trade minutes remain explicit, bounded venue gap fills."""
    path = tmp_path / "candles.parquet"
    pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2025-07-28T00:00:00Z", "2025-07-28T00:02:00Z"], utc=True
            ),
            "open": [100.0, 101.0],
            "high": [100.0, 101.0],
            "low": [100.0, 101.0],
            "close": [100.0, 101.0],
            "volume": [1.0, 2.0],
            "source": ["hl", "hl"],
        }
    ).to_parquet(path, index=False)

    bars, provenance = _module()._load_repaired_candles([path])

    assert len(bars) == 3
    assert provenance == {"native_candle_rows": 2, "gap_fill_rows": 1}
    assert bars.index.is_monotonic_increasing
    assert bars.loc[pd.Timestamp("2025-07-28T00:01:00Z"), "close"] == 100.0
    assert bars.loc[pd.Timestamp("2025-07-28T00:01:00Z"), "volume"] == 0.0


def test_wick_screen_accepts_mixed_iso_outcome_precision() -> None:
    """Whole-second and fractional lifecycle timestamps share one schema."""
    index = pd.date_range("2025-07-28T00:00:00Z", periods=400, freq="1min")
    bars = pd.DataFrame(index=index)
    lifecycles = pd.DataFrame(
        {
            "signal_time_utc": [
                "2025-07-28T05:00:00+00:00",
                "2025-07-28T05:01:00+00:00",
            ],
            "outcome_time_utc": [
                "2025-07-28T05:10:00.123000+00:00",
                "2025-07-28T05:11:00+00:00",
            ],
        }
    )

    coverage = _module()._coverage(bars, lifecycles)

    assert coverage["last_outcome_utc"] == "2025-07-28T05:11:00+00:00"


def _source_payload() -> dict[str, object]:
    return {
        "schema": "hypervelocity_source_continuous_production_replay_v1",
        "report_only": True,
        "runtime_strategy_changed": False,
        "experiment_contract": {
            "candidate": "source_follow_minrange12_continuous_v1",
            "minimum_signal_range_bps": 12.0,
            "margin_fraction": 0.50,
            "leverage": 30.0,
            "gross_margin_target_pct": 8.0,
            "maximum_hold_seconds": 86_400.0,
            "execution_authority": "none",
            "model_authority": "observe",
        },
        "production_replay": {
            "open_positions": 0,
            "trades": [],
        },
        "segments": [],
    }
