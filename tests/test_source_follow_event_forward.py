"""Side-aware forward diagnostics for live source-follow onsets."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hypervector.research import source_follow_event_forward as event_forward


def _row(
    sequence: int,
    *,
    direction: str,
    range_bps: float,
    admitted: bool,
) -> dict[str, object]:
    return {
        "sequence": sequence,
        "run_id": "live-run",
        "event_type": "regime_decision",
        "payload": {
            "feed_ts": f"2026-07-31T16:{sequence:02}:00+00:00",
            "available_at_utc": f"2026-07-31T16:{sequence + 5:02}:00+00:00",
            "reference_price": 64_000.0,
            "source_event": True,
            "structural_direction": direction,
            "source_follow_signal_range_bps": range_bps,
            "entry_allowed": admitted,
            "regime_reason": None if admitted else "signal_range_below_minimum",
        },
    }


def test_extracts_admitted_and_range_excluded_source_events() -> None:
    """The challenger set is selected before the runtime range gate."""
    rows = [
        _row(1, direction="short", range_bps=8.0, admitted=False),
        _row(10, direction="long", range_bps=18.0, admitted=True),
        {
            **_row(20, direction="short", range_bps=20.0, admitted=True),
            "run_id": "other-run",
        },
    ]

    events = event_forward.extract_source_event_decisions(rows, run_id="live-run")

    assert [(item.direction, item.signal_range_bps) for item in events] == [
        ("short", 8.0),
        ("long", 18.0),
    ]
    assert [item.entry_allowed for item in events] == [False, True]


def test_measurement_contract_comes_from_the_run_identity() -> None:
    """Forward thresholds must be anchored to what the live process reported."""
    contract = event_forward.extract_source_event_measurement_contract(
        [_identity_row()],
        run_id="live-run",
    )

    assert contract.symbol == "BTC"
    assert contract.minimum_range_bps == 12.0
    assert contract.maximum_range_bps == 100.0
    assert contract.target_price_fraction == 0.0026666666666666666
    assert contract.profile_fingerprint == "old-process-fingerprint"


def test_empty_event_audit_is_valid_report_only_evidence(tmp_path: Path) -> None:
    """A quiet live window remains an explicit result rather than an error."""
    report = event_forward.audit_source_event_forward_paths(
        tmp_path / "not-opened.duckdb",
        (),
        symbol="BTC",
        target_price_fraction=0.0026666666666666666,
        minimum_range_bps=12.0,
        maximum_range_bps=100.0,
        horizons_minutes=(5, 15),
    )

    assert report["event_rows"] == 0
    assert report["event_distribution"] == {}
    assert report["horizons"] == {"5": {}, "15": {}}
    assert report["paths"] == []
    assert report["execution_authority"] == "none"


def test_side_aware_paths_compare_subminimum_and_admitted_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Favorable and adverse movement follow each event's causal direction."""
    events = event_forward.extract_source_event_decisions(
        [
            _row(1, direction="short", range_bps=8.0, admitted=False),
            _row(10, direction="long", range_bps=18.0, admitted=True),
        ],
        run_id="live-run",
    )
    monkeypatch.setattr(
        event_forward,
        "audit_range_forward_paths",
        lambda *_args, **_kwargs: {
            "latest_trade_at_utc": "2026-07-31T17:00:00+00:00",
            "paths": [
                _base_path(1, maximum_up=4.0, maximum_down=30.0, ending=-20.0),
                _base_path(10, maximum_up=28.0, maximum_down=6.0, ending=18.0),
            ],
        },
    )

    report = event_forward.audit_source_event_forward_paths(
        tmp_path / "market.duckdb",
        events,
        symbol="BTC",
        target_price_fraction=0.0026666666666666666,
        minimum_range_bps=12.0,
        maximum_range_bps=100.0,
        horizons_minutes=(15,),
    )

    first, second = report["paths"]
    assert first["admission"] == "range_below_minimum"
    assert first["horizons"]["15"]["favorable_excursion_bps"] == 30.0
    assert first["horizons"]["15"]["adverse_excursion_bps"] == 4.0
    assert first["horizons"]["15"]["signed_ending_displacement_bps"] == 20.0
    assert first["horizons"]["15"]["target_hit"] is True
    assert second["admission"] == "runtime_admitted"
    assert second["horizons"]["15"]["favorable_excursion_bps"] == 28.0
    assert report["horizons"]["15"]["range_below_minimum"]["target_rows"] == 1
    assert report["horizons"]["15"]["runtime_admitted"]["target_rows"] == 1


def _base_path(
    sequence: int,
    *,
    maximum_up: float,
    maximum_down: float,
    ending: float,
) -> dict[str, object]:
    return {
        "sequence": sequence,
        "feed_at_utc": datetime(2026, 7, 31, 16, tzinfo=UTC).isoformat(),
        "available_at_utc": datetime(2026, 7, 31, 16, 5, tzinfo=UTC).isoformat(),
        "reference_price": 64_000.0,
        "horizons": {
            "15": {
                "minutes": 15,
                "complete": True,
                "quality_usable": True,
                "explicit_stream_gaps": 0,
                "trade_count": 100,
                "maximum_up_bps": maximum_up,
                "maximum_down_bps": maximum_down,
                "path_span_bps": maximum_up + maximum_down,
                "ending_displacement_bps": ending,
                "long_target_hit": maximum_up >= 26.666666666666664,
                "short_target_hit": maximum_down >= 26.666666666666664,
                "first_target_direction": None,
                "first_target_at_utc": None,
            }
        },
    }


def _identity_row() -> dict[str, object]:
    return {
        "sequence": 0,
        "run_id": "live-run",
        "event_type": "configuration_identity",
        "profile_id": "hypervelocity_source_follow_bidirectional_minrange12_alloc35_live_canary_v1",
        "profile_fingerprint": "old-process-fingerprint",
        "payload": {
            "symbol": "BTC",
            "regime_policy": {
                "minimum_completed_5m_range_bps": 12.0,
                "maximum_completed_5m_range_bps": 100.0,
            },
            "exits": {"target_price_fraction": 0.0026666666666666666},
        },
    }
