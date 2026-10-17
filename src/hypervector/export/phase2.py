"""Multi-candidate Phase-2 export under data/exports/ (SRS_HV1_EXPORT_FS)."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from hypervector import __version__
from hypervector.export.schema import (
    EXPORT_SCHEMA_VERSION,
    ExportSchemaError,
    validate_export_dir,
)
from hypervector.export.venue_meta import with_instrument_meta


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
    data_root: Path | str | None = None,
) -> Path:
    """Write minimum bundle: meta.json, params.json, metrics.json (+ optional series).

    Always stamps ``schema_version`` and ``package_version``. Strategy is mirrored
    onto meta when present in params (Phase 2 loadout convenience). For a
    symbol ``nautilus run`` has no built-in geometry for, ``meta.instrument``
    is copied from cached Hyperliquid venue metadata under ``data_root``
    (default: the parent of an ``exports`` directory) — never fetched; when
    none is cached, ``meta.instrument_note`` says how to supply it. The bundle is
    written to a staging directory beside the target and schema-checked there
    when ``validate`` is True (default); only a valid bundle is moved into
    ``export_root/<candidate_id>``. A failed validation leaves no partial bundle
    and keeps any previous bundle of that candidate untouched.
    """
    root = Path(export_root)
    cid = candidate_id or run_id
    out_dir = root / cid
    root.mkdir(parents=True, exist_ok=True)

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
    if data_root is None and root.name == "exports":
        data_root = root.parent
    full_meta = with_instrument_meta(full_meta, data_root)

    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=root))
    try:
        _write_bundle(staging, run_id, full_meta, params, metrics, signals, regime_labels)
        if validate:
            # Loose by default so regime/minimal exports still write; sweep uses
            # full meta. Strict is available for Phase 2 readiness paths.
            try:
                validate_export_dir(staging, strict=strict)
            except ExportSchemaError as exc:
                raise ExportSchemaError(out_dir, exc.errors) from None
        out_dir.mkdir(parents=True, exist_ok=True)
        for item in sorted(staging.iterdir()):
            os.replace(item, out_dir / item.name)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return out_dir


def _write_bundle(
    out_dir: Path,
    run_id: str,
    meta: dict[str, Any],
    params: dict[str, Any],
    metrics: dict[str, Any],
    signals: pd.DataFrame | None,
    regime_labels: pd.Series | None,
) -> None:
    (out_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True, default=str) + "\n",
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
