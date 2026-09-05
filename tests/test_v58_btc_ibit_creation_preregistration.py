from __future__ import annotations

import json
from pathlib import Path


_PATH = Path(
    "docs/research-journal/"
    "v58-btc-ibit-creation-persistence-long-preregistration-20260821-v1.json"
)
_HYPOTHESIS = "V58_BTC_IBIT_CREATION_PERSISTENCE_LONG_V1"


def test_preregistration_freezes_point_in_time_report_only_experiment() -> None:
    """Freeze the exact source, signal, economics, and authority before results."""
    payload = json.loads(_PATH.read_text(encoding="utf-8"))

    assert payload["hypothesis_id"] == _HYPOTHESIS
    assert payload["status"] == (
        "preregistered_before_blackrock_source_acquisition_or_candidate_results"
    )
    assert payload["authority"] == {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
        "orders_supported": False,
    }
    source = payload["source_evidence"]["blackrock_ibit_history"]
    assert source["state"] == "not_acquired_before_preregistration"
    assert source["path"] is None
    assert source["bytes"] is None
    assert source["sha256"] is None


def test_preregistration_freezes_signal_partitions_and_scenarios() -> None:
    """Prevent post-result drift in the causal hypothesis or evaluation matrix."""
    payload = json.loads(_PATH.read_text(encoding="utf-8"))

    signal = payload["frozen_signal_contract"]
    assert signal["primary_condition"] == (
        "two consecutive strictly positive shares-outstanding changes, emitted "
        "only on transition into that persistent-creation state"
    )
    assert signal["availability_time"] == (
        "issuer as-of date plus one calendar day at 12:00 UTC"
    )
    assert signal["entry_time"] == "next Hyperliquid one-minute open"
    assert signal["parameter_grid_allowed"] is False
    assert [row["name"] for row in payload["frozen_partitions"]] == [
        "development",
        "validation",
        "pseudo_holdout",
    ]
    assert payload["required_result_rows"]["scenarios"] == [
        "nominal",
        "stress",
        "publication_delay_24h",
    ]
    assert payload["required_result_rows"]["arms"] == [
        "ibit_two_creation_persistence_candidate",
        "ibit_single_creation_onset_control",
        "ibit_two_redemption_persistence_long_placebo",
        "v58_liquidity_sweep_long_control",
        "no_action",
    ]


def test_preregistration_freezes_costs_acceptance_and_search_disclosure() -> None:
    """Bind economics and usefulness checks without pretending to own a holdout."""
    payload = json.loads(_PATH.read_text(encoding="utf-8"))

    execution = payload["frozen_execution_and_risk_contract"]
    assert execution["stop_bps"] == 60.0
    assert execution["target_bps"] == 60.0
    assert execution["maximum_hold_seconds"] == 86_400
    assert execution["leverage"] == 10.0
    friction = payload["frozen_friction_contract"]
    assert friction["entry_taker_fee_bps"] == 4.5
    assert friction["target_maker_fee_bps"] == 1.5
    assert friction["nominal_taker_slippage_bps_per_side"] == 2.0
    assert friction["stress_taker_slippage_bps_per_side"] == 5.0
    assert friction["publication_delay_sensitivity_minutes"] == 1_440
    acceptance = payload["acceptance_and_disposition_contract"]
    assert acceptance["minimum_completed_trades_per_out_of_development_partition"] == 10
    assert acceptance["automatic_live_change"] is False
    assert "previously opened" in payload["partition_disclosure"]
    assert payload["prior_search_accounting"]["candidate_family_trials"]
    assert payload["corporate_action_integrity"]["unregistered_split_action"] == (
        "technical_failure"
    )
