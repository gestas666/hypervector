"""An entry whose structural anchor is not adverse is journaled and never submitted."""

from dataclasses import dataclass, field

from hypervector.live.bidirectional_intents import RoutingAction
from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.live.cohort_routing_execution import (
    STRUCTURAL_ANCHOR_REFUSAL,
    execute_routing_action,
)


@dataclass
class _Engine:
    decisions: list[dict[str, object]] = field(default_factory=list)
    entries: list[dict[str, object]] = field(default_factory=list)

    def record_strategy_decision(self, payload: dict[str, object]) -> None:
        self.decisions.append(payload)

    def enter(self, **kwargs: object) -> None:
        self.entries.append(kwargs)

    def exit(self, **kwargs: object) -> None:
        raise AssertionError("exit must not be called")


def _contracts() -> dict[tuple[str, str], ProviderExecutionContract]:
    contract = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="structural_clamped_bps",
        minimum_stop_bps=20.0,
        maximum_stop_bps=250.0,
        target_policy="none",
        maximum_hold_seconds=86_400,
    )
    return {("test_channel_provider", "xyz:CCC"): contract}


def _action(side: str, anchor: float) -> RoutingAction:
    return RoutingAction(
        "enter", "test_channel_provider", "xyz:CCC", side, 1_000, 100.0, stop_anchor=anchor
    )


def test_wrong_side_anchor_is_refused_and_journaled() -> None:
    engine = _Engine()
    execute_routing_action(
        _action("long", 100.5),
        engine=engine,
        contracts=_contracts(),
        directional_sizing={},
        fallback_sizing={},
    )
    assert engine.entries == []
    assert engine.decisions[-1]["entry_refusal"] == STRUCTURAL_ANCHOR_REFUSAL
    assert engine.decisions[-1]["routing_action"] == "enter"


def test_adverse_anchor_enters_without_a_refusal_key() -> None:
    engine = _Engine()
    execute_routing_action(
        _action("short", 100.8),
        engine=engine,
        contracts=_contracts(),
        directional_sizing={},
        fallback_sizing={},
    )
    assert len(engine.entries) == 1 and engine.entries[0]["side"] == "short"
    assert "entry_refusal" not in engine.decisions[-1]
