"""Independent retained cash, fills, funding and venue fields constrain the bridge."""

from datetime import datetime
from decimal import Decimal, localcontext
from fractions import Fraction
import json
from pathlib import Path
from unittest.mock import create_autospec

import pytest

from hypervector.live.hyperliquid_btc_adapter import BtcHyperliquidAdapter
from hypervector.live.hyperliquid_protocol import HyperliquidExchangeProtocol, HyperliquidInfoProtocol
from hypervector.research.native_replay_account import ExactFillAccount
from hypervector.research.native_replay_events import FillEvent, FundingEvent, Stamp
from hypervector.research.native_replay_unified import (
    IsolatedCollateral,
    MaintenanceTier,
    project_unified_account,
)
from test_native_replay_adapter import ADDRESS
from test_native_replay_adapter import deny_external_ports as deny_external_ports

D = Decimal
SOURCE = Path(__file__).parent / "fixtures/native_replay_sndk_unified_20260912.json"
SYMBOLS = ("BTC", "ETH", "SOL", "HYPE", "xyz:SPCX", "xyz:SNDK", "xyz:BRENTOIL")


def recovered_source_account() -> tuple[ExactFillAccount, dict[str, object], Decimal, int]:
    """Reconstruct at the capture boundary; no earlier decision consumes late marks."""
    source = json.loads(SOURCE.read_text())
    fill = source["fills"][0]
    position = source["perp_states"]["xyz"]["assetPositions"][0]["position"]
    initial = D(str(source["pre_entry_reconciliation"]["payload"]["account_value_usd"]))
    assert initial == D("4808.47453649") and fill["startPosition"] == "0.0"
    now = int(datetime.fromisoformat(source["captured_at_utc"]).timestamp() * 1000)
    with localcontext() as context:
        context.prec = 50
        mark = D(position["positionValue"]) / abs(D(position["szi"]))
    account = ExactFillAccount(initial, SYMBOLS)
    account.mark(Stamp(now, 0), source_time_ms=now, prices={"xyz:SNDK": mark})
    ack = source["entry_acknowledgement"]["payload"]
    account.apply_fill(
        FillEvent(
            str(fill["tid"]),
            str(fill["oid"]),
            fill["coin"],
            "sell",
            D(fill["sz"]),
            D(fill["px"]),
            D(fill["fee"]),
            D(position["leverage"]["value"]),
            ack["decision_time_ms"],
            ack["submission_observed_at_ms"],
            fill["time"],
            Stamp(now, 1),
            False,
        )
    )
    for index, row in enumerate(source["funding"], 2):
        account.apply_funding(
            FundingEvent(
                f"{row['time']}:{row['hash']}",
                row["delta"]["coin"],
                D(row["delta"]["usdc"]),
                row["time"],
                Stamp(now, index),
            )
        )
    return account, source, mark, now


def test_independent_pre_entry_cash_reconciles_native_sndk_snapshot() -> None:
    """One entry and 33 cash settlements reproduce the independently captured account."""
    account, source, mark, now = recovered_source_account()
    view = account.snapshot()
    position = view.positions["xyz:SNDK"]
    collateral = position.allocated_initial_margin_usd - view.fees_usd + view.funding_usd
    assert source["metadata"]["asset"]["marginTableId"] == 10
    assert source["metadata"]["collateralToken"] == 0
    wire = project_unified_account(
        view,
        symbols=SYMBOLS,
        marks={"xyz:SNDK": mark},
        collateral={"xyz:SNDK": IsolatedCollateral(collateral, (MaintenanceTier(D(0), D("0.05"), D(0)),))},
        additional_hold_usd=D(0),
        observed_time_ms=now,
    )
    expected = source["perp_states"]["xyz"]["assetPositions"][0]["position"]
    actual = wire.perp_states["xyz"]["assetPositions"][0]["position"]
    for field in ("szi", "entryPx", "positionValue", "unrealizedPnl", "marginUsed"):
        assert D(actual[field]) == D(expected[field]), field
    assert D(actual["leverage"]["rawUsd"]) == D(expected["leverage"]["rawUsd"])
    assert abs(D(actual["liquidationPx"]) - D(expected["liquidationPx"])) < D("1e-10")
    balance = wire.spot_state["balances"][0]
    for state in (source["spot_before"], source["spot_after"]):
        for field in ("total", "hold"):
            assert D(balance[field]) == D(state["balances"][0][field])
    assert view.funding_usd == -D(expected["cumFunding"]["sinceOpen"]) == D("0.058435")
    assert view.fees_usd == D("0.043073") and view.equity_usd == D("4809.95869849")
    assert wire.perp_states[""]["assetPositions"] == []


def test_native_adapter_reads_the_shared_wire_for_every_configured_asset() -> None:
    """Real account readers select the proper namespace and source-backed position."""
    account, source, mark, now = recovered_source_account()
    view = account.snapshot()
    cash = view.allocated_initial_margin_usd - view.fees_usd + view.funding_usd
    wire = project_unified_account(
        view,
        symbols=SYMBOLS,
        marks={"xyz:SNDK": mark},
        collateral={"xyz:SNDK": IsolatedCollateral(cash, (MaintenanceTier(D(0), D(".05"), D(0)),))},
        additional_hold_usd=D(0),
        observed_time_ms=now,
    )
    info = create_autospec(HyperliquidInfoProtocol, instance=True, spec_set=True)
    info.query_user_abstraction_state.return_value = source["mode"]
    info.spot_user_state.return_value = wire.spot_state
    info.user_state.side_effect = lambda address, dex: wire.perp_states[dex]
    exchange = create_autospec(HyperliquidExchangeProtocol, instance=True, spec_set=True)
    for symbol in SYMBOLS:
        adapter = BtcHyperliquidAdapter(
            info=info,
            exchange=exchange,
            account_address=ADDRESS,
            max_notional_usd=500,
            slippage_fraction=0.01,
            symbol=symbol,
            perp_dex="xyz" if ":" in symbol else "",
        )
        native = adapter.account_snapshot()
        assert native.account_value_usd == 4809.95869849
        assert native.withdrawable_usd == pytest.approx(4758.62101649)
        assert native.balance_source == "spot_clearinghouse_state"
        assert native.position.size_signed == (-0.306 if symbol == "xyz:SNDK" else 0)
        assert native.total_margin_used_usd == (51.337682 if ":" in symbol else 0)
    assert not exchange.mock_calls


@pytest.mark.parametrize("direction", [1, -1])
@pytest.mark.parametrize("cash", ["1", "9.9", "20", "100"])
def test_liquidation_has_independent_fraction_maintenance_identity(direction: int, cash: str) -> None:
    """An exact Fraction oracle checks collateral equality at the returned root."""
    account = ExactFillAccount(D(5000), ("BTC",))
    account.mark(Stamp(0, 0), source_time_ms=0, prices={"BTC": D(101)})
    account.apply_fill(
        FillEvent(
            "f",
            "o",
            "BTC",
            "buy" if direction == 1 else "sell",
            D(1),
            D(100),
            D(0),
            D(10),
            0,
            1,
            2,
            Stamp(3, 0),
            False,
        )
    )
    tiers = (MaintenanceTier(D(0), D(".05"), D(0)), MaintenanceTier(D(105), D(".1"), D("5.25")))
    wire = project_unified_account(
        account.snapshot(),
        symbols=("BTC",),
        marks={"BTC": D(101)},
        collateral={"BTC": IsolatedCollateral(D(cash), tiers)},
        additional_hold_usd=D(0),
        observed_time_ms=4,
    )
    actual = wire.perp_states[""]["assetPositions"][0]["position"]["liquidationPx"]
    if direction == 1 and cash == "100":
        assert actual is None
        return
    price = Fraction(actual)
    equity = Fraction(cash) + direction * (price - 100)
    requirement = price / 20 if price < 105 else price / 10 - Fraction(21, 4)
    assert abs(equity - requirement) < Fraction(1, 10**45)
