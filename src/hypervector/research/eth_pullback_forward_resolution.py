"""Exact-depth resolution for the isolated ETH pullback observer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.live.eth_breakout_transfer_provider import (
    ETH_BREAKOUT_TRANSFER_STRATEGY,
)
from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    MultiAssetLiveConfig,
    StrategyProviderConfig,
)
from hypervector.research.cohort_eligible_exact_depth_forward import (
    build_eligible_exact_depth_forward_report,
)
from hypervector.research.cohort_eligible_policy_funding import (
    EligiblePolicyFundingEvidence,
    exact_depth_funding_bounds,
)
from hypervector.research.cohort_observer_exact_books import (
    extract_observer_asset_books,
    select_compatible_report_only_observer_runs,
)
from hypervector.research.cohort_prospective_records import (
    prospective_observer_records,
)

Record = Mapping[str, object]
_SYMBOL = "ETH"
_CANDIDATE = f"{ETH_BREAKOUT_TRANSFER_STRATEGY}_v55_forward"
_MAXIMUM_BOOK_DELAY_MS = 60_000


def build_eth_pullback_forward_resolution(
    records: Sequence[Record],
    *,
    config: MultiAssetLiveConfig,
    run_id: str,
    prospective_start_ms: int = 0,
    funding_evidence: EligiblePolicyFundingEvidence | None,
    taker_fee_rate: float,
) -> dict[str, object]:
    """Build the exact report-only ETH pullback lifecycle evidence."""
    selected, identities = select_compatible_report_only_observer_runs(records, run_id)
    scoped = prospective_observer_records(
        selected,
        prospective_start_ms,
        label="ETH",
    )
    provider, asset = _route(config)
    execution = provider.execution_for(_SYMBOL)
    policy = _policy_report(
        config,
        run_id,
        tuple(str(identity["run_id"]) for identity in identities),
        stop_bps=float(execution.stop_bps or 0.0),
        maximum_hold_minutes=execution.maximum_hold_seconds // 60,
        notional_usd=asset.max_notional_usd,
    )
    books = extract_observer_asset_books(scoped, (_SYMBOL,))[_SYMBOL]
    report = build_eligible_exact_depth_forward_report(
        scoped,
        books,
        policy_report=policy,
        funding_evidence=funding_evidence,
        taker_fee_rate=taker_fee_rate,
        maximum_entry_delay_ms=_MAXIMUM_BOOK_DELAY_MS,
        maximum_exit_delay_ms=_MAXIMUM_BOOK_DELAY_MS,
    )
    report["identity"] = {
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
        "source_run_id": run_id,
        "compatible_run_ids": policy["contract"]["compatible_run_ids"],
        "prospective_start_ms": prospective_start_ms,
    }
    return report


def eth_pullback_funding_bounds(report: Record) -> tuple[int, int] | None:
    """Return exact funding bounds for entered ETH virtual lifecycles."""
    return exact_depth_funding_bounds(report)


def _route(
    config: MultiAssetLiveConfig,
) -> tuple[StrategyProviderConfig, AssetLiveConfig]:
    providers = [
        provider
        for provider in config.providers
        if provider.strategy_id == ETH_BREAKOUT_TRANSFER_STRATEGY
        and _SYMBOL in provider.symbols
    ]
    assets = [asset for asset in config.assets if asset.symbol == _SYMBOL]
    if len(providers) != 1 or len(assets) != 1:
        raise ValueError("ETH pullback observer route must be unique")
    provider, asset = providers[0], assets[0]
    execution = provider.execution_for(_SYMBOL)
    if (
        provider.symbols != (_SYMBOL,)
        or provider.sides != frozenset({"long", "short"})
        or provider.execution_symbols != (_SYMBOL,)
        or provider.position_policy != "enter_and_close"
        or execution.entry_liquidity != "taker_ioc"
        or execution.stop_policy != "fixed_bps"
        or execution.stop_bps is None
        or execution.target_policy != "none"
        or execution.maximum_hold_policy != "fixed"
        or execution.maximum_hold_seconds % 60
    ):
        raise ValueError("ETH pullback observer execution contract is unsupported")
    return provider, asset


def _policy_report(
    config: MultiAssetLiveConfig,
    run_id: str,
    compatible_run_ids: tuple[str, ...],
    *,
    stop_bps: float,
    maximum_hold_minutes: int,
    notional_usd: float,
) -> dict[str, object]:
    return {
        "mode": "cohort_config_bound_eligible_policy_forward_report",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "portfolio_pnl_claimed": False,
            "source_strategy_id": ETH_BREAKOUT_TRANSFER_STRATEGY,
            "candidate_strategy_id": _CANDIDATE,
            "symbol": _SYMBOL,
            "source_run_id": run_id,
            "profile_fingerprint": config.profile_fingerprint,
            "compatible_run_ids": list(compatible_run_ids),
            "stop_bps": stop_bps,
            "notional_usd": notional_usd,
            "maximum_hold_minutes": maximum_hold_minutes,
            "close_on_eligible_opposite_signal": True,
            "same_cycle_reversal": False,
            "exit_ordering": "earliest_stop_proxy_or_opposite_intent_then_maximum_hold_stop_ties",
            "protective_stop_trigger_evidence": "adverse_recorded_bbo_proxy",
        },
    }
