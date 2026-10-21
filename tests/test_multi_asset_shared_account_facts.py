"""Cross-namespace shared-account telemetry regressions."""

import pytest

from hypervector.live.hyperliquid_protocol import (
    SolAccountSnapshot,
    SolPositionSnapshot,
    SolReconciliationSnapshot,
)
from hypervector.live.multi_asset_live_runner_support import (
    MultiAssetLiveRunnerError,
    shared_account_facts,
)


def _venue(margin: float, notional: float) -> SolReconciliationSnapshot:
    """Build one unified-account namespace projection."""
    position = SolPositionSnapshot(0.0, None, None, 0.0, 0.0, 0.0, None, None)
    account = SolAccountSnapshot(
        4_984.50,
        4_512.16,
        margin,
        notional,
        position,
        "spot_clearinghouse_state",
    )
    return SolReconciliationSnapshot(account, (), ())


def test_shared_account_sums_one_total_per_perp_namespace() -> None:
    """Core and HIP-3 exposure combine without per-symbol duplication."""
    symbols = ("BTC", "ETH", "HYPE", "xyz:AAA", "xyz:BBB")
    venues = (
        _venue(472.0, 4_972.0),
        _venue(472.0, 4_972.0),
        _venue(472.0, 4_972.0),
        _venue(100.0, 1_000.0),
        _venue(100.0, 1_000.0),
    )

    account = shared_account_facts(symbols, venues)

    assert account.account_value_usd == 4_984.50
    assert account.withdrawable_usd == 4_512.16
    assert account.total_margin_used_usd == 572.0
    assert account.total_notional_position_usd == 5_972.0


def test_shared_account_rejects_symbol_snapshot_mismatch() -> None:
    """Namespace aggregation cannot silently omit a reconciliation row."""
    with pytest.raises(
        MultiAssetLiveRunnerError,
        match="symbols and venue snapshots must agree",
    ):
        shared_account_facts(("BTC", "xyz:AAA"), (_venue(1.0, 10.0),))
