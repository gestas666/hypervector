"""Evidence contract for the v48 defect-versus-edge disposition."""

from __future__ import annotations

import json
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_DISPOSITION = Path("docs/research-journal/v48-strategy-disposition.json")
_CONFIG = Path("configs/multi_asset_growth_first_5000_repaired_candidate_v48.toml")
_HIP3_FRESHNESS = Path(
    "docs/research-journal/hip3-live-pressure-freshness-parity-v3.json"
)


def test_disposition_separates_bugs_from_strategy_underperformance() -> None:
    """Confirmed defects and valid negative economics must remain distinct."""
    report = json.loads(_DISPOSITION.read_text())
    decisions = {row["strategy"]: row for row in report["decisions"]}

    assert decisions["HIP3 pressure v1"]["diagnosis"] == "confirmed contract defect"
    assert decisions["SP500 pressure v2"]["decision"] == "remove from v48"
    assert decisions["SP500 pressure v2"]["diagnosis"] == (
        "freshness repaired; unchanged mechanism remains negative"
    )
    assert decisions["Range Onset"]["diagnosis"] == (
        "research/live parity confirmed; sparse and unstable evidence"
    )
    assert decisions["BTC Hulk short v3"]["diagnosis"] == (
        "target is 3R; historical 2R label is naming debt"
    )
    assert decisions["BTC sweep long"]["resolved_development_trades"] == 5
    assert decisions["BTC sweep long"]["unresolved_development_trades"] == 1


def test_disposition_matches_exact_v48_runtime_and_stress() -> None:
    """The durable recommendation must match the staged profile exactly."""
    report = json.loads(_DISPOSITION.read_text())
    config = load_multi_asset_live_config(_CONFIG, mode="observe")

    assert report["profile_id"] == config.profile_id
    assert report["profile_fingerprint"] == config.profile_fingerprint
    assert report["execution_authority"] == "none"
    assert report["assets"] == ["BTC", "ETH", "SOL", "HYPE"]
    assert report["provider_symbol_routes"] == 5
    assert report["directional_scopes"] == 8
    assert report["maximum_margin_fraction"] == 0.6
    assert report["modeled_p99_stop_wave_pct"] == 5.894084035092394


def test_disposition_includes_latest_closed_hip3_freshness_attribution() -> None:
    """The fifth stale-pressure close must not disappear from disposition evidence."""
    report = json.loads(_DISPOSITION.read_text())
    freshness = json.loads(_HIP3_FRESHNESS.read_text())
    decision = {row["strategy"]: row for row in report["decisions"]}["HIP3 pressure v1"]
    closed = freshness["closed_entry_actions_older_than_15_seconds"]

    assert len(closed) == 5
    assert all(row["pressure_age_seconds"] > 15.0 for row in closed)
    assert round(sum(row["net_pnl_usd"] for row in closed), 6) == -2.713721
    assert freshness["closed_pnl_attribution"]["affected_hip3_closed_trades"] == 5
    assert freshness["closed_pnl_attribution"]["affected_hip3_net_pnl_usd"] == (
        -2.713721
    )
    assert freshness["unaffected_open_entry"]["pressure_age_seconds"] == 11.673
    assert freshness["unaffected_open_entry"]["within_researched_freshness"] is True
    assert "five linked closes lost $2.713721" in decision["evidence"]
    assert str(_HIP3_FRESHNESS) in report["evidence_paths"]
