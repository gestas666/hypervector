"""Exact identity snapshots for versioned candidate acceptance."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from hashlib import sha256
from pathlib import Path

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.research.candidate_acceptance import CandidateAcceptanceSpec
from hypervector.research.cohort_live_audit_values import (
    mapping,
    mapping_list,
    nonnegative_int,
    number,
    text,
    text_list,
)

Record = Mapping[str, object]


def build_candidate_acceptance_snapshot(
    checkpoint: Record,
    journal: Record,
    candidate_path: Path,
    *,
    spec: CandidateAcceptanceSpec,
) -> dict[str, object]:
    """Return a report-only snapshot bound to one candidate identity."""
    candidate = load_multi_asset_live_config(candidate_path, mode="observe")
    observed, executable, observe_only = _validate_candidate(candidate, spec)
    _validate_journal(journal, candidate_path, spec)
    contract = _checkpoint_contract(checkpoint)
    audit = mapping(checkpoint.get("audit"), "checkpoint audit")
    run = _validate_run(audit, candidate, executable, observe_only, spec)
    return {
        "schema_version": spec.snapshot_schema,
        "phase": spec.phase,
        "contract": contract,
        "source_checkpoint_generated_at_utc": text(
            checkpoint.get("generated_at_utc"), "checkpoint generation time"
        ),
        "source_run": run,
        "candidate": _candidate_identity(candidate, observed, executable),
        "live_state": _live_state(checkpoint, audit),
    }


def _validate_candidate(
    candidate: MultiAssetLiveConfig,
    spec: CandidateAcceptanceSpec,
) -> tuple[set[str], set[str], set[str]]:
    if candidate.profile_id != spec.profile_id:
        raise ValueError(
            f"candidate config is not the exact {spec.version_label} profile"
        )
    if len(candidate.assets) != 9 or candidate.maximum_positions != 9:
        raise ValueError(
            f"{spec.version_label} candidate must retain nine-asset capacity"
        )
    observed = _route_strings(
        (provider.strategy_id, symbol)
        for provider in candidate.providers
        for symbol in provider.symbols
    )
    executable = _route_strings(candidate.executable_provider_symbols)
    observe_only = observed - executable
    if (
        len(executable) != spec.executable_routes
        or len(observe_only) != spec.observe_only_routes
    ):
        raise ValueError(f"{spec.version_label} candidate route authority is not exact")
    if not _all_provider_sides_bidirectional(candidate):
        raise ValueError(
            f"{spec.version_label} candidate observation is not bidirectional"
        )
    return observed, executable, observe_only


def _validate_journal(
    journal: Record,
    candidate_path: Path,
    spec: CandidateAcceptanceSpec,
) -> None:
    expected = {
        "hypothesis_id": "hip3-route-authority-pruning",
        "revision_number": spec.journal_revision,
        "status": "candidate",
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }
    for field, value in expected.items():
        if journal.get(field) != value:
            raise ValueError(f"{spec.version_label} journal has invalid {field}")
    rows = [
        row
        for row in mapping_list(journal.get("evidence"), "journal evidence")
        if row.get("role") == spec.candidate_evidence_role
    ]
    if len(rows) != 1:
        raise ValueError(
            f"{spec.version_label} journal must identify one exact candidate"
        )
    content = candidate_path.read_bytes()
    if rows[0].get("bytes") != len(content):
        raise ValueError(
            f"{spec.version_label} candidate config byte count does not match journal"
        )
    if rows[0].get("sha256") != sha256(content).hexdigest():
        raise ValueError(
            f"{spec.version_label} candidate config SHA-256 does not match journal"
        )


def _checkpoint_contract(checkpoint: Record) -> dict[str, object]:
    source = mapping(checkpoint.get("checkpoint_contract"), "checkpoint contract")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
    }
    for field, value in expected.items():
        if source.get(field) != value:
            raise ValueError(f"checkpoint has invalid {field}")
    return {**expected, "automatic_transition": False}


def _validate_run(
    audit: Record,
    candidate: MultiAssetLiveConfig,
    executable: set[str],
    observe_only: set[str],
    spec: CandidateAcceptanceSpec,
) -> dict[str, str]:
    run = mapping(audit.get("run"), "checkpoint run")
    identity = {
        field: text(run.get(field), f"run {field}")
        for field in ("run_id", "profile_id", "profile_fingerprint")
    }
    if (
        identity["profile_id"] != candidate.profile_id
        or identity["profile_fingerprint"] != candidate.profile_fingerprint
    ):
        raise ValueError(
            f"{spec.version_label} run profile identity does not match candidate"
        )
    run_executable = set(
        text_list(run.get("executable_provider_symbols"), "executable routes")
    )
    run_observe = set(
        text_list(run.get("observe_only_provider_symbols"), "observe-only routes")
    )
    if run_executable != executable:
        raise ValueError(
            f"{spec.version_label} executable route scope does not match config"
        )
    if run_observe != observe_only:
        raise ValueError(
            f"{spec.version_label} observe-only route scope does not match config"
        )
    return identity


def _candidate_identity(
    candidate: MultiAssetLiveConfig,
    observed: set[str],
    executable: set[str],
) -> dict[str, object]:
    return {
        "profile_id": candidate.profile_id,
        "profile_fingerprint": candidate.profile_fingerprint,
        "maximum_positions": candidate.maximum_positions,
        "execution_scope": sorted(executable),
        "observe_only_scope": sorted(observed - executable),
        "both_directions": True,
    }


def _live_state(checkpoint: Record, audit: Record) -> dict[str, object]:
    health = mapping(audit.get("health"), "audit health")
    assets = mapping(health.get("assets"), "asset health")
    positions = [
        _open_position(symbol, mapping(asset, f"asset {symbol}"))
        for symbol, asset in sorted(assets.items())
        if mapping(asset, f"asset {symbol}").get("final_state") == "OPEN"
    ]
    return {
        "mode": text(checkpoint.get("mode"), "checkpoint mode"),
        "faults": nonnegative_int(health.get("faults"), "fault count"),
        "open_positions": positions,
        "all_open_positions_protected": all(
            position["protected_if_open"] is True for position in positions
        ),
        "execution": dict(mapping(audit.get("execution"), "audit execution")),
        "portfolio": dict(mapping(audit.get("portfolio"), "audit portfolio")),
    }


def _open_position(symbol: str, asset: Record) -> dict[str, object]:
    protected = asset.get("protected_if_open")
    if not isinstance(protected, bool):
        raise ValueError(f"{symbol} protection state must be boolean")
    return {
        "symbol": symbol,
        "position_size_signed": number(
            asset.get("position_size_signed"), f"{symbol} position size"
        ),
        "protected_if_open": protected,
        "stop_oid": asset.get("stop_oid"),
        "open_order_ids": asset.get("open_order_ids"),
    }


def _route_strings(routes: Iterable[tuple[str, str]]) -> set[str]:
    return {f"{provider}|{symbol}" for provider, symbol in routes}


def _all_provider_sides_bidirectional(candidate: MultiAssetLiveConfig) -> bool:
    return all(
        set(provider.sides) == {"long", "short"} for provider in candidate.providers
    )
