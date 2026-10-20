"""Tests for report-only separate-side portfolio composition research."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_side_composition import build_side_composition


def test_separates_positive_long_from_negative_short_on_same_route() -> None:
    """Opposing side economics must remain separate components."""
    audit = _audit(
        directional={
            "long": {"research_state": "historical_candidate"},
            "short": {"research_state": "contradictory"},
        },
        aligned={
            "strategy|HYPE|long": _alignment("long", 6, 4, 2, 0.8, 2.1, 1.2),
            "strategy|HYPE|short": _alignment("short", 4, 1, 3, -0.7, 0.4, -1.0),
        },
    )

    report = build_side_composition(audit)

    long = report["components"]["strategy|HYPE|long"]
    short = report["components"]["strategy|HYPE|short"]
    assert long["evidence_tier"] == "repeated_positive_mixed_profile"
    assert short["evidence_tier"] == "nonpositive_mixed_profile"
    assert report["frontier"]["long"][0]["component"] == "strategy|HYPE|long"
    assert report["frontier"]["short"] == []
    assert report["contract"]["execution_authority"] == "none"


def test_supportive_historical_short_remains_an_experiment_frontier() -> None:
    """A missing live short remains visible without becoming a promotion claim."""
    audit = _audit(
        directional={
            "long": {"research_state": "historical_candidate"},
            "short": {"research_state": "historical_candidate"},
        },
        aligned={
            "strategy|HYPE|long": _alignment("long", 1, 1, 0, 0.2, None, 0.2),
        },
    )

    report = build_side_composition(audit)

    short = report["components"]["strategy|HYPE|short"]
    assert short["evidence_tier"] == "historical_supportive_no_live"
    assert report["frontier"]["short"][0]["component"] == "strategy|HYPE|short"
    assert report["summary"]["both_side_frontier_available"] is True
    assert report["summary"]["automatic_promotion"] is False


def test_current_profile_outcome_is_separate_from_mixed_profile_history() -> None:
    """Current-profile economics cannot be silently pooled with earlier profiles."""
    audit = _audit(
        directional={"long": {"research_state": "historical_candidate"}},
        aligned={
            "strategy|HYPE|long": _alignment("long", 6, 4, 2, 0.8, 2.1, 1.2),
        },
        current_long=_performance(1, 1, 0, 0.1, None),
    )

    long = build_side_composition(audit)["components"]["strategy|HYPE|long"]

    assert long["live_history"]["scope"] == "all_live_history_mixed_profiles"
    assert long["live_history"]["trades"] == 6
    assert long["current_profile_execution"]["trades"] == 1
    assert long["current_profile_execution"]["net_pnl_usd"] == pytest.approx(0.1)


def test_retired_route_history_is_disclosed_without_blocking_current_profile() -> None:
    """Mixed-profile history may contain routes retired by the current profile."""
    audit = _audit(
        directional={"long": {"research_state": "historical_candidate"}},
        aligned={
            "strategy|HYPE|long": _alignment("long", 1, 1, 0, 0.2, None, 0.2),
            "retired_strategy|HYPE|short": _alignment(
                "short", 1, 0, 1, -0.2, 0.0, -0.2
            ),
        },
    )

    report = build_side_composition(audit)

    assert set(report["components"]) == {"strategy|HYPE|long"}
    assert report["summary"]["retired_history_components"] == 1
    assert report["retired_history_components"] == ["retired_strategy|HYPE|short"]


def test_profit_factor_denominators_are_explicit_in_composition() -> None:
    """Composition cannot relabel return-normalized PF as ordinary USD PF."""
    history = _alignment("long", 6, 4, 2, 0.8, 5.0, 1.2)
    history["outcome"]["usd_profit_factor"] = 2.0
    audit = _audit(
        directional={"long": {"research_state": "historical_candidate"}},
        aligned={"strategy|HYPE|long": history},
        current_long=_performance(2, 1, 1, 0.1, 1.5),
    )

    report = build_side_composition(audit)
    long = report["components"]["strategy|HYPE|long"]
    live = long["live_history"]
    current = long["current_profile_execution"]
    frontier = report["frontier"]["long"][0]

    assert report["schema_version"] == 2
    assert (
        report["contract"]["descriptive_tier_profit_factor_basis"]
        == "normalized_profit_factor"
    )
    assert live["usd_profit_factor"] == pytest.approx(2.0)
    assert live["normalized_profit_factor"] == pytest.approx(5.0)
    assert "profit_factor" not in live
    assert current["usd_profit_factor"] == pytest.approx(1.5)
    assert "profit_factor" not in current
    assert frontier["usd_profit_factor"] == pytest.approx(2.0)
    assert frontier["normalized_profit_factor"] == pytest.approx(5.0)
    assert "profit_factor" not in frontier


def test_rejects_alignment_layer_with_execution_authority() -> None:
    """The composition audit must remain incapable of executing."""
    audit = _audit(directional={}, aligned={})
    audit["entry_alignment_mechanism"]["contract"]["execution_authority"] = (
        "hyperliquid_mainnet"
    )

    with pytest.raises(ValueError, match="execution_authority"):
        build_side_composition(audit)


def _audit(
    *,
    directional: dict[str, object],
    aligned: dict[str, object],
    current_long: dict[str, object] | None = None,
) -> dict[str, object]:
    route = {
        "strategy_id": "strategy",
        "symbol": "HYPE",
        "research_state": "directional_candidate",
        "directional_research": directional,
        "execution_outcomes_identifiable": current_long is not None,
    }
    if current_long is not None:
        route["execution_performance_by_side"] = {"long": current_long}
    return {
        "run": {
            "run_id": "run-1",
            "profile_id": "fixture_profile",
            "profile_fingerprint": "a" * 64,
            "last_observed_at_utc": "2026-08-09T05:00:00+00:00",
        },
        "experiment_contract": _contract(),
        "strategy_scorecard": {
            "contract": _contract(),
            "by_provider_symbol": {"strategy|HYPE": route},
        },
        "entry_alignment_mechanism": {
            "contract": {
                "report_only": True,
                "execution_authority": "none",
                "execution_gate": False,
                "automatic_strategy_changes": False,
                "runtime_strategy_changed": False,
            },
            "scope": "all_live_history_mixed_profiles",
            "by_provider_symbol_side": aligned,
        },
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "performance_gate": False,
        "balance_gate": False,
        "runtime_strategy_changed": False,
    }


def _alignment(
    side: str,
    trades: int,
    wins: int,
    losses: int,
    net: float,
    profit_factor: float | None,
    median_return: float,
) -> dict[str, object]:
    return {
        "side": side,
        "closed_trades": trades,
        "outcome": {
            "trades": trades,
            "wins": wins,
            "losses": losses,
            "breakeven": trades - wins - losses,
            "net_pnl_usd": net,
            "normalized_profit_factor": profit_factor,
            "mean_net_return_on_margin_pct": median_return,
            "median_net_return_on_margin_pct": median_return,
        },
    }


def _performance(
    trades: int,
    wins: int,
    losses: int,
    net: float,
    profit_factor: float | None,
) -> dict[str, object]:
    return {
        "closed_trades": trades,
        "wins": wins,
        "losses": losses,
        "breakeven": trades - wins - losses,
        "net_pnl_usd": net,
        "profit_factor": profit_factor,
        "fees_usd": 0.01,
        "funding_usd": -0.001,
    }
