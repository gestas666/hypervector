"""Zero-authority adapter for the v51 SOL one-blocker forward shadow."""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from hypervector.data.hl_events import (
    AssetContextEvent,
    BookLevel,
    L2SnapshotEvent,
)
from hypervector.data.event_archive import EventArchive
from hypervector.research.sol_route_native_one_blocker_shadow import (
    SolFundingEvidence,
)
import hypervector.research.sol_route_native_one_blocker_command as subject

_CONFIG = Path(
    "configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml"
)
_RUN = "bidirectional-live-source-test"
_CAPTURE_MS = 1_800_000_000_000
_DECISION_MS = _CAPTURE_MS + 60_000


def test_route_native_shadow_command_module_exists() -> None:
    """The prospective experiment has a separately testable I/O boundary."""
    assert (
        importlib.util.find_spec(
            "hypervector.research.sol_route_native_one_blocker_command"
        )
        is not None
    )


def test_source_bundle_binds_exact_v51_route_and_public_venue_inputs() -> None:
    """The adapter derives replay assumptions from v51 and exact public sources."""
    bundle = subject.build_sol_route_native_source_bundle(
        config_path=_CONFIG,
        cohort_rows=_cohort_rows(),
        events=(
            _book(_DECISION_MS - 1_000),
            _book(_DECISION_MS + 1_000),
            _mark(_DECISION_MS + 2_000),
        ),
        funding_evidence=SolFundingEvidence(
            requested_start_ms=_CAPTURE_MS,
            requested_end_ms=_DECISION_MS + 3_000,
            events=(),
        ),
        source_run_id=_RUN,
        capture_start_ms=_CAPTURE_MS,
        taker_fee_rate=0.000432,
    )

    assert bundle.spec.source_profile_fingerprint == (
        "30cd54bb5b5b17249ae0a6a3b01d5702b276d51f8dc5ddd6b4d36ab6aa7d1908"
    )
    assert bundle.spec.notional_usd == 5_000.0
    assert bundle.spec.taker_fee_rate == 0.000432
    assert len(bundle.candidates) == 1
    assert bundle.books[0].recv_ts_ms == _DECISION_MS - 1_000
    assert bundle.marks[0].source == "hyperliquid_ws_activeAssetCtx"
    assert bundle.source_counts == {
        "l2": 2,
        "marks": 1,
        "gaps": 0,
        "clock_skew_adjusted_l2": 0,
        "maximum_negative_clock_skew_ms": 0,
    }


def test_small_negative_clock_skew_uses_conservative_availability() -> None:
    """A modest server-clock lead delays rather than invalidates exact L2."""
    bundle = subject.build_sol_route_native_source_bundle(
        config_path=_CONFIG,
        cohort_rows=_cohort_rows(include_candidate=False),
        events=(
            _book(_CAPTURE_MS + 1_000, exchange_offset_ms=15),
            _mark(_CAPTURE_MS + 2_000),
        ),
        funding_evidence=SolFundingEvidence(_CAPTURE_MS, _CAPTURE_MS + 3_000, ()),
        source_run_id=_RUN,
        capture_start_ms=_CAPTURE_MS,
        taker_fee_rate=0.000432,
    )

    assert bundle.books[0].recv_ts_ms == _CAPTURE_MS + 1_015
    assert bundle.source_counts["clock_skew_adjusted_l2"] == 1
    assert bundle.source_counts["maximum_negative_clock_skew_ms"] == 15


def test_same_millisecond_marks_preserve_nanosecond_receipt_order() -> None:
    """Distinct venue updates inside one millisecond remain causal evidence."""
    observed_ms = _CAPTURE_MS + 2_000
    bundle = subject.build_sol_route_native_source_bundle(
        config_path=_CONFIG,
        cohort_rows=_cohort_rows(include_candidate=False),
        events=(
            _mark_received(observed_ms, observed_ms * 1_000_000 + 200, 100.0),
            _mark_received(observed_ms, observed_ms * 1_000_000 + 700, 100.1),
        ),
        funding_evidence=SolFundingEvidence(_CAPTURE_MS, observed_ms + 1_000, ()),
        source_run_id=_RUN,
        capture_start_ms=_CAPTURE_MS,
        taker_fee_rate=0.000432,
    )

    report = subject.build_sol_route_native_report(bundle)

    assert [mark.received_ts_ns for mark in bundle.marks] == [
        observed_ms * 1_000_000 + 200,
        observed_ms * 1_000_000 + 700,
    ]
    assert report["status"] == "waiting_future_exact_candidate"


def test_large_negative_clock_skew_remains_invalid() -> None:
    """A materially inconsistent receipt clock cannot become replay evidence."""
    with pytest.raises(ValueError, match="clock skew exceeds"):
        subject.build_sol_route_native_source_bundle(
            config_path=_CONFIG,
            cohort_rows=_cohort_rows(include_candidate=False),
            events=(_book(_CAPTURE_MS + 1_000, exchange_offset_ms=1_001),),
            funding_evidence=SolFundingEvidence(_CAPTURE_MS, _CAPTURE_MS + 3_000, ()),
            source_run_id=_RUN,
            capture_start_ms=_CAPTURE_MS,
            taker_fee_rate=0.000432,
        )


def test_empty_prospective_window_reports_waiting_not_zero_performance() -> None:
    """No exact event is explicit waiting evidence, not a flat performance row."""
    bundle = subject.build_sol_route_native_source_bundle(
        config_path=_CONFIG,
        cohort_rows=_cohort_rows(include_candidate=False),
        events=(_book(_CAPTURE_MS + 1_000), _mark(_CAPTURE_MS + 2_000)),
        funding_evidence=SolFundingEvidence(
            requested_start_ms=_CAPTURE_MS,
            requested_end_ms=_CAPTURE_MS + 3_000,
            events=(),
        ),
        source_run_id=_RUN,
        capture_start_ms=_CAPTURE_MS,
        taker_fee_rate=0.000432,
    )

    report = subject.build_sol_route_native_report(bundle)

    assert report["status"] == "waiting_future_exact_candidate"
    assert report["contract"]["execution_authority"] == "none"
    assert "performance" not in report


def test_snapshot_publishes_prefix_bound_zero_authority_report(
    tmp_path: Path,
) -> None:
    """One poll binds both ledgers and public venue evidence before publication."""
    cohort = tmp_path / "cohort.jsonl"
    asset = tmp_path / "sol.jsonl"
    _write_jsonl(cohort, _cohort_rows(include_candidate=False))
    _write_jsonl(asset, _asset_rows())
    archive = EventArchive(data_root=tmp_path, symbol="SOL", batch_size=10)
    archive.append((_book(_CAPTURE_MS + 1_000), _mark(_CAPTURE_MS + 2_000)))
    archive.flush()
    output = tmp_path / "latest.json"

    report = subject.run_sol_route_native_snapshot(
        config_path=_CONFIG,
        cohort_ledger=cohort,
        asset_ledger=asset,
        data_root=tmp_path,
        source_run_id=_RUN,
        capture_start_ms=_CAPTURE_MS,
        observed_at_ms=_CAPTURE_MS + 3_000,
        output=output,
        funding_fetcher=lambda start_ms, end_ms: SolFundingEvidence(
            start_ms,
            end_ms,
            (),
        ),
    )

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted == report
    assert report["status"] == "waiting_future_exact_candidate"
    assert report["contract"]["execution_authority"] == "none"
    assert report["input_evidence"]["cohort_prefix"]["rows"] == 1
    assert report["input_evidence"]["asset_prefix"]["rows"] == 2
    assert report["input_evidence"]["public_events"]["events"] == 2
    funding = report["input_evidence"]["funding"]
    assert funding["source"] == "hyperliquid_info_fundingHistory"
    assert funding["requested_start_ms"] == _CAPTURE_MS
    assert funding["requested_end_ms"] == _CAPTURE_MS + 3_000
    assert funding["events"] == 0
    assert len(funding["sha256"]) == 64


def test_snapshot_excludes_prior_runs_from_live_ledger_prefixes(
    tmp_path: Path,
) -> None:
    """Rolling refresh cost and evidence are bounded to the exact source run."""
    cohort = tmp_path / "cohort.jsonl"
    asset = tmp_path / "sol.jsonl"
    old_identity = {**_cohort_rows(include_candidate=False)[0], "run_id": "old-run"}
    _write_jsonl(cohort, (old_identity, *_cohort_rows(include_candidate=False)))
    old_asset = tuple({**row, "run_id": "old-run"} for row in _asset_rows())
    _write_jsonl(asset, (*old_asset, *_asset_rows()))
    archive = EventArchive(data_root=tmp_path, symbol="SOL", batch_size=10)
    archive.append((_book(_CAPTURE_MS + 1_000), _mark(_CAPTURE_MS + 2_000)))
    archive.flush()

    report = subject.run_sol_route_native_snapshot(
        config_path=_CONFIG,
        cohort_ledger=cohort,
        asset_ledger=asset,
        data_root=tmp_path,
        source_run_id=_RUN,
        capture_start_ms=_CAPTURE_MS,
        observed_at_ms=_CAPTURE_MS + 3_000,
        output=tmp_path / "latest.json",
        funding_fetcher=lambda start_ms, end_ms: SolFundingEvidence(
            start_ms, end_ms, ()
        ),
    )

    cohort_evidence = report["input_evidence"]["cohort_prefix"]
    asset_evidence = report["input_evidence"]["asset_prefix"]
    assert cohort_evidence["rows"] == 1
    assert asset_evidence["rows"] == 2
    for evidence in (cohort_evidence, asset_evidence):
        assert evidence["selected_run_id"] == _RUN
        assert evidence["source_start_offset"] > 0


def test_snapshot_labels_candidate_while_live_sol_is_occupied(
    tmp_path: Path,
) -> None:
    """A canonical SOL position cannot become incremental missed opportunity."""
    cohort = tmp_path / "cohort.jsonl"
    asset = tmp_path / "sol.jsonl"
    _write_jsonl(cohort, _cohort_rows())
    _write_jsonl(asset, _asset_rows())
    archive = EventArchive(data_root=tmp_path, symbol="SOL", batch_size=10)
    archive.append(
        (
            _book(_DECISION_MS - 1_000),
            _book(_DECISION_MS + 1_000),
            _mark(_DECISION_MS + 2_000),
        )
    )
    archive.flush()

    report = subject.run_sol_route_native_snapshot(
        config_path=_CONFIG,
        cohort_ledger=cohort,
        asset_ledger=asset,
        data_root=tmp_path,
        source_run_id=_RUN,
        capture_start_ms=_CAPTURE_MS,
        observed_at_ms=_DECISION_MS + 3_000,
        output=tmp_path / "latest.json",
        funding_fetcher=lambda start_ms, end_ms: SolFundingEvidence(
            start_ms, end_ms, ()
        ),
    )

    portfolio = report["portfolio_journal"]
    assert portfolio["summary"]["deployable"] == 0
    assert portfolio["summary"]["existing_symbol_position"] == 1
    assert (
        portfolio["latest_attempts"][0]["portfolio_classification"]
        == "existing_symbol_position"
    )


def test_source_bundle_rejects_wrong_symbol_mark() -> None:
    """A corrupt non-SOL mark cannot enter the SOL replay evidence."""
    wrong = AssetContextEvent(
        symbol="ETH",
        observed_ts_ms=_CAPTURE_MS + 2_000,
        received_ts_ns=(_CAPTURE_MS + 2_000) * 1_000_000,
        mark_price=100.0,
        oracle_price=100.0,
        funding_rate_hourly=0.0,
        open_interest=1.0,
        mid_price=100.0,
    )

    with pytest.raises(ValueError, match="wrong symbol"):
        subject.build_sol_route_native_source_bundle(
            config_path=_CONFIG,
            cohort_rows=_cohort_rows(include_candidate=False),
            events=(wrong,),
            funding_evidence=SolFundingEvidence(
                _CAPTURE_MS,
                _CAPTURE_MS + 3_000,
                (),
            ),
            source_run_id=_RUN,
            capture_start_ms=_CAPTURE_MS,
            taker_fee_rate=0.000432,
        )


def test_official_funding_evidence_preserves_exact_requested_window() -> None:
    """Funding uses complete official rows and retains the requested bounds."""
    calls: list[tuple[str, int, int]] = []

    def fetch(
        symbol: str, start_ms: int, end_ms: int
    ) -> tuple[tuple[dict[str, object], ...], ...]:
        calls.append((symbol, start_ms, end_ms))
        return (
            (
                {
                    "coin": "SOL",
                    "time": start_ms + 1_000,
                    "fundingRate": "0.00001",
                },
            ),
        )

    evidence = subject.fetch_official_sol_funding_evidence(
        _CAPTURE_MS,
        _CAPTURE_MS + 3_000,
        page_fetcher=fetch,
    )

    assert calls == [("SOL", _CAPTURE_MS, _CAPTURE_MS + 3_000)]
    assert evidence.requested_start_ms == _CAPTURE_MS
    assert evidence.requested_end_ms == _CAPTURE_MS + 3_000
    assert evidence.events == ((_CAPTURE_MS + 1_000, 0.00001),)
    assert evidence.source == "hyperliquid_info_fundingHistory"


def _cohort_rows(*, include_candidate: bool = True) -> tuple[dict[str, object], ...]:
    identity = {
        "sequence": 1,
        "event_type": "configuration_identity",
        "run_id": _RUN,
        "observed_at_utc": _iso(_CAPTURE_MS - 60_000),
        "live_armed": True,
        "profile_id": "multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51",
        "profile_fingerprint": (
            "30cd54bb5b5b17249ae0a6a3b01d5702b276d51f8dc5ddd6b4d36ab6aa7d1908"
        ),
        "payload": {},
    }
    routing = {
        "sequence": 3,
        "event_type": "intent_routing",
        "run_id": _RUN,
        "observed_at_utc": _iso(_DECISION_MS + 500),
        "payload": {"evaluations": [_evaluation()], "actions": [], "withheld": []},
    }
    snapshot = {
        "sequence": 2,
        "event_type": "cohort_snapshot",
        "run_id": _RUN,
        "observed_at_utc": _iso(_DECISION_MS - 1_000),
        "payload": {
            "open_position_count": 1,
            "assets": [
                {
                    "symbol": "SOL",
                    "state": "OPEN",
                    "position_side": "long",
                    "execution_plan": {"strategy_id": "range_onset_bidirectional_v1"},
                }
            ],
        },
    }
    return (identity, snapshot, routing) if include_candidate else (identity,)


def _evaluation() -> dict[str, object]:
    return {
        "strategy_id": "range_onset_bidirectional_v1",
        "symbol": "SOL",
        "decision_time_ms": _DECISION_MS,
        "reference_price": 100.0,
        "side": "short",
        "eligible": False,
        "readiness": {
            "side": "short",
            "blockers": ["awaiting_hourly_sma_cross"],
            "metrics": {"state_5m": "RANGE"},
        },
    }


def _fee_row() -> dict[str, object]:
    return {
        "event_type": "fee",
        "run_id": _RUN,
        "observed_at_utc": _iso(_CAPTURE_MS - 1_000),
        "payload": {
            "source": "venue_fee_schedule",
            "effective_fee_status": "resolved_core_after_referral",
            "effective_taker_fee_rate": 0.000432,
        },
    }


def _asset_rows() -> tuple[dict[str, object], ...]:
    """Mirror the production asset-run identity followed by its fee row."""
    return (_cohort_rows(include_candidate=False)[0], _fee_row())


def _book(received_ms: int, *, exchange_offset_ms: int = -10) -> L2SnapshotEvent:
    return L2SnapshotEvent(
        symbol="SOL",
        exchange_ts_ms=received_ms + exchange_offset_ms,
        received_ts_ns=received_ms * 1_000_000,
        bids=(BookLevel(99.9, 100.0, 1),),
        asks=(BookLevel(100.0, 100.0, 1),),
    )


def _mark(observed_ms: int) -> AssetContextEvent:
    return AssetContextEvent(
        symbol="SOL",
        observed_ts_ms=observed_ms,
        received_ts_ns=observed_ms * 1_000_000,
        mark_price=100.0,
        oracle_price=100.0,
        funding_rate_hourly=0.0,
        open_interest=1.0,
        mid_price=100.0,
    )


def _mark_received(
    observed_ms: int, received_ts_ns: int, mark_price: float
) -> AssetContextEvent:
    """Return one exact receipt-ordered mark inside a millisecond bucket."""
    return AssetContextEvent(
        symbol="SOL",
        observed_ts_ms=observed_ms,
        received_ts_ns=received_ts_ns,
        mark_price=mark_price,
        oracle_price=mark_price,
        funding_rate_hourly=0.0,
        open_interest=1.0,
        mid_price=mark_price,
    )


def _iso(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1_000, UTC).isoformat()


def _write_jsonl(path: Path, rows: tuple[dict[str, object], ...]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
