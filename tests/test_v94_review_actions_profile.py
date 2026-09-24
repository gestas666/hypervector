"""V94 is V93 plus exactly the approved review actions (plan section B).

docs/plans/2026-09-24-v94-review-actions.md: the Donchian routes move to the
strong-short identity with an equity-fraction stop budget, v2 routes that can
reach the +2R floor raise the venue stop to it, HYPE and SPCX band20 become
watch-only, HYPE's envelope shrinks and BTC's inert asset stop matches its
provider. Everything else must equal V93 field for field.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import cohort_runtime_validation_check as check
from hypervector.live import cohort_profile_stage
from hypervector.live.cohort_adaptive_exit_policy import RETENTION_EXIT_POLICY
from hypervector.live.cohort_operator_commands import (
    CohortAssetStage,
    CohortProfileSettings,
    CohortProviderStage,
)
from hypervector.live.cohort_stop_risk_sizing import StopRiskBudget
from hypervector.live.hourly_price_provider import STRONG_SHORT_DONCHIAN20_STRATEGY
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    MultiAssetLiveConfigError,
    StrategyProviderConfig,
    load_multi_asset_live_config,
)

V93 = Path("configs/multi_asset_growth_first_5000_exit_v2_v93_proposal.toml")
V94 = Path("configs/multi_asset_growth_first_5000_review_actions_v94.toml")
V93_FINGERPRINT = "33131f1898d86dda4f5cab2b6091748144f6a81da29b9c9464a644b330dc3e05"
V94_FINGERPRINT = "930117e9ac0f4bb91fc66631666f47eb68a5d66bd8928684d8792f63122b3fd1"
REVIEW_EQUITY = 4_831.43

BTC_SWEEP = "liquidity_sweep_long_1h_stop60_target60_v2"
ETH_RANGE = "eth_range_onset_long_dual_mtf_v2"
V93_DONCHIAN = "hourly_donchian_20_10_atr20_bidirectional_v1"
HYPE_ALIGN = "hype_breakout_compression_alignment_bidirectional_v2"
SPCX_BAND20 = "hourly_band20_reentry_atr20_bidirectional_v1"
DONCHIAN_SYMBOLS = ("SOL", "xyz:SNDK", "xyz:BRENTOIL", "xyz:TSLA")
HYPE_SIDE_OVERRIDE = 'execution_side_overrides = { HYPE = ["long"] }\n'


def _load(path: Path, mode: str = "observe") -> MultiAssetLiveConfig:
    armed = mode == "live"
    return load_multi_asset_live_config(
        path, mode=mode, enabled=armed, accepts_live_risk=armed
    )


def _providers(config: MultiAssetLiveConfig) -> dict[str, StrategyProviderConfig]:
    return {provider.strategy_id: provider for provider in config.providers}


def test_v94_identity_is_pinned_and_v93_is_unchanged() -> None:
    previous = _load(V93)
    candidate = _load(V94)
    assert previous.profile_fingerprint == V93_FINGERPRINT
    assert candidate.profile_fingerprint == V94_FINGERPRINT
    assert candidate.profile_id == "multi_asset_growth_first_5000_review_actions_v94"
    assert not candidate.enabled and not candidate.accepts_live_risk
    assert candidate.transition_approval == Path(
        "docs/live-approvals/v93-to-v94-review-actions-20260924-v1.json"
    )
    assert "PROPOSAL ONLY" not in V94.read_text()


def test_executable_scope_is_btc_eth_long_and_both_donchian_sides() -> None:
    candidate = _load(V94)
    donchian = {
        (STRONG_SHORT_DONCHIAN20_STRATEGY, symbol, side)
        for symbol in DONCHIAN_SYMBOLS
        for side in ("long", "short")
    }
    assert candidate.executable_provider_directions == {
        (BTC_SWEEP, "BTC", "long"),
        (ETH_RANGE, "ETH", "long"),
        *donchian,
    }
    providers = _providers(candidate)
    assert providers[HYPE_ALIGN].execution_symbols == ()
    assert providers[SPCX_BAND20].execution_symbols == ()
    executable_symbols = {symbol for _, symbol, _ in donchian} | {"BTC", "ETH"}
    assert "HYPE" not in executable_symbols and "xyz:SPCX" not in executable_symbols
    assert V93_DONCHIAN not in providers


def test_watch_only_routes_carry_no_residual_override_tables() -> None:
    """Only HYPE's side override remains, because the loader requires it."""
    for provider in _load(V94).providers:
        if provider.execution_symbols:
            continue
        assert provider.sizing_overrides == ()
        assert provider.directional_sizing_overrides == ()
        assert provider.stop_bps_overrides == ()
        assert provider.profit_lock_overrides == ()
        assert provider.entry_context_overrides == ()
    providers = _providers(_load(V94))
    assert providers[SPCX_BAND20].execution_side_overrides == ()
    assert providers[HYPE_ALIGN].execution_side_overrides == (
        ("HYPE", frozenset({"long"})),
    )


def test_hype_side_override_is_load_bearing_for_the_frozen_route(
    tmp_path: Path,
) -> None:
    """Without it the HYPE alignment contract refuses recipe-honoring exits.

    The backend never reads it for a watch-only route (executable directions
    iterate execution_symbols only) and the cockpit accepts it since V90. If
    the validator ever stops requiring it for an execution-disabled route, this
    test fails and the table can be removed.
    """
    text = V94.read_text()
    assert text.count(HYPE_SIDE_OVERRIDE) == 1
    stripped = tmp_path / "v94_without_hype_side_override.toml"
    stripped.write_text(text.replace(HYPE_SIDE_OVERRIDE, ""))
    with pytest.raises(MultiAssetLiveConfigError, match="HYPE compression alignment"):
        _load(stripped)


def test_stop_budgets_and_venue_floor_raise() -> None:
    providers = _providers(_load(V94))
    donchian = providers[STRONG_SHORT_DONCHIAN20_STRATEGY]
    assert donchian.symbols == DONCHIAN_SYMBOLS
    assert donchian.execution.stop_risk_budget == StopRiskBudget(
        None, 20.0, maximum_loss_fraction_of_equity=0.006
    )
    assert donchian.execution.stop_risk_budget.maximum_loss_usd is None
    assert donchian.execution.stop_risk_budget.effective_maximum_loss_usd(
        REVIEW_EQUITY
    ) == pytest.approx(28.98858)
    for strategy_id in (BTC_SWEEP, ETH_RANGE, HYPE_ALIGN, SPCX_BAND20):
        assert providers[strategy_id].execution.stop_risk_budget == StopRiskBudget(
            25.0, 20.0
        )
    for provider in providers.values():
        assert provider.execution.adaptive_exit_policy == RETENTION_EXIT_POLICY
    # BTC's fixed 60/60 bracket takes profit at +1R, before the +2R floor arms,
    # so the floor raise could never run there and BTC keeps the V93 default.
    assert providers[BTC_SWEEP].execution.target_policy == "fixed_bps"
    assert providers[BTC_SWEEP].execution.target_bps == 60.0
    assert providers[BTC_SWEEP].execution.breakeven_stop_target == "entry_offset"
    for strategy_id in (
        ETH_RANGE,
        STRONG_SHORT_DONCHIAN20_STRATEGY,
        HYPE_ALIGN,
        SPCX_BAND20,
    ):
        assert providers[strategy_id].execution.target_policy == "none"
        assert providers[strategy_id].execution.breakeven_stop_target == "floor"


def test_asset_envelopes_respect_venue_leverage() -> None:
    assets = {asset.symbol: asset for asset in _load(V94).assets}
    venue_max = {
        "BTC": 40.0,
        "ETH": 25.0,
        "SOL": 20.0,
        "HYPE": 10.0,
        "xyz:SPCX": 20.0,
        "xyz:SNDK": 10.0,
        "xyz:BRENTOIL": 20.0,
        "xyz:TSLA": 20.0,
    }
    assert {symbol: asset.venue_max_leverage for symbol, asset in assets.items()} == (
        venue_max
    )
    for asset in assets.values():
        assert 0 < asset.leverage <= asset.venue_max_leverage
    hype = assets["HYPE"]
    assert (hype.leverage, hype.margin_fraction, hype.max_notional_usd) == (
        10.0,
        0.013,
        500.0,
    )
    assert assets["BTC"].stop_bps == 60.0


def test_v94_is_v93_plus_only_the_approved_changes() -> None:
    previous = _load(V93)
    candidate = _load(V94)
    assert candidate.maximum_positions == previous.maximum_positions == 8
    assert (
        candidate.network,
        candidate.margin_mode,
        candidate.cohort_ledger,
        candidate.stop_file,
        candidate.poll_seconds,
        candidate.lookback_days,
    ) == (
        previous.network,
        previous.margin_mode,
        previous.cohort_ledger,
        previous.stop_file,
        previous.poll_seconds,
        previous.lookback_days,
    )
    reverted_assets = []
    for asset in candidate.assets:
        asset = replace(asset, parent_profile_id=previous.profile_id)
        if asset.symbol == "HYPE":
            asset = replace(asset, margin_fraction=0.08, max_notional_usd=2_500.0)
        if asset.symbol == "BTC":
            asset = replace(asset, stop_bps=80.0)
        reverted_assets.append(asset)
    assert tuple(reverted_assets) == previous.assets
    reverted_providers = []
    for provider in candidate.providers:
        execution = replace(provider.execution, breakeven_stop_target="entry_offset")
        if provider.strategy_id == STRONG_SHORT_DONCHIAN20_STRATEGY:
            execution = replace(execution, stop_risk_budget=StopRiskBudget(25.0, 20.0))
            provider = replace(provider, strategy_id=V93_DONCHIAN)
        if provider.strategy_id in {HYPE_ALIGN, SPCX_BAND20}:
            provider = replace(provider, execution_symbols=provider.symbols)
        reverted_providers.append(replace(provider, execution=execution))
    assert tuple(reverted_providers) == previous.providers


@pytest.mark.parametrize("mode", ["observe", "live"])
def test_live_runner_validation_accepts_v94(mode: str) -> None:
    assert check.check(V94, mode=mode) == []


def test_book_level_check_at_review_equity() -> None:
    result = check.book_check(V94, equity_usd=REVIEW_EQUITY)
    assert result.problems == ()
    routes = {route.symbol: route for route in result.routes}
    assert set(routes) == {"BTC", "ETH", *DONCHIAN_SYMBOLS}
    sndk = routes["xyz:SNDK"]
    assert sndk.budget_source == "maximum_loss_fraction_of_equity"
    assert sndk.planned_notional_usd == pytest.approx(REVIEW_EQUITY * 0.05 * 8)
    assert sndk.at_stop_loss_usd == pytest.approx(REVIEW_EQUITY * 0.006)
    assert routes["BTC"].stop_bps == 60.0
    assert result.at_stop_loss_usd / REVIEW_EQUITY == pytest.approx(0.01656, abs=1e-4)
    assert result.margin_usd / REVIEW_EQUITY == pytest.approx(0.1089, abs=1e-4)


def test_cockpit_stage_of_v94_preserves_every_provider_contract(
    tmp_path: Path,
) -> None:
    """VALIDATE & STAGE with unchanged values keeps the new V94 contract fields."""
    original_bytes = V94.read_bytes()
    original = _load(V94)
    settings = CohortProfileSettings(
        maximum_positions=original.maximum_positions,
        poll_seconds=original.poll_seconds,
        assets=tuple(
            CohortAssetStage(
                asset.symbol,
                asset.leverage,
                asset.margin_fraction,
                asset.max_notional_usd,
                asset.stop_bps,
                asset.maximum_hold_seconds,
            )
            for asset in original.assets
        ),
        providers=tuple(
            CohortProviderStage(provider.strategy_id, provider.execution_symbols)
            for provider in original.providers
        ),
    )
    output = tmp_path / "v94-staged.toml"
    cohort_profile_stage.stage_cohort_profile(
        config=original, settings=settings, output_path=output
    )
    staged = _load(output)
    assert staged.providers == original.providers
    assert (
        staged.executable_provider_directions == original.executable_provider_directions
    )
    donchian = _providers(staged)[STRONG_SHORT_DONCHIAN20_STRATEGY].execution
    assert donchian.breakeven_stop_target == "floor"
    assert donchian.stop_risk_budget == StopRiskBudget(
        None, 20.0, maximum_loss_fraction_of_equity=0.006
    )
    assert staged.transition_approval is None
    assert not staged.enabled and not staged.accepts_live_risk
    assert V94.read_bytes() == original_bytes
