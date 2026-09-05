"""Validated V58 successor-observer status for the improvement digest."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
import math
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_observer_config import with_observer_ledger_root

Record = Mapping[str, object]

_V57 = "multi_asset_growth_first_5000_spcx_short_containment_v57"
_V58 = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_PROFILE = "24820e4bfad8a978a7b617a29dc0326f8fc0e583389b67e0219ce4ab5789c874"
_BASE_PROFILE = "8a04636c9ff60a7eae141381cb540d7c6ceed081097cda7d5e465d48faa5022b"
_RUN = "1812cbfd3ad4b3f9b939c21c45caa38155e48ca78ddb205e68d68c9dd9b8f1d8"
_RUN_ID_PREFIX = "bidirectional-observe-"
_FIRST_RUN_START_MS = 1_787_108_378_615
_STATUS_PATH = Path("data/runtime/research/v58_eight_asset_observer_latest.json")
_MAXIMUM_AGE_SECONDS = 300.0
_SYMBOLS = (
    "BTC",
    "ETH",
    "SOL",
    "HYPE",
    "xyz:SP500",
    "xyz:SPCX",
    "xyz:SNDK",
    "xyz:BRENTOIL",
)
_REPORTABLE_TECHNICAL_GAPS = {"observer_heartbeat_gap_exceeds_entry_delay"}


@dataclass(frozen=True)
class SuccessorObserverEvidence:
    """Validated successor status and exact checkpoint evidence."""

    status: dict[str, object]
    evidence: dict[str, object]


def load_v58_successor_observer_status(
    path: Path,
    *,
    observed_at: datetime,
    maximum_age_seconds: float,
    config_path: Path | None = None,
) -> SuccessorObserverEvidence:
    """Load one exact execution-incapable V58 observer checkpoint."""
    _require_aware(observed_at)
    _require_positive(maximum_age_seconds)
    raw = path.read_bytes()
    payload = _mapping(json.loads(raw), "successor observer checkpoint")
    _require_top_level_contract(payload)
    timestamp, age = _freshness(payload, observed_at)
    audit = _mapping(payload.get("audit"), "successor observer audit")
    _require_observer_contract(
        _mapping(audit.get("observer_contract"), "successor observer contract")
    )
    ledger = _validated_ledger_evidence(payload.get("evidence"))
    profile_fingerprint, run_fingerprint = _expected_observer_identity(
        config_path,
        ledger,
    )
    run = _mapping(audit.get("run"), "successor observer run")
    _require_run(
        run,
        int(timestamp.timestamp() * 1_000),
        profile_fingerprint=profile_fingerprint,
        run_fingerprint=run_fingerprint,
    )
    technical = _mapping(audit.get("technical"), "successor observer technical")
    _require_technical(technical)
    runtime = _mapping(audit.get("runtime"), "successor observer runtime")
    signals = _mapping(audit.get("signals"), "successor observer signals")
    _require_signals(signals)
    return SuccessorObserverEvidence(
        _status(run, technical, runtime, signals, timestamp, age, maximum_age_seconds),
        {"checkpoint": _raw_evidence(path, raw), "observer_ledger": ledger},
    )


def load_v58_successor_observer_for_profile(
    audit: Record,
    observed_at: datetime,
) -> SuccessorObserverEvidence | None:
    """Load V58 evidence only beside its exact active V57 baseline."""
    run = _mapping(audit.get("run"), "improvement audit run")
    if run.get("profile_id") != _V57:
        return None
    return load_v58_successor_observer_status(
        _STATUS_PATH,
        observed_at=observed_at,
        maximum_age_seconds=_MAXIMUM_AGE_SECONDS,
    )


def _require_top_level_contract(payload: Record) -> None:
    expected = {
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_observer_checkpoint",
    }
    if any(payload.get(field) != value for field, value in expected.items()):
        raise ValueError("successor observer source contract is invalid")
    contract = _mapping(payload.get("checkpoint_contract"), "checkpoint contract")
    required = {
        "automatic_pause": False,
        "automatic_retuning": False,
        "execution_authority": "none",
        "final": False,
        "performance_gate": False,
        "report_only": True,
        "runtime_strategy_changed": False,
    }
    if any(contract.get(field) != value for field, value in required.items()):
        raise ValueError("successor observer checkpoint contract is invalid")


def _require_observer_contract(contract: Record) -> None:
    expected = {
        "execution_authority": "none",
        "fills_observed": False,
        "orders_observed": False,
        "performance_gate": False,
        "profitability_measured": False,
        "report_only": True,
        "runtime_strategy_changed": False,
    }
    if any(contract.get(field) != value for field, value in expected.items()):
        raise ValueError("successor observer audit contract is invalid")


def _require_run(
    run: Record,
    generated_at_ms: int,
    *,
    profile_fingerprint: str,
    run_fingerprint: str,
) -> None:
    expected = {
        "profile_id": _V58,
        "profile_fingerprint": profile_fingerprint,
        "run_fingerprint": run_fingerprint,
    }
    if any(run.get(field) != value for field, value in expected.items()):
        raise ValueError("successor observer run identity is invalid")
    _require_run_id(run.get("run_id"), generated_at_ms)
    if _text_list(run.get("symbols"), "successor symbols") != list(_SYMBOLS):
        raise ValueError("successor observer symbol identity is invalid")


def _expected_observer_identity(
    config_path: Path | None,
    ledger: Record,
) -> tuple[str, str]:
    if config_path is None:
        return _PROFILE, _RUN
    base = load_multi_asset_live_config(config_path, mode="observe")
    if base.profile_id != _V58 or base.profile_fingerprint != _BASE_PROFILE:
        raise ValueError("successor observer base config identity is invalid")
    ledger_path = Path(_text(ledger.get("path"), "observer ledger path"))
    isolated = with_observer_ledger_root(base, ledger_path.parent)
    if isolated.cohort_ledger.resolve() != ledger_path.resolve():
        raise ValueError("successor observer ledger path is invalid")
    return isolated.profile_fingerprint, isolated.run_fingerprint


def _require_run_id(value: object, generated_at_ms: int) -> None:
    run_id = _text(value, "successor observer run id")
    if not run_id.startswith(_RUN_ID_PREFIX):
        raise ValueError("successor observer run identity is invalid")
    raw_timestamp = run_id.removeprefix(_RUN_ID_PREFIX)
    try:
        timestamp_ms = int(raw_timestamp)
    except ValueError as exc:
        raise ValueError("successor observer run identity is invalid") from exc
    if str(timestamp_ms) != raw_timestamp:
        raise ValueError("successor observer run identity is invalid")
    if not _FIRST_RUN_START_MS <= timestamp_ms <= generated_at_ms:
        raise ValueError("successor observer run identity is invalid")


def _require_technical(technical: Record) -> None:
    expected = {
        "expected_provider_symbols": 10,
        "initial_provider_symbols": 10,
        "observed_provider_symbols": 10,
        "duplicate_evaluations": 0,
        "future_decisions": 0,
    }
    if any(technical.get(field) != value for field, value in expected.items()):
        raise ValueError("successor observer technical contract is invalid")
    if technical.get("missing_observed_provider_symbols") != []:
        raise ValueError("successor observer technical gaps are present")
    gaps = _text_list(technical.get("technical_gaps"), "technical gaps")
    if any(gap not in _REPORTABLE_TECHNICAL_GAPS for gap in gaps):
        raise ValueError("successor observer technical gaps are present")
    if technical.get("complete") is not (not gaps):
        raise ValueError("successor observer technical contract is invalid")
    candles = _text_list(technical.get("initial_candle_symbols"), "candle symbols")
    if candles != sorted(_SYMBOLS):
        raise ValueError("successor observer candle coverage is invalid")


def _require_signals(signals: Record) -> None:
    for field in ("eligible_evaluations", "strategy_intents", "routed_actions"):
        _nonnegative_integer(signals.get(field), f"successor {field}")
    if signals.get("routed_actions") != 0:
        raise ValueError("successor observer routed actions are present")


def _status(
    run: Record,
    technical: Record,
    runtime: Record,
    signals: Record,
    timestamp: datetime,
    age: float,
    maximum_age: float,
) -> dict[str, object]:
    return {
        "profile_id": run["profile_id"],
        "profile_fingerprint": run["profile_fingerprint"],
        "base_profile_fingerprint": _BASE_PROFILE,
        "run_fingerprint": run["run_fingerprint"],
        "run_id": run["run_id"],
        "symbols": list(_SYMBOLS),
        "observed_at_utc": timestamp.isoformat(),
        "freshness_status": "fresh" if age <= maximum_age else "stale",
        "age_seconds": age,
        "technical_complete": technical["complete"],
        "technical_gaps": list(technical["technical_gaps"]),
        "provider_symbol_routes": technical["observed_provider_symbols"],
        "poll_cycles": _nonnegative_integer(runtime.get("poll_cycles"), "polls"),
        "degraded_poll_cycles": _nonnegative_integer(
            runtime.get("degraded_poll_cycles"), "degraded polls"
        ),
        "eligible_evaluations": signals["eligible_evaluations"],
        "strategy_intents": signals["strategy_intents"],
        "routed_actions": signals["routed_actions"],
        "live_change_supported": False,
        "automatic_promotion": False,
        "report_only": True,
        "execution_authority": "none",
    }


def _freshness(payload: Record, observed_at: datetime) -> tuple[datetime, float]:
    raw = _text(payload.get("generated_at_utc"), "successor generation time")
    timestamp = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
    age = (observed_at.astimezone(UTC) - timestamp).total_seconds()
    if age < 0.0:
        raise ValueError("successor observer status is from the future")
    return timestamp, age


def _validated_ledger_evidence(value: object) -> dict[str, object]:
    evidence = _mapping(value, "successor observer ledger evidence")
    stable = _nonnegative_integer(evidence.get("stable_bytes"), "stable bytes")
    source = _nonnegative_integer(evidence.get("source_bytes_observed"), "source bytes")
    dropped = _nonnegative_integer(evidence.get("dropped_tail_bytes"), "dropped bytes")
    if evidence.get("bytes") != stable or source - stable != dropped:
        raise ValueError("successor observer ledger byte evidence is invalid")
    if evidence.get("incomplete_tail_dropped") is not (dropped > 0):
        raise ValueError("successor observer ledger tail evidence is invalid")
    if len(_text(evidence.get("sha256"), "ledger sha256")) != 64:
        raise ValueError("successor observer ledger hash is invalid")
    _text(evidence.get("path"), "successor observer ledger path")
    return dict(evidence)


def _raw_evidence(path: Path, raw: bytes) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _text_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    output = [_text(item, label) for item in value]
    if len(output) != len(set(output)):
        raise ValueError(f"{label} must be unique")
    return output


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("successor observer comparison time needs a timezone")


def _require_positive(value: float) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError("successor observer maximum age must be positive and finite")
