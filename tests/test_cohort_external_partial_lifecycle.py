"""Exact partial-lifecycle evidence for external research candidates."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path

import pytest

from hypervector.research.cohort_external_partial_lifecycle import (
    load_external_partial_lifecycle,
)


def test_partial_lifecycle_is_hash_bound_and_never_claims_pnl(
    tmp_path: Path,
) -> None:
    """A censored replay must remain technical evidence, not economics."""
    source = tmp_path / "partial.json"
    source.write_text(json.dumps(_payload()))
    raw = source.read_bytes()
    record = {
        "partial_lifecycle_source": {
            "path": source.name,
            "sha256": sha256(raw).hexdigest(),
            "bytes": len(raw),
        }
    }

    status, evidence = load_external_partial_lifecycle(
        tmp_path / "catalog.json",
        record,
        symbol="xyz:SP500",
        provider_id="fresh15-v3",
        profile_id="sp500-shadow-v3",
        observed_at=datetime(2026, 8, 19, 7, 0, tzinfo=UTC),
    )

    assert status == {
        "evidence_state": "open_censored_lifecycle",
        "observed_at_utc": "2026-08-19T06:56:00+00:00",
        "age_seconds": 240.0,
        "provider_id": "fresh15-v3",
        "profile_id": "sp500-shadow-v3",
        "side": "short",
        "decision_time_ms": 1_787_120_100_000,
        "entry_time_ms": 1_787_120_101_436,
        "censor_reason": "exit_event_censored",
        "nominal_completed": 0,
        "nominal_censored": 1,
        "stress_completed": 0,
        "stress_censored": 1,
        "all_lifecycle_paths_resolved": False,
        "pnl_claimed": False,
        "live_change_supported": False,
    }
    assert evidence is not None
    assert evidence["sha256"] == sha256(raw).hexdigest()


def test_partial_lifecycle_rejects_changed_bytes(tmp_path: Path) -> None:
    """An immutable partial replay must fail closed after byte drift."""
    source = tmp_path / "partial.json"
    source.write_text(json.dumps(_payload()))
    raw = source.read_bytes()
    record = {
        "partial_lifecycle_source": {
            "path": source.name,
            "sha256": sha256(raw).hexdigest(),
            "bytes": len(raw),
        }
    }
    source.write_text(source.read_text() + "\n")

    with pytest.raises(ValueError, match="partial lifecycle evidence mismatch"):
        load_external_partial_lifecycle(
            tmp_path / "catalog.json",
            record,
            symbol="xyz:SP500",
            provider_id="fresh15-v3",
            profile_id="sp500-shadow-v3",
            observed_at=datetime(2026, 8, 19, 7, 0, tzinfo=UTC),
        )


def _payload() -> dict[str, object]:
    summary = {
        "completed_lifecycles": 0,
        "censored_lifecycles": 1,
        "wins": 0,
        "losses": 0,
        "net_pnl_usd": 0,
        "mean_net_return_bps": None,
        "profit_factor": None,
        "net_without_largest_winner_usd": None,
        "censored": [
            {
                "decision_time_ms": 1_787_120_100_000,
                "entry_time_ms": 1_787_120_101_436,
                "reason": "exit_event_censored",
                "route_state_resolved_time_ms": None,
                "side": "short",
            }
        ],
    }
    return {
        "schema_version": "hip3_shadow_lifecycle_replay_v2",
        "symbol": "xyz:SP500",
        "provider_id": "fresh15-v3",
        "profile_id": "sp500-shadow-v3",
        "observed_at_ms": 1_787_122_560_000,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "technical_assessment": {
            "all_lifecycle_paths_resolved": False,
            "entry_identity_reproduced": True,
            "live_promotion_supported": False,
        },
        "nominal": dict(summary),
        "stress": dict(summary),
    }
