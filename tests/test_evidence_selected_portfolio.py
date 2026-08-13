"""Contracts for v29's report-only shared-account priority replay."""

from __future__ import annotations

import pytest
import pandas as pd

from hypervector.research.current_cohort_shared_portfolio import (
    CohortOutcome,
    CohortTradeSpec,
)
from hypervector.research.evidence_selected_portfolio import (
    PrioritizedPortfolioConfig,
    replay_prioritized_outcomes,
)
from hypervector.research.evidence_selected_portfolio_inputs import (
    adapt_hip3_sidecar,
    adapt_range_context_payload,
)
from hypervector.research.shared_trade_portfolio import SharedTradeOutcome


def _trade(
    identity: str,
    strategy: str,
    *,
    symbol: str = "ETH",
    side: str = "long",
    entry: int = 1_000,
    exit_: int = 2_000,
    margin_fraction: float = 0.03,
    entry_fee: float = 0.03,
    net_pnl: float = 1.0,
) -> CohortOutcome:
    """Build one deterministic fixed-cap lifecycle."""
    return CohortOutcome(
        strategy,
        side,
        SharedTradeOutcome(
            trade_id=identity,
            symbol=symbol,
            entry_time_ms=entry,
            exit_time_ms=exit_,
            source_equity_usd=500.0,
            margin_fraction=margin_fraction,
            entry_fee_usd=entry_fee,
            net_pnl_usd=net_pnl,
            outcome="maximum_hold",
        ),
    )


def _config(*priorities: str, maximum_positions: int = 5) -> PrioritizedPortfolioConfig:
    """Return the fixed $500 report-only account contract."""
    return PrioritizedPortfolioConfig(
        initial_equity_usd=500.0,
        maximum_positions=maximum_positions,
        strategy_priority=priorities,
    )


def test_same_timestamp_same_asset_uses_configured_provider_priority() -> None:
    """The lower configured priority must own a simultaneous ETH conflict."""
    high = _trade("high", "priority_10")
    low = _trade("low", "priority_20")

    report = replay_prioritized_outcomes(
        (low, high),
        _config("priority_10", "priority_20"),
    )

    assert [row.trade_id for row in report.accepted] == ["high"]
    assert [(row.trade_id, row.reason) for row in report.rejected] == [
        ("low", "symbol_occupied")
    ]


def test_later_same_asset_lifecycle_is_rejected_while_position_is_open() -> None:
    """Provider priority cannot displace an already-open asset lifecycle."""
    first = _trade("first", "priority_20", entry=1_000, exit_=3_000)
    later = _trade("later", "priority_10", entry=2_000, exit_=4_000)

    report = replay_prioritized_outcomes(
        (first, later),
        _config("priority_10", "priority_20"),
    )

    assert [row.trade_id for row in report.accepted] == ["first"]
    assert report.rejected[0].reason == "symbol_occupied"


def test_exit_precedes_entry_at_same_timestamp() -> None:
    """A completed ETH exit must free the asset before the next entry event."""
    first = _trade("first", "route", exit_=2_000)
    second = _trade("second", "route", entry=2_000, exit_=3_000)

    report = replay_prioritized_outcomes((second, first), _config("route"))

    assert [row.trade_id for row in report.accepted] == ["first", "second"]
    assert report.rejected == ()


def test_maximum_positions_rejects_excess_assets_without_mutating_equity() -> None:
    """The portfolio slot ceiling must retain excess intents as telemetry."""
    btc = _trade("btc", "route", symbol="BTC", entry_fee=0.0)
    eth = _trade("eth", "route", symbol="ETH", entry_fee=0.0)
    sol = _trade("sol", "route", symbol="SOL", entry_fee=0.0)

    report = replay_prioritized_outcomes(
        (sol, eth, btc),
        _config("route", maximum_positions=2),
    )

    assert len(report.accepted) == 2
    assert report.maximum_concurrent_positions == 2
    assert [(row.trade_id, row.reason) for row in report.rejected] == [
        ("sol", "maximum_positions")
    ]
    assert report.net_pnl_usd == pytest.approx(2.0)


def test_fixed_source_cap_prevents_profit_compounding_above_500() -> None:
    """Sequential winners must retain v29's fixed notional rather than compound."""
    first = _trade("first", "route", entry=1_000, exit_=2_000, net_pnl=10.0)
    second = _trade("second", "route", entry=3_000, exit_=4_000, net_pnl=10.0)

    report = replay_prioritized_outcomes((first, second), _config("route"))

    assert report.final_equity_usd == pytest.approx(520.0)
    assert [row.scaling_base_usd for row in report.accepted] == [500.0, 500.0]
    assert report.peak_reserved_margin_usd == pytest.approx(15.0)


def test_losses_scale_later_fixed_cap_to_remaining_shared_equity() -> None:
    """A damaged account cannot reserve against equity it no longer owns."""
    loss = _trade("loss", "route", entry=1_000, exit_=2_000, net_pnl=-100.0)
    win = _trade("win", "route", entry=3_000, exit_=4_000, net_pnl=10.0)

    report = replay_prioritized_outcomes((loss, win), _config("route"))

    assert report.accepted[1].scaling_base_usd == pytest.approx(400.0)
    assert report.accepted[1].net_pnl_usd == pytest.approx(8.0)
    assert report.final_equity_usd == pytest.approx(408.0)


def test_report_reconciles_strategy_and_side_attribution() -> None:
    """Accepted net PnL must reconcile exactly across route and direction."""
    long = _trade("long", "alpha", side="long", entry_fee=0.0, net_pnl=3.0)
    short = _trade(
        "short",
        "beta",
        symbol="SOL",
        side="short",
        entry_fee=0.0,
        net_pnl=-1.0,
    )

    report = replay_prioritized_outcomes(
        (long, short),
        _config("alpha", "beta"),
    )

    assert report.net_pnl_usd == pytest.approx(2.0)
    assert report.profit_factor == pytest.approx(3.0)
    assert report.by_strategy["alpha"]["net_pnl_usd"] == pytest.approx(3.0)
    assert report.by_strategy["beta"]["net_pnl_usd"] == pytest.approx(-1.0)
    assert report.by_strategy_side["alpha|long"]["trades"] == 1
    assert report.by_strategy_side["beta|short"]["losses"] == 1
    assert sum(row.net_pnl_usd for row in report.accepted) == pytest.approx(
        report.net_pnl_usd
    )


def test_replay_rejects_missing_or_duplicate_priority_identity() -> None:
    """Ambiguous route priority cannot silently affect conflict ordering."""
    trade = _trade("one", "alpha")

    with pytest.raises(ValueError, match="priority.*cover"):
        replay_prioritized_outcomes((trade,), _config("beta"))
    with pytest.raises(ValueError, match="priority.*unique"):
        _config("alpha", "alpha")


def _range_context_payload() -> dict[str, object]:
    """Return one exact dual-MTF ETH context-candidate artifact."""
    trade = {
        "direction": "long",
        "entry_time_utc": "2026-01-01T00:01:00+00:00",
        "exit_time_utc": "2026-01-01T01:01:00+00:00",
        "entry_price": 100.0,
        "quantity": 10.0,
        "net_pnl_usd": 50.0,
        "exit_reason": "maximum_hold",
    }
    return {
        "execution_authority": "none",
        "model_authority": "none",
        "symbol": "ETH",
        "continuous": {
            "candidates": [
                {"candidate_id": "current_contract", "trades": []},
                {"candidate_id": "dual_mtf_not_opposed", "trades": [trade]},
            ]
        },
    }


def test_range_context_adapter_selects_exact_candidate_and_live_cap() -> None:
    """The dual-MTF source return must normalize to ETH's $25 v29 cap."""
    spec = CohortTradeSpec("range_onset_bidirectional_v1", "ETH", 25.0, 5.0, 4.5)

    rows = adapt_range_context_payload(
        _range_context_payload(),
        spec,
        candidate_id="dual_mtf_not_opposed",
    )

    assert len(rows) == 1
    assert rows[0].side == "long"
    assert rows[0].outcome.margin_fraction == pytest.approx(0.01)
    assert rows[0].outcome.entry_fee_usd == pytest.approx(0.01125)
    assert rows[0].outcome.net_pnl_usd == pytest.approx(1.25)


def test_range_context_adapter_rejects_authority_and_duplicate_candidate() -> None:
    """Ambiguous or execution-capable source evidence must fail closed."""
    spec = CohortTradeSpec("range_onset_bidirectional_v1", "ETH", 25.0, 5.0, 4.5)
    authority = _range_context_payload()
    authority["execution_authority"] = "hyperliquid_mainnet"
    duplicate = _range_context_payload()
    continuous = duplicate["continuous"]
    assert isinstance(continuous, dict)
    candidates = continuous["candidates"]
    assert isinstance(candidates, list)
    candidates.append(candidates[-1])

    with pytest.raises(ValueError, match="no execution authority"):
        adapt_range_context_payload(
            authority, spec, candidate_id="dual_mtf_not_opposed"
        )
    with pytest.raises(ValueError, match="one exact context candidate"):
        adapt_range_context_payload(
            duplicate, spec, candidate_id="dual_mtf_not_opposed"
        )


def _hip3_sidecar(*, phase: str = "development") -> pd.DataFrame:
    """Return nominal and stress rows for one selected HIP-3 mapping."""
    common = {
        "strategy_id": "hip3_swing",
        "symbol": "xyz:GOLD",
        "phase": phase,
        "direction": "short",
        "entry_time_utc": "2026-01-01T00:15:00+00:00",
        "exit_time_utc": "2026-01-01T01:15:00+00:00",
        "notional_usd": 50.0,
        "fees_usd": 0.02,
        "net_pnl_usd": 1.0,
        "exit_reason": "maximum_hold",
    }
    return pd.DataFrame(
        [common | {"friction": "nominal"}, common | {"friction": "stress"}]
    )


def test_hip3_adapter_filters_friction_and_normalizes_after_cost_return() -> None:
    """Only the requested scenario may use the selected GOLD lifecycle."""
    spec = CohortTradeSpec("hip3_swing", "xyz:GOLD", 75.0, 5.0, 0.0)

    rows = adapt_hip3_sidecar(
        _hip3_sidecar(),
        {(spec.strategy_id, spec.symbol): spec},
        friction="stress",
    )

    assert len(rows) == 1
    assert rows[0].side == "short"
    assert rows[0].outcome.margin_fraction == pytest.approx(0.03)
    assert rows[0].outcome.entry_fee_usd == pytest.approx(0.015)
    assert rows[0].outcome.net_pnl_usd == pytest.approx(1.5)
    assert "|stress|" in rows[0].trade_id


def test_hip3_adapter_orders_same_bar_exit_after_entry() -> None:
    """A conservative same-bar lifecycle must remain causal and retained."""
    spec = CohortTradeSpec("hip3_swing", "xyz:GOLD", 75.0, 5.0, 0.0)
    frame = _hip3_sidecar()
    frame["exit_time_utc"] = frame["entry_time_utc"]

    rows = adapt_hip3_sidecar(
        frame,
        {(spec.strategy_id, spec.symbol): spec},
        friction="nominal",
    )

    assert len(rows) == 1
    assert rows[0].outcome.exit_time_ms == rows[0].outcome.entry_time_ms + 1


def test_hip3_adapter_rejects_holdout_phase_before_filtering() -> None:
    """A sealed holdout row must invalidate the complete source frame."""
    spec = CohortTradeSpec("hip3_swing", "xyz:GOLD", 75.0, 5.0, 0.0)

    with pytest.raises(ValueError, match="HIP-3 phases"):
        adapt_hip3_sidecar(
            _hip3_sidecar(phase="holdout"),
            {(spec.strategy_id, spec.symbol): spec},
            friction="nominal",
        )


def test_hip3_adapter_requires_each_selected_route() -> None:
    """A missing provider-symbol mapping cannot become a zero-trade success."""
    spec = CohortTradeSpec("hip3_breakout", "xyz:SP500", 75.0, 5.0, 0.0)

    with pytest.raises(ValueError, match="contains no selected route"):
        adapt_hip3_sidecar(
            _hip3_sidecar(),
            {(spec.strategy_id, spec.symbol): spec},
            friction="nominal",
        )
