"""Tests for source-bound policy tracking when readiness omits exit fields."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_observer_config import with_observer_ledger_root
from hypervector.research.cohort_config_bound_policy_forward import (
    ConfigBoundPolicyForwardBinding,
    build_config_bound_policy_forward_report,
)

_CONFIG = Path("configs/multi_asset_growth_first_5000_repaired_candidate_v49.toml")
_RUN_ID = "observe-v49"
_STRATEGY = "range_onset_bidirectional_v1"


def _configs(tmp_path: Path):
    base = load_multi_asset_live_config(_CONFIG, mode="observe")
    return base, with_observer_ledger_root(base, tmp_path / "observer")


def _event(
    event_type: str, payload: dict[str, object], sequence: int
) -> dict[str, object]:
    return {
        "sequence": sequence,
        "event_type": event_type,
        "run_id": _RUN_ID,
        "observed_at_utc": f"1970-01-01T00:00:0{sequence}+00:00",
        "payload": payload,
    }


def _records(runtime_fingerprint: str) -> list[dict[str, object]]:
    identity = _event(
        "configuration_identity",
        {
            "profile_fingerprint": runtime_fingerprint,
            "config_source_path": str(_CONFIG),
            "strategy_name": "multi_asset_bidirectional_cohort",
        },
        1,
    )
    identity["profile_fingerprint"] = runtime_fingerprint
    records = [
        identity,
        _event(
            "cohort_snapshot",
            {
                "open_position_count": 0,
                "assets": [{"symbol": "SOL", "state": "FLAT"}],
            },
            2,
        ),
        _event(
            "intent_routing",
            {
                "evaluations": [_evaluation()],
                "actions": [],
                "withheld": [],
            },
            3,
        ),
        _event("market_candles", _candles(), 4),
    ]
    for row in records:
        row.update(
            {
                "execution_mode": "observe",
                "effective_mode": "OBSERVE ONLY",
                "live_armed": False,
                "execution_authority": "none",
                "profile_id": "multi_asset_growth_first_5000_repaired_candidate_v49",
                "profile_fingerprint": runtime_fingerprint,
                "run_fingerprint": "observe-run-fingerprint",
            }
        )
    return records


def _evaluation() -> dict[str, object]:
    return {
        "strategy_id": _STRATEGY,
        "symbol": "SOL",
        "decision_time_ms": 60_000,
        "reference_price": 100.0,
        "eligible": True,
        "side": "short",
        "readiness": {"side": "short", "blockers": [], "metrics": {}},
    }


def _candles() -> dict[str, object]:
    return {
        "timeframe": "1m",
        "bars": {
            "SOL": [
                {
                    "timestamp_ms": 60_000,
                    "open": 100.0,
                    "high": 100.9,
                    "low": 99.9,
                    "close": 100.5,
                }
            ]
        },
    }


def _stress(base_fingerprint: str) -> dict[str, object]:
    return {
        "schema_version": "v49_portfolio_friction_stress_v1",
        "profile_id": "multi_asset_growth_first_5000_repaired_candidate_v49",
        "profile_fingerprint": base_fingerprint,
        "scenarios": [
            {
                "account_value_usd": 5_000.0,
                "asset_slots": {
                    "SOL": {
                        "routes": [
                            {
                                "strategy_id": _STRATEGY,
                                "planned_notional_usd": 7_500.0,
                                "stop_bps": 80.0,
                                "maximum_hold_hours": 48.0,
                                "friction_components_bps": {
                                    "round_trip_taker_fee": 9.0,
                                    "live_entry_slippage_p99": 9.9,
                                    "live_adverse_exit_slippage_p99": 6.1,
                                    "visible_depth_p99": 1.6,
                                    "adverse_maximum_hold_funding": 6.0,
                                },
                            }
                        ]
                    }
                },
            }
        ],
    }


def _binding() -> ConfigBoundPolicyForwardBinding:
    return ConfigBoundPolicyForwardBinding(
        strategy_id=_STRATEGY,
        candidate_strategy_id="range_onset_sol_v49_config_bound_forward_v1",
        symbol="SOL",
        account_value_usd=5_000.0,
    )


def test_sol_override_and_stress_friction_bind_without_mutating_ledger(
    tmp_path: Path,
) -> None:
    base, runtime = _configs(tmp_path)
    records = _records(runtime.profile_fingerprint)
    original = deepcopy(records)

    report = build_config_bound_policy_forward_report(
        records,
        base_config=base,
        runtime_config=runtime,
        stress_report=_stress(base.profile_fingerprint),
        binding=_binding(),
        run_id=_RUN_ID,
    )

    assert records == original
    assert report["summary"]["resolved"] == 1
    assert report["latest_executions"][0]["gross_return_bps"] == pytest.approx(-80.0)
    assert report["latest_executions"][0]["net_return_before_funding_bps"] == (
        pytest.approx(-106.6)
    )
    contract = report["contract"]
    assert contract["stop_bps"] == 80.0
    assert contract["maximum_hold_minutes"] == 2_880
    assert contract["notional_usd"] == 7_500.0
    assert contract["modeled_round_trip_friction_bps"] == pytest.approx(26.6)
    assert contract["execution_contract_source"] == "runtime_profile_config"
    assert contract["profile_fingerprint"] == runtime.profile_fingerprint
    assert contract["friction_scope"] == "stacked_p99_excluding_funding"
    assert report["contract"]["execution_authority"] == "none"


def test_existing_candidate_exit_contract_mismatch_fails_closed(tmp_path: Path) -> None:
    base, runtime = _configs(tmp_path)
    records = _records(runtime.profile_fingerprint)
    metrics = records[2]["payload"]["evaluations"][0]["readiness"]["metrics"]
    metrics["stop_bps"] = 60.0
    metrics["maximum_hold_seconds"] = 172_800

    with pytest.raises(ValueError, match="candidate stop_bps conflicts"):
        build_config_bound_policy_forward_report(
            records,
            base_config=base,
            runtime_config=runtime,
            stress_report=_stress(base.profile_fingerprint),
            binding=_binding(),
            run_id=_RUN_ID,
        )


def test_runtime_profile_mismatch_fails_before_replay(tmp_path: Path) -> None:
    base, runtime = _configs(tmp_path)
    records = _records("wrong-fingerprint")

    with pytest.raises(ValueError, match="runtime profile fingerprint"):
        build_config_bound_policy_forward_report(
            records,
            base_config=base,
            runtime_config=runtime,
            stress_report=_stress(base.profile_fingerprint),
            binding=_binding(),
            run_id=_RUN_ID,
        )


def test_mixed_profile_row_fails_closed(tmp_path: Path) -> None:
    base, runtime = _configs(tmp_path)
    records = _records(runtime.profile_fingerprint)
    records[-1]["profile_fingerprint"] = "different-profile"

    with pytest.raises(ValueError, match="profile fingerprint is inconsistent"):
        build_config_bound_policy_forward_report(
            records,
            base_config=base,
            runtime_config=runtime,
            stress_report=_stress(base.profile_fingerprint),
            binding=_binding(),
            run_id=_RUN_ID,
        )


def test_same_contract_restart_continues_one_pending_policy_path(
    tmp_path: Path,
) -> None:
    """Later candles from an exact observer restart remain in the lifecycle."""
    base, runtime = _configs(tmp_path)
    records = _records(runtime.profile_fingerprint)
    first_bar = records[3]["payload"]["bars"]["SOL"][0]
    first_bar.update({"high": 100.5, "low": 99.9, "close": 100.0})
    identity = deepcopy(records[0])
    candle_row = deepcopy(records[3])
    for row, sequence in ((identity, 5), (candle_row, 6)):
        row["run_id"] = "observe-v49-restart"
        row["sequence"] = sequence
        row["observed_at_utc"] = f"1970-01-01T00:00:0{sequence}+00:00"
    later_bar = candle_row["payload"]["bars"]["SOL"][0]
    later_bar.update(
        {
            "timestamp_ms": 120_000,
            "open": 100.0,
            "high": 100.5,
            "low": 99.9,
            "close": 100.0,
        }
    )

    report = build_config_bound_policy_forward_report(
        [*records, identity, candle_row],
        base_config=base,
        runtime_config=runtime,
        stress_report=_stress(base.profile_fingerprint),
        binding=_binding(),
        run_id=_RUN_ID,
    )

    assert report["contract"]["compatible_run_ids"] == [
        _RUN_ID,
        "observe-v49-restart",
    ]
    assert report["contract"]["compatible_run_count"] == 2
    assert report["latest_attempts"][0]["observed_candles"] == 2
