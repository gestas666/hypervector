"""Multi-candidate Phase-2 export under data/exports/ (SRS_HV1_EXPORT_FS)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from hypervector import __version__
from hypervector.export.schema import EXPORT_SCHEMA_VERSION, validate_export_dir


def export_candidate(
    export_root: Path | str,
    run_id: str,
    *,
    meta: dict[str, Any],
    params: dict[str, Any],
    metrics: dict[str, Any],
    signals: pd.DataFrame | None = None,
    regime_labels: pd.Series | None = None,
    candidate_id: str | None = None,
    validate: bool = True,
    strict: bool = False,
) -> Path:
    """Write minimum bundle: meta.json, params.json, metrics.json (+ optional series).

    Always stamps ``schema_version`` and ``package_version``. Strategy is mirrored
    onto meta when present in params (Phase 2 loadout convenience). When
    ``validate`` is True (default), the written directory is schema-checked.
    """
    root = Path(export_root)
    cid = candidate_id or run_id
    out_dir = root / cid
    out_dir.mkdir(parents=True, exist_ok=True)

    # Caller meta wins on overlap except schema/package/run_id stamps.
    full_meta: dict[str, Any] = {
        **meta,
        "run_id": run_id,
        "package_version": __version__,
        "schema_version": EXPORT_SCHEMA_VERSION,
    }
    # Recency key for 'latest' bundle references (caller may pin its own).
    full_meta.setdefault(
        "created_at_utc", datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    # Mirror strategy onto meta for consumers that only read meta.json
    strategy = params.get("strategy") if isinstance(params, dict) else None
    if strategy and "strategy" not in full_meta:
        full_meta["strategy"] = strategy

    (out_dir / "meta.json").write_text(
        json.dumps(full_meta, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    (out_dir / "params.json").write_text(
        json.dumps(params, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    (out_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    # CSV row for spreadsheet consumers
    metrics_row = pd.DataFrame([{**{"run_id": run_id}, **metrics}])
    metrics_row.to_csv(out_dir / "metrics.csv", index=False)

    if signals is not None:
        signals.to_parquet(out_dir / "signals.parquet", index=True)
    if regime_labels is not None:
        rl = regime_labels
        if isinstance(rl, pd.Series):
            frame = rl.rename("regime").to_frame()
        else:
            frame = pd.DataFrame(rl)
        frame.to_parquet(out_dir / "regime_labels.parquet", index=True)

    if validate:
        # Loose by default so regime/minimal exports still write; sweep uses full meta.
        # Strict is available for Phase 2 readiness paths.
        validate_export_dir(out_dir, strict=strict)

    return out_dir
