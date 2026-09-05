"""Source-bound IO for the live V58 BRENTOIL lifecycle watcher."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path

from hypervector.data.jsonl_prefix import (
    read_jsonl_prefix,
    read_jsonl_verified_prefix,
    require_jsonl_prefix_unchanged,
)
from hypervector.data.oxa_storage import file_evidence
from hypervector.research.hip3_development_provenance import require_unchanged_file
from hypervector.research.v58_brentoil_live_lifecycle import (
    build_v58_brentoil_lifecycle_report,
)

Record = Mapping[str, object]

_PROFILE = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_STRATEGY = "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2"
_SYMBOL = "xyz:BRENTOIL"


def bootstrap_v58_brentoil_preregistration(
    checkpoint: Record,
    venue_preflight: Record,
    *,
    ledger_path: Path,
    config_path: Path,
    prestart_manifest_path: Path,
    generated_at: datetime,
) -> dict[str, object]:
    """Freeze exact open identity and sources after full entry validation."""
    run = _run(checkpoint)
    trade = _open_trade(checkpoint)
    rows, ledger = read_jsonl_prefix(ledger_path, "V58 BRENTOIL asset ledger")
    source_run_id = _text(trade.get("source_run_id"), "source run id")
    runtime_run_id = _text(run.get("run_id"), "runtime run id")
    source_asset = _asset_identity(rows, source_run_id, "source")
    runtime_asset = _asset_identity(rows, runtime_run_id, "runtime")
    stop = _mapping(trade.get("protective_stop"), "protective stop")
    plan = _mapping(trade.get("exit_plan"), "exit plan")
    preregistration = {
        "schema_version": 1,
        "mode": "v58_brentoil_live_lifecycle_preregistration_v1",
        "generated_at_utc": _aware_utc(generated_at).isoformat(),
        "frozen_identity": _frozen_identity(
            run, trade, source_asset, runtime_asset, stop
        ),
        "frozen_exit_contract": _frozen_exit_contract(plan, stop),
        "ledger_prefix": ledger,
        "sources": {
            "config": _file_source(config_path),
            "prestart_manifest": _file_source(prestart_manifest_path),
        },
        "status": "being_tested",
        "contract": _contract(),
    }
    build_v58_brentoil_lifecycle_report(
        preregistration,
        checkpoint,
        venue_preflight,
        rows,
        {**ledger, "frozen_prefix_verified": True},
        generated_at,
    )
    return preregistration


def load_v58_brentoil_lifecycle_cycle(
    preregistration_path: Path,
    *,
    expected_preregistration_sha256: object,
    checkpoint_path: Path,
    venue_path: Path,
    ledger_path: Path,
    generated_at: datetime,
) -> dict[str, object]:
    """Load, authenticate, and reconcile one current lifecycle cycle."""
    prereg, prereg_evidence = _load_json(preregistration_path, "preregistration")
    if prereg_evidence["sha256"] != _sha256_text(
        expected_preregistration_sha256, "preregistration sha256"
    ):
        raise ValueError("V58 BRENTOIL preregistration hash differs")
    sources = _static_sources(prereg)
    prefix = _mapping(prereg.get("ledger_prefix"), "ledger prefix")
    _require_ledger_path(prefix, ledger_path)
    read_jsonl_verified_prefix(
        ledger_path,
        "V58 BRENTOIL authenticated entry ledger",
        length=_positive_int(prefix.get("bytes"), "frozen ledger bytes"),
        expected_sha256=_sha256_text(prefix.get("sha256"), "frozen ledger sha256"),
    )
    rows, ledger = read_jsonl_prefix(ledger_path, "V58 BRENTOIL asset ledger")
    checkpoint, checkpoint_evidence = _load_json(checkpoint_path, "checkpoint")
    venue, venue_evidence = _load_json(venue_path, "venue preflight")
    report = build_v58_brentoil_lifecycle_report(
        prereg,
        checkpoint,
        venue,
        rows,
        {**ledger, "frozen_prefix_verified": True},
        generated_at,
    )
    require_jsonl_prefix_unchanged(ledger_path, ledger, "V58 BRENTOIL asset ledger")
    _recheck_static_sources(sources)
    require_unchanged_file(preregistration_path, prereg_evidence)
    report["source_evidence"] = {
        "preregistration": {
            "path": str(preregistration_path.resolve()),
            **prereg_evidence,
        },
        "checkpoint": {"path": str(checkpoint_path.resolve()), **checkpoint_evidence},
        "venue_preflight": {"path": str(venue_path.resolve()), **venue_evidence},
        "asset_ledger": {**ledger, "frozen_prefix_verified": True},
        **sources,
    }
    return report


def _run(checkpoint: Record) -> Record:
    audit = _mapping(checkpoint.get("audit"), "audit")
    run = _mapping(audit.get("run"), "run")
    if run.get("profile_id") != _PROFILE:
        raise ValueError("V58 BRENTOIL bootstrap profile differs")
    _sha256_text(run.get("profile_fingerprint"), "profile fingerprint")
    _text(run.get("run_id"), "run id")
    return run


def _open_trade(checkpoint: Record) -> Record:
    audit = _mapping(checkpoint.get("audit"), "audit")
    opened = _mapping(audit.get("open_trade_reflections"), "open trades")
    matches = [
        row
        for row in _records(opened.get("trades"), "open trades")
        if row.get("symbol") == _SYMBOL and row.get("strategy_id") == _STRATEGY
    ]
    if len(matches) != 1:
        raise ValueError("V58 BRENTOIL bootstrap requires one open lifecycle")
    return matches[0]


def _asset_identity(rows: Sequence[Record], run_id: str, label: str) -> tuple[str, str]:
    identities = {
        (
            _text(row.get("profile_id"), "asset profile id"),
            _sha256_text(row.get("profile_fingerprint"), "asset fingerprint"),
        )
        for row in rows
        if row.get("run_id") == run_id
    }
    if len(identities) != 1:
        raise ValueError(f"V58 BRENTOIL {label} asset ledger identity is ambiguous")
    return identities.pop()


def _frozen_identity(
    run: Record,
    trade: Record,
    source_asset: tuple[str, str],
    runtime_asset: tuple[str, str],
    stop: Record,
) -> dict[str, object]:
    lifecycle = _text(trade.get("lifecycle_id"), "lifecycle id")
    prefix, separator, oid = lifecycle.rpartition(":")
    if prefix != _SYMBOL or separator != ":" or not oid.isdigit():
        raise ValueError("V58 BRENTOIL bootstrap lifecycle differs")
    return {
        "profile_id": run["profile_id"],
        "profile_fingerprint": run["profile_fingerprint"],
        "run_id": run["run_id"],
        "source_run_id": _text(trade.get("source_run_id"), "source run id"),
        "asset_profile_id": source_asset[0],
        "asset_profile_fingerprint": source_asset[1],
        "runtime_asset_profile_id": runtime_asset[0],
        "runtime_asset_profile_fingerprint": runtime_asset[1],
        "strategy_id": _STRATEGY,
        "route": f"{_STRATEGY}|{_SYMBOL}",
        "symbol": _SYMBOL,
        "side": "long",
        "lifecycle_id": lifecycle,
        "entry_oid": int(oid),
        "protective_stop_oid": _positive_int(stop.get("oid"), "stop oid"),
    }


def _frozen_exit_contract(plan: Record, stop: Record) -> dict[str, object]:
    return {
        "protective_stop_trigger_price": _positive_number(
            stop.get("trigger_price"), "stop price"
        ),
        "maximum_hold_seconds": _positive_int(
            plan.get("maximum_hold_seconds"), "maximum hold"
        ),
        "profit_lock_policy": _text(plan.get("profit_lock_policy"), "profit lock"),
        "provider_recipe_exit_policy": _text(
            plan.get("provider_recipe_exit_policy"), "recipe exit policy"
        ),
        "opposite_intent_exit_scope": _text(
            plan.get("opposite_intent_exit_scope"), "opposite exit scope"
        ),
    }


def _static_sources(preregistration: Record) -> dict[str, dict[str, object]]:
    declared = _mapping(preregistration.get("sources"), "static sources")
    output: dict[str, dict[str, object]] = {}
    for key in ("config", "prestart_manifest"):
        source = _mapping(declared.get(key), key)
        path = Path(_text(source.get("path"), f"{key} path"))
        current = _file_source(path)
        if current != dict(source):
            raise ValueError(f"V58 BRENTOIL static source changed: {key}")
        output[key] = current
    return output


def _recheck_static_sources(sources: Record) -> None:
    for key in ("config", "prestart_manifest"):
        source = _mapping(sources.get(key), key)
        require_unchanged_file(Path(_text(source.get("path"), f"{key} path")), source)


def _require_ledger_path(prefix: Record, path: Path) -> None:
    if Path(_text(prefix.get("path"), "ledger path")).resolve() != path.resolve():
        raise ValueError("V58 BRENTOIL ledger path differs")


def _file_source(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _load_json(path: Path, label: str) -> tuple[Record, dict[str, object]]:
    raw = path.read_bytes()
    evidence = {"bytes": len(raw), "sha256": sha256(raw).hexdigest()}
    return _mapping(json.loads(raw), label), evidence


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "performance_gate": False,
        "runtime_strategy_changed": False,
    }


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("V58 BRENTOIL generation time must be timezone-aware")
    return value.astimezone(UTC)


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"V58 BRENTOIL {label} must be a list")
    return tuple(_mapping(row, label) for row in value)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"V58 BRENTOIL {label} must be a mapping")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"V58 BRENTOIL {label} must be non-empty text")
    return value


def _sha256_text(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise ValueError(f"V58 BRENTOIL {label} must be lowercase sha256")
    return text


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"V58 BRENTOIL {label} must be a positive integer")
    return value


def _positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"V58 BRENTOIL {label} must be numeric")
    output = float(value)
    if not output > 0.0:
        raise ValueError(f"V58 BRENTOIL {label} must be positive")
    return output
