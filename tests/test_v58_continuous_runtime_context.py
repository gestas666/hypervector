"""Runtime health and entry-delay capacity for the V58 research loop."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_observer_config import with_observer_ledger_root
from hypervector.research.cohort_successor_observer_status import (
    SuccessorObserverEvidence,
)
from hypervector.research.v58_continuous_runtime_context import (
    load_v58_runtime_context,
    runtime_context_payload,
)

_CONFIG = Path("configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml")


def test_loader_reports_transport_health_and_entry_delay_headroom(
    tmp_path: Path,
) -> None:
    """Latency capacity remains diagnostic and exact-checkpoint bound."""
    source, observer = _source(tmp_path)

    context = load_v58_runtime_context(source, _CONFIG, observer=observer)
    payload = runtime_context_payload(context)

    assert payload["poll_cycles"] == 100
    assert payload["degraded_poll_cycles"] == 2
    assert payload["measurement_scope"] == "report_only_observer"
    assert payload["active_live_backend_included"] is False
    assert payload["degraded_poll_fraction"] == 0.02
    assert payload["degraded_reasons"] == {"transport_timeout_retry_exhausted": 2}
    assert payload["latest_poll_status"] == "running"
    assert payload["successful_polls_since_last_degraded"] == 5
    assert payload["last_degraded_observed_at_utc"] == "2026-08-19T08:29:05+00:00"
    assert payload["minimum_entry_delay_headroom_seconds"] == 2.5
    assert payload["entry_delay_capacity_status"] == "within_configured_window"
    assert payload["entry_submission_latency_measured"] is False
    assert payload["execution_authority"] == "none"


def test_loader_reports_observed_arrival_beyond_configured_window(
    tmp_path: Path,
) -> None:
    """Late diagnostic evaluations are surfaced without becoming a risk gate."""
    source, observer = _source(tmp_path, excess_seconds=1.0)

    payload = runtime_context_payload(
        load_v58_runtime_context(source, _CONFIG, observer=observer)
    )

    assert payload["minimum_entry_delay_headroom_seconds"] == -1.0
    assert payload["entry_delay_capacity_status"] == "configured_window_exceeded"
    assert payload["automatic_live_change"] is False


def test_loader_reports_not_yet_observed_provider_without_inventing_lag(
    tmp_path: Path,
) -> None:
    """A new epoch may precede the first legitimate hourly route boundary."""
    base = load_multi_asset_live_config(_CONFIG, mode="observe")
    missing_strategy = base.providers[2].strategy_id
    source, observer = _source(tmp_path)
    checkpoint = json.loads(source.read_text())
    timing = checkpoint["audit"]["technical"]["decision_timing_seconds"][
        "steady_state_arrival_lag_by_provider"
    ]
    timing.pop(missing_strategy)
    raw = json.dumps(checkpoint, sort_keys=True).encode()
    source.write_bytes(raw)
    observer.evidence["checkpoint"].update(
        {"sha256": sha256(raw).hexdigest(), "bytes": len(raw)}
    )

    payload = runtime_context_payload(
        load_v58_runtime_context(source, _CONFIG, observer=observer)
    )

    missing = payload["provider_arrival_lag"][missing_strategy]
    assert missing["status"] == "not_observed"
    assert missing["observations"] == 0
    assert missing["maximum_seconds"] is None
    assert missing["headroom_seconds"] is None
    assert payload["entry_delay_capacity_status"] == "within_configured_window"


def _source(
    tmp_path: Path, *, excess_seconds: float | None = None
) -> tuple[Path, SuccessorObserverEvidence]:
    base = load_multi_asset_live_config(_CONFIG, mode="observe")
    rebound = with_observer_ledger_root(base, tmp_path)
    run_id = "bidirectional-observe-1787127644202"
    payload = _checkpoint(rebound, run_id, excess_seconds)
    raw = json.dumps(payload, sort_keys=True).encode()
    source = tmp_path / "checkpoint.json"
    source.write_bytes(raw)
    status = {
        "profile_id": rebound.profile_id,
        "profile_fingerprint": rebound.profile_fingerprint,
        "run_id": run_id,
        "freshness_status": "fresh",
        "technical_complete": True,
        "provider_symbol_routes": 10,
        "routed_actions": 0,
        "report_only": True,
        "execution_authority": "none",
    }
    evidence = {
        "checkpoint": {
            "path": str(source.resolve()),
            "sha256": sha256(raw).hexdigest(),
            "bytes": len(raw),
        },
        "observer_ledger": {"path": str((tmp_path / "decisions.jsonl").resolve())},
    }
    return source, SuccessorObserverEvidence(status, evidence)


def _checkpoint(config, run_id: str, excess: float | None) -> dict[str, object]:
    timing = {}
    for provider in config.providers:
        limit = float(provider.maximum_entry_delay_seconds)
        maximum = limit + excess if excess is not None else limit - 2.5
        timing[provider.strategy_id] = {
            "count": 10,
            "minimum": 1.0,
            "mean": maximum / 2,
            "maximum": maximum,
            "status": "observed",
        }
        excess = None
    return {
        "audit": {
            "run": {
                "profile_id": config.profile_id,
                "profile_fingerprint": config.profile_fingerprint,
                "run_id": run_id,
            },
            "runtime": {
                "poll_cycles": 100,
                "successful_poll_cycles": 98,
                "degraded_poll_cycles": 2,
                "degraded_reasons": {"transport_timeout_retry_exhausted": 2},
                "degraded_sources": {"hyperliquid_public_l2": 2},
                "first_degraded_observed_at_utc": "2026-08-19T08:00:05+00:00",
                "last_degraded_observed_at_utc": "2026-08-19T08:29:05+00:00",
                "successful_polls_since_last_degraded": 5,
                "latest_poll_status": "running",
                "heartbeat_interval_seconds": {
                    "count": 99,
                    "minimum": 14.0,
                    "mean": 15.0,
                    "maximum": 16.0,
                    "status": "observed",
                },
            },
            "technical": {
                "decision_timing_seconds": {
                    "steady_state_arrival_lag_by_provider": timing
                }
            },
        }
    }
