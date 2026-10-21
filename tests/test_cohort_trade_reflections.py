"""Lifecycle-level regime reflection tests for the shared live cohort."""

from __future__ import annotations

from copy import deepcopy

import pytest

from cohort_trade_reflection_fixtures import (
    independent_canonical_rows as _independent_canonical_rows,
    open_reflection_asset_rows as _open_reflection_asset_rows,
    open_reflection_cohort_rows as _open_reflection_cohort_rows,
    reflection_asset_rows as _reflection_asset_rows,
    reflection_cohort_rows as _reflection_cohort_rows,
)
from hypervector.live.asset_live_journal import build_live_journal
from hypervector.research.cohort_live_audit import audit_multi_asset_live_run
from hypervector.research.cohort_trade_reflections import (
    build_all_time_trade_reflections,
    build_trade_reflections,
)
from test_multi_asset_live_audit import (
    _TREND,
    _RUN_ID,
    _SYMBOLS,
    _asset_rows,
)


def test_all_time_reflections_publish_user_history_without_compatibility_claim() -> (
    None
):
    """The TUI archive must retain a full lifecycle under an explicit all-live scope."""
    cohort = _reflection_cohort_rows()
    assets = _reflection_asset_rows()

    report = build_all_time_trade_reflections(
        cohort,
        {"BTC": build_live_journal(assets)},
        asset_records={"BTC": assets},
        live_run_ids=[_RUN_ID],
        horizons_minutes=[5],
    )

    assert report["scope"] == "all_live_history"
    assert report["history_schema_version"] == 1
    assert report["closed_trades"] == 1
    assert report["performance"]["scope"] == "all_live_history"
    assert report["performance"]["total"]["closed_trades"] == 1
    assert report["trades"][0]["source_run_id"] == _RUN_ID
    assert report["trades"][0]["fees_usd"] == pytest.approx(0.02)
    timer = report["maximum_hold_context_journal"]
    assert timer["timer_exits"] == 0
    assert timer["non_timer_exits"] == 1


def test_closed_trade_joins_entry_exit_regimes_and_post_exit_path() -> None:
    """A closed lifecycle retains causal setup, exit, and later-price context."""
    report = audit_multi_asset_live_run(
        _reflection_cohort_rows(),
        {
            "BTC": _reflection_asset_rows(),
            **{symbol: _asset_rows(symbol) for symbol in _SYMBOLS if symbol != "BTC"},
        },
        run_id=_RUN_ID,
    )

    reflections = report["trade_reflections"]
    assert reflections["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
    }
    assert reflections["closed_trades"] == 1
    assert reflections["all_time_live"]["scope"] == "all_live_history"
    assert reflections["all_time_live"]["closed_trades"] == 1
    assert (
        reflections["all_time_live"]["trades"][0]["lifecycle_id"]
        == (reflections["trades"][0]["lifecycle_id"])
    )
    trade = reflections["trades"][0]
    assert trade["strategy_id"] == _TREND
    assert trade["source_profile_fingerprint"] == "cohort-profile-fingerprint"
    assert trade["side"] == "long"
    assert trade["entry_oid"] == 11
    assert trade["exit_oid"] == 22
    assert trade["entry_margin_used_usd"] == pytest.approx(5.0)
    assert trade["leverage"] == pytest.approx(5.0)
    assert trade["price_return_pct"] == pytest.approx((103.98 / 100.01 - 1.0) * 100.0)
    assert trade["net_return_on_margin_pct"] == pytest.approx(19.4)
    assert trade["entry_context"]["signal_provider"]["primary_regime"] == "TREND_UP"
    assert trade["entry_context"]["canonical_regime"]["primary_regime"] == "RANGE"
    assert trade["entry_regime_assessment"]["structure_support_score"] == (
        pytest.approx(5.0 / 12.0)
    )
    assert trade["exit_context"]["signal_provider"]["primary_regime"] == "TRANSITION"
    assert trade["exit_context"]["canonical_regime"]["primary_regime"] == "RANGE"
    assert trade["exit_regime_assessment"]["structure_support_score"] == pytest.approx(
        2.0 / 12.0
    )
    assert trade["exit_regime_assessment"]["maximum_hold_context"] == (
        "mixed_or_transition"
    )
    opposition = trade["regime_opposition_episode"]
    assert opposition["contract"]["execution_authority"] == "none"
    assert opposition["completed_decisions"] == 1
    assert opposition["opposed_decisions"] == 0
    assert opposition["persistence_triggers"]["3"] is None
    path = trade["post_exit_path"]["5"]
    assert path["status"] == "resolved"
    assert path["lowest_price"] > 0.0
    assert path["highest_price"] >= path["lowest_price"]
    assert trade["protective_stop"] == {
        "oid": 33,
        "trigger_price": pytest.approx(99.0),
    }
    assert path["directional_close_return_bps"] == pytest.approx(
        (105.0 / 103.98 - 1.0) * 10_000.0
    )
    assert path["interpretation"] == "continued_original_direction"
    assert reflections["entry_followthrough_horizons_minutes"] == [
        240,
        720,
        1_440,
        2_880,
    ]
    entry_path = trade["entry_followthrough_path"]["240"]
    assert entry_path["status"] == "censored"
    assert entry_path["bars_observed"] == 59
    assert entry_path["bars_required"] == 240
    assert entry_path["first_candle_timestamp_ms"] == 1_785_600_060_000
    assert entry_path["last_candle_timestamp_ms"] == 1_785_603_540_000
    assert entry_path["directional_close_return_bps"] == pytest.approx(
        (109.9 / 100.01 - 1.0) * 10_000.0
    )
    assert entry_path["protective_stop_price_crossed"] is False
    assert entry_path["first_stop_price_cross_timestamp_ms"] is None
    assert "protective_stop_hit" not in entry_path
    capture = trade["completed_hold_capture"]
    assert capture["economic_outcome"] == "profitable_after_costs"
    assert capture["observed_cost_hurdle_bps"] == pytest.approx(
        0.03 / (100.01 * 0.25) * 10_000.0
    )
    assert capture["realized_net_return_bps"] == pytest.approx(
        0.97 / (100.01 * 0.25) * 10_000.0
    )
    assert capture["authoritative_gross_return_bps"] == pytest.approx(
        1.0 / (100.01 * 0.25) * 10_000.0
    )
    performance = reflections["performance"]
    assert performance["return_basis"] == "net_pnl_divided_by_sum_entry_margin"
    expected_total = {
        "closed_trades": 1,
        "wins": 1,
        "losses": 0,
        "breakeven": 0,
        "win_rate_pct": 100.0,
        "net_pnl_usd": pytest.approx(0.97),
        "entry_margin_used_usd": pytest.approx(5.0),
        "net_return_on_margin_pct": pytest.approx(19.4),
        "mean_trade_return_on_margin_pct": pytest.approx(19.4),
        "profit_factor": None,
        "fees_usd": pytest.approx(0.02),
        "funding_usd": pytest.approx(-0.01),
    }
    assert {key: performance["total"][key] for key in expected_total} == expected_total
    assert performance["by_strategy"][_TREND] == performance["total"]
    assert performance["mixed_profile_history"] is False
    assert performance["profile_fingerprint_count"] == 1
    assert performance["current_profile"]["total"] == performance["total"]
    repeatability = reflections["repeatability"]
    assert repeatability["contract"]["trade_count_gate"] is False
    repeatability_pair = repeatability["by_provider_symbol"][f"{_TREND}|BTC"]
    assert repeatability_pair["closed_trades"] == 1
    assert repeatability_pair["evidence_state"] == "single_trade_only"
    assert repeatability_pair["trades_per_24h_observed"] is None
    assert repeatability_pair["net_pnl_usd"] == pytest.approx(0.97)
    assert repeatability_pair["profit_forecast"] is None
    scorecard_repeatability = report["strategy_scorecard"]["by_provider_symbol"][
        f"{_TREND}|BTC"
    ]["repeatability_evidence"]
    assert scorecard_repeatability == repeatability_pair


def test_closed_trade_uses_independent_canonical_regime_evidence() -> None:
    """Entry and exit regime context comes from the canonical telemetry rows."""
    cohort = _independent_canonical_rows(_reflection_cohort_rows())
    report = audit_multi_asset_live_run(
        cohort,
        {
            "BTC": _reflection_asset_rows(),
            **{symbol: _asset_rows(symbol) for symbol in _SYMBOLS if symbol != "BTC"},
        },
        run_id=_RUN_ID,
    )

    trade = report["trade_reflections"]["trades"][0]
    assert trade["entry_context"]["canonical_regime"]["primary_regime"] == "RANGE"
    assert trade["exit_context"]["canonical_regime"]["primary_regime"] == "RANGE"


def test_entry_followthrough_records_first_protective_stop_cross() -> None:
    """A partial 48-hour path preserves the first completed-bar stop cross."""
    cohort = _reflection_cohort_rows()
    market = next(row for row in cohort if row["event_type"] == "market_candles")
    stop_bar = market["payload"]["bars"]["BTC"][3]
    stop_bar.update({"open": 99.1, "high": 99.2, "low": 98.5, "close": 98.9})

    report = audit_multi_asset_live_run(
        cohort,
        {
            "BTC": _reflection_asset_rows(),
            **{symbol: _asset_rows(symbol) for symbol in _SYMBOLS if symbol != "BTC"},
        },
        run_id=_RUN_ID,
    )

    path = report["trade_reflections"]["trades"][0]["entry_followthrough_path"]["240"]
    assert path["status"] == "censored"
    assert path["protective_stop_price_crossed"] is True
    assert path["first_stop_price_cross_timestamp_ms"] == 1_785_600_180_000


def test_trade_reflections_quantify_context_coverage() -> None:
    """Missing lifecycle context cannot be hidden by the aggregate report."""
    report = audit_multi_asset_live_run(
        _reflection_cohort_rows(),
        {
            "BTC": _reflection_asset_rows(),
            **{symbol: _asset_rows(symbol) for symbol in _SYMBOLS if symbol != "BTC"},
        },
        run_id=_RUN_ID,
    )

    assert report["trade_reflections"]["context_coverage"] == {
        "complete": True,
        "closed_trades": 1,
        "observed": {
            "entry_signal_provider": 1,
            "entry_canonical_regime": 1,
            "exit_signal_provider": 1,
            "exit_canonical_regime": 1,
        },
        "missing": {
            "entry_signal_provider": 0,
            "entry_canonical_regime": 0,
            "exit_signal_provider": 0,
            "exit_canonical_regime": 0,
        },
    }


def test_trade_reflections_group_post_exit_evidence_by_exit_reason() -> None:
    """Exit-policy review separates continuation evidence from censored paths."""
    report = audit_multi_asset_live_run(
        _reflection_cohort_rows(),
        {
            "BTC": _reflection_asset_rows(),
            **{symbol: _asset_rows(symbol) for symbol in _SYMBOLS if symbol != "BTC"},
        },
        run_id=_RUN_ID,
    )

    reason = report["trade_reflections"]["by_exit_reason"]["opposite_strategy_intent"]
    assert reason["closed_trades"] == 1
    assert reason["net_pnl_usd"] == pytest.approx(0.97)
    assert reason["horizons"]["5"] == {
        "resolved": 1,
        "continued_original_direction": 1,
        "reversed_against_original_direction": 0,
        "unchanged": 0,
        "censored": 0,
        "missing_data": 0,
    }
    assert reason["horizons"]["60"]["censored"] == 1
    timer = report["trade_reflections"]["maximum_hold_context_journal"]
    assert timer["timer_exits"] == 0
    assert timer["non_timer_exits"] == 1


def test_trade_reflections_identify_cross_provider_exit_controller() -> None:
    """A different provider closing a trade cannot inherit entry-provider credit."""
    asset_rows = _reflection_asset_rows()
    exit_decision = next(
        row
        for row in asset_rows
        if row["event_type"] == "regime_decision"
        and row["payload"].get("decision_action") == "long_exit"
    )
    exit_decision["payload"]["strategy_id"] = "test_breakout_1m"

    report = audit_multi_asset_live_run(
        _reflection_cohort_rows(),
        {
            "BTC": asset_rows,
            **{symbol: _asset_rows(symbol) for symbol in _SYMBOLS if symbol != "BTC"},
        },
        run_id=_RUN_ID,
    )

    trade = report["trade_reflections"]["trades"][0]
    assert trade["entry_strategy_id"] == _TREND
    assert trade["exit_controller_strategy_id"] == "test_breakout_1m"
    assert trade["cross_provider_exit"] is True
    assert trade["exit_context"]["signal_provider"]["strategy_id"] == _TREND
    assert trade["exit_context"]["exit_controller"]["strategy_id"] == (
        "test_breakout_1m"
    )
    attribution = report["trade_reflections"]["exit_controller_attribution"]
    assert attribution["cross_provider_exits"] == 1
    assert attribution["same_provider_exits"] == 0
    route = attribution["by_entry_and_exit_controller"][
        f"{_TREND}|test_breakout_1m"
    ]
    assert route["closed_trades"] == 1
    assert route["net_pnl_usd"] == pytest.approx(0.97)
    assert route["exit_reasons"] == {"opposite_strategy_intent": 1}


def test_restart_overlap_uses_the_trade_source_run_for_entry_context() -> None:
    """A later recomputation cannot rewrite the regime that caused an entry."""
    cohort = _reflection_cohort_rows()
    duplicate = deepcopy(cohort[1])
    duplicate["sequence"] = len(cohort) + 1
    duplicate["run_id"] = "restart-run"
    duplicate["payload"]["actions"] = []
    trend = next(
        evaluation
        for evaluation in duplicate["payload"]["evaluations"]
        if evaluation["strategy_id"] == _TREND and evaluation["symbol"] == "BTC"
    )
    trend.update({"primary_regime": "RANGE", "eligible": False})
    asset_rows = _reflection_asset_rows()

    reflections = build_trade_reflections(
        [*cohort, duplicate],
        {"BTC": build_live_journal(asset_rows)},
        asset_records={"BTC": asset_rows},
        compatible_run_ids=[_RUN_ID, "restart-run"],
        current_profile_fingerprint="cohort-profile-fingerprint",
        current_run_id="restart-run",
        horizons_minutes=[5],
    )

    trade = reflections["trades"][0]
    assert trade["source_run_id"] == _RUN_ID
    assert trade["entry_context"]["signal_provider"]["primary_regime"] == "TREND_UP"


def test_open_lifecycle_joins_entry_regime_to_current_regime_and_mark() -> None:
    """An open position shows causal regime drift without inventing an exit."""
    report = audit_multi_asset_live_run(
        _open_reflection_cohort_rows(),
        {
            "BTC": _open_reflection_asset_rows(),
            **{symbol: _asset_rows(symbol) for symbol in _SYMBOLS if symbol != "BTC"},
        },
        run_id=_RUN_ID,
    )

    reflections = report["open_trade_reflections"]
    assert reflections["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
    }
    assert reflections["open_lifecycles"] == 1
    trade = reflections["trades"][0]
    assert trade["symbol"] == "BTC"
    assert trade["side"] == "long"
    assert trade["protective_stop"] == {
        "oid": 33,
        "trigger_price": pytest.approx(99.0),
    }
    exit_plan = trade["exit_plan"]
    assert exit_plan["maximum_hold_seconds"] == 28_800
    assert exit_plan["source"] == "asset_runtime_default"
    assert exit_plan["controller"] == "cohort_maximum_hold"
    assert exit_plan["opposite_intent_exit_scope"] == (
        "selected_opposite_from_any_executable_provider_same_symbol"
    )
    assert exit_plan["opposite_intent_arbitration"] == "regime_then_priority"
    assert exit_plan["provider_recipe_exit_policy"] == "ignore"
    assert exit_plan["deadline_timestamp_ms"] == (
        trade["entry"]["venue_timestamp_ms"] + 28_800_000
    )
    assert exit_plan["remaining_time_ms"] == max(
        0,
        exit_plan["deadline_timestamp_ms"] - reflections["as_of_timestamp_ms"],
    )
    assert exit_plan["expired"] is False
    path = trade["path_since_entry"]
    assert path["status"] == "unavailable"
    assert path["completed_bars"] == 0
    assert path["current_directional_return_bps"] == pytest.approx(
        (104.5 / 100.01 - 1.0) * 10_000.0
    )
    assert path["maximum_favorable_excursion_bps"] is None
    assert path["maximum_adverse_excursion_bps"] is None
    assert path["peak_giveback_bps"] is None
    assert trade["entry_context"]["signal_provider"]["primary_regime"] == "TREND_UP"
    assert trade["entry_context"]["canonical_regime"]["primary_regime"] == "RANGE"
    assert trade["entry_regime_assessment"]["structure_support_score"] == (
        pytest.approx(5.0 / 12.0)
    )
    assert trade["current_context"]["signal_provider"]["primary_regime"] == "TRANSITION"
    assert trade["current_context"]["canonical_regime"]["primary_regime"] == "RANGE"
    assert trade["regime_drift"] == {
        "signal_provider_changed": True,
        "canonical_regime_changed": False,
    }
    assert trade["regime_assessment"]["structure_support_score"] == pytest.approx(
        2.0 / 12.0
    )
    assert trade["regime_assessment"]["maximum_hold_context"] == ("mixed_or_transition")
    opposition = trade["regime_opposition_episode"]
    assert opposition["contract"]["execution_authority"] == "none"
    assert opposition["completed_decisions"] == 0
    assert opposition["current_active"] is False
    assert trade["marked_economics"]["mark_price"] == pytest.approx(104.5)
    assert trade["marked_economics"][
        "active_lifecycle_marked_net_pnl_usd"
    ] == pytest.approx(1.1025)
    protection = trade["profit_protection"]
    assert protection["status"] == "open_profit_unprotected"
    assert protection["estimated_exit_now_net_usd"] < 1.1025
    assert protection["estimated_stop_net_usd"] < 0.0
    assert protection["marked_to_stop_giveback_usd"] == pytest.approx(
        protection["estimated_exit_now_net_usd"] - protection["estimated_stop_net_usd"]
    )
    assert protection["protected_profit_fraction"] == pytest.approx(0.0)


def test_open_lifecycle_retains_exact_active_target_order() -> None:
    """An open reflection exposes the backend-bound reduce-only target."""
    cohort = _open_reflection_cohort_rows()
    for row in cohort:
        if row["event_type"] != "cohort_snapshot":
            continue
        btc = next(
            asset for asset in row["payload"]["assets"] if asset["symbol"] == "BTC"
        )
        btc.update({"target_oid": 44, "target_price": 106.0})

    report = audit_multi_asset_live_run(
        cohort,
        {
            "BTC": _open_reflection_asset_rows(),
            **{symbol: _asset_rows(symbol) for symbol in _SYMBOLS if symbol != "BTC"},
        },
        run_id=_RUN_ID,
    )

    trade = report["open_trade_reflections"]["trades"][0]
    assert trade["target_order"] == {
        "oid": 44,
        "limit_price": pytest.approx(106.0),
        "directional_distance_bps": pytest.approx((106.0 / 104.5 - 1.0) * 10_000.0),
    }


def test_open_entry_context_prefers_exact_provider_evaluation() -> None:
    """Sparse asset decisions cannot erase the causal cohort entry regime."""
    assets = _open_reflection_asset_rows()
    decision = next(row for row in assets if row["event_type"] == "regime_decision")
    decision["payload"].update(
        {
            "primary_regime": None,
            "state_1m": None,
            "state_5m": None,
            "context_15m": None,
            "confidence": None,
        }
    )
    report = audit_multi_asset_live_run(
        _open_reflection_cohort_rows(),
        {
            "BTC": assets,
            **{symbol: _asset_rows(symbol) for symbol in _SYMBOLS if symbol != "BTC"},
        },
        run_id=_RUN_ID,
    )

    entry = report["open_trade_reflections"]["trades"][0]["entry_context"]
    assert entry["signal_provider"]["primary_regime"] == "TREND_UP"


def test_open_exit_plan_prefers_the_bound_provider_contract() -> None:
    """A bound entry contract overrides the asset-level legacy timer."""
    cohort = _open_reflection_cohort_rows()
    snapshot = next(
        row for row in reversed(cohort) if row["event_type"] == "cohort_snapshot"
    )
    btc = next(
        asset for asset in snapshot["payload"]["assets"] if asset["symbol"] == "BTC"
    )
    btc["execution_plan"] = {
        "strategy_id": _TREND,
        "maximum_hold_seconds": 28_800,
        "maximum_hold_policy": "extend_while_regime_supported",
        "hard_maximum_hold_seconds": 86_400,
        "provider_recipe_exit_policy": "honor",
    }
    report = audit_multi_asset_live_run(
        cohort,
        {
            "BTC": _open_reflection_asset_rows(),
            **{symbol: _asset_rows(symbol) for symbol in _SYMBOLS if symbol != "BTC"},
        },
        run_id=_RUN_ID,
    )

    trade = report["open_trade_reflections"]["trades"][0]
    plan = trade["exit_plan"]
    assert plan["maximum_hold_seconds"] == 28_800
    assert plan["maximum_hold_policy"] == "extend_while_regime_supported"
    assert plan["hard_maximum_hold_seconds"] == 86_400
    assert plan["provider_recipe_exit_policy"] == "honor"
    assert plan["soft_deadline_timestamp_ms"] < plan["hard_deadline_timestamp_ms"]
    assert plan["source"] == "bound_execution_plan"
    path = trade["path_since_soft_deadline"]
    assert path["status"] == "pending_soft_deadline"
    assert path["boundary_timestamp_ms"] == plan["soft_deadline_timestamp_ms"]
    assert path["completed_bars"] == 0
    assert path["current_directional_return_bps"] is None


def test_open_exit_plan_uses_persisted_runtime_timer_origin() -> None:
    """Displayed deadlines use the same opened_at clock as the live controller."""
    cohort = _open_reflection_cohort_rows()
    snapshot = next(
        row for row in reversed(cohort) if row["event_type"] == "cohort_snapshot"
    )
    btc = next(
        asset for asset in snapshot["payload"]["assets"] if asset["symbol"] == "BTC"
    )
    btc["execution_plan"] = {
        "strategy_id": _TREND,
        "maximum_hold_seconds": 28_800,
        "maximum_hold_policy": "extend_while_regime_supported",
        "hard_maximum_hold_seconds": 86_400,
    }
    assets = _open_reflection_asset_rows()
    assets.append(
        {
            **deepcopy(assets[-1]),
            "sequence": len(assets) + 1,
            "event_type": "state_transition",
            "payload": {
                "state": "OPEN",
                "entry_oid": 11,
                "opened_at_ms": 1_785_599_990_000,
                "execution_plan": dict(btc["execution_plan"]),
            },
        }
    )

    report = audit_multi_asset_live_run(
        cohort,
        {
            "BTC": assets,
            **{symbol: _asset_rows(symbol) for symbol in _SYMBOLS if symbol != "BTC"},
        },
        run_id=_RUN_ID,
    )

    plan = report["open_trade_reflections"]["trades"][0]["exit_plan"]
    assert plan["timer_origin"] == "persisted_runtime_opened_at"
    assert plan["opened_at_ms"] == 1_785_599_990_000
    assert plan["soft_deadline_timestamp_ms"] == 1_785_628_790_000
