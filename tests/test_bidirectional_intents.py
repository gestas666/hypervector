"""Portfolio routing tests for multi-asset bidirectional strategy intents."""

from __future__ import annotations

import pytest

from hypervector.live.bidirectional_intents import (
    BidirectionalIntentRouter,
    PositionState,
    StrategyCapability,
    StrategyIntent,
)

_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")


def _capabilities() -> tuple[StrategyCapability, ...]:
    return tuple(
        StrategyCapability(
            strategy_id="hulk_bidirectional",
            symbol=symbol,
            sides=frozenset({"long", "short"}),
            priority=10,
        )
        for symbol in _SYMBOLS
    )


def _intent(
    symbol: str,
    side: str,
    *,
    strategy: str = "hulk_bidirectional",
    regime_score: float | None = None,
) -> StrategyIntent:
    return StrategyIntent(
        strategy_id=strategy,
        symbol=symbol,
        side=side,
        decision_time_ms=1_785_600_000_000,
        reference_price=100.0,
        reason="completed_signal",
        regime_alignment_score=regime_score,
        regime_alignment_stance=(
            "directionally_supported"
            if regime_score is not None and regime_score >= 0.5
            else "directionally_opposed"
            if regime_score is not None and regime_score <= -0.5
            else "mixed_or_transition"
            if regime_score is not None
            else None
        ),
        regime_decision_time_ms=(
            1_785_600_000_000 if regime_score is not None else None
        ),
        regime_alignment_basis=(
            "canonical_1m_5m_15m_1_3_2_v1" if regime_score is not None else None
        ),
    )


def _flat() -> dict[str, PositionState]:
    return {symbol: PositionState(symbol=symbol, side=None) for symbol in _SYMBOLS}


@pytest.mark.parametrize("symbol", _SYMBOLS)
@pytest.mark.parametrize("side", ["long", "short"])
def test_every_enabled_symbol_routes_both_sides(symbol: str, side: str) -> None:
    """A declared bidirectional provider retains both routing directions."""
    router = BidirectionalIntentRouter(_capabilities(), maximum_positions=2)

    report = router.route((_intent(symbol, side),), positions=_flat())

    assert [
        (action.symbol, action.side, action.action) for action in report.actions
    ] == [(symbol, side, "enter")]
    assert report.withheld == ()


@pytest.mark.parametrize("side", ["long", "short"])
def test_one_sided_capability_routes_only_its_declared_direction(side: str) -> None:
    """A directional provider works without inventing opposite-side support."""
    capabilities = (
        StrategyCapability(
            strategy_id="directional",
            symbol="BTC",
            sides=frozenset({side}),
            priority=10,
        ),
    )

    router = BidirectionalIntentRouter(capabilities, maximum_positions=1)
    positions = {"BTC": PositionState("BTC", None)}
    report = router.route(
        (_intent("BTC", side, strategy="directional"),), positions=positions
    )
    assert [(action.symbol, action.side, action.action) for action in report.actions] == [
        ("BTC", side, "enter")
    ]
    opposite = "short" if side == "long" else "long"
    with pytest.raises(ValueError, match="undeclared strategy direction"):
        router.route(
            (_intent("BTC", opposite, strategy="directional"),), positions=positions
        )


def test_two_coins_may_enter_but_third_is_attributed_as_capacity_conflict() -> None:
    """Shared capital permits two distinct symbols without stacking a third."""
    router = BidirectionalIntentRouter(_capabilities(), maximum_positions=2)
    intents = (
        _intent("BTC", "long"),
        _intent("ETH", "short"),
        _intent("SOL", "long"),
    )

    report = router.route(intents, positions=_flat())

    assert [(action.symbol, action.side) for action in report.actions] == [
        ("BTC", "long"),
        ("ETH", "short"),
    ]
    assert [(item.intent.symbol, item.reason) for item in report.withheld] == [
        ("SOL", "portfolio_position_capacity")
    ]


def test_open_symbol_cannot_stack_and_opposite_intent_closes_before_reversal() -> None:
    """One-way positions never add or reverse within one decision cycle."""
    router = BidirectionalIntentRouter(_capabilities(), maximum_positions=2)
    positions = _flat()
    positions["BTC"] = PositionState(symbol="BTC", side="long")

    same = router.route((_intent("BTC", "long"),), positions=positions)
    opposite = router.route((_intent("BTC", "short"),), positions=positions)

    assert same.actions == ()
    assert same.withheld[0].reason == "same_direction_position_open"
    assert opposite.actions[0].action == "close"
    assert opposite.actions[0].side == "short"


def test_explicit_provider_priority_resolves_same_symbol_conflict() -> None:
    """Conflicting signals are attributed and resolved without hidden scoring."""
    capabilities = (
        StrategyCapability(
            "hulk_bidirectional",
            "BTC",
            frozenset({"long", "short"}),
            10,
        ),
        StrategyCapability(
            "range_onset",
            "BTC",
            frozenset({"long", "short"}),
            20,
        ),
    )
    router = BidirectionalIntentRouter(capabilities, maximum_positions=2)

    report = router.route(
        (
            _intent("BTC", "long"),
            _intent("BTC", "short", strategy="range_onset"),
        ),
        positions={"BTC": PositionState("BTC", None)},
    )

    assert report.actions[0].strategy_id == "range_onset"
    assert report.actions[0].side == "short"
    assert report.withheld[0].reason == "lower_provider_priority"


def test_regime_alignment_resolves_conflict_before_static_provider_priority() -> None:
    """Causal regime context can rank conflicts without gating lone signals."""
    capabilities = (
        StrategyCapability(
            "hulk_bidirectional",
            "BTC",
            frozenset({"long", "short"}),
            30,
        ),
        StrategyCapability(
            "range_onset",
            "BTC",
            frozenset({"long", "short"}),
            10,
        ),
    )
    router = BidirectionalIntentRouter(capabilities, maximum_positions=1)
    opposed = _intent("BTC", "long", regime_score=-1.0)
    aligned = _intent(
        "BTC",
        "short",
        strategy="range_onset",
        regime_score=1.0,
    )

    report = router.route(
        (opposed, aligned),
        positions={"BTC": PositionState("BTC", None)},
    )

    assert report.actions[0].strategy_id == "range_onset"
    assert report.actions[0].regime_alignment_score == 1.0
    assert [(item.intent, item.reason) for item in report.withheld] == [
        (opposed, "lower_regime_alignment")
    ]


def test_lone_opposed_intent_remains_routable() -> None:
    """Regime weighting is a preference and never becomes an implicit gate."""
    router = BidirectionalIntentRouter(_capabilities(), maximum_positions=2)
    intent = _intent("BTC", "long", regime_score=-1.0)

    report = router.route((intent,), positions=_flat())

    assert [action.side for action in report.actions] == ["long"]
    assert report.withheld == ()


def test_regime_preference_can_select_an_opposite_intent_exit_during_conflict() -> None:
    """Conflict weighting applies symmetrically to entry and exit selection."""
    capabilities = (
        StrategyCapability(
            "hulk_bidirectional",
            "BTC",
            frozenset({"long", "short"}),
            30,
        ),
        StrategyCapability(
            "range_onset",
            "BTC",
            frozenset({"long", "short"}),
            10,
        ),
    )
    router = BidirectionalIntentRouter(capabilities, maximum_positions=1)

    report = router.route(
        (
            _intent("BTC", "long", regime_score=-1.0),
            _intent(
                "BTC",
                "short",
                strategy="range_onset",
                regime_score=1.0,
            ),
        ),
        positions={"BTC": PositionState("BTC", "long")},
    )

    assert [(action.action, action.side) for action in report.actions] == [
        ("close", "short")
    ]
    assert report.withheld[0].reason == "lower_regime_alignment"


def test_open_position_gives_eligible_opposite_exit_precedence() -> None:
    """An eligible opposite closes before a stronger same-side hold intent."""
    capabilities = (
        StrategyCapability(
            "hulk_bidirectional", "BTC", frozenset({"long", "short"}), 30
        ),
        StrategyCapability("range_onset", "BTC", frozenset({"long", "short"}), 10),
    )
    router = BidirectionalIntentRouter(capabilities, maximum_positions=1)

    report = router.route(
        (
            _intent("BTC", "long", regime_score=1.0),
            _intent("BTC", "short", strategy="range_onset", regime_score=-1.0),
        ),
        positions={"BTC": PositionState("BTC", "long")},
    )

    assert [(action.action, action.side) for action in report.actions] == [
        ("close", "short")
    ]
    assert report.withheld[0].reason == "opposite_position_exit_precedence"


def test_namespaced_hip3_symbol_is_preserved_in_intent_and_position() -> None:
    """Portfolio routing preserves exact builder-perp venue identity."""
    intent = StrategyIntent(
        strategy_id="hip3_swing",
        symbol="xyz:AAA",
        side="long",
        decision_time_ms=1,
        reference_price=6_000.0,
        reason="alignment",
    )
    position = PositionState("xyz:AAA", None)

    assert intent.symbol == "xyz:AAA"
    assert position.symbol == "xyz:AAA"
