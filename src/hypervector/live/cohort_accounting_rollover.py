"""Fail-closed manifest for a recoverable cohort accounting epoch."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path

from hypervector.live.cohort_accounting_continuation import (
    validate_accounting_continuation,
)
from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.research.cohort_live_portfolio_archive import CohortAccountingEpoch

# Profile fingerprints whose start must carry a verified clean accounting
# epoch (--accounting-epoch-bundle). None is registered today.
_CLEAN_ACCOUNTING_REQUIRED_PROFILE_FINGERPRINTS: frozenset[str] = frozenset()


def load_required_accounting_epoch(
    bundle: Path | str | None,
    successor: MultiAssetLiveConfig,
) -> CohortAccountingEpoch | None:
    """Require a verified clean epoch for profiles that declare the rollover."""
    required = (
        successor.profile_fingerprint in _CLEAN_ACCOUNTING_REQUIRED_PROFILE_FINGERPRINTS
    )
    if bundle is None:
        if required:
            raise ValueError(
                f"profile {successor.profile_id} requires --accounting-epoch-bundle"
            )
        return None
    return load_accounting_rollover_manifest(bundle, successor)


def load_accounting_rollover_manifest(
    bundle: Path | str,
    successor: MultiAssetLiveConfig,
) -> CohortAccountingEpoch:
    """Verify one immutable bundle and return its exact reporting epoch."""
    root = Path(bundle)
    document = _load_manifest(root / "manifest.json")
    _validate_loaded_contract(document)
    successor_identity = _mapping(
        document.get("successor_identity"), "successor identity"
    )
    _require_identity(successor_identity, successor, "successor")
    epoch = _loaded_epoch(document.get("accounting_epoch"))
    if epoch.profile_fingerprint != successor.profile_fingerprint:
        raise ValueError("accounting rollover epoch profile differs from successor")
    if "continuation" in document:
        validate_accounting_continuation(root, document, epoch)
    else:
        _validate_loaded_acceptance(document.get("acceptance"))
    _validate_preserved_evidence(root, document.get("preserved_prior_history"))
    return epoch


def _load_manifest(path: Path) -> dict[str, object]:
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"accounting rollover manifest cannot be read: {path}"
        ) from exc
    if not isinstance(decoded, dict):
        raise ValueError("accounting rollover manifest must be an object")
    return decoded


def _validate_loaded_contract(document: Mapping[str, object]) -> None:
    expected = {
        "schema_version": 1,
        "mode": "cohort_accounting_epoch_rollover_v1",
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "rollover_authority": "prepared_not_armed",
    }
    if any(document.get(key) != value for key, value in expected.items()):
        raise ValueError("accounting rollover manifest contract differs")
    contract = _mapping(document.get("contract"), "contract")
    required = {
        "report_only": True,
        "automatic_live_start": False,
        "live_risk_flags_required_separately": True,
        "prior_history_preserved": True,
        "prior_history_excluded_from_new_epoch_metrics": True,
        "current_venue_equity_retained": True,
    }
    if any(contract.get(key) != value for key, value in required.items()):
        raise ValueError("accounting rollover report-only contract differs")


def _loaded_epoch(value: object) -> CohortAccountingEpoch:
    epoch = _mapping(value, "accounting epoch")
    included = epoch.get("included_profile_fingerprints", [])
    profiles = tuple(
        _text(item, "accounting epoch included profile")
        for item in _sequence(included, "accounting epoch included profiles")
    )
    return CohortAccountingEpoch(
        _text(epoch.get("epoch_id"), "accounting epoch id"),
        _text(epoch.get("profile_fingerprint"), "accounting epoch profile"),
        _integer(epoch.get("start_venue_timestamp_ms"), "accounting epoch start"),
        included_profile_fingerprints=profiles,
    )


def _validate_loaded_acceptance(value: object) -> None:
    acceptance = _mapping(value, "acceptance")
    for key in (
        "all_time_closed_trades",
        "current_run_closed_trades",
        "open_lifecycles",
    ):
        if acceptance.get(key) != 0:
            raise ValueError(f"accounting rollover acceptance {key} is not zero")
    _positive_number(acceptance.get("venue_equity_usd"), "venue equity")
    if "sizing_reference_equity_usd" in acceptance:
        _positive_number(
            acceptance.get("sizing_reference_equity_usd"),
            "sizing reference equity",
        )


def _validate_preserved_evidence(root: Path, value: object) -> None:
    preserved = _mapping(value, "preserved prior history")
    if preserved.get("history_deleted") is not False:
        raise ValueError("accounting rollover history deletion flag differs")
    if preserved.get("history_rewritten") is not False:
        raise ValueError("accounting rollover history rewrite flag differs")
    _verify_internal_evidence(
        root,
        preserved.get("final_checkpoint"),
        "final_checkpoint.json",
        "final checkpoint",
    )
    _verify_internal_evidence(
        root,
        preserved.get("final_preflight"),
        "final_preflight.json",
        "final preflight",
    )
    backup = _mapping(preserved.get("prestart_backup"), "prestart backup")
    backup_path = Path(_text(backup.get("path"), "prestart backup path"))
    if not backup_path.is_absolute():
        raise ValueError("accounting rollover prestart backup path must be absolute")
    _verify_file_evidence(backup_path, backup, "prestart backup")


def _verify_internal_evidence(
    root: Path,
    value: object,
    expected_name: str,
    label: str,
) -> None:
    evidence = _mapping(value, label)
    if evidence.get("path") != expected_name:
        raise ValueError(f"accounting rollover {label} path differs")
    _verify_file_evidence(root / expected_name, evidence, label)


def _verify_file_evidence(
    path: Path,
    evidence: Mapping[str, object],
    label: str,
) -> None:
    if not path.is_file():
        raise ValueError(f"accounting rollover {label} is missing: {path}")
    raw = path.read_bytes()
    if evidence.get("bytes") != len(raw):
        raise ValueError(f"accounting rollover {label} evidence differs")
    if evidence.get("sha256") != hashlib.sha256(raw).hexdigest():
        raise ValueError(f"accounting rollover {label} evidence differs")


def build_accounting_rollover_manifest(
    prior: MultiAssetLiveConfig,
    successor: MultiAssetLiveConfig,
    checkpoint: Mapping[str, object],
    preflight: Mapping[str, object],
    backup_manifest: Mapping[str, object],
    *,
    epoch_id: str,
    backup_bundle_evidence: Mapping[str, object],
    checkpoint_evidence: Mapping[str, object],
    preflight_evidence: Mapping[str, object],
    now: datetime,
) -> dict[str, object]:
    """Build a no-authority epoch only from flat, preserved exact identities."""
    boundary = _aware_utc(now)
    prior_run_id = _validate_checkpoint(checkpoint, prior, boundary)
    venue_equity, sizing_reference_equity = _validate_preflight(
        preflight, prior, successor, boundary
    )
    _validate_backup(backup_manifest, prior, successor, prior_run_id)
    epoch = CohortAccountingEpoch(
        epoch_id,
        successor.profile_fingerprint,
        int(boundary.timestamp() * 1_000),
    )
    return _rollover_document(
        prior,
        successor,
        prior_run_id,
        boundary,
        epoch,
        venue_equity,
        sizing_reference_equity,
        backup_bundle_evidence,
        checkpoint_evidence,
        preflight_evidence,
    )


def _rollover_document(
    prior: MultiAssetLiveConfig,
    successor: MultiAssetLiveConfig,
    prior_run_id: str,
    boundary: datetime,
    epoch: CohortAccountingEpoch,
    venue_equity: float,
    sizing_reference_equity: float,
    backup_bundle_evidence: Mapping[str, object],
    checkpoint_evidence: Mapping[str, object],
    preflight_evidence: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "cohort_accounting_epoch_rollover_v1",
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "rollover_authority": "prepared_not_armed",
        "created_at_utc": boundary.isoformat(),
        "prior_identity": _profile_identity(prior, prior_run_id),
        "successor_identity": _profile_identity(successor, None),
        "accounting_epoch": epoch.to_dict(),
        "acceptance": {
            "all_time_closed_trades": 0,
            "current_run_closed_trades": 0,
            "open_lifecycles": 0,
            "venue_equity_usd": venue_equity,
            "sizing_reference_equity_usd": sizing_reference_equity,
        },
        "preserved_prior_history": {
            "prestart_backup": _evidence(backup_bundle_evidence, "prestart backup"),
            "final_checkpoint": _evidence(checkpoint_evidence, "checkpoint"),
            "final_preflight": _evidence(preflight_evidence, "preflight"),
            "history_deleted": False,
            "history_rewritten": False,
        },
        "contract": _contract(),
    }


def _validate_checkpoint(
    checkpoint: Mapping[str, object],
    prior: MultiAssetLiveConfig,
    boundary: datetime,
) -> str:
    generated = _timestamp(checkpoint.get("generated_at_utc"), "checkpoint generated")
    if generated > boundary:
        raise ValueError("accounting rollover checkpoint is from the future")
    audit = _mapping(checkpoint.get("audit"), "checkpoint audit")
    run = _mapping(audit.get("run"), "checkpoint run")
    _require_identity(run, prior, "checkpoint")
    reflections = _mapping(audit.get("open_trade_reflections"), "open reflections")
    if _integer(reflections.get("open_lifecycles"), "open lifecycles") != 0:
        raise ValueError("accounting rollover checkpoint has open lifecycles")
    if _sequence(reflections.get("trades"), "open reflection trades"):
        raise ValueError("accounting rollover checkpoint has open trade rows")
    health = _mapping(audit.get("health"), "checkpoint health")
    _validate_flat_assets(_mapping(health.get("assets"), "checkpoint assets"), prior)
    return _text(run.get("run_id"), "checkpoint run id")


def _validate_flat_assets(
    rows: Mapping[str, object], prior: MultiAssetLiveConfig
) -> None:
    if set(rows) != set(prior.symbols):
        raise ValueError("accounting rollover checkpoint asset set differs")
    for symbol, value in rows.items():
        row = _mapping(value, f"checkpoint asset {symbol}")
        flat = row.get("final_state") == "FLAT"
        size = _number(row.get("position_size_signed"), f"{symbol} position")
        orders = _sequence(row.get("open_order_ids"), f"{symbol} orders")
        if not flat or not math.isclose(size, 0.0) or orders:
            raise ValueError(f"accounting rollover checkpoint is not flat: {symbol}")


def _validate_preflight(
    preflight: Mapping[str, object],
    prior: MultiAssetLiveConfig,
    successor: MultiAssetLiveConfig,
    boundary: datetime,
) -> tuple[float, float]:
    observed = _timestamp(preflight.get("observed_at_utc"), "preflight observed")
    if observed > boundary:
        raise ValueError("accounting rollover preflight is from the future")
    identity = _mapping(preflight.get("identity"), "preflight identity")
    _require_prefixed_identity(identity, prior, "active")
    _require_prefixed_identity(identity, successor, "candidate")
    portfolio = _mapping(preflight.get("portfolio"), "preflight portfolio")
    _require_flat_preflight(portfolio)
    venue_equity = _observed_venue_equity(preflight.get("assets"), successor)
    sizing_reference = _positive_number(
        portfolio.get("sizing_reference_equity_usd"), "sizing reference equity"
    )
    return venue_equity, sizing_reference


def _observed_venue_equity(value: object, successor: MultiAssetLiveConfig) -> float:
    assets = _sequence(value, "preflight assets")
    equity_by_symbol: dict[str, float] = {}
    for value in assets:
        asset = _mapping(value, "preflight asset")
        symbol = _text(asset.get("symbol"), "preflight asset symbol")
        if symbol in equity_by_symbol:
            raise ValueError("accounting rollover preflight asset is duplicated")
        sizing = _mapping(asset.get("sizing"), f"preflight {symbol} sizing")
        equity_by_symbol[symbol] = _positive_number(
            sizing.get("actual_account_value_usd"),
            f"preflight {symbol} observed venue equity",
        )
    if set(equity_by_symbol) != set(successor.symbols):
        raise ValueError("accounting rollover preflight asset set differs")
    observed = next(iter(equity_by_symbol.values()))
    if any(
        not math.isclose(equity, observed, rel_tol=0.0, abs_tol=1e-9)
        for equity in equity_by_symbol.values()
    ):
        raise ValueError("accounting rollover observed venue equity differs by asset")
    return observed


def _require_flat_preflight(portfolio: Mapping[str, object]) -> None:
    exact = {
        "flat_no_orders": True,
        "ledger_reconciled": True,
        "open_positions": 0,
        "open_orders": 0,
        "technically_ready_for_profile_transition": True,
    }
    if any(portfolio.get(key) != value for key, value in exact.items()):
        raise ValueError("accounting rollover preflight is not flat and order-free")
    blockers = _sequence(
        portfolio.get("transition_blocking_assets"), "transition blockers"
    )
    if blockers:
        raise ValueError("accounting rollover preflight has transition blockers")


def _validate_backup(
    manifest: Mapping[str, object],
    prior: MultiAssetLiveConfig,
    successor: MultiAssetLiveConfig,
    prior_run_id: str,
) -> None:
    if manifest.get("schema_version") != 1:
        raise ValueError("accounting rollover backup schema is unsupported")
    if manifest.get("bundle_type") != "cohort_prestart_backup":
        raise ValueError("accounting rollover backup type differs")
    target = _mapping(manifest.get("target_identity"), "backup target identity")
    previous = _mapping(manifest.get("previous_identity"), "backup previous identity")
    _require_identity(target, successor, "backup target")
    _require_identity(previous, prior, "backup previous")
    if previous.get("run_id") != prior_run_id:
        raise ValueError("accounting rollover backup previous run differs")


def _require_identity(
    values: Mapping[str, object], config: MultiAssetLiveConfig, label: str
) -> None:
    expected = {
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
    }
    if any(values.get(key) != value for key, value in expected.items()):
        raise ValueError(f"accounting rollover {label} identity differs")


def _require_prefixed_identity(
    values: Mapping[str, object], config: MultiAssetLiveConfig, prefix: str
) -> None:
    expected = {
        f"{prefix}_profile_id": config.profile_id,
        f"{prefix}_profile_fingerprint": config.profile_fingerprint,
    }
    if any(values.get(key) != value for key, value in expected.items()):
        raise ValueError(f"accounting rollover preflight {prefix} identity differs")


def _profile_identity(
    config: MultiAssetLiveConfig, run_id: str | None
) -> dict[str, object]:
    return {
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
        "source_path": str(config.source_path),
        "run_id": run_id,
    }


def _evidence(value: Mapping[str, object], label: str) -> dict[str, object]:
    path = _text(value.get("path"), f"{label} path")
    sha256 = _text(value.get("sha256"), f"{label} sha256")
    size = _integer(value.get("bytes"), f"{label} bytes")
    if len(sha256) != 64 or any(char not in "0123456789abcdef" for char in sha256):
        raise ValueError(f"accounting rollover {label} sha256 is invalid")
    if size <= 0:
        raise ValueError(f"accounting rollover {label} bytes must be positive")
    return {"path": path, "sha256": sha256, "bytes": size}


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "automatic_live_start": False,
        "live_risk_flags_required_separately": True,
        "prior_history_preserved": True,
        "prior_history_excluded_from_new_epoch_metrics": True,
        "current_venue_equity_retained": True,
    }


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("accounting rollover clock must be timezone-aware")
    return value.astimezone(UTC)


def _timestamp(value: object, label: str) -> datetime:
    text = _text(value, label)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"accounting rollover {label} must be timezone-aware")
    return parsed.astimezone(UTC)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"accounting rollover {label} must be an object")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ValueError(f"accounting rollover {label} must be a list")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"accounting rollover {label} must be non-empty text")
    return value.strip()


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"accounting rollover {label} must be non-negative integer")
    return value


def _positive_number(value: object, label: str) -> float:
    number = _number(value, label)
    if number <= 0.0:
        raise ValueError(f"accounting rollover {label} must be positive")
    return number


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"accounting rollover {label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"accounting rollover {label} must be finite")
    return number
