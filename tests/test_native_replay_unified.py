"""Native unified-account consumers must share one exact economic balance."""

from dataclasses import replace
from decimal import Decimal, localcontext

import pytest

from hypervector.live.hyperliquid_perp_parsing import parse_account_mode_for_symbol
from hypervector.live.hyperliquid_protocol import SolReconciliationSnapshot
from hypervector.live.multi_asset_live_runner_support import shared_account_facts
from hypervector.research.native_replay_account import AccountView, ExactFillAccount
from hypervector.research.native_replay_events import FillEvent, Stamp
from hypervector.research.native_replay_unified import (
    IsolatedCollateral,
    MaintenanceTier,
    UnifiedAccountWire,
    project_unified_account,
)

D = Decimal
SYMBOLS = ("BTC", "ETH", "SOL", "HYPE", "xyz:SPCX", "xyz:SNDK", "xyz:BRENTOIL")
TIERS = (MaintenanceTier(D(0), D("0.05"), D(0)),)


def account_view(side: str = "buy") -> AccountView:
    """Open seven exact positions with independently simple economic totals."""
    account = ExactFillAccount(D(5000), SYMBOLS)
    account.mark(Stamp(0, 0), source_time_ms=0, prices=dict.fromkeys(SYMBOLS, D(100)))
    for index, symbol in enumerate(SYMBOLS):
        account.apply_fill(
            FillEvent(
                str(index),
                str(index),
                symbol,
                side,
                D(1),
                D(100),
                D("0.1"),
                D(10),
                0,
                1,
                2,
                Stamp(3, index),
                False,
            )
        )
    account.mark(Stamp(4, 0), source_time_ms=4, prices=dict.fromkeys(SYMBOLS, D(101)))
    return account.snapshot()


def project(view: AccountView, **changes: object) -> UnifiedAccountWire:
    """Supply explicit collateral and marks; tests may replace individual inputs."""
    arguments = {
        "symbols": SYMBOLS,
        "marks": dict.fromkeys(SYMBOLS, D(101)),
        "collateral": dict.fromkeys(SYMBOLS, IsolatedCollateral(D("9.9"), TIERS)),
        "additional_hold_usd": D(2),
        "observed_time_ms": 5,
        **changes,
    }
    return project_unified_account(view, **arguments)


@pytest.mark.parametrize(
    "side,equity,margin,withdrawable",
    [
        ("buy", 5006.3, 76.3, 4928),
        ("sell", 4992.3, 62.3, 4928),
    ],
)
def test_seven_native_projections_do_not_duplicate_equity_or_margin(
    side: str,
    equity: float,
    margin: float,
    withdrawable: float,
) -> None:
    """Actual parsers and namespace aggregation consume one shared balance."""
    wire = project(account_view(side))
    venues = tuple(
        SolReconciliationSnapshot(
            parse_account_mode_for_symbol(
                mode="unifiedAccount",
                perp_state=wire.perp_states[symbol.partition(":")[0] if ":" in symbol else ""],
                spot_state=wire.spot_state,
                symbol=symbol,
            ),
            (),
            (),
        )
        for symbol in SYMBOLS
    )
    shared = shared_account_facts(SYMBOLS, venues)
    assert shared.account_value_usd == equity
    assert shared.total_margin_used_usd == pytest.approx(margin)
    assert shared.total_notional_position_usd == 707
    assert shared.withdrawable_usd == withdrawable
    assert all(venue.account.account_value_usd == equity for venue in venues)
    assert all(venue.position.entry_price == 100 for venue in venues)
    assert all(venue.position.size_signed == (1 if side == "buy" else -1) for venue in venues)
    assert wire.liquidatable_symbols == ()


def test_flat_wire_and_request_time_are_explicit() -> None:
    """A flat account retains the configured namespaces and its shared cash."""
    wire = project(ExactFillAccount(D(5000), SYMBOLS).snapshot(), marks={}, collateral={})
    assert wire.spot_state["balances"] == [{"coin": "USDC", "token": 0, "total": "5000", "hold": "2"}]
    assert set(wire.perp_states) == {"", "xyz"}
    for state in wire.perp_states.values():
        assert state["time"] == 5 and state["assetPositions"] == []
        assert D(state["marginSummary"]["totalMarginUsed"]) == 0


@pytest.mark.parametrize("side,cash,expected", [("buy", "9.9", "90.1"), ("sell", "9.9", "109.9")])
def test_liquidation_root_obeys_its_own_maintenance_tier(side: str, cash: str, expected: str) -> None:
    """A liquidation price may belong to a different tier than the current mark."""
    tiers = (MaintenanceTier(D(0), D("0.05"), D(0)), MaintenanceTier(D(105), D("0.10"), D("5.25")))
    wire = project(account_view(side), collateral=dict.fromkeys(SYMBOLS, IsolatedCollateral(D(cash), tiers)))
    position = wire.perp_states[""]["assetPositions"][0]["position"]
    price = D(position["liquidationPx"])
    with localcontext() as context:
        context.prec = 50
        wanted = D(expected) / (D("0.95") if side == "buy" else D("1.05"))
    assert price == wanted


def test_liquidation_in_higher_tier_and_no_positive_long_boundary() -> None:
    """Solve a higher-tier boundary and explicitly retain a fully funded long."""
    tiers = (MaintenanceTier(D(0), D("0.05"), D(0)), MaintenanceTier(D(105), D("0.1"), D("5.25")))
    wire = project(account_view("sell"), collateral=dict.fromkeys(SYMBOLS, IsolatedCollateral(D(20), tiers)))
    with localcontext() as context:
        context.prec = 50
        expected = D("125.25") / D("1.1")
    assert D(wire.perp_states[""]["assetPositions"][0]["position"]["liquidationPx"]) == expected
    funded = project(account_view(), collateral=dict.fromkeys(SYMBOLS, IsolatedCollateral(D(100), TIERS)))
    assert funded.perp_states[""]["assetPositions"][0]["position"]["liquidationPx"] is None


def test_maintenance_contact_is_reported_without_a_loss_gate() -> None:
    """An insolvent modeled position stays an explicit outcome requiring lifecycle handling."""
    wire = project(account_view("sell"), collateral=dict.fromkeys(SYMBOLS, IsolatedCollateral(D(1), TIERS)))
    assert wire.liquidatable_symbols == SYMBOLS
    assert D(wire.perp_states[""]["assetPositions"][0]["position"]["marginUsed"]) == 0


@pytest.mark.parametrize(
    "changes,match",
    [
        ({"symbols": ()}, "symbols"),
        ({"symbols": ("BTC", "BTC")}, "symbols"),
        ({"symbols": ("BTC",)}, "configured"),
        ({"marks": {}}, "marks"),
        ({"marks": dict.fromkeys(SYMBOLS, D(102))}, "economic view"),
        ({"collateral": {}}, "collateral"),
        ({"additional_hold_usd": D(-1)}, "additional hold"),
        ({"additional_hold_usd": 0.0}, "Decimal"),
        ({"observed_time_ms": 3}, "observation"),
    ],
)
def test_projection_refuses_incomplete_or_inconsistent_evidence(
    changes: dict[str, object], match: str
) -> None:
    """Unknown values must not become plausible native account balances."""
    with pytest.raises(ValueError, match=match):
        project(account_view(), **changes)


def test_projection_rejects_corrupt_economic_summary() -> None:
    """Explicit marks cannot silently disagree with the shared economic snapshot."""
    with pytest.raises(ValueError, match="economic view"):
        project(replace(account_view(), equity_usd=D(5000)))


def test_compensating_mark_errors_cannot_hide_behind_matching_portfolio_totals() -> None:
    """Each mark must match its retained position input even when errors cancel."""
    marks = dict.fromkeys(SYMBOLS, D(101))
    marks.update(BTC=D(100), ETH=D(102))
    with pytest.raises(ValueError, match="retained mark"):
        project(account_view(), marks=marks)


def test_native_mapping_rejects_untyped_collateral_and_fractional_leverage() -> None:
    """Incomplete collateral and non-native leverage cannot become account facts."""
    with pytest.raises(ValueError, match="IsolatedCollateral"):
        project(account_view(), collateral=dict.fromkeys(SYMBOLS, D(10)))
    view = account_view()
    positions = dict(view.positions)
    positions["BTC"] = replace(positions["BTC"], leverage=D("1.5"))
    with pytest.raises(ValueError, match="integer"):
        project(replace(view, positions=positions))


def test_account_marks_are_immutable_and_projection_ignores_ambient_precision() -> None:
    """Retained per-symbol source values cannot drift or lose decimal precision."""
    view = account_view()
    expected = project(view)
    with pytest.raises(TypeError):
        view.mark_prices["BTC"] = D(102)
    with localcontext() as context:
        context.prec = 3
        assert project(view) == expected


@pytest.mark.parametrize(
    "tiers",
    [
        (),
        (MaintenanceTier(D(1), D("0.05"), D(0)),),
        (MaintenanceTier(D(0), D("0.05"), D(0)), MaintenanceTier(D(100), D("0.1"), D(0))),
    ],
)
def test_collateral_refuses_missing_or_discontinuous_tiers(tiers: tuple[MaintenanceTier, ...]) -> None:
    """A guessed maintenance schedule cannot supply a liquidation field."""
    with pytest.raises(ValueError, match="maintenance"):
        IsolatedCollateral(D(10), tiers)


@pytest.mark.parametrize(
    "lower,rate,deduction", [("-1", ".05", "0"), ("0", "0", "0"), ("0", "1", "0"), ("0", ".05", "-1")]
)
def test_invalid_maintenance_terms_fail(lower: str, rate: str, deduction: str) -> None:
    """Validate signs and a rate strictly below one before any arithmetic."""
    with pytest.raises(ValueError):
        MaintenanceTier(D(lower), D(rate), D(deduction))
