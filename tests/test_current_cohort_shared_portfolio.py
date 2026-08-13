"""Tests for exact-cap shared replay of the current cohort candidates."""

from __future__ import annotations

from dataclasses import replace

import pytest

from hypervector.research import current_cohort_shared_portfolio as portfolio
from hypervector.research.current_cohort_shared_portfolio import (
    CohortTradeSpec,
    adapt_breakout_trades,
    adapt_hulk_payloads,
    default_sol_range_artifact_paths,
    partition_cohort_outcomes,
    replay_cohort_outcomes,
)
from hypervector.research.hype_breakout_exit_models import HypeExitTrade


def _hulk_payload() -> dict[str, object]:
    """Return one source-backed Hulk lifecycle."""
    return {
        "execution_authority": "none",
        "profile": {"name": "hulk_expansion_bidirectional_tuned_v2"},
        "replay": {
            "trades": [
                {
                    "symbol": "BTC",
                    "direction": "long",
                    "entry_time_utc": "2026-01-01T00:00:00+00:00",
                    "exit_time_utc": "2026-01-01T01:00:00+00:00",
                    "entry_price": 100.0,
                    "initial_quantity": 0.5,
                    "net_pnl_usd": 5.0,
                    "exit_reason": "target_3r",
                }
            ]
        },
    }


def _breakout_trade() -> HypeExitTrade:
    """Return one unit-notional breakout lifecycle."""
    return HypeExitTrade(
        side="short",
        signal_time_utc="2026-01-02T00:00:00+00:00",
        entry_time_utc="2026-01-02T00:01:00+00:00",
        exit_time_utc="2026-01-02T01:01:00+00:00",
        entry_price=100.0,
        exit_price=99.0,
        stop_price=100.8,
        gross_return_bps=100.0,
        fee_bps=9.0,
        funding_bps=0.0,
        net_return_bps=91.0,
        hold_minutes=60,
        maximum_favorable_excursion_bps=110.0,
        maximum_adverse_excursion_bps=10.0,
        exit_reason="maximum_hold",
    )


def _range_payload() -> dict[str, object]:
    """Return one event-replayed SOL lifecycle at the frozen exposure."""
    return {
        "execution_authority": "none",
        "model_authority": "none",
        "symbol": "SOL",
        "continuous": {
            "trials": [
                {
                    "effective_exposure": 0.15,
                    "event_replay": {
                        "status": "complete",
                        "failure": None,
                        "trades": [
                            {
                                "direction": "short",
                                "entry_snapshot_time_ms": 1_700_000_000_000,
                                "exit_snapshot_time_ms": 1_700_003_600_000,
                                "entry_price": 100.0,
                                "quantity": 10.0,
                                "net_pnl_usd": 50.0,
                                "exit_reason": "max_hold",
                            }
                        ],
                    },
                }
            ]
        },
    }


def test_hulk_adapter_normalizes_source_size_to_exact_live_cap() -> None:
    """Hulk source PnL must become the fixed $25 live-notional return."""
    spec = CohortTradeSpec(
        "hulk_expansion_bidirectional_tuned_v2",
        "BTC",
        notional_usd=25.0,
        leverage=5.0,
        entry_fee_bps=4.5,
    )

    adapted = adapt_hulk_payloads((_hulk_payload(),), spec)

    assert len(adapted) == 1
    trade = adapted[0]
    assert trade.strategy_id == spec.strategy_id
    assert trade.side == "long"
    assert trade.outcome.margin_fraction == pytest.approx(0.01)
    assert trade.outcome.entry_fee_usd == pytest.approx(0.01125)
    assert trade.outcome.net_pnl_usd == pytest.approx(2.5)


def test_default_sol_range_sources_are_unique_measured_blocks() -> None:
    """Shared portfolio commands must reuse one exact SOL source manifest."""
    paths = default_sol_range_artifact_paths()

    assert len(paths) == 12
    assert len(paths) == len(set(paths))
    assert all(
        path.name.startswith("multi_asset_range_onset_event_replay_SOL_")
        for path in paths
    )


def test_hulk_adapter_rejects_wrong_profile_identity() -> None:
    """A similarly shaped artifact must not impersonate the live provider."""
    payload = _hulk_payload()
    payload["profile"] = {"name": "different_strategy"}
    spec = CohortTradeSpec(
        "hulk_expansion_bidirectional_tuned_v2", "BTC", 25.0, 5.0, 4.5
    )

    with pytest.raises(ValueError, match="profile identity"):
        adapt_hulk_payloads((payload,), spec)


def test_hulk_same_bar_exit_gets_one_millisecond_ordering_only() -> None:
    """An intrabar exit timestamped at bar open must remain entry-before-exit."""
    payload = _hulk_payload()
    replay = payload["replay"]
    assert isinstance(replay, dict)
    trades = replay["trades"]
    assert isinstance(trades, list)
    trade = trades[0]
    assert isinstance(trade, dict)
    trade["exit_time_utc"] = trade["entry_time_utc"]
    spec = CohortTradeSpec(
        "hulk_expansion_bidirectional_tuned_v2", "BTC", 25.0, 5.0, 4.5
    )

    outcome = adapt_hulk_payloads((payload,), spec)[0].outcome

    assert outcome.exit_time_ms == outcome.entry_time_ms + 1


def test_breakout_adapter_preserves_unit_notional_return_and_side() -> None:
    """Breakout bps must scale to the exact HYPE cap without reinterpretation."""
    spec = CohortTradeSpec(
        "hype_breakout_onset_bidirectional_v1",
        "HYPE",
        notional_usd=75.0,
        leverage=5.0,
        entry_fee_bps=4.5,
    )

    trade = adapt_breakout_trades((_breakout_trade(),), spec)[0]

    assert trade.side == "short"
    assert trade.outcome.margin_fraction == pytest.approx(0.03)
    assert trade.outcome.entry_fee_usd == pytest.approx(0.03375)
    assert trade.outcome.net_pnl_usd == pytest.approx(0.6825)


def test_range_event_adapter_normalizes_exact_exposure_to_live_cap() -> None:
    """The $2,250 source lifecycle must preserve return at the $75 cap."""
    spec = CohortTradeSpec(
        "range_onset_bidirectional_v1",
        "SOL",
        notional_usd=75.0,
        leverage=5.0,
        entry_fee_bps=4.5,
    )

    adapter = getattr(portfolio, "adapt_range_event_payloads", None)
    assert adapter is not None, "range-event adapter is not implemented"
    trade = adapter((_range_payload(),), spec)[0]

    assert trade.side == "short"
    assert trade.outcome.entry_time_ms == 1_700_000_000_000
    assert trade.outcome.exit_time_ms == 1_700_003_600_000
    assert trade.outcome.margin_fraction == pytest.approx(0.03)
    assert trade.outcome.entry_fee_usd == pytest.approx(0.03375)
    assert trade.outcome.net_pnl_usd == pytest.approx(3.75)


def test_range_event_adapter_rejects_non_report_only_source() -> None:
    """A source with execution authority cannot enter the research replay."""
    payload = _range_payload()
    payload["execution_authority"] = "hyperliquid_mainnet"
    spec = CohortTradeSpec("range_onset_bidirectional_v1", "SOL", 75.0, 5.0, 4.5)

    with pytest.raises(ValueError, match="no execution authority"):
        adapter = getattr(portfolio, "adapt_range_event_payloads", None)
        assert adapter is not None, "range-event adapter is not implemented"
        adapter((payload,), spec)


def test_partition_uses_common_purge_boundaries_without_leakage() -> None:
    """Trades in the common purge gap must enter neither evidence partition."""
    spec = CohortTradeSpec("hype", "HYPE", 75.0, 5.0, 4.5)
    source = _breakout_trade()
    development = adapt_breakout_trades((source,), spec)[0]
    purge = adapt_breakout_trades(
        (
            replace(
                source,
                entry_time_utc="2026-05-28T12:00:00+00:00",
                exit_time_utc="2026-05-28T13:00:00+00:00",
            ),
        ),
        spec,
    )[0]
    holdout = adapt_breakout_trades(
        (
            replace(
                source,
                entry_time_utc="2026-05-29T00:00:00+00:00",
                exit_time_utc="2026-05-29T01:00:00+00:00",
            ),
        ),
        spec,
    )[0]

    partitions = partition_cohort_outcomes(
        (development, purge, holdout),
        development_end_utc="2026-05-28T00:00:00+00:00",
        holdout_start_utc="2026-05-29T00:00:00+00:00",
        holdout_end_utc="2026-07-28T00:00:00+00:00",
    )

    assert [trade.trade_id for trade in partitions["development"]] == [
        development.trade_id
    ]
    assert [trade.trade_id for trade in partitions["opened_final_60d"]] == [
        holdout.trade_id
    ]
    assert partitions["purged"] == (purge,)


def test_shared_replay_reports_strategy_and_side_attribution() -> None:
    """The shared total must expose every contributing strategy and direction."""
    btc_spec = CohortTradeSpec(
        "hulk_expansion_bidirectional_tuned_v2", "BTC", 25.0, 5.0, 4.5
    )
    hype_spec = CohortTradeSpec(
        "hype_breakout_onset_bidirectional_v1", "HYPE", 75.0, 5.0, 4.5
    )
    trades = adapt_hulk_payloads((_hulk_payload(),), btc_spec) + (
        adapt_breakout_trades((_breakout_trade(),), hype_spec)[0],
    )

    report = replay_cohort_outcomes(trades, initial_equity_usd=500.0)

    assert report["performance"]["completed_trades"] == 2
    assert report["performance"]["net_pnl_usd"] == pytest.approx(3.1825)
    assert report["capacity"]["maximum_concurrent_positions"] == 1
    assert report["by_strategy"][btc_spec.strategy_id]["net_pnl_usd"] == pytest.approx(
        2.5
    )
    assert report["by_strategy_side"][f"{hype_spec.strategy_id}|short"][
        "net_pnl_usd"
    ] == pytest.approx(0.6825)


def test_shared_replay_month_attribution_uses_utc() -> None:
    """An exit just after UTC midnight must not fall into the host-local month."""
    spec = CohortTradeSpec("candidate", "HYPE", 75.0, 5.0, 4.5)
    source = replace(
        _breakout_trade(),
        entry_time_utc="2026-05-31T23:01:00+00:00",
        exit_time_utc="2026-06-01T00:01:00+00:00",
    )
    trade = adapt_breakout_trades((source,), spec)[0]

    report = replay_cohort_outcomes((trade,), initial_equity_usd=500.0)

    assert set(report["by_exit_month"]) == {"2026-06"}
