"""Append-only history contracts for continuous cohort improvement."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from hypervector.research.cohort_improvement_history import (
    append_material_report,
    material_state_sha256,
)


def test_prospective_poll_progress_does_not_flood_material_history() -> None:
    """Routine observer evaluations are ephemeral, but new onsets are material."""
    first = _prospective_report("2026-08-15T12:00:00Z", 10, 1)
    second = _prospective_report("2026-08-15T12:02:00Z", 12, 1)

    assert material_state_sha256(first) == material_state_sha256(second)
    second["experiment_queue"][0]["prospective_observation"]["independent_onsets"] = 2
    second["prospective_experiment_evidence"][0]["independent_onsets"] = 2
    assert material_state_sha256(first) != material_state_sha256(second)


def test_index_signal_progress_does_not_flood_material_history() -> None:
    """Healthy boundary progress is ephemeral while an outage is material."""
    first = _signal_capture_report("healthy", 20, 20, 1_000)
    second = _signal_capture_report("healthy", 22, 22, 1_900)

    assert material_state_sha256(first) == material_state_sha256(second)
    second["index_signal_capture"].update(
        {
            "status": "degraded_internal_gaps",
            "missing_boundaries_total": 2,
            "missing_ranges": [{"symbol": "xyz:SPCX", "count": 2}],
        }
    )
    assert material_state_sha256(first) != material_state_sha256(second)


def test_runtime_progress_does_not_flood_material_history() -> None:
    """Routine live counters and marked projections are not research decisions."""
    first = _runtime_progress_report(100, 5_000.0, "2026-08-16T02:00:00Z")
    second = _runtime_progress_report(101, 5_001.0, "2026-08-16T02:01:00Z")

    assert material_state_sha256(first) == material_state_sha256(second)
    episodes = second["live_opportunity_diagnostics"]["routes"][0]
    episodes["blocker_episode_combinations"][0]["episodes"] = 2
    assert material_state_sha256(first) != material_state_sha256(second)


def test_runtime_material_events_remain_in_material_history() -> None:
    """Eligible signals, risk breaches, and closed economics remain durable."""
    baseline = _runtime_progress_report(100, 5_000.0, "2026-08-16T02:00:00Z")
    eligible = _runtime_progress_report(101, 5_001.0, "2026-08-16T02:01:00Z")
    eligible["external_asset_pipeline"]["candidates"][0]["observer"][
        "eligible_decisions_total"
    ] = 1
    breached = _runtime_progress_report(101, 5_001.0, "2026-08-16T02:01:00Z")
    breached["execution_diagnostics"]["entry_age"]["by_provider_symbol"]["route|ASSET"][
        "submitted_entries_over_limit"
    ] = 1
    closed = _runtime_progress_report(101, 5_001.0, "2026-08-16T02:01:00Z")
    closed["performance"]["closed_trades"] = 1
    closed["performance"]["net_pnl_usd"] = 12.5

    assert material_state_sha256(baseline) != material_state_sha256(eligible)
    assert material_state_sha256(baseline) != material_state_sha256(breached)
    assert material_state_sha256(baseline) != material_state_sha256(closed)


def test_orderbook_coverage_progress_waits_for_resolved_path_evidence() -> None:
    """Raw candidate coverage is progress; a newly resolved path is material."""
    baseline = _runtime_progress_report(100, 5_000.0, "2026-08-16T02:00:00Z")
    progressed = _runtime_progress_report(101, 5_001.0, "2026-08-16T02:01:00Z")
    opportunity = progressed["mandate_evidence"]["opportunities"]
    opportunity.update(
        {
            "exact_one_blocker_candidates": 3,
            "book_matched_candidates": 2,
            "book_stale_candidates": 1,
        }
    )

    assert material_state_sha256(baseline) == material_state_sha256(progressed)
    progressed["live_opportunity_diagnostics"]["routes"][0]["one_blocker_paths"] = [
        {"independent_resolved": 1, "mean_after_estimated_friction_bps": 4.0}
    ]
    assert material_state_sha256(baseline) != material_state_sha256(progressed)


def test_open_hype_markout_progress_does_not_flood_material_history() -> None:
    """Open mark changes are ephemeral; lifecycle resolution remains material."""
    first = {"hype_native_prospective_lifecycle": _open_hype_status(5.0, 60.0)}
    second = {"hype_native_prospective_lifecycle": _open_hype_status(7.0, 80.0)}

    assert material_state_sha256(first) == material_state_sha256(second)
    second["hype_native_prospective_lifecycle"].update(
        {
            "watch_state": "resolved_proxy_lifecycle_evidence_available",
            "open_lifecycles": 0,
            "resolved_lifecycles": 1,
            "current_open_lifecycle": None,
        }
    )
    assert material_state_sha256(first) != material_state_sha256(second)


def test_route_lifecycle_poll_progress_does_not_flood_material_history() -> None:
    """Routine route polls are ephemeral while eligibility remains material."""
    first = {"active_hypothesis_lifecycle_statuses": [_route_status(3, 0)]}
    second = {"active_hypothesis_lifecycle_statuses": [_route_status(4, 0)]}

    assert material_state_sha256(first) == material_state_sha256(second)
    second["active_hypothesis_lifecycle_statuses"][0]["prospective_eligible"] = 1
    assert material_state_sha256(first) != material_state_sha256(second)


def _route_status(evaluations: int, eligible: int) -> dict[str, object]:
    return {
        "hypothesis_id": "route-first",
        "route": "provider|BTC",
        "state": "awaiting_short",
        "observed_at_utc": "2026-08-18T21:00:00+00:00",
        "age_seconds": 10.0,
        "freshness_status": "fresh",
        "prospective_evaluations": evaluations,
        "prospective_eligible": eligible,
        "resolved_lifecycles": 0,
    }


def _open_hype_status(net_usd: float, gross_bps: float) -> dict[str, object]:
    return {
        "watch_state": "tracking_open_lifecycle",
        "freshness_status": "fresh",
        "observed_at_utc": "2026-08-18T06:45:00+00:00",
        "age_seconds": 10.0,
        "eligible_long_entries": 1,
        "open_lifecycles": 1,
        "resolved_lifecycles": 0,
        "technically_unresolved_lifecycles": 0,
        "current_open_lifecycle": {
            "current_book_time_ms": 100_000,
            "current_exit_price": 60.0,
            "current_gross_return_bps": gross_bps,
            "current_modeled_net_usd_excluding_funding": net_usd,
            "maximum_favorable_excursion_bps": 95.0,
            "maximum_adverse_excursion_bps": 2.0,
            "maximum_book_gap_ms": 15_000,
            "peak_giveback_bps": 95.0 - gross_bps,
            "technical_path_resolved": True,
        },
    }


def _runtime_progress_report(
    cycle: int, equity_usd: float, observed_at_utc: str
) -> dict[str, object]:
    return {
        "performance": {
            "closed_trades": 0,
            "net_pnl_usd": 0.0,
            "equity_usd": equity_usd,
        },
        "execution_diagnostics": {"entry_age": _entry_age_progress(cycle)},
        "external_asset_pipeline": {
            "observed_at_utc": observed_at_utc,
            "candidates": [{"observer": _observer_progress(cycle, observed_at_utc)}],
        },
        "mandate_evidence": _mandate_progress(cycle, equity_usd),
        "live_opportunity_diagnostics": {
            "routes": [
                {
                    "decision_side_coverage": {
                        "status": "available",
                        "by_side": {
                            "long": {
                                "evaluations": cycle,
                                "eligible_evaluations": 0,
                            },
                            "short": {
                                "evaluations": 0,
                                "eligible_evaluations": 0,
                            },
                        },
                        "directional_evaluations": cycle,
                        "nondirectional_evaluations": 0,
                        "observed_sides": ["long"],
                        "eligible_sides": [],
                        "both_sides_observed": False,
                    },
                    "blocker_combinations": [{"evaluations": cycle}],
                    "blocker_episode_combinations": [
                        {
                            "blockers": ["gate_absent"],
                            "episodes": 1,
                            "evaluations": cycle,
                        }
                    ],
                }
            ]
        },
    }


def _entry_age_progress(cycle: int) -> dict[str, object]:
    return {
        "paired_cycles": cycle,
        "evaluations": cycle * 7,
        "by_provider_symbol": {
            "route|ASSET": {
                "evaluations": cycle,
                "eligible_evaluations": 0,
                "submitted_entries_over_limit": 0,
                "minimum_submission_headroom_ms": 4_000,
            }
        },
    }


def _observer_progress(cycle: int, observed_at_utc: str) -> dict[str, object]:
    return {
        "observed_at_utc": observed_at_utc,
        "age_seconds": float(cycle % 7),
        "prospective_candle_rows_total": cycle,
        "decision_rows_total": cycle,
        "non_action_decisions_total": cycle,
        "latest_trailing_return_bps": float(cycle),
        "latest_threshold_fraction": float(cycle) / 1_000.0,
        "maximum_threshold_fraction_total": 0.42,
        "eligible_decisions_total": 0,
    }


def _mandate_progress(cycle: int, equity_usd: float) -> dict[str, object]:
    return {
        "execution": {"cycles": cycle, "fills": 0},
        "opportunities": {
            "provider_evaluations": cycle * 7,
            "directional_evaluations": cycle * 14,
            "exact_one_blocker_candidates": 2,
        },
        "portfolio_interactions": {
            "realized": {"snapshot_count": cycle, "maximum_drawdown_pct": 1.0},
            "planned": {
                "planned_margin_usd": equity_usd * 0.6,
                "planned_notional_usd": equity_usd * 6.0,
                "maximum_simultaneous_effective_margin_fraction": 0.6,
                "largest_margin_share": 1.0 / 6.0,
                "cap_bound_assets": 0,
            },
        },
        "regimes": {"evaluations": cycle * 6, "status": "measured"},
    }


def _signal_capture_report(
    status: str, expected: int, observed: int, watermark: int
) -> dict[str, object]:
    return {
        "index_signal_capture": {
            "status": status,
            "common_watermark_ms": watermark,
            "expected_decisions_total": expected,
            "observed_decisions_total": observed,
            "missing_boundaries_total": 0,
            "missing_ranges": [],
            "age_seconds_by_symbol": {"xyz:SP500": 2.0, "xyz:SPCX": 3.0},
            "cursor_skew_boundaries": expected % 2,
        }
    }


def _prospective_report(
    observed_at_utc: str, raw_evaluations: int, onsets: int
) -> dict[str, object]:
    observation = {
        "availability_status": "available",
        "observer_status": "candidate_lifecycle_pending",
        "observed_at_utc": observed_at_utc,
        "raw_exact_evaluations": raw_evaluations,
        "independent_onsets": onsets,
        "attempts": 1,
        "resolved_lifecycles": 0,
    }
    return {
        "experiment_queue": [{"prospective_observation": dict(observation)}],
        "prospective_experiment_evidence": [dict(observation)],
        "hypothesis_ledger": [{"prospective_observation": dict(observation)}],
    }


def test_history_appends_only_distinct_material_states(tmp_path: Path) -> None:
    """Polling the same hypothesis state must not spam the durable ledger."""
    path = tmp_path / "history.jsonl"
    report = _report("healthy")

    assert append_material_report(path, report) is True
    assert append_material_report(path, report) is False
    assert append_material_report(path, _report("degraded")) is True

    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [row["sequence"] for row in rows] == [1, 2]
    assert rows[0]["previous_event_sha256"] is None
    assert rows[1]["previous_event_sha256"] == rows[0]["event_sha256"]
    assert rows[0]["schema_version"] == 2
    assert rows[1]["material_state_sha256"] == material_state_sha256(
        _report("degraded")
    )
    assert rows[1]["changed_paths"] == ["$.operational_assessment.status"]
    assert (
        material_state_sha256(rows[1]["material_payload"])
        == rows[1]["material_state_sha256"]
    )


def test_history_rejects_a_corrupt_existing_chain(tmp_path: Path) -> None:
    """A broken audit trail must fail closed instead of being overwritten."""
    path = tmp_path / "history.jsonl"
    path.write_text('{"sequence":1,"event_sha256":"bad"}\n')

    with pytest.raises(ValueError, match="history event"):
        append_material_report(path, _report("healthy"))


def test_history_rejects_a_material_payload_hash_mismatch(tmp_path: Path) -> None:
    """A success-shaped event may not claim a different material state."""
    path = tmp_path / "history.jsonl"
    report = _report("healthy")
    assert append_material_report(path, report) is True
    event = json.loads(path.read_text())
    event["material_payload"]["operational_assessment"]["status"] = "tampered"
    event.pop("event_sha256")
    encoded = json.dumps(event, sort_keys=True, separators=(",", ":"))
    event["event_sha256"] = sha256(encoded.encode()).hexdigest()
    path.write_text(json.dumps(event) + "\n")

    with pytest.raises(ValueError, match="material payload hash"):
        append_material_report(path, report)


def test_history_migrates_from_a_valid_schema_one_event(tmp_path: Path) -> None:
    """The first reconstructible event after legacy history establishes a baseline."""
    path = tmp_path / "history.jsonl"
    legacy = _legacy_event()
    path.write_text(json.dumps(legacy) + "\n", encoding="utf-8")

    assert append_material_report(path, _report("legacy")) is True

    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [row["schema_version"] for row in rows] == [1, 2]
    assert rows[1]["previous_event_sha256"] == rows[0]["event_sha256"]
    assert rows[1]["changed_paths"] == ["$"]


def _report(status: str) -> dict[str, object]:
    report = {
        "generated_at_utc": "2026-08-13T22:00:00+00:00",
        "source": {
            "run_id": "run-51",
            "profile_id": "profile-51",
            "profile_fingerprint": "d" * 64,
        },
        "operational_assessment": {"status": status},
        "highest_value_next_investigation": {"route": "range|SOL"},
        "hypothesis_ledger": [{"route": "range|SOL", "status": "being_tested"}],
        "change_proposals": [],
        "contract": {"report_only": True, "execution_authority": "none"},
    }
    report["material_state_sha256"] = material_state_sha256(report)
    return report


def _legacy_event() -> dict[str, object]:
    report = _report("legacy")
    event = {
        "schema_version": 1,
        "sequence": 1,
        "recorded_at_utc": report["generated_at_utc"],
        "previous_event_sha256": None,
        "material_state_sha256": report["material_state_sha256"],
        "source": report["source"],
        "operational_assessment": report["operational_assessment"],
        "highest_value_next_investigation": report["highest_value_next_investigation"],
        "hypothesis_ledger": report["hypothesis_ledger"],
        "change_proposals": report["change_proposals"],
        "contract": report["contract"],
    }
    encoded = json.dumps(event, sort_keys=True, separators=(",", ":"))
    event["event_sha256"] = sha256(encoded.encode()).hexdigest()
    return event
