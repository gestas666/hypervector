"""Evidence contract for V57 portfolio opportunity capacity."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_ROOT = Path(__file__).parents[1]
_CONFIG = (
    _ROOT / "configs/multi_asset_growth_first_5000_spcx_short_containment_v57.toml"
)
_CADENCE = (
    _ROOT / "docs/research-journal/v57-route-cadence-review-thresholds-20260818-v2.json"
)
_REPORT = (
    _ROOT / "docs/research-journal/v57-portfolio-opportunity-capacity-20260818-v1.json"
)
JsonRecord = dict[str, object]


def _sha256(path: Path) -> str:
    """Return the exact file SHA-256."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _weekly_rate(row: JsonRecord) -> float:
    """Return the frozen weekly sensitivity for one route."""
    explicit = row.get("historical_trades_per_week")
    if explicit is not None:
        return float(cast(float, explicit))
    events = float(cast(float, row["expected_events_at_threshold_sensitivity"]))
    days = float(cast(float, row["threshold_days"]))
    return events * 7.0 / days


def test_v57_capacity_reconciles_exact_identity_and_route_arithmetic() -> None:
    """The report must preserve V57 identity and avoid double-count claims."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    cadence = json.loads(_CADENCE.read_text())
    report = json.loads(_REPORT.read_text())
    thresholds = cast(dict[str, JsonRecord], cadence["route_thresholds"])
    rates = {route: _weekly_rate(row) for route, row in thresholds.items()}

    assert report["live_identity"]["profile_id"] == config.profile_id
    assert report["live_identity"]["profile_fingerprint"] == config.profile_fingerprint
    assert set(report["route_rates_per_week"]) == set(thresholds)
    assert report["route_rates_per_week"] == rates
    assert report["portfolio_capacity"]["independent_asset_slots"] == 3
    assert report["portfolio_capacity"]["configured_route_count"] == 5
    assert report["portfolio_capacity"]["btc_routes_share_one_slot"] is True
    assert report["portfolio_capacity"]["naive_route_sum_per_week"] == sum(
        rates.values()
    )
    assert report["portfolio_capacity"]["naive_sum_is_forecast"] is False


def test_v57_capacity_is_report_only_and_evidence_bound() -> None:
    """The diagnosis cannot mutate live strategy or overstate an addition."""
    report = json.loads(_REPORT.read_text())
    evidence = cast(list[JsonRecord], report["evidence"])
    indexed = {cast(str, row["role"]): row for row in evidence}

    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }
    assert report["proposed_live_change"] is None
    assert report["status"] == "capacity_diagnosed_no_live_change"
    assert report["highest_value_next_investigation"]["scope"] == (
        "one_independent_liquid_asset_specific_mechanism"
    )
    assert report["highest_value_next_investigation"]["approval_requested"] is False
    assert indexed["exact_live_configuration"]["sha256"] == _sha256(_CONFIG)
    assert indexed["frozen_route_cadence"]["sha256"] == _sha256(_CADENCE)
