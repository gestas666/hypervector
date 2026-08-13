"""Effective episode clustering tests for exact v39 forward evidence."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import importlib

import pytest

from v39_forward_evidence_fixtures import (
    NOW,
    checkpoint,
    config,
    install_current_run,
    open_row,
    routes,
)

Record = Mapping[str, object]
EpisodeBuilder = Callable[[Sequence[Record], Sequence[Record], str], dict[str, object]]


def test_transitive_overlap_is_one_ongoing_effective_episode() -> None:
    """Overlapping lifecycles count as one episode, not independent trades."""
    build = _builder()
    closed = [
        _closed("SNDK:1", 50, 80, 1.0),
        _closed("SPCX:2", 100, 200, -1.0),
        _closed("SP500:3", 180, 250, 2.0),
    ]
    opened = [_opened("BTC:4", 240, 500, 3.0)]

    report = build(closed, opened, "run-v39")

    assert report["raw_lifecycles"] == 4
    assert report["effective_episode_clusters"] == 2
    assert report["completed_effective_episodes"] == 1
    assert report["ongoing_effective_episodes"] == 1
    assert report["clusters"][1]["lifecycle_count"] == 3
    assert report["clusters"][1]["closed_net_pnl_usd"] == 1.0
    assert report["clusters"][1]["open_marked_pnl_usd"] == 3.0


def test_v39_snapshot_publishes_exact_run_effective_episodes() -> None:
    """The live snapshot exposes overlap without changing execution authority."""
    live_config = config()
    source = checkpoint(live_config)
    closed_route = routes(live_config)[0]
    open_route = next(route for route in routes(live_config) if "|HYPE" in route)
    install_current_run(source, closed_route)
    closed = source["audit"]["trade_reflections"]["trades"][0]
    closed.update(_timing(100, 200))
    strategy, symbol = open_route.split("|", 1)
    opened = open_row(strategy, symbol, "short")
    opened.update(_open_timing(150, 300))
    source["audit"]["open_trade_reflections"].update(
        {"open_lifecycles": 1, "trades": [opened]}
    )

    report = _snapshot_builder()(source, live_config, observed_at=NOW)

    evidence = report["effective_episode_evidence"]
    assert report["schema_version"] == "v39_forward_evidence_v2"
    assert evidence["raw_lifecycles"] == 2
    assert evidence["effective_episode_clusters"] == 1
    assert evidence["ongoing_effective_episodes"] == 1
    assert report["contract"]["execution_authority"] == "none"


def _builder() -> EpisodeBuilder:
    try:
        module = importlib.import_module("hypervector.research.v39_effective_episodes")
    except ModuleNotFoundError:
        pytest.fail("v39 effective episode evidence module is missing")
    return module.build_effective_episode_evidence


def _snapshot_builder() -> Callable[..., dict[str, object]]:
    module = importlib.import_module("hypervector.research.v39_forward_evidence")
    return module.build_v39_forward_evidence


def _timing(entry_ms: int, exit_ms: int) -> dict[str, object]:
    return {
        "entry": {"venue_timestamp_ms": entry_ms},
        "exit": {"venue_timestamp_ms": exit_ms},
    }


def _open_timing(entry_ms: int, observed_ms: int) -> dict[str, object]:
    return {
        "entry": {"venue_timestamp_ms": entry_ms},
        "open_profit_lock_challenger": {"as_of_timestamp_ms": observed_ms},
    }


def _closed(
    lifecycle_id: str,
    entry_ms: int,
    exit_ms: int,
    net_pnl_usd: float,
) -> dict[str, object]:
    symbol = lifecycle_id.split(":", 1)[0]
    return {
        "lifecycle_id": lifecycle_id,
        "source_run_id": "run-v39",
        "strategy_id": "strategy",
        "symbol": symbol,
        "side": "short",
        "entry": {"venue_timestamp_ms": entry_ms},
        "exit": {"venue_timestamp_ms": exit_ms},
        "net_pnl_usd": net_pnl_usd,
    }


def _opened(
    lifecycle_id: str,
    entry_ms: int,
    observed_ms: int,
    marked_net_pnl_usd: float,
) -> dict[str, object]:
    symbol = lifecycle_id.split(":", 1)[0]
    return {
        "lifecycle_id": lifecycle_id,
        "source_run_id": "run-v39",
        "strategy_id": "strategy",
        "symbol": symbol,
        "side": "short",
        "entry": {"venue_timestamp_ms": entry_ms},
        "open_profit_lock_challenger": {"as_of_timestamp_ms": observed_ms},
        "marked_economics": {"active_lifecycle_marked_net_pnl_usd": marked_net_pnl_usd},
    }
