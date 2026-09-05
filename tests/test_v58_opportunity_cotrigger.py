"""Tests for the report-only V58 opportunity and co-trigger prefix."""

from __future__ import annotations

from hypervector.research.v58_opportunity_cotrigger import (
    OpportunityContract,
    build_opportunity_cotrigger_report,
)


def test_report_counts_executable_symbols_once_per_cycle() -> None:
    """Same-symbol providers share margin while distinct symbols add exposure."""
    contract = _contract()
    rows = (
        _routing(
            1,
            _evaluation("btc_a", "BTC", "short", 100),
            _evaluation("btc_b", "BTC", "short", 100),
            _evaluation("eth", "ETH", "long", 100),
        ),
        _routing(2, _evaluation("sol", "SOL", "long", 200)),
    )

    report = build_opportunity_cotrigger_report(
        rows, contract=contract, run_id="run-1", source_evidence={"bytes": 42}
    )

    assert report["summary"] == {
        "routing_cycles": 2,
        "prospective_evaluations": 4,
        "eligible_provider_events": 4,
        "executable_eligible_events": 3,
        "observe_only_eligible_events": 1,
        "eligible_symbols": 3,
        "maximum_concurrent_eligible_symbols": 2,
        "maximum_concurrent_margin_fraction": 0.13,
    }
    assert report["co_trigger_cycles"][0]["symbols"] == ["BTC", "ETH"]
    assert report["co_trigger_cycles"][0]["margin_fraction"] == 0.13


def test_report_excludes_readiness_seed_and_deduplicates_identical_rows() -> None:
    """Pre-activation seeds and repeated exact evaluations are not opportunities."""
    eligible = _evaluation("eth", "ETH", "long", 100)
    seed = dict(eligible, backend_non_action_reason="pre_activation_readiness_seed")
    report = build_opportunity_cotrigger_report(
        (_routing(1, seed), _routing(2, eligible), _routing(3, eligible)),
        contract=_contract(),
        run_id="run-1",
        source_evidence={"bytes": 42},
    )

    assert report["summary"]["prospective_evaluations"] == 1
    assert report["summary"]["eligible_provider_events"] == 1
    assert report["routes"]["eth|ETH"]["eligible_events"] == 1


def test_report_rejects_profile_or_duplicate_conflicts() -> None:
    """Identity drift and contradictory repeated decisions fail closed."""
    contract = _contract()
    wrong = _routing(1, _evaluation("eth", "ETH", "long", 100))
    wrong["profile_fingerprint"] = "wrong"
    try:
        build_opportunity_cotrigger_report(
            (wrong,), contract=contract, run_id="run-1", source_evidence={}
        )
    except ValueError as error:
        assert "profile fingerprint" in str(error)
    else:
        raise AssertionError("profile mismatch must reject")

    first = _evaluation("eth", "ETH", "long", 100)
    conflict = dict(first, eligible=False, reason="changed")
    try:
        build_opportunity_cotrigger_report(
            (_routing(1, first), _routing(2, conflict)),
            contract=contract,
            run_id="run-1",
            source_evidence={},
        )
    except ValueError as error:
        assert "conflicting duplicate" in str(error)
    else:
        raise AssertionError("conflicting duplicate must reject")


def _contract() -> OpportunityContract:
    return OpportunityContract(
        profile_id="v58",
        profile_fingerprint="fingerprint",
        margin_fractions={"BTC": 0.10, "ETH": 0.03, "SOL": 0.03},
        executable_directions=frozenset(
            {
                ("btc_a", "BTC", "short"),
                ("eth", "ETH", "long"),
                ("sol", "SOL", "long"),
            }
        ),
    )


def _routing(sequence: int, *evaluations: dict[str, object]) -> dict[str, object]:
    return {
        "event_type": "intent_routing",
        "sequence": sequence,
        "observed_at_utc": f"2026-08-19T09:0{sequence}:00+00:00",
        "run_id": "run-1",
        "profile_id": "v58",
        "profile_fingerprint": "fingerprint",
        "execution_authority": "none",
        "payload": {"evaluations": list(evaluations)},
    }


def _evaluation(
    strategy_id: str, symbol: str, side: str, decision_time_ms: int
) -> dict[str, object]:
    return {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "side": side,
        "decision_time_ms": decision_time_ms,
        "eligible": True,
        "reason": "ready",
        "decision_action": "enter_long" if side == "long" else "enter_short",
        "backend_non_action_reason": None,
    }
