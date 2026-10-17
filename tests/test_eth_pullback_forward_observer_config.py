"""Acceptance contract for the isolated ETH pullback forward observer."""

import json
from pathlib import Path

import pytest

from hypervector.data.oxa_storage import file_evidence
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)
from hypervector.live.sol_range_onset_ledger import SolLiveLedger


PROFILE = Path("configs/research/multi_asset_eth_pullback_forward_observer_v1.toml")
STRATEGY = "eth_breakout_precompression_pullback_bidirectional_v1"
JOURNAL = Path("docs/research-journal/eth-breakout-precompression-pullback-v9.json")


def test_eth_pullback_observer_freezes_one_exact_route_and_isolated_ledger() -> None:
    """The research profile must preserve the prior route without portfolio authority."""
    config = load_multi_asset_live_config(PROFILE, mode="observe")

    assert config.profile_id == "multi_asset_eth_pullback_forward_observer_v1"
    assert config.symbols == ("ETH",)
    assert config.maximum_positions == 1
    assert config.cohort_ledger == Path(
        "data/observe/eth_pullback_forward_observer/decisions.jsonl"
    )
    assert config.stop_file == Path("data/observe/eth_pullback_forward_observer/STOP")

    assert len(config.assets) == 1
    asset = config.assets[0]
    assert asset.symbol == "ETH"
    assert asset.leverage == 5.0
    assert asset.margin_fraction == 0.03

    assert len(config.providers) == 1
    provider = config.providers[0]
    assert provider.strategy_id == STRATEGY
    assert provider.symbols == ("ETH",)
    assert provider.sides == frozenset({"long", "short"})
    assert provider.execution_symbols == ("ETH",)
    assert provider.timeframe == "1m"
    assert provider.maximum_entry_delay_seconds == 60
    assert provider.execution.stop_policy == "fixed_bps"
    assert provider.execution.stop_bps == 60.0
    assert provider.execution.target_policy == "none"
    assert provider.execution.maximum_hold_seconds == 43_200


def test_eth_pullback_research_profile_cannot_load_as_a_live_cohort() -> None:
    """Single-asset research isolation must remain unavailable to live startup."""
    with pytest.raises(MultiAssetLiveConfigError, match="at least two assets"):
        load_multi_asset_live_config(
            PROFILE,
            mode="live",
            enabled=True,
            accepts_live_risk=True,
        )


def test_eth_pullback_observer_ledger_is_accepted_as_disarmed() -> None:
    """The configured path must satisfy the durable observer-ledger boundary."""
    config = load_multi_asset_live_config(PROFILE, mode="observe")

    ledger = SolLiveLedger(
        path=config.cohort_ledger,
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id="eth-pullback-observer-contract-test",
        execution_mode="observe",
    )

    assert ledger.path == config.cohort_ledger


def test_eth_pullback_v9_preserves_cutoff_and_reports_no_entry_nearmiss() -> None:
    """Revision nine must preserve the cutoff and avoid success-shaped cadence."""
    report = json.loads(JOURNAL.read_text(encoding="utf-8"))

    assert report["revision_number"] == 9
    assert report["supersedes_revision_id"] == (
        "eth-breakout-precompression-pullback-v8"
    )
    assert report["status"] == "prospective_window_collecting_no_eligible_signal"
    assert report["strategy_id"] == STRATEGY
    assert report["prospective_window"]["start_ms"] == 1_786_974_300_000
    assert report["observations"]["evaluations"] == 39
    assert report["observations"]["eligible_evaluations"] == 0
    assert report["observations"]["readiness"]["maximum_conditions_met"] == 1
    assert (
        report["observations"]["readiness"]["independent_setup_count_claimed"] is False
    )
    assert report["interpretation"]["entry_near_miss_observed"] is False
    assert report["interpretation"]["cadence_estimate_updated"] is False
    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "v53_changed": False,
        "orders_supported": False,
        "no_parameter_retuning_during_window": True,
    }


@pytest.mark.evidence
def test_eth_pullback_v9_source_evidence_matches_current_bytes() -> None:
    """Every frozen observer generator must retain its recorded bytes."""
    report = json.loads(JOURNAL.read_text(encoding="utf-8"))
    evidence = report["source_evidence"]

    for source in evidence:
        path = Path(source["path"])
        actual = file_evidence(path)
        assert actual["sha256"] == source["sha256"]
        assert actual["bytes"] == source["bytes"]

    prefix_source = next(
        source
        for source in evidence
        if source["role"] == "immutable_cutoff_bound_observer_prefix"
    )
    prefix = json.loads(Path(prefix_source["path"]).read_text(encoding="utf-8"))
    assert prefix["signals"]["eligible_evaluations"] == 0
    assert prefix["signals"]["readiness"]["maximum_fraction"] == pytest.approx(1 / 3)
    assert prefix["technical"]["complete"] is True
