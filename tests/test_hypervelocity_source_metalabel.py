"""Evidence contracts for the gap-separated strict-source metalabel dataset."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.research.hypervelocity_source_metalabel import (
    validate_source_segment,
)


def _payload() -> dict[str, object]:
    lifecycle = {
        "lifecycle_id": 0,
        "direction": "long",
        "signal_time_utc": "2026-01-01T00:00:00+00:00",
        "entry_time_utc": "2026-01-01T00:00:01+00:00",
        "outcome_time_utc": "2026-01-01T00:10:00+00:00",
        "status": "liquidated",
    }
    return {
        "ok": True,
        "report_only": True,
        "runtime_strategy_changed": False,
        "allocation_fraction": 0.70,
        "leverage": 40.0,
        "gross_margin_target_pct": 8.0,
        "window_start_utc": "2026-01-01T00:00:00+00:00",
        "window_end_utc": "2026-01-01T01:00:00+00:00",
        "metalabel_policy": {
            "mode": "observe",
            "may_filter": False,
            "may_scale": False,
        },
        "archive": {
            "start": "2026-01-01T00:00:00+00:00",
            "end": "2026-01-01T01:00:00+00:00",
            "checksums_verified": True,
            "empty_book_windows": 0,
            "empty_trade_windows": 0,
        },
        "candidate_configs": {
            "strict_source_control": {
                "entry_depth_ticks": 0,
                "entry_ttl_seconds": 300.0,
                "fill_rule": "trade-through",
                "fixed_margin_stop_pct": None,
                "maximum_hold_seconds": None,
                "reentry_cooldown_seconds": 60.0,
                "same_direction_reentry_policy": "regime_reset",
                "target_continuation_limit_per_episode": None,
            }
        },
        "comparison": {
            "candidates": {
                "strict_source_control": {
                    "replay": {
                        "fill_rule": "trade-through",
                        "liquidation_model": "hyperliquid_mark_bbo_execution_v1",
                        "execution_economics_conclusive": True,
                        "active_book_gap_windows": 0,
                        "empty_book_evidence_windows": 0,
                        "lifecycles": [lifecycle],
                    }
                }
            }
        },
    }


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_source_segment_requires_corrected_runtime_and_conclusive_evidence(
    tmp_path: Path,
) -> None:
    """Only the exact runtime60, gap-free replay identity is model eligible."""
    path = tmp_path / "segment.json"
    _write(path, _payload())

    segment = validate_source_segment(path)

    assert len(segment.lifecycles) == 1
    assert segment.lifecycles["liquidation_risk"].tolist() == [1]
    assert segment.candidate_config["reentry_cooldown_seconds"] == 60.0


def test_source_segment_rejects_old_research_cooldown(tmp_path: Path) -> None:
    """The former 300-second research inheritance cannot enter model evidence."""
    payload = _payload()
    configs = payload["candidate_configs"]
    assert isinstance(configs, dict)
    candidate = configs["strict_source_control"]
    assert isinstance(candidate, dict)
    candidate["reentry_cooldown_seconds"] = 300.0
    path = tmp_path / "segment.json"
    _write(path, payload)

    with pytest.raises(ValueError, match="runtime replay settings differ"):
        validate_source_segment(path)


def test_source_segment_rejects_active_book_gap(tmp_path: Path) -> None:
    """A replay that traded through missing L2 evidence is not model eligible."""
    payload = _payload()
    comparison = payload["comparison"]
    assert isinstance(comparison, dict)
    candidates = comparison["candidates"]
    assert isinstance(candidates, dict)
    candidate = candidates["strict_source_control"]
    assert isinstance(candidate, dict)
    replay = candidate["replay"]
    assert isinstance(replay, dict)
    replay["active_book_gap_windows"] = 1
    path = tmp_path / "segment.json"
    _write(path, payload)

    with pytest.raises(ValueError, match="evidence is inconclusive"):
        validate_source_segment(path)
