"""Exact asset-book extraction from report-only cohort observer ledgers."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from hypervector.research.cohort_observer_exact_books import (
    extract_observer_asset_books,
    select_compatible_report_only_observer_runs,
    select_report_only_observer_run,
)
from hypervector.research.cohort_one_blocker_execution_contract import (
    OneBlockerExecutionContract,
)
from hypervector.research.cohort_one_blocker_execution_feasibility import (
    build_one_blocker_execution_feasibility,
)

_RUN_ID = "bidirectional-observe-1"
_NOW_MS = 1_800_000_000_000


def test_selects_one_observe_run_and_preserves_exact_asset_bbo() -> None:
    """Embedded observer books become ordinary report-only asset observations."""
    selected, identity = select_report_only_observer_run(_records())
    books = extract_observer_asset_books(selected, ("BTC", "SOL"))

    assert identity["run_id"] == _RUN_ID
    assert set(books) == {"BTC", "SOL"}
    btc = books["BTC"][0]
    assert btc["event_type"] == "book_observation"
    assert btc["execution_authority"] == "none"
    assert btc["payload"]["recv_ts_ms"] == _NOW_MS
    assert btc["payload"]["bids"][0] == {
        "price": 100.0,
        "size": 2.0,
        "orders": 1,
    }


def test_selection_rejects_live_authority_and_book_symbol_alias() -> None:
    """Observer research cannot consume armed rows or cross-symbol books."""
    armed = [dict(row, live_armed=True) for row in _records()]
    with pytest.raises(ValueError, match="report-only observe run"):
        select_report_only_observer_run(armed)

    selected, _ = select_report_only_observer_run(_records())
    payload = selected[-1]["payload"]
    assert isinstance(payload, dict)
    books = payload["books"]
    assert isinstance(books, dict)
    aliased = dict(books["BTC"], symbol="ETH")
    books["BTC"] = aliased
    with pytest.raises(ValueError, match="symbol identity"):
        extract_observer_asset_books(selected, ("BTC", "SOL"))


def test_selection_rejects_mixed_profile_rows_within_one_run() -> None:
    """A reused run ID cannot alias evidence from another profile revision."""
    records = _records()
    records[-1]["profile_fingerprint"] = "different-fingerprint"

    with pytest.raises(ValueError, match="profile fingerprint"):
        select_report_only_observer_run(records)


def test_extraction_rejects_missing_required_asset_and_duplicate_timestamp() -> None:
    """Incomplete scope and duplicate receive timestamps fail closed."""
    selected, _ = select_report_only_observer_run(_records())
    with pytest.raises(ValueError, match="missing required symbols"):
        extract_observer_asset_books(selected, ("BTC", "ETH", "SOL"))

    duplicated = (*selected, selected[-1])
    with pytest.raises(ValueError, match="duplicate BTC book receive timestamp"):
        extract_observer_asset_books(duplicated, ("BTC", "SOL"))


def test_extracted_observer_books_drive_exact_bbo_feasibility() -> None:
    """Observer books retain the exact prices consumed by the shared replay."""
    records = _records() + [
        _routing_row(_NOW_MS + 200),
        _books_row(_NOW_MS + 300, 100.1),
        _books_row(_NOW_MS + 60_300, 100.2),
    ]
    selected, _ = select_report_only_observer_run(records)
    books = extract_observer_asset_books(selected, ("BTC",))

    report = build_one_blocker_execution_feasibility(
        selected,
        books,
        (),
        contract=_contract(),
    )

    assert report["coverage"]["resolved_executions"] == 1
    execution = report["executions"][0]
    assert execution["entry_price"] == pytest.approx(100.2)
    assert execution["exit_price"] == pytest.approx(100.2)
    assert execution["entry_time_ms"] == _NOW_MS + 300


def test_compatible_restart_extends_the_original_observer_evidence() -> None:
    """A same-contract restart must not censor an already-open virtual path."""
    records = _records()
    continued = _continued_records("bidirectional-observe-2", _NOW_MS + 60_000)

    selected, identities = select_compatible_report_only_observer_runs(
        [*records, *continued], _RUN_ID
    )
    books = extract_observer_asset_books(selected, ("SOL",))["SOL"]

    assert [row["run_id"] for row in identities] == [
        _RUN_ID,
        "bidirectional-observe-2",
    ]
    assert len(books) == 2
    assert books[-1]["payload"]["recv_ts_ms"] == _NOW_MS + 60_000


def test_incompatible_restart_fails_closed_instead_of_freezing_the_path() -> None:
    """A profile change cannot silently continue or truncate one lifecycle."""
    continued = _continued_records("bidirectional-observe-2", _NOW_MS + 60_000)
    for row in continued:
        row["profile_fingerprint"] = "changed-profile"
    identity_payload = continued[0]["payload"]
    assert isinstance(identity_payload, dict)
    identity_payload["profile_fingerprint"] = "changed-profile"

    with pytest.raises(ValueError, match="continuation identity differs"):
        select_compatible_report_only_observer_runs([*_records(), *continued], _RUN_ID)


def _records() -> list[dict[str, object]]:
    return [
        _row("configuration_identity", _identity_payload(), _NOW_MS - 1_000),
        _row(
            "market_books",
            {"books": {"BTC": _book("BTC", 100.0), "SOL": _book("SOL", 75.0)}},
            _NOW_MS + 100,
        ),
    ]


def _continued_records(run_id: str, observed_ms: int) -> list[dict[str, object]]:
    rows = [
        _row("configuration_identity", _identity_payload(), observed_ms - 1_000),
        _row(
            "market_books",
            {"books": {"SOL": _book("SOL", 75.0)}},
            observed_ms + 100,
        ),
    ]
    for row in rows:
        row["run_id"] = run_id
    book_payload = rows[-1]["payload"]
    assert isinstance(book_payload, dict)
    books = book_payload["books"]
    assert isinstance(books, dict)
    sol = books["SOL"]
    assert isinstance(sol, dict)
    sol["exchange_ts_ms"] = observed_ms - 50
    sol["recv_ts_ms"] = observed_ms
    return rows


def _routing_row(observed_ms: int) -> dict[str, object]:
    evaluation = {
        "strategy_id": "range_onset_bidirectional_v1",
        "symbol": "BTC",
        "decision_time_ms": _NOW_MS,
        "reference_price": 100.0,
        "side": None,
        "eligible": False,
        "readiness": {
            "side": "long",
            "blockers": ["awaiting_hourly_sma_cross"],
            "metrics": {},
        },
    }
    return _row("intent_routing", {"evaluations": [evaluation]}, observed_ms)


def _books_row(recv_ms: int, bid: float) -> dict[str, object]:
    book = _book("BTC", bid)
    book["exchange_ts_ms"] = recv_ms - 50
    book["recv_ts_ms"] = recv_ms
    return _row("market_books", {"books": {"BTC": book}}, recv_ms + 50)


def _contract() -> OneBlockerExecutionContract:
    return OneBlockerExecutionContract(
        strategy_id="range_onset_bidirectional_v1",
        symbol="BTC",
        blocker="awaiting_hourly_sma_cross",
        horizon_minutes=1,
        maximum_context_age_ms=1_000,
        maximum_entry_delay_ms=1_000,
        maximum_exit_delay_ms=1_000,
        notional_usd=25.0,
        taker_fee_rate=0.000432,
        stop_proxy_bps=60.0,
        opi_cohort="all",
    )


def _identity_payload() -> dict[str, object]:
    return {
        "strategy_name": "multi_asset_bidirectional_cohort",
        "profile_fingerprint": "fingerprint",
        "enabled_symbols": ["BTC", "SOL"],
    }


def _book(symbol: str, bid: float) -> dict[str, object]:
    return {
        "symbol": symbol,
        "source": "hyperliquid_mainnet_l2_rest",
        "exchange_ts_ms": _NOW_MS - 50,
        "recv_ts_ms": _NOW_MS,
        "opi": 0.4,
        "bids": [{"price": bid, "size": 2.0, "orders": 1}],
        "asks": [{"price": bid + 0.1, "size": 2.0, "orders": 1}],
    }


def _row(
    event_type: str, payload: dict[str, object], observed_ms: int
) -> dict[str, object]:
    return {
        "event_type": event_type,
        "observed_at_utc": datetime.fromtimestamp(
            observed_ms / 1_000, timezone.utc
        ).isoformat(),
        "execution_mode": "observe",
        "effective_mode": "OBSERVE ONLY",
        "live_armed": False,
        "execution_authority": "none",
        "profile_id": "observer-profile",
        "profile_fingerprint": "fingerprint",
        "run_fingerprint": "run-fingerprint",
        "run_id": _RUN_ID,
        "payload": payload,
    }
