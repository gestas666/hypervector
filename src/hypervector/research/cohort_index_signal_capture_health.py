"""Current-run continuity health for report-only HIP-3 index observers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
import math
from pathlib import Path

from hypervector.live.hip3_breakout_shadow_specs import (
    SP500_SHADOW_SPEC,
    SPCX_SHADOW_SPEC,
    Hip3BreakoutShadowSpec,
)
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger

_CADENCE_MS = 900_000
_SOURCE = "hyperliquid_public_candleSnapshot_15m_plus_mainnet_l2_rest"
_V51_PROFILE = "multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51"
_MAXIMUM_AGE_SECONDS = 90.0
_SPECS = {
    SP500_SHADOW_SPEC.symbol: SP500_SHADOW_SPEC,
    SPCX_SHADOW_SPEC.symbol: SPCX_SHADOW_SPEC,
}
_DEFAULT_STATUSES = {
    "xyz:SP500": Path("data/runtime/research/xyz_sp500_fresh15_v3_latest.json"),
    "xyz:SPCX": Path("data/runtime/research/xyz_spcx_fresh15_v3_latest.json"),
}
_DEFAULT_JOURNALS = {
    "xyz:SP500": Path("data/live/research/xyz_sp500_fresh15_v3_decisions.jsonl"),
    "xyz:SPCX": Path("data/live/research/xyz_spcx_fresh15_v3_decisions.jsonl"),
}


@dataclass(frozen=True)
class SignalCaptureHealth:
    """Material signal-capture health plus exact source evidence."""

    status: dict[str, object]
    evidence: dict[str, object] | None


@dataclass(frozen=True)
class _Source:
    symbol: str
    cursor_ms: int
    age_seconds: float
    boundaries: tuple[int, ...]
    status_evidence: dict[str, object]
    journal_evidence: dict[str, object]


def default_index_signal_capture_paths() -> tuple[dict[str, Path], dict[str, Path]]:
    """Return the frozen v51 observer status and decision journal paths."""
    return dict(_DEFAULT_STATUSES), dict(_DEFAULT_JOURNALS)


def load_v51_index_signal_capture_for_audit(
    audit: Mapping[str, object],
    *,
    observed_at: datetime,
    maximum_age_seconds: float = _MAXIMUM_AGE_SECONDS,
) -> SignalCaptureHealth | None:
    """Load v51 signal continuity or return no evidence for another profile."""
    run = _mapping(audit.get("run"), "improvement audit run")
    if run.get("profile_id") != _V51_PROFILE:
        return None
    statuses, journals = default_index_signal_capture_paths()
    return load_index_signal_capture_health(
        status_paths=statuses,
        journal_paths=journals,
        run_started_at=_timestamp(run.get("first_observed_at_utc"), "run start"),
        observed_at=observed_at,
        maximum_age_seconds=maximum_age_seconds,
    )


def load_index_signal_capture_health(
    *,
    status_paths: Mapping[str, Path],
    journal_paths: Mapping[str, Path],
    run_started_at: datetime,
    observed_at: datetime,
    maximum_age_seconds: float,
) -> SignalCaptureHealth:
    """Reconcile current-run observer freshness and every completed boundary."""
    _validate_inputs(
        status_paths,
        journal_paths,
        run_started_at,
        observed_at,
        maximum_age_seconds,
    )
    missing = _missing_paths(status_paths, journal_paths)
    if missing:
        return SignalCaptureHealth(_unavailable("unavailable_missing", missing), None)
    sources = tuple(
        _load_source(
            _SPECS[symbol],
            status_paths[symbol],
            journal_paths[symbol],
            observed_at,
        )
        for symbol in _SPECS
    )
    status = _capture_status(
        sources,
        run_started_at,
        maximum_age_seconds=maximum_age_seconds,
    )
    return SignalCaptureHealth(status, _capture_evidence(sources))


def _validate_inputs(
    statuses: Mapping[str, Path],
    journals: Mapping[str, Path],
    run_started_at: datetime,
    observed_at: datetime,
    maximum_age_seconds: float,
) -> None:
    if set(statuses) != set(_SPECS) or set(journals) != set(_SPECS):
        raise ValueError("index signal capture paths must bind both exact symbols")
    if run_started_at.tzinfo is None or observed_at.tzinfo is None:
        raise ValueError("index signal capture times must include timezones")
    if observed_at < run_started_at:
        raise ValueError("index signal observation precedes the run")
    if not math.isfinite(maximum_age_seconds) or maximum_age_seconds <= 0.0:
        raise ValueError("maximum index signal age must be positive and finite")


def _missing_paths(
    statuses: Mapping[str, Path], journals: Mapping[str, Path]
) -> list[str]:
    return sorted(
        str(path.resolve())
        for path in (*statuses.values(), *journals.values())
        if not path.is_file()
    )


def _load_source(
    spec: Hip3BreakoutShadowSpec,
    status_path: Path,
    journal_path: Path,
    observed_at: datetime,
) -> _Source:
    raw = status_path.read_bytes()
    status = _mapping(json.loads(raw), f"{spec.symbol} observer status")
    _validate_status(status, spec)
    cursor = _integer(status.get("cursor_decision_time_ms"), "status cursor")
    observed_ms = _integer(status.get("observed_at_ms"), "status observed_at")
    if cursor % _CADENCE_MS or observed_ms < cursor:
        raise ValueError(f"{spec.symbol} observer status times are inconsistent")
    age = _age_seconds(observed_at, observed_ms, spec.symbol)
    boundaries, journal_evidence = _load_journal(journal_path, spec)
    return _Source(
        spec.symbol,
        cursor,
        age,
        boundaries,
        _file_evidence(status_path, raw),
        journal_evidence,
    )


def _validate_status(
    status: Mapping[str, object], spec: Hip3BreakoutShadowSpec
) -> None:
    token = spec.symbol.removeprefix("xyz:").lower()
    expected = {
        "schema_version": 1,
        "mode": f"{token}_hip3_breakout_shadow_observer",
        "symbol": spec.symbol,
        "provider_id": spec.provider_id,
        "profile_id": spec.profile_id,
        "execution_authority": "none",
        "report_only": True,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "signing_client_constructed": False,
        "orders_supported": False,
        "signal_ohlc_source": "hyperliquid_public_candleSnapshot_15m",
        "pressure_source": "hyperliquid_mainnet_l2_rest",
    }
    for field, value in expected.items():
        if status.get(field) != value:
            raise ValueError(f"{spec.symbol} observer has invalid {field}")


def _load_journal(
    path: Path, spec: Hip3BreakoutShadowSpec
) -> tuple[tuple[int, ...], dict[str, object]]:
    with snapshot_decision_ledger(path, allow_incomplete_tail=True) as (rows, evidence):
        boundaries = tuple(_decision_boundary(row, spec) for row in rows)
        output = dict(evidence)
    if len(boundaries) != len(set(boundaries)):
        raise ValueError(f"{spec.symbol} journal contains duplicate boundaries")
    if tuple(sorted(boundaries)) != boundaries:
        raise ValueError(f"{spec.symbol} journal boundaries are not ordered")
    output["path"] = str(path.resolve())
    return boundaries, output


def _decision_boundary(row: Mapping[str, object], spec: Hip3BreakoutShadowSpec) -> int:
    decision = _mapping(row.get("decision"), f"{spec.symbol} journal decision")
    boundary = _integer(decision.get("decision_time_ms"), "decision boundary")
    token = spec.symbol.removeprefix("xyz:").lower()
    expected_id = f"{spec.provider_id}|{spec.symbol}|{boundary}"
    exact = (
        boundary % _CADENCE_MS == 0
        and row.get("schema_version") == 1
        and row.get("event_type") == f"{token}_hip3_breakout_shadow_decision"
        and row.get("event_id") == expected_id
        and row.get("report_only") is True
        and row.get("execution_authority") == "none"
        and row.get("runtime_strategy_changed") is False
        and row.get("intents") == []
        and decision.get("provider_id") == spec.provider_id
        and decision.get("profile_id") == spec.profile_id
        and decision.get("symbol") == spec.symbol
        and decision.get("prospective") is True
        and decision.get("execution_authority") == "none"
    )
    if not exact:
        raise ValueError(f"{spec.symbol} journal decision identity is invalid")
    return boundary


def _capture_status(
    sources: tuple[_Source, ...],
    run_started_at: datetime,
    *,
    maximum_age_seconds: float,
) -> dict[str, object]:
    start = _next_boundary_ms(run_started_at)
    watermark = min(source.cursor_ms for source in sources)
    expected = _expected_boundaries(start, watermark)
    missing = _all_missing_ranges(sources, expected)
    ages = {source.symbol: source.age_seconds for source in sources}
    observed = sum(len(set(source.boundaries) & expected) for source in sources)
    state = _capture_state(sources, missing, maximum_age_seconds)
    cursor_min = min(source.cursor_ms for source in sources)
    cursor_max = max(source.cursor_ms for source in sources)
    return {
        "status": state,
        "symbols": list(_SPECS),
        "source": _SOURCE,
        "cadence_seconds": _CADENCE_MS // 1_000,
        "run_start_boundary_ms": start,
        "common_watermark_ms": watermark,
        "expected_decisions_total": len(expected) * len(sources),
        "observed_decisions_total": observed,
        "missing_boundaries_total": sum(row["count"] for row in missing),
        "missing_ranges": missing,
        "age_seconds_by_symbol": ages,
        "cursor_skew_boundaries": (cursor_max - cursor_min) // _CADENCE_MS,
        "execution_authority": "none",
        "report_only": True,
        "orders_supported": False,
    }


def _capture_state(
    sources: tuple[_Source, ...],
    missing: list[dict[str, object]],
    maximum_age_seconds: float,
) -> str:
    if any(source.age_seconds > maximum_age_seconds for source in sources):
        return "unavailable_stale"
    if missing:
        return "degraded_internal_gaps"
    cursors = [source.cursor_ms for source in sources]
    if max(cursors) - min(cursors) > _CADENCE_MS:
        return "degraded_cursor_skew"
    return "healthy"


def _all_missing_ranges(
    sources: tuple[_Source, ...], expected: set[int]
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for source in sources:
        missing = sorted(expected - set(source.boundaries))
        output.extend(_compress_ranges(source.symbol, missing))
    return output


def _compress_ranges(symbol: str, boundaries: list[int]) -> list[dict[str, object]]:
    if not boundaries:
        return []
    groups: list[list[int]] = [[boundaries[0]]]
    for boundary in boundaries[1:]:
        if boundary - groups[-1][-1] == _CADENCE_MS:
            groups[-1].append(boundary)
        else:
            groups.append([boundary])
    return [
        {
            "symbol": symbol,
            "first_boundary_ms": group[0],
            "last_boundary_ms": group[-1],
            "count": len(group),
        }
        for group in groups
    ]


def _expected_boundaries(start: int, watermark: int) -> set[int]:
    if watermark < start:
        return set()
    return set(range(start, watermark + _CADENCE_MS, _CADENCE_MS))


def _next_boundary_ms(value: datetime) -> int:
    timestamp = int(value.astimezone(UTC).timestamp() * 1_000)
    return (timestamp // _CADENCE_MS + 1) * _CADENCE_MS


def _age_seconds(observed_at: datetime, recorded_ms: int, symbol: str) -> float:
    recorded = datetime.fromtimestamp(recorded_ms / 1_000, UTC)
    age = (observed_at.astimezone(UTC) - recorded).total_seconds()
    if age < 0.0:
        raise ValueError(f"{symbol} observer status is in the future")
    return age


def _capture_evidence(sources: tuple[_Source, ...]) -> dict[str, object]:
    return {
        "statuses": {source.symbol: source.status_evidence for source in sources},
        "journals": {source.symbol: source.journal_evidence for source in sources},
    }


def _unavailable(status: str, missing: list[str]) -> dict[str, object]:
    return {
        "status": status,
        "symbols": list(_SPECS),
        "source": _SOURCE,
        "missing_paths": missing,
        "execution_authority": "none",
        "report_only": True,
        "orders_supported": False,
    }


def _file_evidence(path: Path, raw: bytes) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed.astimezone(UTC)
