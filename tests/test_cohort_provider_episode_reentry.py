"""Causal live provider episode and re-entry attribution tests."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_provider_episode_reentry import (
    build_provider_episode_reentry,
)

_STRATEGY = "hip3_swing_ha_sp500_spcx_bidirectional_v2"
_SYMBOL = "xyz:SPCX"
_CADENCE_MS = 900_000


def test_state_episode_tracks_reentries_across_compatible_restart() -> None:
    """A process restart cannot relabel a persistent provider state as fresh."""
    records = [
        _routing("run-a", "profile-a", 0, aligned=True, sequence=1),
        _routing("run-a", "profile-a", 1, aligned=True, sequence=2),
        _routing("run-b", "profile-a", 2, aligned=True, sequence=3),
        _routing("run-b", "profile-a", 3, aligned=False, sequence=4),
        _routing("run-b", "profile-a", 4, aligned=True, sequence=5),
    ]
    trades = [
        _closed("first", "run-a", 0, 1.0, 10.0),
        _closed("repeat-a", "run-a", 1, -0.25, -2.5),
        _closed("repeat-b", "run-b", 2, -0.50, -5.0),
        _closed("new-episode", "run-b", 4, 0.30, 3.0),
    ]

    report = build_provider_episode_reentry(records, trades)

    coverage = report["evaluation_coverage"]
    assert coverage == {
        "matching_rows": 5,
        "deduplicated_decisions": 5,
        "unavailable_rows": 0,
        "technical_boundary_rows": 0,
        "episodes": 2,
        "restart_spanning_episodes": 1,
        "profile_boundary_resets": 0,
        "data_gap_resets": 0,
        "routing_rows_without_evaluations": 0,
    }
    resolved = report["resolved"]
    assert resolved["matching_trades"] == 4
    assert resolved["attributable"] == 4
    assert resolved["unavailable"] == 0
    assert resolved["first_entries"] == 2
    assert resolved["repeat_entries"] == 2
    assert resolved["first_entry"]["net_pnl_usd"] == pytest.approx(1.30)
    assert resolved["repeat_entry"]["net_pnl_usd"] == pytest.approx(-0.75)
    pair = resolved["by_provider_symbol_side"][f"{_STRATEGY}|{_SYMBOL}|long"]
    assert pair["episodes_with_entries"] == 2
    assert pair["episodes_with_reentries"] == 1
    lifecycles = pair["lifecycles"]
    assert [row["reentry_ordinal"] for row in lifecycles] == [1, 2, 3, 1]
    assert [row["entry_class"] for row in lifecycles] == [
        "first_entry",
        "repeat_entry",
        "repeat_entry",
        "first_entry",
    ]
    assert lifecycles[0]["episode_id"] == lifecycles[2]["episode_id"]
    assert lifecycles[3]["episode_id"] != lifecycles[2]["episode_id"]
    assert report["episodes"][0]["run_ids"] == ["run-a", "run-b"]


def test_profile_change_and_missing_decision_break_episode_identity() -> None:
    """Changed implementation identity and unseen bars both reset attribution."""
    records = [
        _routing("run-a", "profile-a", 0, aligned=True, sequence=1),
        _routing("run-b", "profile-b", 1, aligned=True, sequence=2),
        _routing("run-b", "profile-b", 3, aligned=True, sequence=3),
    ]

    report = build_provider_episode_reentry(records, [])

    coverage = report["evaluation_coverage"]
    assert coverage["episodes"] == 3
    assert coverage["profile_boundary_resets"] == 1
    assert coverage["data_gap_resets"] == 1
    assert [row["start_decision_time_ms"] for row in report["episodes"]] == [
        _decision_ms(0),
        _decision_ms(1),
        _decision_ms(3),
    ]


def test_onset_provider_alignment_persists_until_a_native_component_breaks() -> None:
    """Missing a fresh onset alone does not falsely end an aligned state."""
    strategy = "hip3_swing_ha_sndk_gold_brent_bidirectional_v1"
    records = [
        _routing(
            "run-a",
            "profile-a",
            0,
            aligned=True,
            sequence=1,
            strategy=strategy,
            entry_mode="onset",
        ),
        _routing(
            "run-a",
            "profile-a",
            1,
            aligned=True,
            sequence=2,
            strategy=strategy,
            entry_mode="onset",
            eligible=False,
            blockers=["fresh_entry_onset_absent"],
        ),
        _routing(
            "run-a",
            "profile-a",
            2,
            aligned=False,
            sequence=3,
            strategy=strategy,
            entry_mode="onset",
            blockers=["fresh_entry_onset_absent", "heikin_ashi_color_mismatch"],
        ),
        _routing(
            "run-a",
            "profile-a",
            3,
            aligned=True,
            sequence=4,
            strategy=strategy,
            entry_mode="onset",
        ),
    ]

    report = build_provider_episode_reentry(records, [])

    assert report["evaluation_coverage"]["episodes"] == 2
    assert [row["decision_count"] for row in report["episodes"]] == [2, 1]


def test_indicator_warmup_is_a_known_episode_boundary() -> None:
    """Gap-segment warmup ends continuity without becoming unknown evidence."""
    strategy = "hip3_swing_ha_sndk_gold_brent_bidirectional_v1"
    records = [
        _routing(
            "run-a",
            "profile-a",
            0,
            aligned=True,
            sequence=1,
            strategy=strategy,
            entry_mode="onset",
        ),
        _routing(
            "run-a",
            "profile-a",
            1,
            aligned=False,
            sequence=2,
            strategy=strategy,
            entry_mode="onset",
            eligible=False,
            blockers=["indicator_warmup"],
        ),
        _routing(
            "run-a",
            "profile-a",
            2,
            aligned=True,
            sequence=3,
            strategy=strategy,
            entry_mode="onset",
        ),
    ]

    report = build_provider_episode_reentry(records, [])

    coverage = report["evaluation_coverage"]
    assert coverage["technical_boundary_rows"] == 1
    assert coverage["unavailable_rows"] == 0
    assert coverage["episodes"] == 2


def test_conflicting_duplicate_decision_fails_instead_of_guessing() -> None:
    """Two incompatible states for one causal decision are an evidence defect."""
    records = [
        _routing("run-a", "profile-a", 0, aligned=True, sequence=1),
        _routing("run-a", "profile-a", 0, aligned=False, sequence=2),
    ]

    with pytest.raises(ValueError, match="conflicting provider decision"):
        build_provider_episode_reentry(records, [])


def test_open_marks_remain_provisional_and_missing_episode_is_explicit() -> None:
    """An unmatched open position cannot contaminate resolved re-entry economics."""
    records = [_routing("run-a", "profile-a", 0, aligned=True, sequence=1)]
    closed = [_closed("closed", "run-a", 0, 0.25, 2.5)]
    opened = [_open("open", "run-a", 1, marked_net=-0.10, margin=10.0)]

    report = build_provider_episode_reentry(records, closed, open_trades=opened)

    assert report["resolved"]["attributable"] == 1
    assert report["resolved"]["net_pnl_includes_open_marks"] is False
    provisional = report["provisional_open"]
    assert provisional["matching_positions"] == 1
    assert provisional["attributable"] == 0
    assert provisional["unavailable"] == 1
    assert provisional["pooled_with_resolved"] is False
    assert provisional["positions"][0]["attribution_status"] == "unavailable"
    assert provisional["positions"][0]["unavailable_reason"] == (
        "no_exact_provider_episode_evidence"
    )


def _routing(
    run_id: str,
    profile: str,
    position: int,
    *,
    aligned: bool,
    sequence: int,
    strategy: str = _STRATEGY,
    entry_mode: str = "state",
    eligible: bool | None = None,
    blockers: list[str] | None = None,
) -> dict[str, object]:
    """Build one exact completed-provider evaluation row."""
    is_eligible = aligned if eligible is None else eligible
    active_blockers = blockers
    if active_blockers is None:
        active_blockers = [] if aligned else ["entry_state_absent"]
    return {
        "event_type": "intent_routing",
        "run_id": run_id,
        "profile_fingerprint": profile,
        "observed_at_utc": "2026-08-09T00:00:00+00:00",
        "sequence": sequence,
        "payload": {
            "evaluations": [
                {
                    "strategy_id": strategy,
                    "symbol": _SYMBOL,
                    "decision_time_ms": _decision_ms(position),
                    "side": "long",
                    "eligible": is_eligible,
                    "readiness": {
                        "side": "long",
                        "blockers": active_blockers,
                        "metrics": {
                            "entry_mode": entry_mode,
                            "source_timeframe": "15m",
                        },
                    },
                }
            ]
        },
    }


def _closed(
    lifecycle_id: str,
    run_id: str,
    position: int,
    net_pnl: float,
    return_pct: float,
) -> dict[str, object]:
    """Build one resolved live lifecycle with causal provider attribution."""
    return {
        **_trade_identity(lifecycle_id, run_id, position),
        "net_pnl_usd": net_pnl,
        "net_return_on_margin_pct": return_pct,
    }


def _open(
    lifecycle_id: str,
    run_id: str,
    position: int,
    *,
    marked_net: float,
    margin: float,
) -> dict[str, object]:
    """Build one provisional open lifecycle."""
    return {
        **_trade_identity(lifecycle_id, run_id, position),
        "marked_economics": {
            "active_lifecycle_marked_net_pnl_usd": marked_net,
            "margin_used_usd": margin,
        },
    }


def _trade_identity(
    lifecycle_id: str,
    run_id: str,
    position: int,
) -> dict[str, object]:
    return {
        "lifecycle_id": lifecycle_id,
        "source_run_id": run_id,
        "strategy_id": _STRATEGY,
        "symbol": _SYMBOL,
        "side": "long",
        "entry_context": {
            "signal_provider": {
                "strategy_id": _STRATEGY,
                "decision_time_ms": _decision_ms(position),
                "eligible": True,
                "side": "long",
            }
        },
    }


def _decision_ms(position: int) -> int:
    return 1_800_000 + position * _CADENCE_MS
