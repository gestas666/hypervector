from __future__ import annotations

from copy import deepcopy

import pytest

from hypervector.research.cohort_mandate_evidence import build_mandate_evidence


def test_zero_population_is_measured_without_inventing_rejections() -> None:
    report = build_mandate_evidence(_audit())

    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
    }
    assert report["execution"]["status"] == "measured_zero_fills"
    assert report["execution"]["order_rejections"] == {
        "status": "measured_no_submission_attempts",
        "count": 0,
        "submission_capable_actions": 0,
    }
    assert report["trades"]["status"] == "measured_zero"
    assert report["trades"]["current_run"]["closed_trades"] == 0
    assert report["trades"]["accounting_epoch"]["closed_trades"] == 0
    assert report["trades"]["mixed_contract_all_live"]["closed_trades"] == 73
    assert report["trades"]["open_lifecycles"] == 0


def test_order_rejections_remain_unknown_after_an_action_without_outcomes() -> None:
    """Absence of faults cannot prove that an attempted order was accepted."""
    audit = _audit()
    audit["routing"]["actions"] = 1

    report = build_mandate_evidence(audit)

    assert report["execution"]["order_rejections"] == {
        "status": "unavailable_submission_outcomes_not_projected",
        "count": None,
        "submission_capable_actions": 1,
    }


def test_withheld_intent_reasons_are_preserved_and_reconciled() -> None:
    """The mandate report must retain every backend non-action cause."""
    audit = _audit()
    audit["routing"]["withheld"] = 3
    audit["routing"]["withheld_reasons"] = {
        "provider_direction_observe_only": 1,
        "same_direction_position_open": 2,
    }

    execution = build_mandate_evidence(audit)["execution"]

    assert execution["withheld_reasons"] == {
        "provider_direction_observe_only": 1,
        "same_direction_position_open": 2,
    }


def test_withheld_reason_totals_fail_closed_on_contradiction() -> None:
    """A summary cannot hide withheld intents behind incomplete reason rows."""
    audit = _audit()
    audit["routing"]["withheld"] = 2
    audit["routing"]["withheld_reasons"] = {"same_direction_position_open": 1}

    with pytest.raises(ValueError, match="withheld reason counts disagree"):
        build_mandate_evidence(audit)


def test_opportunities_are_annotations_not_missed_trade_claims() -> None:
    report = build_mandate_evidence(_audit())

    opportunity = report["opportunities"]
    assert opportunity["status"] == "measured_no_eligible_signals"
    assert opportunity["provider_evaluations"] == 12
    assert opportunity["directional_evaluations"] == 10
    assert opportunity["eligible_evaluations"] == 0
    assert opportunity["exact_one_blocker_candidates"] == 6
    assert opportunity["book_matched_candidates"] == 5
    assert opportunity["book_missing_candidates"] == 1
    assert opportunity["missed_trade_claimed"] is False
    assert opportunity["rejected_order_claimed"] is False


def test_portfolio_separates_realized_and_planned_concentration() -> None:
    report = build_mandate_evidence(_audit())

    portfolio = report["portfolio_interactions"]
    assert portfolio["status"] == "measured_flat"
    assert portfolio["realized"]["maximum_open_positions"] == 0
    assert portfolio["planned"]["configured_assets"] == 2
    assert portfolio["planned"]["configured_maximum_positions"] == 10
    assert portfolio["planned"]["practical_asset_slots"] == 2
    assert portfolio["planned"]["planned_margin_usd"] == pytest.approx(500.0)
    assert portfolio["planned"]["planned_notional_usd"] == pytest.approx(5000.0)
    assert portfolio["planned"]["largest_margin_share"] == pytest.approx(0.6)
    assert (
        portfolio["correlation_evidence"]["status"]
        == "unavailable_no_overlap_projection"
    )


def test_trade_population_reconciles_nonzero_lifecycles() -> None:
    audit = _audit()
    audit["execution"].update(
        {
            "closed_trades": 1,
            "open_lifecycles": 1,
            "fills": 3,
            "current_run_fills": 3,
            "wins": 1,
            "net_pnl_usd": 12.0,
            "fees_usd": 1.5,
            "funding_usd": -0.25,
            "open_positions": [_open_position()],
        }
    )
    audit["trade_reflections"]["closed_trades"] = 1
    audit["trade_reflections"]["trades"] = [{"lifecycle_id": "BTC:1"}]
    audit["trade_reflections"]["performance"]["current_run"]["total"] = _performance(
        closed=1,
        wins=1,
        net=12.0,
    )
    audit["open_trade_reflections"]["open_lifecycles"] = 1
    audit["open_trade_reflections"]["trades"] = [{"lifecycle_id": "ETH:2"}]
    audit["portfolio_archive"]["coverage"]["closed_orders"] = 1
    audit["portfolio_archive"]["performance"]["total"] = _performance(
        closed=1,
        wins=1,
        net=12.0,
    )

    report = build_mandate_evidence(audit)

    assert report["execution"]["status"] == "measured"
    assert report["trades"]["status"] == "measured"
    assert report["trades"]["closed_lifecycles"] == 1
    assert report["trades"]["open_lifecycles"] == 1
    assert report["trades"]["reflection_reconciliation"] == "exact"


def test_execution_economics_separates_provisional_open_costs_and_pnl() -> None:
    """Open marks and entry costs must not disappear behind closed-only totals."""
    audit = _audit()
    audit["execution"].update(
        {
            "fills": 1,
            "current_run_fills": 1,
            "open_lifecycles": 1,
            "open_positions": [_open_position()],
        }
    )
    audit["open_trade_reflections"]["open_lifecycles"] = 1
    audit["open_trade_reflections"]["trades"] = [{"lifecycle_id": "xyz:SPCX:1"}]

    economics = build_mandate_evidence(audit)["execution"]["economics"]

    assert economics["net_pnl_usd"] == 0.0
    assert economics["fees_usd"] == 0.0
    assert economics["open_totals"] == {
        "fees_usd": pytest.approx(0.423812),
        "funding_usd": pytest.approx(0.0016),
        "realized_pnl_usd": 0.0,
        "unrealized_pnl_usd": pytest.approx(-6.944),
        "marked_net_pnl_usd": pytest.approx(-7.366212),
        "margin_used_usd": pytest.approx(483.157948),
        "position_value_usd": pytest.approx(4898.2976),
    }
    assert economics["combined_closed_plus_open_marked_pnl_usd"] == pytest.approx(
        -7.366212
    )
    assert economics["open_positions"][0]["symbol"] == "xyz:SPCX"


def test_conflicting_trade_counts_fail_closed() -> None:
    audit = _audit()
    audit["execution"]["closed_trades"] = 1

    with pytest.raises(ValueError, match="closed lifecycle counts disagree"):
        build_mandate_evidence(audit)


def test_missing_sources_remain_explicitly_unavailable() -> None:
    report = build_mandate_evidence({"health": {"faults": 0}})

    assert report["execution"] == {
        "status": "unavailable",
        "reason": "execution_or_routing_unavailable",
    }
    assert report["trades"] == {
        "status": "unavailable",
        "reason": "trade_reflections_unavailable",
    }
    assert report["opportunities"] == {
        "status": "unavailable",
        "reason": "signal_or_orderbook_opportunity_unavailable",
    }
    assert report["portfolio_interactions"] == {
        "status": "unavailable",
        "reason": "portfolio_or_risk_utilization_unavailable",
    }


def test_nested_execution_authority_is_rejected() -> None:
    audit = _audit()
    audit["risk_utilization"]["contract"]["execution_authority"] = "live"

    with pytest.raises(ValueError, match="risk utilization is not report-only"):
        build_mandate_evidence(audit)


def _audit() -> dict[str, object]:
    return {
        "execution": _execution(),
        "routing": _routing(),
        "trade_reflections": _trade_reflections(),
        "open_trade_reflections": _open_trade_reflections(),
        "portfolio_archive": _portfolio_archive(),
        "portfolio": _portfolio(),
        "risk_utilization": _risk_utilization(),
        "readiness": _readiness(),
        "signal_outcomes": _signal_outcomes(),
        "orderbook_opportunity": _orderbook_opportunity(),
        "canonical_regime_telemetry": _regime(),
        "coverage": {"complete": True, "technical_gaps": []},
        "health": _health(),
    }


def _execution() -> dict[str, object]:
    empty_metric = {"status": "not_applicable_no_fills", "count": 0}
    return {
        "scope": "compatible_profile_history",
        "closed_trades": 0,
        "open_lifecycles": 0,
        "fills": 0,
        "current_run_fills": 0,
        "wins": 0,
        "losses": 0,
        "net_pnl_usd": 0.0,
        "fees_usd": 0.0,
        "funding_usd": 0.0,
        "history_run_ids": ["run-51"],
        "slippage_bps": deepcopy(empty_metric),
        "acknowledgement_latency_ms": deepcopy(empty_metric),
        "markout_bps": deepcopy(empty_metric),
        "friction_parity": {
            "summary": {
                "provider_symbols": 2,
                "provider_symbols_with_entry_fills": 0,
                "runtime_shape_aligned": 2,
                "contract_mismatch": 0,
                "runtime_contract_missing": 0,
                "unsupported_contract": 0,
            }
        },
    }


def _open_position() -> dict[str, object]:
    return {
        "symbol": "xyz:SPCX",
        "side": "long",
        "fees_usd": 0.423812,
        "funding_usd": 0.0016,
        "realized_pnl_usd": 0.0,
        "unrealized_pnl_usd": -6.944,
        "active_lifecycle_marked_net_pnl_usd": -7.366212,
        "margin_used_usd": 483.157948,
        "position_value_usd": 4898.2976,
    }


def _routing() -> dict[str, object]:
    return {
        "cycles": 8,
        "strategy_intents": 0,
        "actions": 0,
        "lifecycle_actions": 0,
        "withheld": 0,
        "withheld_reasons": {},
    }


def _trade_reflections() -> dict[str, object]:
    return {
        "scope": "compatible_profile_history",
        "closed_trades": 0,
        "trades": [],
        "contract": _report_only_contract(),
        "performance": {
            "current_run": {"run_id": "run-51", "total": _performance()},
            "all_time_live": {
                "total": _performance(closed=73, wins=34, losses=39, net=4.2)
            },
        },
    }


def _open_trade_reflections() -> dict[str, object]:
    return {
        "scope": "compatible_profile_history",
        "open_lifecycles": 0,
        "trades": [],
        "contract": _report_only_contract(),
    }


def _portfolio_archive() -> dict[str, object]:
    return {
        "contract": _report_only_contract(),
        "accounting_epoch": {"epoch_id": "v51-first-live"},
        "coverage": {"closed_orders": 0, "complete": True},
        "performance": {"total": _performance()},
    }


def _portfolio() -> dict[str, object]:
    return {
        "status": "observed",
        "initial_equity_usd": 1000.0,
        "final_equity_usd": 1000.0,
        "equity_change_usd": 0.0,
        "maximum_drawdown_pct": 0.0,
        "maximum_margin_used_usd": 0.0,
        "maximum_notional_usd": 0.0,
        "maximum_open_positions": 0,
        "snapshot_count": 8,
    }


def _risk_utilization() -> dict[str, object]:
    return {
        "contract": _report_only_contract(),
        "account_value_usd": 1000.0,
        "by_asset": {
            "BTC": {"planned_margin_usd": 300.0, "planned_notional_usd": 3000.0},
            "ETH": {"planned_margin_usd": 200.0, "planned_notional_usd": 2000.0},
        },
        "summary": {
            "configured_assets": 2,
            "configured_maximum_positions": 10,
            "maximum_simultaneous_effective_margin_fraction": 0.5,
            "cap_bound_assets": 1,
        },
    }


def _readiness() -> dict[str, object]:
    return {
        "evaluations": 12,
        "expected_provider_symbols": 2,
        "observed_provider_symbols": 2,
        "missing_provider_symbols": [],
        "by_provider_symbol": {},
    }


def _signal_outcomes() -> dict[str, object]:
    return {
        "contract": {
            "counterfactual_only": True,
            "execution_authority": "none",
            "fills_assumed": False,
            "pnl_claimed": False,
        },
        "evaluations": 12,
        "directional_evaluations": 10,
        "eligible_evaluations": 0,
        "direction_conflicts": 1,
        "coverage": {"right_censored_observations": 3, "complete": True},
    }


def _orderbook_opportunity() -> dict[str, object]:
    return {
        "contract": _report_only_contract(),
        "coverage": {
            "exact_one_blocker_candidates": 6,
            "book_matched": 5,
            "book_missing": 1,
            "book_stale": 0,
        },
        "eligible_signal_context": {
            "coverage": {
                "eligible_signals": 0,
                "book_matched": 0,
                "book_missing": 0,
                "book_stale": 0,
            }
        },
    }


def _regime() -> dict[str, object]:
    return {
        "contract": {"execution_authority": "none", "intents_emitted": False},
        "evaluations": 6,
        "symbols": 2,
        "by_symbol": {"BTC": {}, "ETH": {}},
    }


def _health() -> dict[str, object]:
    return {
        "faults": 0,
        "assets": {
            "BTC": {"position_size_signed": 0.0, "protected_if_open": True},
            "ETH": {"position_size_signed": 0.0, "protected_if_open": True},
        },
    }


def _performance(
    *,
    closed: int = 0,
    wins: int = 0,
    losses: int = 0,
    net: float = 0.0,
) -> dict[str, object]:
    return {
        "closed_trades": closed,
        "wins": wins,
        "losses": losses,
        "breakeven": closed - wins - losses,
        "net_pnl_usd": net,
        "fees_usd": 0.0,
        "funding_usd": 0.0,
        "profit_factor": None,
        "net_pnl_excluding_largest_winner_usd": None,
        "maximum_closed_sequence_drawdown_usd": 0.0,
    }


def _report_only_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
    }
