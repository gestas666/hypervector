"""The V90 option-B package: unlocked hourly routes plus xyz:TSLA, fail-closed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.live.hourly_price_evidence import hourly_price_evidence_rows
from hypervector.live.hourly_price_provider import (
    DONCHIAN20_STRATEGY,
    HOURLY_PRICE_SYMBOLS,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_strategy_evidence import strategy_research_evidence
from hypervector.research.cohort_friction_contract_recent import (
    v89_hourly_modeled_contracts,
    v90_hourly_modeled_contracts,
)
from hypervector.research.cohort_friction_contracts import modeled_contract
from hypervector.research.hip3_roster_observer import ACTIVE_HIP3_MARKETS

PROFILE = Path(
    "configs/multi_asset_growth_first_5000_bankroll_builder_candidate_v90.toml"
)
APPROVAL = Path(
    "docs/live-approvals/v89-to-v90-bankroll-builder-pending-20260920-v1.json"
)
V90_ROUTES = ("SOL", "xyz:BRENTOIL", "xyz:TSLA")
BREADTH = Path(
    "data/logs/research/bidirectional_cohort/v90_expansion_screen_20260920_v1/"
    "screen_breadth_H1.json"
)


def test_tsla_is_the_only_symbol_added_to_the_hourly_allowlist() -> None:
    """The gate widens by exactly one screened market."""
    assert "xyz:TSLA" in HOURLY_PRICE_SYMBOLS
    assert HOURLY_PRICE_SYMBOLS == frozenset(
        {
            "BTC",
            "ETH",
            "SOL",
            "HYPE",
            "xyz:SPCX",
            "xyz:SP500",
            "xyz:SNDK",
            "xyz:BRENTOIL",
            "xyz:TSLA",
        }
    )


def test_roster_observer_covers_tsla_at_its_venue_maximum() -> None:
    """The fee-regime probe can only alert on a market the observer reads."""
    specs = {spec.symbol: spec.expected_max_leverage for spec in ACTIVE_HIP3_MARKETS}
    assert specs["xyz:TSLA"] == 20
    assert len(specs) == len(ACTIVE_HIP3_MARKETS)


@pytest.mark.parametrize("symbol", V90_ROUTES)
def test_v90_routes_resolve_a_source_bound_modeled_contract(symbol: str) -> None:
    """Each moved or added route carries the fee its screen actually charged."""
    contract = modeled_contract(DONCHIAN20_STRATEGY, symbol)
    assert contract is not None
    assert contract.entry_fee_bps == (4.5 if symbol == "SOL" else 0.9)
    assert contract.stop_policy == "structural_clamped_bps"
    assert (contract.minimum_stop_bps, contract.maximum_stop_bps) == (20.0, 250.0)
    assert contract.maximum_hold_seconds == 86_400
    assert contract.maximum_hold_policy == "fixed"
    assert contract.target_policy == "none"
    assert contract.entry_slippage_bps == 5.5  # the screens' adverse arm
    evidence = Path(contract.evidence_source)
    if not evidence.exists():
        pytest.skip(f"screen evidence is operator-local: {evidence}")
    published = json.loads(evidence.read_text())
    assert any(cell["symbol"] == symbol for cell in published["cells"])
    assert any(cell["cost"] == "adverse" for cell in published["cells"])
    grid = (
        published.get("declared_grid")
        or json.loads(BREADTH.read_text())["declared_grid"]
    )
    adverse = grid["costs"]["adverse"]  # (entry slip, exit slip, hip3 fee, crypto fee)
    assert adverse[0] == contract.entry_slippage_bps
    assert adverse[3 if symbol == "SOL" else 2] == contract.entry_fee_bps


def test_v90_contracts_do_not_touch_the_frozen_v89_table() -> None:
    """V89's three cited routes keep their exact keys and evidence file."""
    assert set(v89_hourly_modeled_contracts()) == {
        ("hourly_band20_reentry_atr20_bidirectional_v1", "xyz:SPCX"),
        (DONCHIAN20_STRATEGY, "xyz:SNDK"),
        ("hourly_donchian_8_4_atr20_bidirectional_v1", "xyz:BRENTOIL"),
    }
    assert set(v90_hourly_modeled_contracts()) == {
        (DONCHIAN20_STRATEGY, symbol) for symbol in V90_ROUTES
    }
    sndk = modeled_contract(DONCHIAN20_STRATEGY, "xyz:SNDK")
    assert sndk is not None and sndk.evidence_source.endswith(
        "v89_hourly_nominal_friction_contracts_20260907_v1.json"
    )


@pytest.mark.parametrize(
    "symbol", ["xyz:SPCX", "xyz:GOLD", "xyz:MU", "xyz:SP500", None]
)
def test_unresearched_symbols_still_resolve_no_contract(symbol: str | None) -> None:
    """Sharing the recipe identity never implies research on another asset."""
    assert modeled_contract(DONCHIAN20_STRATEGY, symbol) is None


@pytest.mark.parametrize(
    ("symbol", "state", "caveat"),
    [
        (
            "xyz:SNDK",
            "exploratory_positive_all_windows_size_raised_3_9x_unvalidated",
            "risk preference",
        ),
        ("SOL", "exploratory_candidate_two_windows_positive", "budget zero"),
        ("xyz:BRENTOIL", "mechanism_standardisation_untested", "p=0.52"),
        ("xyz:TSLA", "exploratory_addition_failed_predeclared_bar", "0 of 18"),
        ("xyz:SPCX", "unreviewed_exact_mapping", "not evidence of edge"),
    ],
)
def test_evidence_rows_name_each_route_honestly(
    symbol: str, state: str, caveat: str
) -> None:
    """Every executable mapping carries an explicit, low-confidence record."""
    evidence = strategy_research_evidence(DONCHIAN20_STRATEGY, symbol)
    assert evidence.research_state == state
    assert evidence.confidence == "low"
    assert caveat in evidence.summary
    assert evidence.execution_effect == "report_only"


def test_candidate_loads_armed_and_every_executable_cap_is_non_binding() -> None:
    """Position size follows equity; nothing is silently pinned by a cap."""
    config = load_multi_asset_live_config(
        PROFILE, mode="live", enabled=True, accepts_live_risk=True
    )
    executable = {s for p in config.providers for s in p.execution_symbols}
    assert executable == {"BTC", "SOL", "xyz:SNDK", "xyz:BRENTOIL", "xyz:TSLA"}
    equity = 4_870.28
    for asset in config.assets:
        if asset.symbol not in executable:
            continue
        formula = equity * asset.margin_fraction * asset.leverage
        assert formula < asset.max_notional_usd, asset.symbol
        assert asset.leverage <= 10.0
    for asset in config.assets:
        if asset.symbol.startswith("xyz:") and asset.symbol in executable:
            assert asset.leverage == 8.0, asset.symbol


def test_approval_is_signed_and_bound_to_this_exact_candidate() -> None:
    """The record names the current fingerprint, the operator, and the correction."""
    config = load_multi_asset_live_config(PROFILE, mode="observe")
    if not APPROVAL.exists():
        pytest.skip("approval record is operator-local")
    document = json.loads(APPROVAL.read_text())
    assert document["approval_status"] == "approved_for_live_transition"
    assert (
        document["candidate_profile"]["profile_fingerprint"]
        == config.profile_fingerprint
    )
    assert document["execution_authority"] == "none"
    scopes = set(document["change_scopes"])
    assert any("no_profit_lock" in scope for scope in scopes)
    assert any("xyz_tsla" in scope for scope in scopes)
    assert any("post_approval_correction" in scope for scope in scopes)
    added = {
        (r["replacement_scope"]["strategy_id"], r["replacement_scope"]["symbol"])
        for r in document["retirements"]
        if r["replacement_scope"] is not None
    }
    assert added == {
        (DONCHIAN20_STRATEGY, "SOL"),
        (DONCHIAN20_STRATEGY, "xyz:BRENTOIL"),
    }


def test_sndk_evidence_quotes_its_own_screen_cell_exactly() -> None:
    """Published route evidence must match the cell it cites, metric for metric.

    The row quoted the roster screen's payoff ratio as its profit factor and took
    its adverse net from a different screen run at 10x, on the largest-notional
    executable route in the profile.
    """
    screen = json.loads(
        Path(
            "data/logs/research/bidirectional_cohort/v90_expansion_screen_20260920_v1"
            "/exit_policy_v90_roster_63d.json"
        ).read_text()
    )
    cells = {
        (cell["symbol"], cell["cost"], cell["arm"]): cell for cell in screen["cells"]
    }
    measured = cells[("xyz:SNDK", "measured", "none")]
    adverse = cells[("xyz:SNDK", "adverse", "none")]
    row = next(
        row
        for row in hourly_price_evidence_rows()
        if row[1] == "xyz:SNDK" and "8x" in row[4]
    )
    limitations = row[5]

    assert f"+${measured['net_usd']:.2f}" in limitations
    assert f"adverse +${adverse['net_usd']:.2f}" in limitations
    assert f"payoff ratio {measured['payoff_ratio']:.2f}" in limitations
    assert f"PF {measured['profit_factor']:.2f}" in limitations
    assert "PF 2.82" not in limitations


def test_the_adverse_arm_claim_names_only_the_routes_it_holds_for() -> None:
    """xyz:SNDK resolves the frozen V89 nominal contract, not the adverse arm."""
    v90 = v90_hourly_modeled_contracts()
    assert "xyz:SNDK" not in {symbol for _provider, symbol in v90}
    sndk = next(
        row
        for row in hourly_price_evidence_rows()
        if row[1] == "xyz:SNDK" and "8x" in row[4]
    )
    assert "keeps the frozen V89 nominal contract" in sndk[5]
