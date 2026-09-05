"""Checkpoint-bound runtime and latency context for continuous V58 research."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_observer_config import with_observer_ledger_root
from hypervector.research.cohort_successor_observer_status import (
    SuccessorObserverEvidence,
)
from hypervector.research.v58_observer_technical_state import (
    require_reportable_v58_observer_status,
)

Record = Mapping[str, object]


@dataclass(frozen=True)
class ProviderArrivalLag:
    """One provider's observed decision arrival versus its configured limit."""

    strategy_id: str
    observations: int
    minimum_seconds: float | None
    mean_seconds: float | None
    maximum_seconds: float | None
    configured_limit_seconds: float
    headroom_seconds: float | None
    status: str = "observed"


@dataclass(frozen=True)
class RuntimeContext:
    """Validated transport health and provider timing capacity."""

    poll_cycles: int
    successful_poll_cycles: int
    degraded_poll_cycles: int
    degraded_reasons: dict[str, int]
    degraded_sources: dict[str, int]
    first_degraded_observed_at_utc: str | None
    last_degraded_observed_at_utc: str | None
    successful_polls_since_last_degraded: int
    latest_poll_status: str
    heartbeat: dict[str, object]
    provider_arrival_lags: tuple[ProviderArrivalLag, ...]
    evidence: dict[str, object]
    execution_authority: str = "none"


def load_v58_runtime_context(
    checkpoint_path: Path,
    config_path: Path,
    *,
    observer: SuccessorObserverEvidence,
) -> RuntimeContext:
    """Load exact runtime health from the observer-authenticated checkpoint."""
    _require_observer(observer.status)
    raw = checkpoint_path.read_bytes()
    _require_checkpoint(checkpoint_path, raw, observer.evidence)
    payload = _mapping(json.loads(raw), "V58 runtime checkpoint")
    audit = _mapping(payload.get("audit"), "V58 runtime audit")
    _require_run(_mapping(audit.get("run"), "V58 runtime run"), observer.status)
    config_evidence = file_evidence(config_path)
    config = _observer_config(config_path, observer)
    runtime = _mapping(audit.get("runtime"), "V58 runtime telemetry")
    technical = _mapping(audit.get("technical"), "V58 technical telemetry")
    timing = _timing(technical)
    context = _runtime_context(runtime, timing, config)
    if file_evidence(config_path) != config_evidence:
        raise ValueError("V58 config changed during runtime context evaluation")
    evidence = {
        "checkpoint": dict(_mapping(observer.evidence["checkpoint"], "checkpoint")),
        "config": {"path": str(config_path.resolve()), **config_evidence},
    }
    return RuntimeContext(*context, evidence)


def runtime_context_payload(context: RuntimeContext) -> dict[str, object]:
    """Serialize runtime capacity without implying edge or execution authority."""
    minimum, capacity_status = _entry_delay_capacity(context.provider_arrival_lags)
    return {
        "measurement_scope": "report_only_observer",
        "active_live_backend_included": False,
        "poll_cycles": context.poll_cycles,
        "successful_poll_cycles": context.successful_poll_cycles,
        "degraded_poll_cycles": context.degraded_poll_cycles,
        "degraded_poll_fraction": context.degraded_poll_cycles / context.poll_cycles,
        "degraded_reasons": context.degraded_reasons,
        "degraded_sources": context.degraded_sources,
        "first_degraded_observed_at_utc": context.first_degraded_observed_at_utc,
        "last_degraded_observed_at_utc": context.last_degraded_observed_at_utc,
        "successful_polls_since_last_degraded": (
            context.successful_polls_since_last_degraded
        ),
        "latest_poll_status": context.latest_poll_status,
        "heartbeat_interval_seconds": context.heartbeat,
        "provider_arrival_lag": {
            row.strategy_id: asdict(row) for row in context.provider_arrival_lags
        },
        "minimum_entry_delay_headroom_seconds": minimum,
        "entry_delay_capacity_status": capacity_status,
        "entry_submission_latency_measured": False,
        "profitability_claim": False,
        "automatic_live_change": False,
        "execution_authority": context.execution_authority,
    }


def _entry_delay_capacity(
    rows: tuple[ProviderArrivalLag, ...],
) -> tuple[float | None, str]:
    observed = [
        row.headroom_seconds for row in rows if row.headroom_seconds is not None
    ]
    if not observed:
        return None, "not_observed"
    minimum = min(observed)
    status = (
        "within_configured_window" if minimum >= 0.0 else "configured_window_exceeded"
    )
    return minimum, status


def _runtime_context(
    runtime: Record,
    timing: Record,
    config: MultiAssetLiveConfig,
) -> tuple[
    int,
    int,
    int,
    dict[str, int],
    dict[str, int],
    str | None,
    str | None,
    int,
    str,
    dict[str, object],
    tuple[ProviderArrivalLag, ...],
]:
    polls = _positive_integer(runtime.get("poll_cycles"), "poll cycles")
    successful = _nonnegative_integer(
        runtime.get("successful_poll_cycles"), "successful polls"
    )
    degraded = _nonnegative_integer(
        runtime.get("degraded_poll_cycles"), "degraded polls"
    )
    if successful + degraded != polls:
        raise ValueError("V58 poll accounting is inconsistent")
    reasons = _count_map(runtime.get("degraded_reasons"), "degraded reasons")
    sources = _count_map(runtime.get("degraded_sources"), "degraded sources")
    if sum(reasons.values()) != degraded or sum(sources.values()) != degraded:
        raise ValueError("V58 degradation attribution is inconsistent")
    recency = _degradation_recency(runtime, degraded, successful)
    heartbeat = _metric_payload(runtime.get("heartbeat_interval_seconds"), "heartbeat")
    lags = _provider_lags(timing, config)
    return polls, successful, degraded, reasons, sources, *recency, heartbeat, lags


def _degradation_recency(
    runtime: Record, degraded: int, successful: int
) -> tuple[str | None, str | None, int, str]:
    first = _optional_text(runtime.get("first_degraded_observed_at_utc"))
    last = _optional_text(runtime.get("last_degraded_observed_at_utc"))
    streak = _nonnegative_integer(
        runtime.get("successful_polls_since_last_degraded"), "successful poll streak"
    )
    latest = _text(runtime.get("latest_poll_status"), "latest poll status")
    if latest not in {"running", "degraded"}:
        raise ValueError("V58 latest poll status is invalid")
    if degraded and (first is None or last is None):
        raise ValueError("V58 degradation timestamps are missing")
    if not degraded and (first is not None or last is not None):
        raise ValueError("V58 degradation timestamps contradict zero events")
    if streak > successful or (streak == 0) != (latest == "degraded"):
        raise ValueError("V58 degradation recovery state is inconsistent")
    return first, last, streak, latest


def _provider_lags(
    timing: Record, config: MultiAssetLiveConfig
) -> tuple[ProviderArrivalLag, ...]:
    providers = {provider.strategy_id: provider for provider in config.providers}
    if len(providers) != len(config.providers) or not set(timing).issubset(providers):
        raise ValueError("V58 provider timing set is unknown or aliased")
    rows = []
    for strategy in sorted(providers):
        limit = float(providers[strategy].maximum_entry_delay_seconds)
        if strategy not in timing:
            rows.append(_unobserved_provider_lag(strategy, limit))
            continue
        metrics = _metric_payload(timing[strategy], f"{strategy} arrival lag")
        maximum = float(metrics["maximum"])
        rows.append(
            ProviderArrivalLag(
                strategy,
                int(metrics["count"]),
                float(metrics["minimum"]),
                float(metrics["mean"]),
                maximum,
                limit,
                limit - maximum,
                "observed",
            )
        )
    return tuple(rows)


def _unobserved_provider_lag(
    strategy_id: str, configured_limit_seconds: float
) -> ProviderArrivalLag:
    return ProviderArrivalLag(
        strategy_id,
        0,
        None,
        None,
        None,
        configured_limit_seconds,
        None,
        "not_observed",
    )


def _metric_payload(value: object, label: str) -> dict[str, object]:
    metrics = _mapping(value, label)
    count = _positive_integer(metrics.get("count"), f"{label} count")
    minimum = _nonnegative_number(metrics.get("minimum"), f"{label} minimum")
    mean = _nonnegative_number(metrics.get("mean"), f"{label} mean")
    maximum = _nonnegative_number(metrics.get("maximum"), f"{label} maximum")
    if not minimum <= mean <= maximum or metrics.get("status") != "observed":
        raise ValueError(f"{label} metrics are inconsistent")
    return {"count": count, "minimum": minimum, "mean": mean, "maximum": maximum}


def _observer_config(
    config_path: Path, observer: SuccessorObserverEvidence
) -> MultiAssetLiveConfig:
    ledger = _mapping(observer.evidence.get("observer_ledger"), "observer ledger")
    ledger_path = Path(_text(ledger.get("path"), "observer ledger path"))
    base = load_multi_asset_live_config(config_path, mode="observe")
    config = with_observer_ledger_root(base, ledger_path.parent)
    expected = (
        observer.status.get("profile_id"),
        observer.status.get("profile_fingerprint"),
    )
    if (config.profile_id, config.profile_fingerprint) != expected:
        raise ValueError("V58 runtime config identity is invalid")
    return config


def _require_checkpoint(path: Path, raw: bytes, evidence: Record) -> None:
    checkpoint = _mapping(evidence.get("checkpoint"), "checkpoint evidence")
    if (
        Path(_text(checkpoint.get("path"), "checkpoint path")).resolve()
        != path.resolve()
    ):
        raise ValueError("V58 runtime checkpoint path is invalid")
    if (
        checkpoint.get("bytes") != len(raw)
        or checkpoint.get("sha256") != sha256(raw).hexdigest()
    ):
        raise ValueError("V58 runtime checkpoint evidence changed")


def _require_run(run: Record, status: Record) -> None:
    fields = ("profile_id", "profile_fingerprint", "run_id")
    if any(run.get(field) != status.get(field) for field in fields):
        raise ValueError("V58 runtime run identity is invalid")


def _require_observer(status: Record) -> None:
    expected = {
        "freshness_status": "fresh",
        "provider_symbol_routes": 10,
        "routed_actions": 0,
        "report_only": True,
        "execution_authority": "none",
    }
    if any(status.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 runtime observer contract is invalid")
    require_reportable_v58_observer_status(status, "V58 runtime observer")


def _timing(technical: Record) -> Record:
    decision = _mapping(technical.get("decision_timing_seconds"), "decision timing")
    return _mapping(
        decision.get("steady_state_arrival_lag_by_provider"), "provider arrival lag"
    )


def _count_map(value: object, label: str) -> dict[str, int]:
    record = _mapping(value, label)
    return {
        _text(key, label): _positive_integer(count, label)
        for key, count in record.items()
    }


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _optional_text(value: object) -> str | None:
    return None if value is None else _text(value, "optional text")


def _positive_integer(value: object, label: str) -> int:
    number = _nonnegative_integer(value, label)
    if number == 0:
        raise ValueError(f"{label} must be positive")
    return number


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _nonnegative_number(value: object, label: str) -> float:
    valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    if not valid or not isfinite(value) or float(value) < 0.0:
        raise ValueError(f"{label} must be a nonnegative finite number")
    return float(value)
