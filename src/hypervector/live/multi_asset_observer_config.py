"""Safe identity-preserving output rebinding for cohort observers."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    validate_multi_asset_live_config,
)


def with_observer_ledger_root(
    config: MultiAssetLiveConfig,
    root: Path,
) -> MultiAssetLiveConfig:
    """Rebind observer outputs while preserving all strategy parameters."""
    resolved_root = root.resolve()
    broad_roots = {Path("/"), Path.home().resolve(), Path.cwd().resolve()}
    if resolved_root in broad_roots:
        raise ValueError(f"unsafe broad observer ledger root: {resolved_root}")
    if resolved_root == config.cohort_ledger.parent.resolve():
        raise ValueError("observer ledger root must differ from configured root")
    assets = tuple(
        replace(asset, live_ledger=root / f"{asset.symbol.lower()}.jsonl")
        for asset in config.assets
    )
    isolated = replace(
        config,
        cohort_ledger=root / "decisions.jsonl",
        stop_file=root / "STOP",
        assets=assets,
    )
    validate_multi_asset_live_config(isolated)
    return isolated
