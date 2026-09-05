"""Frozen contract tests for the V58 BTC Deribit option-flow long trial."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


_JOURNAL = Path("docs/research-journal")
_QUALIFICATION = _JOURNAL / (
    "v58-btc-deribit-option-flow-source-qualification-20260822-v1.json"
)
_PREREGISTRATION = _JOURNAL / (
    "v58-btc-deribit-option-flow-long-preregistration-20260822-v1.json"
)
_PREREGISTRATION_V2 = _JOURNAL / (
    "v58-btc-deribit-option-flow-long-preregistration-20260822-v2.json"
)
_CADENCE_AUDIT = _JOURNAL / (
    "v58-btc-option-flow-candle-cadence-audit-20260822-v1.json"
)
_PREREGISTRATION_V3 = _JOURNAL / (
    "v58-btc-deribit-option-flow-long-preregistration-20260822-v3.json"
)
_HORIZON_AUDIT = _JOURNAL / (
    "v58-btc-option-flow-execution-horizon-audit-20260822-v1.json"
)


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_preregistration_cannot_authorize_a_live_change() -> None:
    """Historical research must never acquire live deployment authority."""
    record = _load(_PREREGISTRATION)

    assert record["execution_authority"] == "none"
    assert record["automatic_promotion"] is False
    assert record["runtime_strategy_changed"] is False
    assert record["orders_supported"] is False
    assert record["live_change_authorized"] is False


def test_preregistration_binds_source_feature_economics_and_acceptance() -> None:
    """Every candidate-defining invariant must remain explicit and frozen."""
    record = _load(_PREREGISTRATION)
    qualification = record["source_qualification"]
    source = record["source_contract"]
    feature = record["feature_contract"]
    strategy = record["strategy_contract"]
    acceptance = record["acceptance"]

    assert record["hypothesis_id"] == "V58_BTC_DERIBIT_OTM_DIRECTIONAL_FLOW_LONG_V1"
    assert qualification["sha256"] == _sha256(_QUALIFICATION)
    assert qualification["bytes"] == _QUALIFICATION.stat().st_size
    assert source["deribit_trades"]["start_utc"] == "2025-04-01T00:00:00Z"
    assert source["deribit_trades"]["end_utc"] == "2026-08-01T00:00:00Z"
    assert source["deribit_trades"]["excluded_trade_classes"] == [
        "block_trade_id_nonnull",
        "block_rfq_id_nonnull",
        "combo_id_nonnull",
        "combo_trade_id_nonnull",
    ]
    assert feature["threshold"] == {
        "rolling_prior_hours": 2160,
        "minimum_prior_hours": 1440,
        "bullish_quantile": 0.99,
        "bearish_quantile": 0.01,
        "current_hour_excluded": True,
    }
    assert strategy["protective_exit"] == {
        "stop_bps": 100.0,
        "target_bps": 200.0,
        "maximum_hold_hours": 24,
    }
    assert acceptance["minimum_primary_trades_per_oos_partition"] == 10
    assert acceptance["one_hour_delay_survival_required"] is True
    assert acceptance["live_promotion_authorized_by_acceptance"] is False


def test_preregistration_discloses_prior_search_and_forbids_retuning() -> None:
    """The new input must not disguise another search over opened BTC paths."""
    record = _load(_PREREGISTRATION)
    disclosure = record["multiple_testing_disclosure"]

    assert disclosure["all_existing_btc_price_partitions_previously_opened"] is True
    assert disclosure["within_family_trial_number"] == 1
    assert disclosure["parameter_grid_permitted"] is False
    assert disclosure["nearby_retuning_after_outcome"] is False
    assert record["outcomes_inspected_before_preregistration"] is False
    assert record["candidate_signal_counts_inspected"] is False
    assert record["candidate_forward_returns_inspected"] is False
    assert record["candidate_trade_outcomes_inspected"] is False


def test_v2_changes_only_outcome_blind_source_window_and_partitions() -> None:
    """The clean source revision must preserve every economic candidate choice."""
    original = _load(_PREREGISTRATION)
    revised = _load(_PREREGISTRATION_V2)

    for field in (
        "feature_contract",
        "strategy_contract",
        "trial_arms",
        "control_contracts",
        "economics",
        "acceptance",
        "multiple_testing_disclosure",
    ):
        assert revised[field] == original[field]
    source = revised["source_contract"]
    assert source["deribit_trades"]["acquisition_start_utc"] == ("2025-04-01T00:00:00Z")
    assert source["deribit_trades"]["start_utc"] == "2025-08-01T00:00:00Z"
    assert source["hyperliquid_btc_minutes"]["start_utc"] == ("2025-08-01T00:00:00Z")
    assert source["hyperliquid_funding"]["start_utc"] == "2025-08-01T00:00:00Z"
    assert revised["partitions"]["source_warmup"] == [
        "2025-08-01T00:00:00Z",
        "2025-10-01T00:00:00Z",
    ]
    assert revised["partitions"]["development_entries"] == [
        "2025-10-01T00:00:00Z",
        "2025-12-01T00:00:00Z",
    ]
    for field in (
        "first_purge",
        "validation_entries",
        "second_purge",
        "pseudo_holdout_entries",
    ):
        assert revised["partitions"][field] == original["partitions"][field]


def test_v2_binds_cadence_evidence_and_retains_no_live_authority() -> None:
    """The revised source must be immutable, outcome-blind, and report-only."""
    revised = _load(_PREREGISTRATION_V2)
    cadence = revised["source_revision"]["candle_cadence_audit"]

    assert cadence["sha256"] == _sha256(_CADENCE_AUDIT)
    assert cadence["bytes"] == _CADENCE_AUDIT.stat().st_size
    assert revised["source_revision"]["candidate_outcomes_opened"] is False
    assert revised["outcomes_inspected_before_preregistration"] is False
    assert revised["candidate_signal_counts_inspected"] is False
    assert revised["candidate_forward_returns_inspected"] is False
    assert revised["candidate_trade_outcomes_inspected"] is False
    assert revised["execution_authority"] == "none"
    assert revised["automatic_promotion"] is False
    assert revised["runtime_strategy_changed"] is False
    assert revised["orders_supported"] is False
    assert revised["live_change_authorized"] is False


def test_v3_adds_only_required_post_entry_execution_horizon() -> None:
    """A 24-hour exit horizon must not alter candidate or entry definitions."""
    revised = _load(_PREREGISTRATION_V2)
    horizon = _load(_PREREGISTRATION_V3)

    for field in (
        "feature_contract",
        "strategy_contract",
        "trial_arms",
        "control_contracts",
        "economics",
        "acceptance",
        "multiple_testing_disclosure",
        "partitions",
    ):
        assert horizon[field] == revised[field]
    assert (
        horizon["source_contract"]["deribit_trades"]
        == (revised["source_contract"]["deribit_trades"])
    )
    candles = horizon["source_contract"]["hyperliquid_btc_minutes"]
    funding = horizon["source_contract"]["hyperliquid_funding"]
    assert candles["entry_source_end_utc"] == "2026-08-01T00:00:00Z"
    assert candles["execution_end_utc"] == "2026-08-02T00:00:00Z"
    assert funding["entry_source_end_utc"] == "2026-08-01T00:00:00Z"
    assert funding["execution_end_utc"] == "2026-08-02T00:00:00Z"
    evidence = horizon["execution_horizon_revision"]["audit"]
    assert evidence["sha256"] == _sha256(_HORIZON_AUDIT)
    assert evidence["bytes"] == _HORIZON_AUDIT.stat().st_size
    assert horizon["execution_horizon_revision"]["candidate_outcomes_opened"] is False


def test_v3_remains_outcome_blind_and_report_only() -> None:
    """Correcting lifecycle coverage cannot grant strategy or live authority."""
    record = _load(_PREREGISTRATION_V3)

    assert record["outcomes_inspected_before_preregistration"] is False
    assert record["candidate_signal_counts_inspected"] is False
    assert record["candidate_forward_returns_inspected"] is False
    assert record["candidate_trade_outcomes_inspected"] is False
    assert record["execution_authority"] == "none"
    assert record["automatic_promotion"] is False
    assert record["runtime_strategy_changed"] is False
    assert record["orders_supported"] is False
    assert record["live_change_authorized"] is False
