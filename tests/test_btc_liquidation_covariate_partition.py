"""Development-only partition binding for BTC liquidation replay."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.research.btc_liquidation_covariate_inputs import ArchiveHour
from hypervector.research.btc_liquidation_covariate_partition import (
    bind_development_episodes,
    development_windows,
    hours_for_window,
)

_DEVELOPMENT_START_MS = 1_764_547_200_000
_DEVELOPMENT_END_MS = 1_780_272_000_000


def _plan() -> dict[str, object]:
    """Build a minimal frozen-plan shape with a sealed later partition."""
    return {
        "schema_version": 1,
        "mode": "v58_btc_liquidation_covariate_acquisition_plan",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "strategy_outcomes_inspected": False,
        },
        "partitions": [
            {
                "name": "development",
                "start_ms": _DEVELOPMENT_START_MS,
                "end_ms": _DEVELOPMENT_END_MS,
            },
            {
                "name": "validation",
                "start_ms": _DEVELOPMENT_END_MS,
                "end_ms": _DEVELOPMENT_END_MS + 1_000_000,
            },
        ],
        "windows": [
            {
                "partition": "development",
                "start_ms": _DEVELOPMENT_START_MS + 1_000,
                "end_ms": _DEVELOPMENT_START_MS + 10_000,
                "episode_ids": ["dev-a", "dev-b"],
            },
            {
                "partition": "validation",
                "start_ms": _DEVELOPMENT_END_MS + 1_000,
                "end_ms": _DEVELOPMENT_END_MS + 10_000,
                "episode_ids": ["sealed-validation"],
            },
        ],
    }


def _episode_row(episode_id: str, branch: str) -> dict[str, object]:
    """Build one outcome-blind treatment row."""
    return {
        "schema_version": "btc_liquidation_treatment_episode_v1",
        "episode_id": episode_id,
        "symbol": "BTC",
        "candidate_branch": branch,
        "end_ms": _DEVELOPMENT_START_MS + 5_000,
        "volume_weighted_price": "100.25",
        "eligible_arms": ["5s_p95", "15s_p95"],
    }


def test_development_windows_ignore_later_partition_rows() -> None:
    """Expose only development identities while validation remains sealed."""
    windows = development_windows(_plan())

    assert len(windows) == 1
    assert windows[0].partition == "development"
    assert windows[0].episode_ids == ("dev-a", "dev-b")


def test_development_windows_reject_outcome_opened_plan() -> None:
    """Refuse a plan whose report-only evidence boundary was weakened."""
    plan = _plan()
    contract = plan["contract"]
    assert isinstance(contract, dict)
    contract["strategy_outcomes_inspected"] = True

    with pytest.raises(ValueError, match="outcome-blind"):
        development_windows(plan)


def test_episode_binding_requires_exact_development_coverage() -> None:
    """Bind every planned development identity once and ignore sealed rows."""
    windows = development_windows(_plan())
    rows = (
        _episode_row("dev-a", "continuation_long"),
        _episode_row("dev-b", "exhaustion_reclaim_long"),
        _episode_row("sealed-validation", "continuation_long"),
    )

    episodes = bind_development_episodes(rows, windows)

    assert tuple(row.episode_id for row in episodes) == ("dev-a", "dev-b")
    assert tuple(row.partition for row in episodes) == ("development", "development")

    with pytest.raises(ValueError, match="coverage"):
        bind_development_episodes(rows[:1], windows)


def test_hours_for_window_requires_contiguous_source_coverage() -> None:
    """Refuse a source gap across the requested entry-to-exit interval."""
    windows = development_windows(_plan())
    window = windows[0]
    first = ArchiveHour(
        _DEVELOPMENT_START_MS,
        _DEVELOPMENT_START_MS + 3_600_000,
        Path("book-a"),
        Path("trade-a"),
    )
    second = ArchiveHour(
        first.end_ms,
        first.end_ms + 3_600_000,
        Path("book-b"),
        Path("trade-b"),
    )

    selected = hours_for_window(
        (first, second),
        window,
        required_end_ms=first.end_ms + 1,
    )

    assert selected == (first, second)

    gapped = ArchiveHour(
        first.end_ms + 1,
        second.end_ms + 1,
        Path("book-c"),
        Path("trade-c"),
    )
    with pytest.raises(ValueError, match="contiguous"):
        hours_for_window((first, gapped), window, required_end_ms=gapped.start_ms + 1)
