"""Validated accounting-epoch continuity across one exact profile transition."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from hypervector.research.cohort_live_portfolio_archive import CohortAccountingEpoch

_ROLLOVER_MODE = "cohort_accounting_epoch_rollover_v1"
_PARENT_MANIFEST_NAME = "parent_accounting_epoch_manifest.json"


def build_accounting_continuation_manifest(
    rollover: Mapping[str, object],
    parent: Mapping[str, object],
    checkpoint: Mapping[str, object],
    *,
    parent_manifest_evidence: Mapping[str, object],
) -> dict[str, object]:
    """Continue a verified single-profile epoch across one adjacent successor."""
    _require_rollover(rollover, "rollover")
    _require_rollover(parent, "parent")
    prior_identity = _mapping(rollover.get("prior_identity"), "prior identity")
    successor_identity = _mapping(
        rollover.get("successor_identity"), "successor identity"
    )
    parent_successor = _mapping(
        parent.get("successor_identity"), "parent successor identity"
    )
    if not _same_profile(prior_identity, parent_successor):
        raise ValueError("accounting continuation parent successor differs")
    parent_epoch = _parent_epoch(parent, parent_successor)
    successor_fingerprint = _text(
        successor_identity.get("profile_fingerprint"), "successor fingerprint"
    )
    parent_profiles = parent_epoch.effective_profile_fingerprints
    if successor_fingerprint in parent_profiles:
        raise ValueError("accounting continuation successor is already in parent epoch")
    inherited = _inherited_closed_trades(checkpoint, parent_epoch)
    evidence = _validated_evidence(parent_manifest_evidence)
    return _continued_document(
        rollover,
        parent_epoch,
        parent_successor,
        successor_fingerprint,
        inherited,
        evidence,
    )


def _continued_document(
    rollover: Mapping[str, object],
    parent_epoch: CohortAccountingEpoch,
    parent_successor: Mapping[str, object],
    successor_fingerprint: str,
    inherited: int,
    evidence: Mapping[str, object],
) -> dict[str, object]:
    result = deepcopy(dict(rollover))
    epoch_id = _text(
        _mapping(rollover.get("accounting_epoch"), "rollover accounting epoch").get(
            "epoch_id"
        ),
        "rollover accounting epoch id",
    )
    epoch = CohortAccountingEpoch(
        epoch_id,
        successor_fingerprint,
        parent_epoch.start_venue_timestamp_ms,
        included_profile_fingerprints=(
            *parent_epoch.effective_profile_fingerprints,
            successor_fingerprint,
        ),
    )
    base_acceptance = _mapping(rollover.get("acceptance"), "rollover acceptance")
    result["accounting_epoch"] = epoch.to_dict()
    result["acceptance"] = {
        "inherited_closed_trades": inherited,
        "successor_closed_trades_at_boundary": 0,
        "open_lifecycles": 0,
        "venue_equity_usd": _positive_number(
            base_acceptance.get("venue_equity_usd"), "venue equity"
        ),
        "sizing_reference_equity_usd": _positive_number(
            base_acceptance.get("sizing_reference_equity_usd"),
            "sizing reference equity",
        ),
    }
    contract = dict(_mapping(result.get("contract"), "rollover contract"))
    contract["profile_lineage_continued"] = True
    result["contract"] = contract
    result["continuation"] = {
        "parent_accounting_epoch": parent_epoch.to_dict(),
        "parent_successor_identity": dict(parent_successor),
        "parent_manifest": evidence,
    }
    return result


def validate_accounting_continuation(
    root: Path,
    document: Mapping[str, object],
    epoch: CohortAccountingEpoch,
) -> None:
    """Verify internal parent evidence and the exact adjacent profile lineage."""
    continuation = _mapping(document.get("continuation"), "continuation")
    evidence = _mapping(continuation.get("parent_manifest"), "parent manifest")
    parent = _load_verified_parent(root, evidence)
    _require_rollover(parent, "parent")
    parent_epoch_raw = _mapping(
        continuation.get("parent_accounting_epoch"), "parent accounting epoch"
    )
    if parent.get("accounting_epoch") != parent_epoch_raw:
        raise ValueError("accounting continuation parent accounting epoch differs")
    parent_successor = _mapping(
        continuation.get("parent_successor_identity"), "parent successor identity"
    )
    if parent.get("successor_identity") != parent_successor:
        raise ValueError("accounting continuation parent successor differs")
    prior = _mapping(document.get("prior_identity"), "prior identity")
    successor = _mapping(document.get("successor_identity"), "successor identity")
    if not _same_profile(prior, parent_successor):
        raise ValueError("accounting continuation prior profile differs")
    parent_epoch = _parent_epoch(parent, parent_successor)
    successor_fingerprint = _text(
        successor.get("profile_fingerprint"), "successor fingerprint"
    )
    expected_profiles = (
        *parent_epoch.effective_profile_fingerprints,
        successor_fingerprint,
    )
    if (
        epoch.profile_fingerprint != successor_fingerprint
        or epoch.start_venue_timestamp_ms != parent_epoch.start_venue_timestamp_ms
        or epoch.included_profile_fingerprints != expected_profiles
    ):
        raise ValueError("accounting continuation epoch lineage differs")
    contract = _mapping(document.get("contract"), "contract")
    if contract.get("profile_lineage_continued") is not True:
        raise ValueError("accounting continuation contract differs")
    _validate_acceptance(document.get("acceptance"))


def _require_rollover(value: Mapping[str, object], label: str) -> None:
    if value.get("schema_version") != 1 or value.get("mode") != _ROLLOVER_MODE:
        raise ValueError(f"accounting continuation {label} contract differs")


def _parent_epoch(
    parent: Mapping[str, object],
    parent_successor: Mapping[str, object],
) -> CohortAccountingEpoch:
    raw = _mapping(parent.get("accounting_epoch"), "parent accounting epoch")
    included_raw = raw.get("included_profile_fingerprints")
    if included_raw is None:
        included: tuple[str, ...] = ()
    elif isinstance(included_raw, list):
        included = tuple(
            _text(value, "parent accounting epoch included profile")
            for value in included_raw
        )
    else:
        raise ValueError("accounting continuation parent accounting epoch differs")
    try:
        epoch = CohortAccountingEpoch(
            _text(raw.get("epoch_id"), "parent accounting epoch id"),
            _text(
                raw.get("profile_fingerprint"),
                "parent accounting epoch profile",
            ),
            _nonnegative_integer(
                raw.get("start_venue_timestamp_ms"),
                "parent accounting epoch start",
            ),
            included_profile_fingerprints=included,
        )
    except ValueError as exc:
        raise ValueError(
            "accounting continuation parent accounting epoch differs"
        ) from exc
    if (
        epoch.profile_fingerprint != parent_successor.get("profile_fingerprint")
        or epoch.effective_profile_fingerprints[-1] != epoch.profile_fingerprint
    ):
        raise ValueError("accounting continuation parent accounting epoch differs")
    return epoch


def _inherited_closed_trades(
    checkpoint: Mapping[str, object], parent_epoch: CohortAccountingEpoch
) -> int:
    audit = _mapping(checkpoint.get("audit"), "checkpoint audit")
    reflections = _mapping(
        audit.get("open_trade_reflections"), "checkpoint open reflections"
    )
    if (
        _nonnegative_integer(
            reflections.get("open_lifecycles"), "checkpoint open lifecycles"
        )
        != 0
        or reflections.get("trades") != []
    ):
        raise ValueError("accounting continuation checkpoint is not flat")
    archive = _mapping(audit.get("portfolio_archive"), "checkpoint portfolio archive")
    if archive.get("accounting_epoch") != parent_epoch.to_dict():
        raise ValueError("accounting continuation checkpoint accounting epoch differs")
    performance = _mapping(archive.get("performance"), "checkpoint performance")
    total = _mapping(performance.get("total"), "checkpoint total performance")
    return _nonnegative_integer(
        total.get("closed_trades"), "checkpoint inherited closed trades"
    )


def _validated_evidence(value: Mapping[str, object]) -> dict[str, object]:
    path = _text(value.get("path"), "parent manifest path")
    digest = _text(value.get("sha256"), "parent manifest sha256")
    size = _nonnegative_integer(value.get("bytes"), "parent manifest bytes")
    if (
        path != _PARENT_MANIFEST_NAME
        or size <= 0
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError("accounting continuation parent manifest evidence is invalid")
    return {"path": path, "sha256": digest, "bytes": size}


def _load_verified_parent(
    root: Path, evidence: Mapping[str, object]
) -> Mapping[str, object]:
    validated = _validated_evidence(evidence)
    path = root / _PARENT_MANIFEST_NAME
    raw = path.read_bytes()
    if (
        len(raw) != validated["bytes"]
        or hashlib.sha256(raw).hexdigest() != validated["sha256"]
    ):
        raise ValueError("parent accounting epoch evidence differs")
    decoded = json.loads(raw)
    return _mapping(decoded, "parent accounting epoch manifest")


def _validate_acceptance(value: object) -> None:
    acceptance = _mapping(value, "acceptance")
    _nonnegative_integer(
        acceptance.get("inherited_closed_trades"), "inherited closed trades"
    )
    if (
        acceptance.get("successor_closed_trades_at_boundary") != 0
        or acceptance.get("open_lifecycles") != 0
    ):
        raise ValueError("accounting continuation acceptance differs")
    _positive_number(acceptance.get("venue_equity_usd"), "venue equity")
    _positive_number(
        acceptance.get("sizing_reference_equity_usd"), "sizing reference equity"
    )


def _same_profile(left: Mapping[str, object], right: Mapping[str, object]) -> bool:
    return all(
        left.get(key) == right.get(key) for key in ("profile_id", "profile_fingerprint")
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"accounting continuation {label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"accounting continuation {label} must be non-empty text")
    return value.strip()


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"accounting continuation {label} must be nonnegative")
    return value


def _positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"accounting continuation {label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"accounting continuation {label} must be positive")
    return result
