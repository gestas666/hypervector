"""Configuration tests for the HYPE-native long-authority challenger."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from hypervector.live.hype_native_breakout_provider import (
    HYPE_NATIVE_BREAKOUT_LONG_STRATEGY,
    HypeNativeBreakoutOnsetCollector,
)
from hypervector.live.cohort_provider_exit_controller import (
    CohortProviderExitController,
)
from hypervector.live.multi_asset_default_collectors import build_default_collector
from hypervector.live.multi_asset_live_config import (
    StrategyProviderConfig,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError
from hypervector.live.multi_asset_polling_contract import (
    READINESS_SEED_LOOKBACK_MINUTES,
    SOURCE_TIMEFRAMES,
)
from hypervector.live.multi_asset_signal_source import ProviderEvaluation
from hypervector.live.multi_asset_strategy_evidence import strategy_research_evidence
from hypervector.live.provider_readiness import SignalReadiness
from hypervector.live.sol_range_onset_state import SolLiveSnapshot, SolLiveState

_ROOT = Path(__file__).parents[1]
_CONFIG = (
    _ROOT / "configs/research/"
    "multi_asset_growth_first_5000_hype_native_long_challenger_v54.toml"
)


class _ExitTelemetry:
    def __init__(self) -> None:
        self.decisions: dict[str, dict[str, object]] = {}

    def recorded_provider_exit_decision(
        self, decision_id: str
    ) -> dict[str, object] | None:
        return self.decisions.get(decision_id)

    def emit_provider_exit_decision(self, payload: dict[str, object]) -> None:
        self.decisions[str(payload["decision_id"])] = dict(payload)


def test_challenger_executes_long_but_observes_both_native_sides() -> None:
    """Short native onsets remain visible and exit-capable without short entries."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    provider = next(
        row
        for row in config.providers
        if row.strategy_id == HYPE_NATIVE_BREAKOUT_LONG_STRATEGY
    )

    assert provider.symbols == ("HYPE",)
    assert provider.sides == frozenset({"long", "short"})
    assert provider.executable_sides("HYPE") == frozenset({"long"})
    assert provider.execution_symbols == ("HYPE",)
    assert provider.position_policy == "enter_and_close"
    assert provider.execution.stop_bps == 80.0
    assert provider.execution.maximum_hold_seconds == 28_800
    assert provider.execution.maximum_hold_policy == "fixed"
    assert provider.execution.provider_recipe_exit_policy == "honor"
    assert SOURCE_TIMEFRAMES[HYPE_NATIVE_BREAKOUT_LONG_STRATEGY] == "1m"
    assert READINESS_SEED_LOOKBACK_MINUTES[HYPE_NATIVE_BREAKOUT_LONG_STRATEGY] == 2
    assert (
        HYPE_NATIVE_BREAKOUT_LONG_STRATEGY,
        "HYPE",
        "short",
    ) not in config.executable_provider_directions


def test_challenger_factory_builds_directional_native_collector() -> None:
    """The default registry recognizes the distinct long-authority identity."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    provider = next(
        row
        for row in config.providers
        if row.strategy_id == HYPE_NATIVE_BREAKOUT_LONG_STRATEGY
    )

    collector = build_default_collector(provider, config, _ROOT)

    assert isinstance(collector, HypeNativeBreakoutOnsetCollector)


def test_challenger_tui_evidence_is_directional_and_report_only() -> None:
    """Cockpit metadata must not inherit the stale bidirectional approval claim."""
    evidence = strategy_research_evidence(HYPE_NATIVE_BREAKOUT_LONG_STRATEGY, "HYPE")

    assert evidence.research_state == "directional_challenger_report_only"
    assert evidence.confidence == "low"
    assert "long-only" in evidence.summary
    assert evidence.evidence_source.endswith(
        "v54-hype-native-directional-authority-challenger-v1.json"
    )


def test_challenger_rejects_bidirectional_execution_override(tmp_path: Path) -> None:
    """The challenger cannot silently restore weak short entry authority."""
    malformed = _CONFIG.read_text().replace(
        'execution_side_overrides = { HYPE = ["long"] }',
        'execution_side_overrides = { HYPE = ["long", "short"] }',
    )
    path = tmp_path / "malformed.toml"
    path.write_text(malformed)

    with pytest.raises(MultiAssetLiveConfigError, match="long-authority"):
        load_multi_asset_live_config(path, mode="observe")


def test_short_onset_closes_bound_long_without_short_entry() -> None:
    """The persisted v3 plan honors its exit-only opposite native onset."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    provider = next(
        row
        for row in config.providers
        if row.strategy_id == HYPE_NATIVE_BREAKOUT_LONG_STRATEGY
    )
    controller = CohortProviderExitController(
        symbols=("HYPE",),
        engines={"HYPE": SimpleNamespace(snapshot=_open_long(provider))},
        telemetry=_ExitTelemetry(),
    )

    closing, actions = controller.actions(
        observed_ms=200,
        reference_prices={"HYPE": 41.0},
        evaluations={(provider.strategy_id, "HYPE"): _short_exit(provider.strategy_id)},
        excluded_symbols=set(),
    )

    assert closing == {"HYPE"}
    assert [(row.action, row.side, row.exit_reason) for row in actions] == [
        ("close", "long", "opposite_native_onset")
    ]


def _open_long(provider: StrategyProviderConfig) -> SolLiveSnapshot:
    plan = provider.execution.bind(
        strategy_id=provider.strategy_id,
        stop_anchor=None,
    )
    return SolLiveSnapshot(
        state=SolLiveState.OPEN,
        entry_oid=7,
        stop_oid=8,
        position_size_signed=1.0,
        opened_at_ms=100,
        execution_plan=plan,
    )


def _short_exit(strategy_id: str) -> ProviderEvaluation:
    readiness = SignalReadiness(
        "short",
        0,
        1,
        ("entry_authority_long_only",),
        ("SHORT EXIT ONLY",),
        {},
    )
    return ProviderEvaluation(
        strategy_id=strategy_id,
        symbol="HYPE",
        decision_time_ms=200,
        reference_price=40.0,
        decision_action="close_long",
        eligible=False,
        reason="opposite_native_onset_exit_only",
        side="short",
        readiness=readiness,
        exit_sides=frozenset({"long"}),
        exit_reason="opposite_native_onset",
    )
