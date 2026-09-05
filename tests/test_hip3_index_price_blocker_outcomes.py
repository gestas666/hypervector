"""Causal outcome tests for exact live HIP-3 price-blocker observations."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.hip3_index_price_blocker_outcomes import (
    build_hip3_index_price_blocker_outcomes,
)


def test_reports_forward_path_without_claiming_execution() -> None:
    """One missing-price setup must retain gross, cost, and stop-path evidence."""
    report = build_hip3_index_price_blocker_outcomes(
        condition_report=_condition_report(),
        candles=_candles(),
        side="long",
        horizons_minutes=(15, 30),
        round_trip_friction_bps=5.0,
        stop_bps=80.0,
    )

    assert report["contract"]["execution_authority"] == "none"
    assert report["scope"]["candidate_observations"] == 1
    outcomes = report["outcomes"]
    assert outcomes[0]["gross_close_return_bps"] == pytest.approx(10.0)
    assert outcomes[0]["after_friction_bps"] == pytest.approx(5.0)
    assert outcomes[0]["maximum_favorable_excursion_bps"] == pytest.approx(20.0)
    assert outcomes[0]["maximum_adverse_excursion_bps"] == pytest.approx(-10.0)
    assert outcomes[0]["stop_touched"] is False
    assert outcomes[1]["gross_close_return_bps"] == pytest.approx(-10.0)
    assert report["by_horizon"]["15"]["resolved"] == 1
    assert report["by_horizon"]["30"]["mean_after_friction_bps"] == pytest.approx(-15.0)
    assert report["assessment"]["parameter_change_supported"] is False


def test_rejects_non_report_only_or_wrong_blocker_contract() -> None:
    """Malformed authority and non-price blockers cannot enter this diagnostic."""
    condition = _condition_report()
    condition["contract"]["execution_authority"] = "live"
    with pytest.raises(ValueError, match="condition report contract"):
        build_hip3_index_price_blocker_outcomes(
            condition_report=condition,
            candles=_candles(),
            side="long",
            horizons_minutes=(15,),
            round_trip_friction_bps=5.0,
            stop_bps=80.0,
        )

    condition = _condition_report()
    condition["observations"][0]["long"]["ema_alignment"] = False
    with pytest.raises(ValueError, match="no exact price-only blocker"):
        build_hip3_index_price_blocker_outcomes(
            condition_report=condition,
            candles=_candles(),
            side="long",
            horizons_minutes=(15,),
            round_trip_friction_bps=5.0,
            stop_bps=80.0,
        )


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


def _candles() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime([900_000, 1_800_000], unit="ms", utc=True),
            "open": [100.0, 100.1],
            "high": [100.2, 100.3],
            "low": [99.9, 99.7],
            "close": [100.1, 99.9],
        }
    )
