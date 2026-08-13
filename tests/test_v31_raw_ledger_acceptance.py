"""Raw-ledger acceptance contracts for v31 pressure and funding evidence."""

from __future__ import annotations

from copy import deepcopy

from hypervector.research.v31_poststart_acceptance import PRESSURE_ROUTES
from hypervector.research.v31_raw_identity import V31_SYMBOLS
from hypervector.research.v31_raw_ledger_acceptance import (
    build_candidate_raw_ledger_acceptance,
    build_v31_raw_ledger_acceptance,
)
from hypervector.research.v32_acceptance import build_v32_raw_ledger_acceptance

_PROFILE = "multi_asset_bidirectional_swing_pruned_candidate_v31"
_FINGERPRINT = "candidate-fingerprint"
_RUN_ID = "v31-live-run"
_CUTOFF_MS = 2_000
_V32_PROFILE = "multi_asset_bidirectional_commodity_swing_retired_candidate_v32"


def test_exact_books_and_contiguous_funding_cursor_are_accepted() -> None:
    report = build_v31_raw_ledger_acceptance(
        _checkpoint(), _aggregate(), _cohort(), _assets()
    )

    assert report["accepted"] is True
    assert report["reasons"] == []
    assert len(report["checks"]["aggregate_acceptance"]["sha256"]) == 64
    books = report["checks"]["causal_pressure_books"]
    assert books["passed"] is True
    assert books["common_provider_cutoff_time_ms"] == _CUTOFF_MS
    assert set(books["routes"]) == set(PRESSURE_ROUTES)
    funding = report["checks"]["funding_cursor_continuity"]
    assert funding["passed"] is True
    assert funding["windows"] == 1
    payments = report["checks"]["funding_payment_uniqueness"]
    assert set(payments["unique_payments_by_symbol"]) == set(V31_SYMBOLS)


def test_metric_book_must_be_latest_admissible_exact_symbol_book() -> None:
    assets = _assets()
    route = PRESSURE_ROUTES[0]
    symbol = route.split("|", maxsplit=1)[1]
    assets[symbol].append(_book(symbol, 1_900, 4.0, sequence=2))

    report = build_v31_raw_ledger_acceptance(
        _checkpoint(), _aggregate(), _cohort(), assets
    )

    assert report["accepted"] is False
    assert f"causal_book_not_latest:{route}" in report["reasons"]


def test_routes_must_resolve_to_one_common_provider_cutoff() -> None:
    cohort = _cohort()
    evaluation = cohort[0]["payload"]["evaluations"][0]
    evaluation["readiness"]["metrics"]["pressure_age_seconds"] += 0.001

    report = build_v31_raw_ledger_acceptance(
        _checkpoint(), _aggregate(), cohort, _assets()
    )

    assert report["accepted"] is False
    assert "pressure_cutoff_mismatch" in report["reasons"]


def test_funding_cursor_gap_is_rejected() -> None:
    cohort = _cohort()
    prior = _funding_window(sequence=1, cutoff_ms=1_500)
    prior["payload"].update(
        {
            "funding_start_time_ms": 0,
            "initial_funding_end_time_ms": 1_400,
            "committed_funding_end_time_ms": 1_400,
            "next_funding_start_time_ms": 1_400,
        }
    )
    cohort[0]["sequence"] = 2
    cohort[1]["sequence"] = 3
    cohort[1]["payload"]["funding_start_time_ms"] = 1_500
    cohort[:] = [prior, *cohort]

    report = build_v31_raw_ledger_acceptance(
        _checkpoint(), _aggregate(), cohort, _assets()
    )

    assert report["accepted"] is False
    assert "funding_cursor_gap_or_overlap" in report["reasons"]


def test_funding_window_must_follow_its_routing_cycle() -> None:
    cohort = _cohort()
    cohort[0]["sequence"] = 2
    cohort[1]["sequence"] = 1

    report = build_v31_raw_ledger_acceptance(
        _checkpoint(), _aggregate(), cohort, _assets()
    )

    assert report["accepted"] is False
    assert "funding_window_order_invalid" in report["reasons"]


def test_duplicate_asset_funding_payment_is_rejected() -> None:
    assets = _assets()
    symbol = "xyz:GOLD"
    payment = _funding_payment(symbol, sequence=2)
    assets[symbol].extend((payment, deepcopy(payment)))
    assets[symbol][-1]["sequence"] = 3

    report = build_v31_raw_ledger_acceptance(
        _checkpoint(), _aggregate(), _cohort(), assets
    )

    assert report["accepted"] is False
    assert f"duplicate_funding_payment:{symbol}" in report["reasons"]


def test_v32_raw_identity_is_isolated_from_v31_acceptance() -> None:
    checkpoint = _checkpoint()
    checkpoint["audit"]["run"]["profile_id"] = _V32_PROFILE
    aggregate = _aggregate()
    aggregate["run"]["profile_id"] = _V32_PROFILE
    cohort = _cohort()
    for row in cohort:
        row["profile_id"] = _V32_PROFILE

    report = build_candidate_raw_ledger_acceptance(
        checkpoint,
        aggregate,
        cohort,
        _assets(),
        expected_profile_id=_V32_PROFILE,
        symbols=V31_SYMBOLS,
        schema_version="v32_raw_ledger_acceptance_v1",
    )
    v31_report = build_v31_raw_ledger_acceptance(
        checkpoint, aggregate, cohort, _assets()
    )

    assert report["accepted"] is True
    assert report["schema_version"] == "v32_raw_ledger_acceptance_v1"
    assert v31_report["accepted"] is False
    assert "candidate_identity_not_active" in v31_report["reasons"]


def test_named_v32_raw_builder_binds_exact_schema_and_identity() -> None:
    checkpoint = _checkpoint()
    checkpoint["audit"]["run"]["profile_id"] = _V32_PROFILE
    aggregate = _aggregate()
    aggregate["run"]["profile_id"] = _V32_PROFILE
    cohort = _cohort()
    for row in cohort:
        row["profile_id"] = _V32_PROFILE

    report = build_v32_raw_ledger_acceptance(checkpoint, aggregate, cohort, _assets())

    assert report["accepted"] is True
    assert report["schema_version"] == "v32_raw_ledger_acceptance_v1"


def _checkpoint() -> dict[str, object]:
    return {
        "generated_at_utc": "2026-08-09T20:00:00+00:00",
        "audit": {
            "run": {
                "run_id": _RUN_ID,
                "profile_id": _PROFILE,
                "profile_fingerprint": _FINGERPRINT,
            }
        },
    }


def _aggregate() -> dict[str, object]:
    return {
        "accepted": True,
        "contract": {"report_only": True, "execution_authority": "none"},
        "run": {
            "run_id": _RUN_ID,
            "profile_id": _PROFILE,
            "profile_fingerprint": _FINGERPRINT,
        },
    }


def _cohort() -> list[dict[str, object]]:
    evaluations = []
    for index, route in enumerate(PRESSURE_ROUTES):
        symbol = route.split("|", maxsplit=1)[1]
        recv_ms = 1_800 + index * 10
        bid_size = 1.0 + index * 0.1
        evaluations.append(
            {
                "strategy_id": route.split("|", maxsplit=1)[0],
                "symbol": symbol,
                "decision_time_ms": 1_000,
                "readiness": {
                    "metrics": {
                        "imbalance_10": _imbalance(bid_size),
                        "pressure_age_seconds": (_CUTOFF_MS - recv_ms) / 1_000,
                        "maximum_pressure_age_seconds": 30.0,
                    }
                },
            }
        )
    routing = _record("intent_routing", 1, {"evaluations": evaluations, "actions": []})
    return [routing, _funding_window(sequence=2, cutoff_ms=_CUTOFF_MS)]


def _assets() -> dict[str, list[dict[str, object]]]:
    assets: dict[str, list[dict[str, object]]] = {symbol: [] for symbol in V31_SYMBOLS}
    for index, route in enumerate(PRESSURE_ROUTES):
        symbol = route.split("|", maxsplit=1)[1]
        assets[symbol] = [_book(symbol, 1_800 + index * 10, 1.0 + index * 0.1)]
    return assets


def _book(
    symbol: str, recv_ms: int, bid_size: float, *, sequence: int = 1
) -> dict[str, object]:
    levels = 10
    return {
        **_record(
            "book_observation",
            sequence,
            {
                "source": "hyperliquid_mainnet_l2_rest",
                "exchange_ts_ms": recv_ms - 1,
                "recv_ts_ms": recv_ms,
                "bids": [
                    {"price": 100.0 - index * 0.1, "size": bid_size}
                    for index in range(levels)
                ],
                "asks": [
                    {"price": 100.1 + index * 0.1, "size": 1.0}
                    for index in range(levels)
                ],
            },
        ),
        "profile_id": f"{_PROFILE}_{symbol.lower()}",
    }


def _funding_window(*, sequence: int, cutoff_ms: int) -> dict[str, object]:
    return _record(
        "funding_reconciliation_window",
        sequence,
        {
            "funding_start_time_ms": 0,
            "initial_funding_end_time_ms": cutoff_ms - 100,
            "provider_cutoff_time_ms": cutoff_ms,
            "committed_funding_end_time_ms": cutoff_ms - 100,
            "next_funding_start_time_ms": cutoff_ms - 100,
            "action_count": 0,
            "post_action_reconciliation": False,
            "boundary_semantics": (
                "contiguous_cursor_with_inclusive_venue_deduplication"
            ),
        },
    )


def _funding_payment(symbol: str, *, sequence: int) -> dict[str, object]:
    return {
        **_record(
            "funding",
            sequence,
            {
                "venue_timestamp_ms": 1_500,
                "transaction_hash": "0xfunding",
                "usdc_delta": -0.01,
            },
        ),
        "profile_id": f"{_PROFILE}_{symbol.lower()}",
    }


def _record(
    event_type: str, sequence: int, payload: dict[str, object]
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "sequence": sequence,
        "event_type": event_type,
        "observed_at_utc": "1970-01-01T00:00:02.200000+00:00",
        "execution_mode": "live",
        "live_armed": True,
        "execution_authority": "hyperliquid_mainnet",
        "profile_id": _PROFILE,
        "profile_fingerprint": _FINGERPRINT,
        "run_fingerprint": "run-fingerprint",
        "run_id": _RUN_ID,
        "payload": payload,
    }


def _imbalance(bid_size: float) -> float:
    bid, ask = 10.0 * bid_size, 10.0
    return (bid - ask) / (bid + ask)
