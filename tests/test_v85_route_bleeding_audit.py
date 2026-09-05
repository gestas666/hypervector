"""Route-level economic and technical diagnosis for the frozen V85 cohort."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from hypervector.research.v85_route_bleeding_audit import (
    build_route_bleeding_audit,
    load_frozen_jsonl_prefix,
)


_RUN_ID = "bidirectional-live-v85"
_PROFILE_ID = "v85-profile"
_FINGERPRINT = "8" * 64
_HULK = "hulk_expansion_short_robust_v3|BTC"
_ZEC = "zec_donchian_20_10_atr20_long_v1|ZEC"
_SPCX = "hip3_spcx_cash_session_fresh15_long_v4|xyz:SPCX"
_ROUTES = (
    _HULK,
    "hulk_expansion_short_tuned_v2|BTC",
    "liquidity_sweep_long_1h_stop60_target60_v2|BTC",
    "eth_range_onset_long_dual_mtf_v2|ETH",
    "sol_range_onset_short_dual_mtf_v2|SOL",
    "hype_breakout_compression_alignment_bidirectional_v2|HYPE",
    _ZEC,
    _SPCX,
    "hip3_breakout_pressure_sndk_fresh15s_bidirectional_v3|xyz:SNDK",
)


def test_frozen_prefix_loader_verifies_hash_range_and_source_sequences(
    tmp_path: Path,
) -> None:
    """The loader must bind the exact byte range without reading appended rows."""
    path = tmp_path / "decisions.jsonl"
    old = _line(40, "old")
    frozen = _line(41, _RUN_ID) + _line(42, _RUN_ID)
    appended = _line(43, _RUN_ID)
    path.write_bytes(old + frozen + appended)
    evidence = _prefix(path, len(old), frozen, 41, 42)

    rows, facts = load_frozen_jsonl_prefix(evidence)

    assert [row["sequence"] for row in rows] == [1, 2]
    assert facts["sha256"] == sha256(frozen).hexdigest()
    assert facts["source_sequence_start"] == 41
    assert facts["source_sequence_end"] == 42
    assert facts["appended_bytes_excluded"] == len(appended)


def test_frozen_prefix_loader_rejects_changed_or_incomplete_evidence(
    tmp_path: Path,
) -> None:
    """Mutated bytes and a torn frozen tail must fail closed."""
    path = tmp_path / "zec.jsonl"
    complete = _line(9, _RUN_ID)
    path.write_bytes(complete)
    changed = _prefix(path, 0, complete, 9, 9)
    changed["sha256"] = "0" * 64

    with pytest.raises(ValueError, match="SHA-256"):
        load_frozen_jsonl_prefix(changed)

    torn = b'{"sequence":9'
    path.write_bytes(torn)
    evidence = _prefix(path, 0, torn, 9, 9)
    with pytest.raises(ValueError, match="complete JSONL row"):
        load_frozen_jsonl_prefix(evidence)


def test_report_covers_all_routes_and_separates_negative_from_insufficient() -> None:
    """Corroborated losses retire routes; sparse routes remain explicitly unknown."""
    report = build_route_bleeding_audit(_audit(), _preregistration())

    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "automatic_strategy_mutation": False,
        "runtime_strategy_changed": False,
    }
    assert report["summary"]["monitored_routes"] == 9
    assert report["summary"]["executable_routes"] == 8
    assert report["summary"]["technical_fault_routes"] == 0
    assert report["summary"]["negative_signal_routes"] == 2
    assert set(report["routes"]) == set(_ROUTES)
    assert report["routes"][_HULK]["classifications"] == ["negative_signal"]
    assert report["routes"][_ZEC]["classifications"] == [
        "negative_signal",
        "exit_leakage",
    ]
    assert report["routes"][_SPCX]["classifications"] == ["insufficient_evidence"]
    assert report["successor_disposition"]["remove_execution_routes"] == [
        _HULK,
        _ZEC,
    ]
    assert report["successor_disposition"]["required_same_asset_replacements"] == [
        "ZEC"
    ]
    assert report["successor_disposition"]["v86_complete"] is False


def test_report_reconciles_costs_excursions_drawdown_and_namespaced_lifecycle() -> None:
    """The economic projection must retain complete route lifecycle evidence."""
    report = build_route_bleeding_audit(_audit(), _preregistration())

    zec = report["routes"][_ZEC]
    current = zec["current_run_economics"]
    assert current["closed_trades"] == 1
    assert current["wins"] == 0
    assert current["losses"] == 1
    assert current["gross_pnl_usd"] == pytest.approx(-12.7824)
    assert current["net_pnl_usd"] == pytest.approx(-13.196532)
    assert current["fees_usd"] == pytest.approx(0.414132)
    assert current["funding_usd"] == 0.0
    assert current["maximum_drawdown_usd"] == pytest.approx(13.196532)
    assert current["net_pnl_excluding_largest_winner_usd"] is None
    assert current["exit_reasons"] == {"protective_stop": 1}
    assert current["maximum_favorable_excursion_bps"]["maximum"] == 80.0
    assert current["maximum_adverse_excursion_bps"]["maximum"] == 263.0
    assert current["peak_giveback_bps"]["maximum"] == 343.0
    assert zec["combined_exact_live_economics"]["closed_trades"] == 1
    assert zec["lifecycle_diagnostics"][0]["lifecycle_id"] == "ZEC:535965339071"

    spcx = report["routes"][_SPCX]
    assert spcx["combined_exact_live_economics"]["closed_trades"] == 1
    assert spcx["combined_exact_live_economics"]["net_pnl_usd"] == pytest.approx(
        5.940383
    )


def test_open_entry_without_protection_is_a_route_technical_fault() -> None:
    """An uncovered live position cannot be reported as merely low sample size."""
    audit = _audit()
    audit["open_trade_reflections"] = {
        "trades": [
            {
                "lifecycle_id": "xyz:SPCX:77",
                "source_run_id": _RUN_ID,
                "strategy_id": _SPCX.rpartition("|")[0],
                "symbol": "xyz:SPCX",
                "side": "long",
            }
        ]
    }

    report = build_route_bleeding_audit(audit, _preregistration())

    route = report["routes"][_SPCX]
    assert route["classifications"] == ["technical_fault"]
    assert route["technical_findings"] == ["open_lifecycle_missing_protective_stop"]


def test_friction_contract_mismatch_is_a_route_technical_fault() -> None:
    """Runtime/model drift must outrank an economic interpretation."""
    audit = _audit()
    parity = audit["execution"]["friction_parity"]["by_provider_symbol"]
    parity[_SPCX] = {"mismatches": ["stop_bps"], "parity_state": "mismatch"}

    report = build_route_bleeding_audit(audit, _preregistration())

    route = report["routes"][_SPCX]
    assert route["classifications"] == ["technical_fault"]
    assert route["technical_findings"] == ["friction_contract_mismatch:stop_bps"]


def test_partial_exit_size_is_a_route_technical_fault() -> None:
    """A reflected close that does not reconcile entry size must fail closed."""
    audit = _audit()
    trade = audit["trade_reflections"]["trades"][0]
    trade["entry"]["size"] = 0.48
    trade["exit"]["size"] = 0.24

    report = build_route_bleeding_audit(audit, _preregistration())

    zec = report["routes"][_ZEC]
    assert zec["classifications"] == ["technical_fault"]
    assert zec["technical_findings"] == [
        "closed_lifecycle_size_mismatch:ZEC:535965339071"
    ]


def test_rejected_submission_accounting_is_preserved_and_validated() -> None:
    """Rejected entries are evidence, while inconsistent totals are malformed."""
    audit = _audit()
    audit["execution"]["current_run_submission_outcomes"] = {
        "outcomes": 3,
        "accepted": 2,
        "rejected": 1,
        "rejection_reasons": {"entry_slippage_cap_exceeded": 1},
    }

    report = build_route_bleeding_audit(audit, _preregistration())

    assert report["execution_reconciliation"] == {
        "outcomes": 3,
        "accepted": 2,
        "rejected": 1,
        "rejection_reasons": {"entry_slippage_cap_exceeded": 1},
    }

    audit["execution"]["current_run_submission_outcomes"]["outcomes"] = 4
    with pytest.raises(ValueError, match="submission outcome counts"):
        build_route_bleeding_audit(audit, _preregistration())


def test_identity_drift_or_missing_route_fails_before_classification() -> None:
    """No report may inherit another profile or omit an expected route."""
    audit = _audit()
    audit["run"]["profile_fingerprint"] = "9" * 64
    with pytest.raises(ValueError, match="profile fingerprint"):
        build_route_bleeding_audit(audit, _preregistration())

    audit = _audit()
    del audit["readiness"]["by_provider_symbol"][_SPCX]
    with pytest.raises(ValueError, match="missing monitored routes"):
        build_route_bleeding_audit(audit, _preregistration())


def _line(sequence: int, run_id: str) -> bytes:
    return (
        json.dumps({"sequence": sequence, "run_id": run_id, "payload": {}}) + "\n"
    ).encode()


def _prefix(
    path: Path,
    start: int,
    content: bytes,
    sequence_start: int,
    sequence_end: int,
) -> dict[str, object]:
    return {
        "path": str(path),
        "source_start_offset": start,
        "source_bytes_observed": start + len(content),
        "suffix_bytes": len(content),
        "source_sequence_start": sequence_start,
        "source_sequence_end": sequence_end,
        "sha256": sha256(content).hexdigest(),
    }


def _preregistration() -> dict[str, object]:
    contracts = [
        {
            "route": route,
            "execution_authority_in_v85": route != "hulk_expansion_short_tuned_v2|BTC",
            "directions": ["long" if "short" not in route else "short"],
        }
        for route in _ROUTES
    ]
    prior = {
        route: {
            "exact_live": {
                "closed_trades": 0,
                "wins": 0,
                "losses": 0,
                "breakeven": 0,
                "net_pnl_usd": 0.0,
                "fees_usd": 0.0,
                "funding_usd": 0.0,
            },
            "corroborated_negative_test": False,
        }
        for route in _ROUTES
    }
    prior[_HULK] = {
        "exact_live": {
            "closed_trades": 2,
            "wins": 0,
            "losses": 2,
            "breakeven": 0,
            "net_pnl_usd": -113.12719,
            "fees_usd": 12.912058,
            "funding_usd": 1.092988,
        },
        "corroborated_negative_test": True,
    }
    prior[_ZEC]["corroborated_negative_test"] = True
    prior[_SPCX] = {
        "exact_live": {
            "closed_trades": 1,
            "wins": 1,
            "losses": 0,
            "breakeven": 0,
            "net_pnl_usd": 5.940383,
            "fees_usd": 0.057607,
            "funding_usd": 0.009216,
        },
        "corroborated_negative_test": False,
    }
    return {
        "execution_authority": "none",
        "automatic_strategy_mutation": False,
        "frozen_runtime_identity": {
            "run_id": _RUN_ID,
            "profile_id": _PROFILE_ID,
            "profile_fingerprint": _FINGERPRINT,
        },
        "roster_contract": {
            "required_assets": [
                "BTC",
                "ETH",
                "SOL",
                "HYPE",
                "ZEC",
                "xyz:SPCX",
                "xyz:SNDK",
            ]
        },
        "route_contracts": contracts,
        "economic_contract": {
            "fallback_round_trip_hurdle_bps": 13.0,
            "robust_gross_move_hurdle_bps": 26.0,
        },
        "frozen_prior_route_evidence": prior,
    }


def _audit() -> dict[str, object]:
    readiness = {route: {"count": 5, "eligible": 0} for route in _ROUTES}
    scorecards = {
        route: {
            "research_state": "probation",
            "confidence": "low",
            "historical_cadence": "sparse",
            "historical_summary": "fixture",
        }
        for route in _ROUTES
    }
    parity = {
        route: {"mismatches": [], "parity_state": "runtime_shape_aligned"}
        for route in _ROUTES
    }
    return {
        "run": {
            "run_id": _RUN_ID,
            "profile_id": _PROFILE_ID,
            "profile_fingerprint": _FINGERPRINT,
            "symbols": ["BTC", "ETH", "SOL", "HYPE", "ZEC", "xyz:SPCX", "xyz:SNDK"],
            "executable_provider_symbols": [
                route
                for route in _ROUTES
                if route != "hulk_expansion_short_tuned_v2|BTC"
            ],
            "observe_only_provider_symbols": ["hulk_expansion_short_tuned_v2|BTC"],
        },
        "coverage": {"complete": True, "technical_gaps": []},
        "readiness": {"by_provider_symbol": readiness},
        "strategy_scorecard": {"by_provider_symbol": scorecards},
        "execution": {"friction_parity": {"by_provider_symbol": parity}},
        "trade_reflections": {"trades": [_zec_trade()]},
        "open_trade_reflections": {"trades": []},
    }


def _zec_trade() -> dict[str, object]:
    return {
        "lifecycle_id": "ZEC:535965339071",
        "source_run_id": _RUN_ID,
        "entry_strategy_id": _ZEC.rpartition("|")[0],
        "symbol": "ZEC",
        "side": "long",
        "net_pnl_usd": -13.196532,
        "fees_usd": 0.414132,
        "funding_usd": 0.0,
        "entry_margin_used_usd": 96.907181,
        "holding_time_ms": 1_869_051,
        "exit_reason": "protective_stop",
        "entry": {
            "slippage_bps": 6.922468,
            "size": 0.48,
            "venue_timestamp_ms": 1_788_523_221_414,
        },
        "exit": {
            "slippage_bps": 13.505946,
            "size": 0.48,
            "venue_timestamp_ms": 1_788_525_090_465,
        },
        "protective_stop": {"oid": 535965366879, "trigger_price": 986.6025},
        "completed_hold_capture": {
            "status": "resolved",
            "maximum_favorable_excursion_bps": 80.0,
            "maximum_adverse_excursion_bps": 263.0,
            "maximum_net_excursion_bps": 71.5,
            "observed_cost_hurdle_bps": 8.5,
            "peak_giveback_bps": 343.0,
        },
    }
