"""Causal report-only profit-lock challenger tests."""

from __future__ import annotations

import pytest

from hypervector.research import cohort_profit_lock_challenger
from hypervector.research.cohort_profit_lock_challenger import (
    build_profit_lock_challenger,
    build_regime_conditioned_profit_lock_mechanism,
)


def test_profit_lock_arms_from_one_completed_bar_and_triggers_on_next() -> None:
    """The activation bar may only protect profit on a later bar."""
    report = build_profit_lock_challenger(
        _cohort_rows(
            _bar(60_000, 100.0, 100.30, 99.95, 100.20),
            _bar(120_000, 100.25, 100.25, 100.15, 100.20),
        ),
        {"HYPE": _asset_rows()},
        [_trade()],
        current_profile_fingerprint="profile-current",
        current_run_id="run-current",
    )

    assert report["contract"]["execution_authority"] == "none"
    result = report["latest_results"][0]["policies"]["a25_floor15_trail10"]
    assert result["status"] == "triggered"
    assert result["activation_timestamp_ms"] == 60_000
    assert result["trigger_timestamp_ms"] == 120_000
    assert result["stop_price_before_trigger"] == pytest.approx(100.1997)
    assert result["estimated_exit_price"] == pytest.approx(100.1997)
    assert result["estimated_net_pnl_usd"] == pytest.approx(0.099610135)
    summary = report["summary_by_policy"]["a25_floor15_trail10"]
    assert summary["eligible_lifecycles"] == 1
    assert summary["triggered"] == 1
    assert summary["estimated_minus_actual_net_usd"] == pytest.approx(0.199610135)
    assert report["current_run"]["summary_by_policy"] == report["summary_by_policy"]


def test_profit_lock_does_not_use_activation_bar_retracement() -> None:
    """A bar's low cannot hit a stop derived from that same bar's high."""
    trade = _trade(exit_ms=130_000)
    report = build_profit_lock_challenger(
        _cohort_rows(_bar(60_000, 100.0, 100.30, 99.90, 100.20)),
        {"HYPE": _asset_rows(exit_ms=130_000)},
        [trade],
        current_profile_fingerprint="profile-current",
        current_run_id="run-current",
    )

    result = report["latest_results"][0]["policies"]["a25_floor15_trail10"]
    assert result["status"] == "armed_not_triggered_before_actual_exit"
    assert result["activation_timestamp_ms"] == 60_000
    assert result["trigger_timestamp_ms"] is None
    assert result["estimated_net_pnl_usd"] == pytest.approx(-0.10)


def test_profit_lock_is_directionally_symmetric_for_short_positions() -> None:
    """Short protection trails a completed trough and triggers above it."""
    trade = _trade(side="short")
    report = build_profit_lock_challenger(
        _cohort_rows(
            _bar(60_000, 100.0, 100.05, 99.70, 99.80),
            _bar(120_000, 99.75, 99.85, 99.75, 99.80),
        ),
        {"HYPE": _asset_rows()},
        [trade],
        current_profile_fingerprint="profile-current",
        current_run_id="run-current",
    )

    result = report["latest_results"][0]["policies"]["a25_floor15_trail10"]
    assert result["status"] == "triggered"
    assert result["stop_price_before_trigger"] == pytest.approx(99.7997)
    assert result["estimated_exit_price"] == pytest.approx(99.7997)


def test_profit_lock_withholds_incomplete_candle_coverage() -> None:
    """Missing holding bars cannot become a success-shaped non-trigger."""
    report = build_profit_lock_challenger(
        _cohort_rows(_bar(60_000, 100.0, 100.30, 99.95, 100.20)),
        {"HYPE": _asset_rows()},
        [_trade()],
        current_profile_fingerprint="profile-current",
        current_run_id="run-current",
    )

    result = report["latest_results"][0]
    assert result["status"] == "insufficient_candle_coverage"
    assert result["completed_bars_expected"] == 2
    assert result["completed_bars_observed"] == 1
    summary = report["summary_by_policy"]["a25_floor15_trail10"]
    assert summary["eligible_lifecycles"] == 0
    assert summary["withheld_lifecycles"] == 1


def test_all_time_mechanism_normalizes_live_exit_economics_to_basis_points() -> None:
    """Mixed sizing contracts must be compared as normalized mechanism evidence."""
    builder = getattr(
        cohort_profit_lock_challenger,
        "build_all_time_profit_lock_mechanism",
        None,
    )
    assert callable(builder), "all-time live profit-lock mechanism is not implemented"

    report = builder(
        _cohort_rows(
            _bar(60_000, 100.0, 100.30, 99.95, 100.20),
            _bar(120_000, 100.25, 100.25, 100.15, 100.20),
        ),
        {"HYPE": _asset_rows()},
        [_trade()],
    )

    assert report["scope"] == "all_live_history_normalized_mechanism"
    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["portfolio_pnl_claimed"] is False
    assert report["profile_contracts_may_differ"] is True
    summary = report["summary_by_policy"]["a25_floor15_trail10"]
    assert summary["eligible_lifecycles"] == 1
    assert summary["mean_actual_net_return_bps"] == pytest.approx(-10.0)
    assert summary["mean_estimated_net_return_bps"] == pytest.approx(9.9610135)
    assert summary["mean_delta_net_return_bps"] == pytest.approx(19.9610135)
    robustness = report["robustness_by_policy"]["a25_floor15_trail10"]
    assert robustness["eligible_lifecycles"] == 1
    assert robustness["all_eligible_delta_net_return_bps"]["mean"] == pytest.approx(
        19.9610135
    )
    grouped = report["by_provider_symbol"]["hype_breakout_onset_bidirectional_v1|HYPE"]
    assert grouped["robustness_by_policy"] == report["robustness_by_policy"]


def test_regime_conditioned_lock_waits_for_five_opposed_decisions() -> None:
    """Pre-gate profit may inform a stop but cannot arm or trigger it early."""
    trade = _trade(exit_ms=250_000)
    trade["regime_opposition_episode"] = _opposition_episode(120_000)
    report = build_regime_conditioned_profit_lock_mechanism(
        _cohort_rows(
            _bar(60_000, 100.0, 100.50, 99.90, 100.40),
            _bar(120_000, 100.40, 100.45, 100.10, 100.20),
            _bar(180_000, 100.20, 100.25, 100.10, 100.15),
        ),
        {"HYPE": _asset_rows(exit_ms=250_000)},
        [trade],
    )

    assert report["contract"]["execution_authority"] == "none"
    assert report["activation_contract"]["persistence_decisions"] == 5
    result = report["latest_results"][0]["policies"]["a25_floor15_trail10"]
    assert result["status"] == "triggered"
    assert result["opposition_trigger_timestamp_ms"] == 120_000
    assert result["activation_timestamp_ms"] == 120_000
    assert result["trigger_timestamp_ms"] == 180_000


def test_support_decay_lock_arms_after_five_weak_structure_decisions() -> None:
    """A profitable trade may lock only after causal support decay persists."""
    builder = getattr(
        cohort_profit_lock_challenger,
        "build_support_decay_profit_lock_mechanism",
        None,
    )
    assert callable(builder), "support-decay profit-lock mechanism is not implemented"
    bars = (
        _bar(60_000, 100.0, 100.50, 99.95, 100.40),
        _bar(120_000, 100.40, 100.45, 100.30, 100.35),
        _bar(180_000, 100.35, 100.40, 100.30, 100.35),
        _bar(240_000, 100.35, 100.40, 100.30, 100.35),
        _bar(300_000, 100.35, 100.40, 100.30, 100.35),
        _bar(360_000, 100.35, 100.35, 100.25, 100.30),
    )
    report = builder(
        _cohort_rows_with_range_evaluations(bars),
        {"HYPE": _asset_rows(exit_ms=430_000)},
        [_trade(exit_ms=430_000)],
    )

    assert report["contract"]["execution_authority"] == "none"
    assert report["activation_contract"]["support_decay_threshold"] == pytest.approx(
        0.25
    )
    result = report["latest_results"][0]
    assert result["status"] == "eligible_persistent_support_decay"
    policy = result["policies"]["a40_floor15_trail20"]
    assert policy["status"] == "triggered"
    assert policy["support_decay_trigger_timestamp_ms"] == 300_000
    assert policy["activation_timestamp_ms"] == 300_000
    assert policy["trigger_timestamp_ms"] == 360_000
    assert policy["estimated_minus_actual_net_usd"] > 0.0


def test_no_persistent_opposition_preserves_actual_exit_without_candles() -> None:
    """A measured non-trigger needs no price counterfactual and stays eligible."""
    trade = _trade()
    trade["regime_opposition_episode"] = _opposition_episode(None)
    report = build_regime_conditioned_profit_lock_mechanism(
        [],
        {"HYPE": _asset_rows()},
        [trade],
    )

    result = report["latest_results"][0]
    assert result["status"] == "eligible_no_persistent_opposition"
    policy = result["policies"]["a25_floor15_trail10"]
    assert policy["status"] == "not_activated_no_persistent_opposition"
    assert policy["estimated_net_pnl_usd"] == pytest.approx(-0.10)
    assert report["summary_by_policy"]["a25_floor15_trail10"] == {
        "lifecycles": 1,
        "eligible_lifecycles": 1,
        "withheld_lifecycles": 0,
        "triggered": 0,
        "wins": 0,
        "losses": 1,
        "mean_estimated_net_return_bps": pytest.approx(-10.0),
        "mean_actual_net_return_bps": pytest.approx(-10.0),
        "mean_delta_net_return_bps": pytest.approx(0.0),
        "normalized_profit_factor": pytest.approx(0.0),
    }


def test_missing_opposition_episode_is_withheld_not_shaped_as_no_trigger() -> None:
    """Absent causal regime evidence cannot silently preserve an actual outcome."""
    report = build_regime_conditioned_profit_lock_mechanism(
        _cohort_rows(
            _bar(60_000, 100.0, 100.30, 99.95, 100.20),
            _bar(120_000, 100.25, 100.25, 100.15, 100.20),
        ),
        {"HYPE": _asset_rows()},
        [_trade()],
    )

    result = report["latest_results"][0]
    assert result["status"] == "missing_regime_opposition_evidence"
    policy = result["policies"]["a25_floor15_trail10"]
    assert policy["status"] == "withheld_missing_regime_opposition_evidence"
    assert policy["estimated_net_pnl_usd"] is None
    summary = report["summary_by_policy"]["a25_floor15_trail10"]
    assert summary["eligible_lifecycles"] == 0
    assert summary["withheld_lifecycles"] == 1


def test_malformed_opposition_trigger_contract_fails_closed() -> None:
    """A missing five-decision key cannot masquerade as an observed non-trigger."""
    trade = _trade()
    episode = _opposition_episode(None)
    episode["persistence_triggers"] = {"1": None, "3": None}
    trade["regime_opposition_episode"] = episode

    with pytest.raises(ValueError, match="five-decision opposition trigger"):
        build_regime_conditioned_profit_lock_mechanism(
            [],
            {"HYPE": _asset_rows()},
            [trade],
        )


def _cohort_rows(*bars: dict[str, object]) -> list[dict[str, object]]:
    return [
        {
            "event_type": "market_candles",
            "run_id": "run-current",
            "payload": {"timeframe": "1m", "bars": {"HYPE": list(bars)}},
        }
    ]


def _cohort_rows_with_range_evaluations(
    bars: tuple[dict[str, object], ...],
) -> list[dict[str, object]]:
    rows = _cohort_rows(*bars)
    for timestamp_ms in (60_000, 120_000, 180_000, 240_000, 300_000):
        rows.append(
            {
                "event_type": "intent_routing",
                "run_id": "run-current",
                "payload": {
                    "evaluations": [
                        _evaluation(
                            "hype_breakout_onset_bidirectional_v1", timestamp_ms
                        ),
                        _evaluation("range_onset_bidirectional_v1", timestamp_ms),
                    ]
                },
            }
        )
    return rows


def _evaluation(strategy_id: str, timestamp_ms: int) -> dict[str, object]:
    return {
        "strategy_id": strategy_id,
        "symbol": "HYPE",
        "decision_time_ms": timestamp_ms,
        "primary_regime": "RANGE",
        "state_1m": "RANGE",
        "state_5m": "RANGE",
        "context_15m": "RANGE",
        "confidence": 0.2,
    }


def _bar(
    timestamp_ms: int, open_price: float, high: float, low: float, close: float
) -> dict[str, object]:
    return {
        "timestamp_ms": timestamp_ms,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
    }


def _asset_rows(*, exit_ms: int = 190_000) -> list[dict[str, object]]:
    return [
        _event(
            "fill",
            oid=11,
            trade_id=101,
            venue_timestamp_ms=10_000,
            price=100.0,
            size=1.0,
            fee_usd=0.045,
        ),
        _event("funding", venue_timestamp_ms=120_000, usdc_delta=-0.01),
        _event(
            "fill",
            oid=12,
            trade_id=102,
            venue_timestamp_ms=exit_ms,
            price=100.0,
            size=1.0,
            fee_usd=0.045,
        ),
    ]


def _event(event_type: str, **payload: object) -> dict[str, object]:
    return {"event_type": event_type, "payload": payload}


def _opposition_episode(trigger_ms: int | None) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "causal_regime_opposition_persistence_v1",
        "entry_timestamp_ms": 10_000,
        "end_timestamp_ms": 250_000 if trigger_ms is not None else 190_000,
        "opposition_threshold": -0.5,
        "persistence_decisions": [1, 3, 5],
        "persistence_triggers": {"1": trigger_ms, "3": trigger_ms, "5": trigger_ms},
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
            "automatic_strategy_changes": False,
        },
    }


def _trade(*, side: str = "long", exit_ms: int = 190_000) -> dict[str, object]:
    return {
        "lifecycle_id": "HYPE:11",
        "source_run_id": "run-current",
        "source_profile_fingerprint": "profile-current",
        "symbol": "HYPE",
        "strategy_id": "hype_breakout_onset_bidirectional_v1",
        "side": side,
        "entry_oid": 11,
        "exit_oid": 12,
        "entry": {"price": 100.0, "size": 1.0, "venue_timestamp_ms": 10_000},
        "exit": {
            "price": 100.0,
            "size": 1.0,
            "venue_timestamp_ms": exit_ms,
            "expected_reference_price": 100.0,
        },
        "fees_usd": 0.09,
        "funding_usd": -0.01,
        "net_pnl_usd": -0.10,
    }
