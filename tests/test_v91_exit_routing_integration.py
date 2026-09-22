"""Exercise canonical evidence through the real configured-exit routing boundary."""

from dataclasses import dataclass, replace
from unittest.mock import Mock

import pytest

from test_cohort_adaptive_exit_controller import bars, book, engine
from test_cohort_regime_routing import _evaluation
from hypervector.live.cohort_adaptive_exit_journal import AdaptiveExitJournal
from hypervector.live.cohort_profit_lock_controller import CohortProfitLockController
from hypervector.live.cohort_route_cycle import admitted_intents, configured_exit_batch
from hypervector.live.hyperliquid_protocol import SolBookSnapshot, SolReconciliationSnapshot
from hypervector.live.multi_asset_intent_poller import CohortIntentPoll
from hypervector.live.sol_range_onset_state import SolLiveSnapshot


@dataclass
class OwnedEngine:
    """Expose the production controller's exact owned lifecycle inputs."""

    snapshot: SolLiveSnapshot
    latest_book: SolBookSnapshot


@pytest.mark.parametrize("side,trend,opposed,peak,cross", [
    ("long", "TREND_UP", "TREND_DOWN", 101.0, 100.6),
    ("short", "TREND_DOWN", "TREND_UP", 99.0, 99.4),
])
def test_canonical_deterioration_routes_persisted_exit_and_suppresses_entry(
    side: str, trend: str, opposed: str, peak: float, cross: float,
) -> None:
    """Real batch assembly passes regime evidence and preserves close precedence."""
    now = 1_260_000
    owner = OwnedEngine(engine(side).snapshot, book(now, peak))
    sink = Mock()
    sink.adaptive_exit_journal = AdaptiveExitJournal([], Mock())
    controller = CohortProfitLockController(symbols=("SOL",), engines={"SOL": owner}, telemetry=sink)
    timer, recipe = Mock(), Mock()
    timer.actions.return_value = recipe.actions.return_value = (set(), ())
    venue = Mock(spec=SolReconciliationSnapshot)
    venue.position.entry_price = 100.0
    batch = None
    for stamp, direction, price in [(now, trend, peak), (now + 15_000, opposed, cross)]:
        owner.latest_book = book(stamp, price)
        evaluation = replace(_evaluation(direction, direction, direction, decision_time_ms=stamp), symbol="SOL")
        batch = configured_exit_batch(
            symbols=("SOL",), observed_ms=stamp,
            poll=CohortIntentPoll((), {"SOL": price}, exit_bars={"SOL": bars(stamp)}),
            venues=(venue,), evaluations={(evaluation.strategy_id, "SOL"): evaluation},
            maximum_hold=timer, recipe_exit=recipe, profit_lock=controller,
        )
        if stamp == now:
            assert batch.actions == ()
    assert batch is not None and batch.closing_symbols == {"SOL"}
    assert len(batch.actions) == 1 and batch.actions[0].exit_reason == "adaptive_profit_floor"
    recorded = sink.adaptive_exit_journal.recorded("SOL:7:1200000")
    assert recorded["alignment"] == -1.0 and recorded["state"]["exit_reason"] == "adaptive_profit_floor"
    assert admitted_intents((Mock(symbol="SOL"),), closing_symbols=batch.closing_symbols,
                            operator_symbols=set(), positions={}, executable_pairs=frozenset(),
                            executable_directions=frozenset(), transition_drain_active=False) == ()
