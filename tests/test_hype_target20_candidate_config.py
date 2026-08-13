"""Live-contract tests for the prospective HYPE target-first candidate."""

import json
from pathlib import Path

import pandas as pd

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_intent_poller import (
    ConfiguredMultiAssetIntentPoller,
)
from hypervector.live.multi_asset_strategy_evidence import (
    strategy_research_evidence,
)

_PROFILE = Path("configs/multi_asset_bidirectional_hype_target20_candidate.toml")
_STRATEGY = "hype_breakout_relaxed_target20_60m_bidirectional_v3"


def test_target20_profile_preserves_entry_risk_and_changes_exit_capture() -> None:
    """V3 must differ from V2 only through identity and target-first exit."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    provider = next(row for row in config.providers if row.strategy_id == _STRATEGY)
    asset = next(row for row in config.assets if row.symbol == "HYPE")

    assert provider.symbols == ("HYPE",)
    assert provider.sides == frozenset({"long", "short"})
    assert provider.execution_symbols == ("HYPE",)
    assert provider.position_policy == "flat_entry_only"
    assert provider.execution.stop_bps == 80.0
    assert provider.execution.target_policy == "fixed_bps"
    assert provider.execution.target_bps == 20.0
    assert provider.execution.maximum_hold_seconds == 3_600
    assert asset.leverage == 5.0
    assert asset.max_notional_usd == 25.0


def test_default_poller_builds_the_target20_collector(tmp_path: Path) -> None:
    """The live runner must have a concrete collector for the V3 provider."""
    dependency = tmp_path / "backtest_lab"
    dependency.mkdir()
    config = load_multi_asset_live_config(_PROFILE, mode="observe")

    poller = ConfiguredMultiAssetIntentPoller.with_default_collectors(
        config=config,
        fetch_bars=lambda *_args, **_kwargs: pd.DataFrame(),
        backtest_lab_root=dependency,
    )

    assert poller is not None


def test_target20_mapping_reports_the_frozen_forward_evidence() -> None:
    """The TUI evidence card must not label the exact V3 mapping unreviewed."""
    evidence = strategy_research_evidence(_STRATEGY, "HYPE")

    assert evidence.research_state == "prospective_target_first_falsified_n3"
    assert evidence.confidence == "low"
    assert "-15.5073 bps" in evidence.summary
    assert "PF 0.6738" in evidence.summary
    assert "2W/1L" in evidence.summary
    assert "long-only" in evidence.summary
    assert "not staged" in evidence.summary


def test_target20_static_card_matches_immutable_n3_artifact() -> None:
    """Static TUI evidence must remain bound to the exact frozen N3 report."""
    evidence = strategy_research_evidence(_STRATEGY, "HYPE")
    artifact = json.loads(Path(evidence.evidence_source).read_text())
    summary = artifact["forward_challenger"]["summary"]

    assert summary["resolved"] == 3
    assert summary["wins"] == 2
    assert summary["losses"] == 1
    assert summary["short_resolved"] == 0
    assert summary["total_net_return_bps"] == -15.507308955862323
    assert summary["profit_factor"] == 0.6737817202889027
