"""Independent native reports sharing an existing observer's external evidence."""

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hypervector.live.cohort_monitor_identity import (
    checkpoint_identity,
    fresh_checkpoint_document,
)
from hypervector.live.cohort_checkpoint_identity import require_checkpoint_accounting_epoch
from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.cohort_live_audit_values import mapping, text
from hypervector.research.cohort_live_checkpoint import publish_live_checkpoint
from hypervector.research.cohort_live_portfolio_archive import CohortAccountingEpoch

SOURCE_MAXIMUM_AGE_SECONDS = 90.0


def publish_independent_checkpoint(
    *,
    source_path: Path,
    destination: Path,
    config: MultiAssetLiveConfig,
    run_id: str,
    accounting_epoch: CohortAccountingEpoch | None = None,
) -> dict[str, object]:
    """Rebuild exact history without network, database writes or source replacement."""
    if source_path.resolve() == destination.resolve():
        raise ValueError("independent checkpoint must not replace its shared source")
    source = _shared_source(source_path, config, run_id, accounting_epoch)
    source_audit = mapping(source.get("audit"), "shared audit")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".projection-", dir=destination.parent) as temporary:
        result = publish_live_checkpoint(
            config.cohort_ledger.parent, Path(temporary) / "checkpoint.json",
            run_id=run_id, config_path=config.source_path, current_run_only=True,
            venue_portfolio=_optional_mapping(source, "venue_portfolio"),
            portfolio_archive=_optional_mapping(source_audit, "portfolio_archive"),
            research_sync=_optional_mapping(source, "research_sync"),
        )
    _require_retained_sections(source, result)
    result["shared_reporting_source"] = {
        "path": str(source_path), "generated_at_utc": source["generated_at_utc"],
        "canonical_sha256": sha256(json.dumps(source, sort_keys=True, allow_nan=False).encode()).hexdigest(),
        "execution_authority": "none", "network_requests": False,
        "database_writes": False,
    }
    write_atomic_json(destination, result)
    return result


def _shared_source(
    path: Path,
    config: MultiAssetLiveConfig,
    run_id: str,
    epoch: CohortAccountingEpoch | None,
) -> dict[str, object]:
    source = fresh_checkpoint_document(
        path, config, maximum_age_seconds=SOURCE_MAXIMUM_AGE_SECONDS,
    )
    if source is None:
        raise ValueError(f"shared reporting checkpoint is missing or stale: {path}")
    if checkpoint_identity(source).run_id != run_id:
        raise ValueError("shared reporting checkpoint differs from the monitor run")
    observed = datetime.fromisoformat(text(source.get("generated_at_utc"), "shared generated time"))
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("shared reporting timestamp must be timezone-aware")
    age = (datetime.now(timezone.utc) - observed).total_seconds()
    if not 0.0 <= age <= SOURCE_MAXIMUM_AGE_SECONDS:
        raise ValueError(f"shared reporting generation is stale or future-dated: {path}")
    if epoch is not None:
        require_checkpoint_accounting_epoch(source, epoch)
    return source


def _optional_mapping(values: Mapping[str, object], key: str) -> Mapping[str, object] | None:
    if key not in values:
        return None
    return deepcopy(mapping(values[key], f"shared {key}"))


def _require_retained_sections(source: Mapping[str, object], result: Mapping[str, object]) -> None:
    if checkpoint_identity(source) != checkpoint_identity(result):
        raise ValueError("rebuilt checkpoint identity differs from its shared source")
    missing = set(source).difference(result)
    source_audit = mapping(source.get("audit"), "shared audit")
    result_audit = mapping(result.get("audit"), "rebuilt audit")
    missing.update(f"audit.{key}" for key in set(source_audit).difference(result_audit))
    if missing:
        raise ValueError(f"independent checkpoint would omit shared sections: {sorted(missing)}")
