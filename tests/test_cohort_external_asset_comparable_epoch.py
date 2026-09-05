"""Comparable decision-epoch evidence for external candidate monitoring."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path

from hypervector.research.cohort_external_asset_pipeline import (
    load_external_asset_pipeline,
)


def test_pipeline_separates_cumulative_and_source_comparable_eligibles(
    tmp_path: Path,
) -> None:
    """Pre-epoch eligibility must not appear in the repaired source window."""
    observed_at = datetime.fromtimestamp(4, tz=UTC)
    journal = tmp_path / "decisions.jsonl"
    rows = (
        _decision(1_000, eligible=True, side="long"),
        _decision(2_000, eligible=False, side=None),
        _decision(3_000, eligible=True, side="short"),
    )
    journal.write_text("".join(f"{json.dumps(row)}\n" for row in rows))
    observer = tmp_path / "observer.json"
    observer.write_text(json.dumps(_observer(observed_at)))
    liquidity = tmp_path / "liquidity.json"
    liquidity.write_text(json.dumps(_liquidity()))
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps(_catalog(liquidity, observer, journal)))

    result = load_external_asset_pipeline(
        catalog,
        observed_at=observed_at,
        maximum_observer_age_seconds=120.0,
    )

    candidate = result.status["candidates"][0]
    assert candidate["observer"]["eligible_decisions_total"] == 2
    assert candidate["comparable_decision_epoch"] == {
        "decision_start_ms": 2_000,
        "decision_rows": 2,
        "eligible_decisions": 1,
        "long_decisions": 0,
        "short_decisions": 1,
        "non_action_decisions": 1,
        "first_decision_time_ms": 2_000,
        "last_decision_time_ms": 3_000,
        "state": "eligible_onset_observed",
    }
    evidence = result.evidence["candidates"]["xyz:SP500"]
    assert evidence["comparable_decision_epoch"]["rows"] == 3
    assert evidence["comparable_decision_epoch"]["sha256"]


def _catalog(liquidity: Path, observer: Path, journal: Path) -> dict[str, object]:
    return {
        "contract": _report_only_contract(),
        "liquidity_source": _evidence(liquidity),
        "candidates": [
            {
                "symbol": "xyz:SP500",
                "stage": "frozen_source_native_lifecycle_collection_v1",
                "observer_path": observer.name,
                "comparable_decision_epoch": {
                    "decision_start_ms": 2_000,
                    "journal_path": journal.name,
                },
                "historical_live_source": None,
                "immutable_evidence": [],
            }
        ],
    }


def _observer(observed_at: datetime) -> dict[str, object]:
    return {
        **_report_only_contract(),
        "orders_supported": False,
        "signing_client_constructed": False,
        "symbol": "xyz:SP500",
        "observed_at_ms": int(observed_at.timestamp() * 1_000),
        "mode": "sp500_hip3_breakout_shadow_observer",
        "profile_id": "sp500_fresh15_pressure_shadow_research_v3",
        "provider_id": "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3",
        "promotion_blockers": ["forward_edge_unproven"],
        "eligible_decisions_total": 2,
    }


def _decision(time_ms: int, *, eligible: bool, side: str | None) -> dict[str, object]:
    return {
        "event_type": "sp500_hip3_breakout_shadow_decision",
        "execution_authority": "none",
        "report_only": True,
        "runtime_strategy_changed": False,
        "decision": {
            "decision_time_ms": time_ms,
            "eligible": eligible,
            "side": side,
            "prospective": True,
            "symbol": "xyz:SP500",
            "profile_id": "sp500_fresh15_pressure_shadow_research_v3",
            "provider_id": "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3",
            "execution_authority": "none",
        },
    }


def _liquidity() -> dict[str, object]:
    return {
        "mode": "hip3_market_qualification_v1",
        "status": "qualified_for_observation_only",
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "markets": [
            {
                "symbol": "xyz:SP500",
                "market": {"day_notional_volume_usd": 73_000_000.0},
                "book": {"spread_bps": 0.4},
                "max_leverage": 50,
            }
        ],
    }


def _report_only_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }


def _evidence(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {"path": path.name, "sha256": sha256(raw).hexdigest(), "bytes": len(raw)}
