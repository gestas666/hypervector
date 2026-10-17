"""Exercise approved V88 runtime assembly without execution clients or networks."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from hypervector.live.bidirectional_intents import PositionState, StrategyIntent
from hypervector.live.multi_asset_live_runner import MultiAssetLiveRunner
from test_multi_asset_bidirectional_live_script import _load_module

_CONFIG = Path(
    "tests/fixtures/profiles/multi_asset_growth_first_5000_four_core_evidence_candidate_v88.toml"
)


def test_approved_four_core_router_routes_each_configured_direction() -> None:
    """The actual launcher router accepts the frozen four-core source contract."""
    script = _load_module()
    config = script.load_multi_asset_live_config(_CONFIG, mode="observe")
    router = script.build_router(config)
    intents = tuple(
        StrategyIntent(
            provider.strategy_id,
            symbol,
            side,
            1_788_702_755_030,
            100.0,
            "synthetic_offline_contract_validation",
        )
        for provider in config.providers
        for symbol in provider.execution_symbols
        for side in sorted(provider.executable_sides(symbol))
    )
    report = router.route(
        intents,
        positions={symbol: PositionState(symbol, None) for symbol in config.symbols},
    )
    assert router.symbols == config.symbols
    assert {(action.symbol, action.side) for action in report.actions} == {
        ("BTC", "long"),
        ("ETH", "long"),
        ("SOL", "short"),
        ("HYPE", "long"),
    }
    assert report.withheld == ()


def test_approved_four_core_runtime_constructs_without_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise runtime controllers with inert dependencies and the real profile."""
    script = _load_module()
    config = script.load_multi_asset_live_config(_CONFIG, mode="observe")
    monkeypatch.setattr(
        script,
        "install_process_signal_stop",
        lambda *_args: SimpleNamespace(requested=False),
    )
    forbidden = Mock(
        side_effect=AssertionError("execution clients are forbidden in this test")
    )
    monkeypatch.setattr(script, "create_armed_multi_asset_adapters", forbidden)
    engines = {symbol: Mock() for symbol in config.symbols}
    runner = script._create_runner(
        config, engines, Mock(), Mock(), Mock(), "offline-v88-assembly"
    )
    assert isinstance(runner, MultiAssetLiveRunner)
    forbidden.assert_not_called()
    for engine in engines.values():
        assert engine.mock_calls == []
