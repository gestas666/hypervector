"""Adversarial native boundaries for the remaining partial-stop exit obligation."""

from decimal import Decimal
from pathlib import Path

import pytest
from test_native_partial_protective_recovery import assert_closed_economics, restart
from test_native_protective_execution_progress import _partial_fixture
from test_native_replay_adapter import deny_external_ports

from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError
from hypervector.live.sol_range_onset_state import SolLiveState

__all__ = ["deny_external_ports"]


@pytest.mark.parametrize("during_rejection", ["unchanged", "partial_target", "full_target"])
def test_rejected_remainder_close_preserves_obligation_and_accounts_for_racing_target(
    tmp_path: Path, during_rejection: str
) -> None:
    """A rejected IOC must retain its pending exit or adopt exact racing protective receipts."""
    replay, original = _partial_fixture(tmp_path, "BTC", "stop", False, Decimal("0.5"))
    real_close = replay._exchange.market_close.side_effect

    def reject(*args: object, **kwargs: object) -> dict[str, object]:
        if during_rejection == "full_target":
            replay.fill_owned_order(original.target_oid, history_delay_ms=0)
        elif during_rejection == "partial_target":
            replay.fill_partial_protection(
                original.target_oid,
                remaining_collateral=replay.collateral["BTC"],
                history_delay_ms=0,
                remainder_open=True,
                fee_rate=Decimal("0.00015"),
            )
        return {
            "status": "ok",
            "response": {
                "type": "order",
                "data": {"statuses": [{"error": "fixture IOC rejected before acceptance"}]},
            },
        }

    replay._exchange.market_close.side_effect = reject
    engine = replay.engines["BTC"]
    engine.reconcile_telemetry(
        funding_start_time_ms=original.opened_at_ms, funding_end_time_ms=replay.clock.now_ms
    )
    assert replay._exchange.market_close.call_count == 1
    if during_rejection == "full_target":
        assert_closed_economics(replay, "BTC")
        return
    assert engine.snapshot.state is SolLiveState.EXIT_PENDING
    assert engine.snapshot.protective_progress.stop_exit_required
    assert engine.snapshot.opened_at_ms == original.opened_at_ms
    assert engine.snapshot.position_size_signed == float(
        replay.account.snapshot().positions["BTC"].quantity_signed
    )
    replay._exchange.market_close.side_effect = real_close
    restart(replay, "BTC")
    assert replay._exchange.market_close.call_count == 2
    assert_closed_economics(replay, "BTC")


@pytest.mark.parametrize("corruption", ["unknown", "duplicate", "side", "reduce_only", "size"])
@pytest.mark.parametrize("on_restart", [False, True])
def test_partial_target_rejects_invalid_remaining_venue_orders_without_mutations(
    tmp_path: Path, corruption: str, on_restart: bool
) -> None:
    """Exact fill credit cannot authorize adoption of a contradictory remaining bracket."""
    replay, original = _partial_fixture(tmp_path, "BTC", "target", False, Decimal("0.5"))

    def corrupted(address: str, dex: str) -> list[dict[str, object]]:
        rows = replay._visible_orders(address, dex)
        stop = next(row for row in rows if row["oid"] == original.stop_oid)
        if corruption == "duplicate":
            rows.append(dict(stop))
        else:
            key, value = {
                "unknown": ("oid", 99999),
                "side": ("side", "B"),
                "reduce_only": ("reduceOnly", False),
                "size": ("sz", "0.00001"),
            }[corruption]
            stop[key] = value
        return rows

    replay._info.frontend_open_orders.side_effect = corrupted
    before = list(replay.mutations)
    with pytest.raises(SolLiveEngineError):
        if on_restart:
            restart(replay, "BTC")
        else:
            replay.engines["BTC"].reconcile_telemetry(
                funding_start_time_ms=original.opened_at_ms, funding_end_time_ms=replay.clock.now_ms
            )
    assert replay.mutations == before
