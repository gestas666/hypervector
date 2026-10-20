"""Backend protection warnings reach the supervisor probe unchanged.

The checkpoint job writes a top-level ``protection_warnings`` list into the file
the supervisor's health probe reads. Each side has its own tests; this pins the
junction: the same file, the same key and an entry shape the probe accepts.
"""

from __future__ import annotations

import json

import cohort_supervisor_health as health
from cohort_supervisor_models import REPOSITORY_ROOT, SupervisorPaths
import multi_asset_bidirectional_live_checkpoint as checkpoint_job
from hypervector.live.cohort_breakeven_events import RAISE_EXHAUSTED_EVENT
from hypervector.research.cohort_protection_warnings import protection_warnings

STRONG_SHORT = "hourly_donchian_20_10_atr20_strong_short_v1"


def _snapshot(size: float) -> dict[str, object]:
    return {
        "event_type": "cohort_snapshot",
        "payload": {
            "assets": [
                {"symbol": "xyz:SNDK", "entry_oid": 41, "position_size_signed": size}
            ]
        },
    }


def _exhausted(strategy_id: str | None) -> dict[str, object]:
    return {
        "event_type": RAISE_EXHAUSTED_EVENT,
        "observed_at_utc": "2026-09-24T18:00:00+00:00",
        "payload": {
            "symbol": "xyz:SNDK",
            "strategy_id": strategy_id,
            "entry_oid": 41,
            "reason": RAISE_EXHAUSTED_EVENT,
            "attempts": 3,
        },
    }


def _published(warnings: list[dict[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {"schema_version": 1}
    if warnings:
        document["protection_warnings"] = warnings
    return json.loads(json.dumps(document))


def test_checkpoint_job_publishes_the_file_the_probe_reads() -> None:
    assert (
        REPOSITORY_ROOT
        / checkpoint_job.build_parser().parse_args(["--config", "p.toml"]).out
        == SupervisorPaths().checkpoint
    )


def test_exhausted_raise_on_an_open_lifecycle_is_a_readable_probe_warning() -> None:
    for strategy_id in (STRONG_SHORT, None):
        warnings = protection_warnings([_exhausted(strategy_id)], _snapshot(-2.0))
        assert len(warnings) == 1
        valid, unreadable = health.protection_warnings(_published(warnings))
        assert valid == tuple(warnings)
        assert not unreadable


def test_no_open_lifecycle_publishes_no_key_and_reads_as_no_warning() -> None:
    warnings = protection_warnings([_exhausted(STRONG_SHORT)], _snapshot(0.0))
    assert warnings == []
    document = _published(warnings)
    assert "protection_warnings" not in document
    assert health.protection_warnings(document) == ((), False)
