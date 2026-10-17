"""Receipt-backed protective reductions retain exact cumulative execution evidence."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from native_replay_engine_fixture import FEE_RATE
from native_replay_partial_protective_fixture import PartialProtectiveFixture
from test_native_partial_protective_execution import CASES, assert_partial_economics
from test_native_replay_adapter import deny_external_ports

from hypervector.live.sol_protective_execution_evidence import (
    ProtectiveExecutionProgress,
    observe_protective_execution,
)
from hypervector.live.sol_range_onset_state import SolLiveSnapshot
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

__all__ = ["deny_external_ports"]


@pytest.mark.parametrize("symbol,kind,last_side", CASES)
@pytest.mark.parametrize("collateral_fraction", [Decimal("0.5"), Decimal(1)])
def test_partial_native_receipts_explain_exact_remaining_exposure(
    tmp_path: Path, symbol: str, kind: str, last_side: bool, collateral_fraction: Decimal
) -> None:
    """Prove attribution independently of collateral policy and order-remainder status."""
    replay, original = _partial_fixture(tmp_path, symbol, kind, last_side, collateral_fraction)
    oid = original.target_oid if kind == "target" else original.stop_oid
    venue = replay.engines[symbol]._adapter.reconcile()
    progress = observe_protective_execution(
        previous_size_signed=original.position_size_signed,
        current_size_signed=venue.position.size_signed,
        opened_at_ms=original.opened_at_ms,
        observed_at_ms=replay.clock.now_ms,
        stop_oid=original.stop_oid,
        target_oid=original.target_oid,
        prior=ProtectiveExecutionProgress(),
        fills=venue.fills,
    )
    assert progress.stop_exit_required is (kind == "stop")
    assert len(progress.fills) == 1 and progress.fills[0].oid == oid
    assert sum(fill.size for fill in progress.fills) == pytest.approx(
        abs(original.position_size_signed) - abs(venue.position.size_signed)
    )
    restored = ProtectiveExecutionProgress.from_payload(progress.as_payload())
    assert restored == progress
    assert (
        observe_protective_execution(
            previous_size_signed=venue.position.size_signed,
            current_size_signed=venue.position.size_signed,
            opened_at_ms=original.opened_at_ms,
            observed_at_ms=replay.clock.now_ms,
            stop_oid=original.stop_oid,
            target_oid=original.target_oid,
            prior=restored,
            fills=venue.fills,
        )
        == restored
    )
    assert_partial_economics(replay)


def test_partial_matrix_covers_each_configured_side_once() -> None:
    """Reject missing or duplicate configured directions instead of inflating case counts."""
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/multi_asset_growth_first_5000_noncrypto_live_v89.toml", mode="observe"
    )
    by_symbol = {
        asset.symbol: sorted(
            next(
                provider.executable_sides(asset.symbol)
                for provider in config.providers
                if asset.symbol in provider.execution_symbols
            )
        )
        for asset in config.assets
    }
    expected = {(symbol, "stop", side) for symbol, sides in by_symbol.items() for side in sides}
    expected.update(("BTC", "target", side) for side in by_symbol["BTC"])
    observed = [
        (symbol, kind, by_symbol[symbol][-1 if last else 0]) for symbol, kind, last in CASES
    ]
    assert len(observed) == len(set(observed))
    assert set(observed) == expected


def _partial_fixture(
    root: Path, symbol: str, kind: str, last_side: bool, collateral_fraction: Decimal
) -> tuple[PartialProtectiveFixture, SolLiveSnapshot]:
    replay = PartialProtectiveFixture(root)
    original = replay.enter_current(replay.assets[symbol], last_side=last_side)
    oid = original.target_oid if kind == "target" else original.stop_oid
    assert oid is not None and original.stop_oid is not None
    prior = replay.collateral[symbol]
    replay.fill_partial_protection(
        oid,
        remaining_collateral=replace(prior, cash_usd=prior.cash_usd * collateral_fraction),
        history_delay_ms=0,
        remainder_open=kind == "target",
        fee_rate=Decimal("0.00015") if kind == "target" else FEE_RATE,
    )
    return replay, original
