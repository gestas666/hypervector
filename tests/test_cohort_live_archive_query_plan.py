"""Resource-bound invariants for durable lifecycle archive SQL."""

from __future__ import annotations

import re

from hypervector.data.cohort_research_sql import COHORT_LIVE_SCHEMA_SQL
from hypervector.research import cohort_live_archive_query as archive_query


def test_nonzero_positions_are_materialized_before_sequence_join() -> None:
    """Flat heartbeat history must not participate in the non-equality join."""
    tables = dict(archive_query._TABLES)
    names = tuple(tables)

    assert names.index("archive_open_position_events") < names.index(
        "archive_entry_position_sequences"
    )
    assert (
        "ASOF JOIN archive_open_position_events AS position"
        in tables["archive_entry_position_sequences"]
    )
    assert (
        "JOIN archive_open_position_events AS position"
        in tables["archive_entry_positions"]
    )


def test_repeated_fill_snapshots_group_by_bounded_digest() -> None:
    """Repeated multi-kilobyte fill arrays must not be window-partition keys."""
    assert "sha256(CAST(recent_fills AS VARCHAR)) AS revision_sha256" in (
        COHORT_LIVE_SCHEMA_SQL
    )
    assert re.search(r"arg_max\(\s*recent_fills", COHORT_LIVE_SCHEMA_SQL)
    assert "GROUP BY revision_sha256" in COHORT_LIVE_SCHEMA_SQL
    assert "PARTITION BY recent_fills" not in COHORT_LIVE_SCHEMA_SQL
