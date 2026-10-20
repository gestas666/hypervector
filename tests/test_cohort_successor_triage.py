"""Tests for report-only, side-aware portfolio successor triage."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_successor_triage import build_successor_triage


def test_negative_history_is_not_erased_by_one_live_winner() -> None:
    """One profitable long cannot rehabilitate a negative exact contract."""
    audit = _audit(
        _record(
            state="historical_native_transfer_negative",
            execution=_execution(long=(1, 0, 0.55)),
        )
    )

    report = build_successor_triage(audit)

    route = report["routes"]["strategy|HYPE"]
    assert route["historical_assessment"] == "adverse_exact_contract"
    assert route["live_translation"]["closed_trades"] == 1
    assert route["live_translation"]["net_pnl_usd"] == pytest.approx(0.55)
    assert route["live_translation"]["observed_sides"] == ["long"]
    assert route["triage"] == "STOP"
    assert route["next_experiment"] == "new_mechanic_version_required"
    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["performance_gate"] is False


def test_directional_contradiction_requires_separate_side_mechanisms() -> None:
    """A positive route label cannot hide contradictory short evidence."""
    record = _record(
        state="directional_candidate",
        directional={
            "long": {"research_state": "historical_candidate"},
            "short": {"research_state": "contradictory"},
        },
    )

    route = build_successor_triage(_audit(record))["routes"]["strategy|HYPE"]

    assert route["historical_assessment"] == "directionally_contradictory"
    assert route["side_assessments"] == {
        "long": "supportive",
        "short": "contradictory",
    }
    assert route["triage"] == "REVISE"
    assert route["next_experiment"] == "separate_long_short_mechanisms"


def test_exhausted_side_timing_set_requires_new_mechanism_identity() -> None:
    """A falsified timing set must not be queued for the same split again."""
    record = _record(
        state="side_timing_set_falsified_new_mechanism_required",
        directional={
            "long": {"research_state": "contradictory"},
            "short": {"research_state": "contradictory"},
        },
    )

    route = build_successor_triage(_audit(record))["routes"]["strategy|HYPE"]

    assert route["historical_assessment"] == "tested_side_timing_set_falsified"
    assert route["triage"] == "REVISE"
    assert route["next_experiment"] == "new_side_mechanic_version_required"


def test_exhausted_side_relation_set_requires_new_mechanism_identity() -> None:
    """An exhausted breakout-relation split must not be recommended again."""
    record = _record(
        state="side_relation_set_falsified_new_mechanism_required",
        directional={
            "long": {"research_state": "contradictory"},
            "short": {"research_state": "contradictory"},
        },
    )

    route = build_successor_triage(_audit(record))["routes"]["strategy|HYPE"]

    assert route["historical_assessment"] == "tested_side_relation_set_falsified"
    assert route["triage"] == "REVISE"
    assert route["next_experiment"] == "new_side_mechanic_version_required"


def test_both_side_repeatable_after_cost_route_can_reach_portfolio_stage() -> None:
    """Proceed requires supportive, both-side, non-concentrated live evidence."""
    record = _record(
        state="historical_candidate",
        directional={
            "long": {"research_state": "historical_candidate"},
            "short": {"research_state": "historical_candidate"},
        },
        execution=_execution(
            long=(3, 1, 1.2),
            short=(2, 1, 0.8),
            profit_factor=1.8,
        ),
        repeatability={
            "closed_trades": 7,
            "evidence_state": "descriptive_multi_trade_sample",
            "net_pnl_excluding_largest_winner_usd": 0.6,
        },
        horizons={
            "15": {
                "resolved": 7,
                "independent": 5,
                "mean_directional_return_bps": 18.0,
                "positive_directional_rate": 0.7,
            }
        },
    )

    route = build_successor_triage(_audit(record))["routes"]["strategy|HYPE"]

    assert route["triage"] == "PROCEED"
    assert route["next_experiment"] == "shared_portfolio_interaction_replay"
    assert route["live_translation"]["observed_sides"] == ["long", "short"]
    assert route["cost_survival"] == "positive_after_observed_costs"
    assert route["concentration"] == "positive_without_largest_winner"


def test_open_mark_is_provisional_and_cannot_change_triage() -> None:
    """An unresolved marked gain remains separate from closed outcomes."""
    audit = _audit(
        _record(state="historical_candidate"),
        opens=[
            {
                "strategy_id": "strategy",
                "symbol": "HYPE",
                "side": "long",
                "marked_economics": {
                    "active_lifecycle_marked_net_pnl_usd": 4.2,
                },
            }
        ],
    )

    route = build_successor_triage(audit)["routes"]["strategy|HYPE"]

    assert route["triage"] == "REVISE"
    assert route["live_translation"]["closed_trades"] == 0
    assert route["provisional_open"] == {
        "count": 1,
        "marked_net_pnl_usd": 4.2,
        "sides": ["long"],
    }
    assert "open" not in route["next_experiment"]


def test_rejects_scorecard_with_execution_authority() -> None:
    """The triage cannot consume evidence carrying execution authority."""
    audit = _audit(_record(state="historical_candidate"))
    audit["strategy_scorecard"]["contract"]["execution_authority"] = (
        "hyperliquid_mainnet"
    )

    with pytest.raises(ValueError, match="execution_authority"):
        build_successor_triage(audit)


def _audit(
    record: dict[str, object],
    *,
    opens: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "run": {
            "run_id": "run-1",
            "profile_id": "fixture_profile",
            "profile_fingerprint": "a" * 64,
            "last_observed_at_utc": "2026-08-08T21:00:00+00:00",
        },
        "experiment_contract": {
            "report_only": True,
            "execution_authority": "none",
            "performance_gate": False,
            "balance_gate": False,
            "runtime_strategy_changed": False,
        },
        "strategy_scorecard": {
            "contract": {
                "report_only": True,
                "execution_authority": "none",
                "performance_gate": False,
                "balance_gate": False,
                "trade_count_gate": False,
                "automatic_pause": False,
                "automatic_retuning": False,
            },
            "by_provider_symbol": {"strategy|HYPE": record},
        },
        "open_trade_reflections": {
            "contract": {
                "report_only": True,
                "execution_authority": "none",
                "automatic_strategy_changes": False,
                "runtime_strategy_changed": False,
            },
            "trades": opens or [],
        },
    }


def _record(
    *,
    state: str,
    directional: dict[str, object] | None = None,
    execution: dict[str, object] | None = None,
    repeatability: dict[str, object] | None = None,
    horizons: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "strategy_id": "strategy",
        "symbol": "HYPE",
        "research_state": state,
        "confidence": "medium",
        "historical_cadence": "historical sample",
        "historical_summary": "source-backed result",
        "evidence_source": "evidence.json",
        "directional_research": directional or {},
        "forward_evaluations": 100,
        "eligible_signals": 7 if horizons else 0,
        "eligible_signal_horizons": horizons or {},
        "execution_outcomes_identifiable": execution is not None,
        **({"execution_performance": execution} if execution else {}),
        **(
            {"execution_performance_by_side": execution["by_side"]}
            if execution and "by_side" in execution
            else {}
        ),
        **({"repeatability_evidence": repeatability} if repeatability else {}),
    }


def _execution(
    *,
    long: tuple[int, int, float] | None = None,
    short: tuple[int, int, float] | None = None,
    profit_factor: float | None = None,
) -> dict[str, object]:
    sides = {
        side: _side_summary(*values)
        for side, values in (("long", long), ("short", short))
        if values is not None
    }
    closed = sum(int(value["closed_trades"]) for value in sides.values())
    wins = sum(int(value["wins"]) for value in sides.values())
    losses = sum(int(value["losses"]) for value in sides.values())
    net = sum(float(value["net_pnl_usd"]) for value in sides.values())
    return {
        "closed_trades": closed,
        "wins": wins,
        "losses": losses,
        "breakeven": 0,
        "net_pnl_usd": net,
        "profit_factor": profit_factor,
        "fees_usd": 0.1,
        "funding_usd": -0.01,
        "by_side": sides,
    }


def _side_summary(wins: int, losses: int, net: float) -> dict[str, object]:
    return {
        "closed_trades": wins + losses,
        "wins": wins,
        "losses": losses,
        "breakeven": 0,
        "net_pnl_usd": net,
        "profit_factor": None,
        "fees_usd": 0.05,
        "funding_usd": -0.005,
    }
