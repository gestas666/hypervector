"""Resolve exact ledger and prior-profile sources for cohort backups."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig


class CohortLedgerSourceError(ValueError):
    """A cohort ledger identity cannot produce a safe backup source set."""


@dataclass(frozen=True)
class CohortLedgerBackupPlan:
    """Ledger files to archive and candidate assets without prior ledgers."""

    source_pairs: tuple[tuple[str, Path], ...]
    new_assets_without_prior_ledgers: tuple[str, ...]


def build_cohort_ledger_backup_plan(
    config: MultiAssetLiveConfig,
    previous: Mapping[str, object] | None,
) -> CohortLedgerBackupPlan:
    """Resolve the prior active ledgers without requiring new-asset history."""
    previous_symbols = _previous_enabled_symbols(previous)
    if previous_symbols is None:
        return CohortLedgerBackupPlan(
            source_pairs=_legacy_ledger_source_pairs(config),
            new_assets_without_prior_ledgers=(),
        )
    root = config.cohort_ledger.parent
    required = (
        ("cohort_ledger", config.cohort_ledger),
        *(
            (_asset_ledger_role(symbol), root / f"{symbol.lower()}.jsonl")
            for symbol in previous_symbols
        ),
    )
    missing = [str(path) for _, path in required if not path.is_file()]
    if missing:
        raise CohortLedgerSourceError(
            f"partial ledger state; missing required ledger(s): {missing}"
        )
    prior = set(previous_symbols)
    candidate_existing = tuple(
        (_asset_ledger_role(asset.symbol), asset.live_ledger)
        for asset in config.assets
        if asset.symbol not in prior and asset.live_ledger.is_file()
    )
    candidate_missing = tuple(
        asset.symbol
        for asset in config.assets
        if asset.symbol not in prior and not asset.live_ledger.exists()
    )
    return CohortLedgerBackupPlan(
        source_pairs=required + candidate_existing,
        new_assets_without_prior_ledgers=candidate_missing,
    )


def previous_configuration_paths(previous: Mapping[str, object]) -> list[Path]:
    """Return the previous cohort config followed by provider profile paths."""
    payload = previous.get("payload")
    if not isinstance(payload, Mapping):
        return []
    raw_config = payload.get("config_source_path")
    paths = [Path(raw_config)] if isinstance(raw_config, str) and raw_config else []
    providers = payload.get("providers")
    if not isinstance(providers, list):
        return paths
    for provider in providers:
        if not isinstance(provider, Mapping):
            continue
        raw_source = provider.get("source_profile")
        if isinstance(raw_source, str) and raw_source:
            paths.append(Path(raw_source))
    return paths


def _legacy_ledger_source_pairs(
    config: MultiAssetLiveConfig,
) -> tuple[tuple[str, Path], ...]:
    paths = (config.cohort_ledger, *(asset.live_ledger for asset in config.assets))
    existing = [path.exists() for path in paths]
    if any(existing) and not all(existing):
        missing = [str(path) for path, exists in zip(paths, existing) if not exists]
        raise CohortLedgerSourceError(
            f"partial ledger state; missing required ledger(s): {missing}"
        )
    if not any(existing):
        return ()
    roles = (
        "cohort_ledger",
        *(_asset_ledger_role(asset.symbol) for asset in config.assets),
    )
    return tuple(zip(roles, paths))


def _asset_ledger_role(symbol: str) -> str:
    normalized = "".join(
        character if character.isalnum() else "_" for character in symbol.lower()
    )
    return f"asset_{normalized}_ledger"


def _previous_enabled_symbols(
    previous: Mapping[str, object] | None,
) -> tuple[str, ...] | None:
    if previous is None:
        return None
    payload = previous.get("payload")
    if not isinstance(payload, Mapping) or "enabled_symbols" not in payload:
        return None
    raw = payload["enabled_symbols"]
    if (
        not isinstance(raw, list)
        or not raw
        or any(not isinstance(symbol, str) or not symbol for symbol in raw)
    ):
        raise CohortLedgerSourceError("previous enabled-symbol identity is invalid")
    symbols = tuple(raw)
    if len(set(symbols)) != len(symbols):
        raise CohortLedgerSourceError(
            "previous enabled-symbol identity contains duplicates"
        )
    return symbols
