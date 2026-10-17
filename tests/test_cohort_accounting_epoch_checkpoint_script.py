"""Checkpoint CLI wiring tests for the clean accounting epoch."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import pytest

from hypervector.research.cohort_live_portfolio_archive import (
    PORTFOLIO_ARCHIVE_PROJECTION_REVISION,
    CohortAccountingEpoch,
)

SCRIPT = (
    Path(__file__).parents[1]
    / "src" / "hypervector" / "operations" / 'multi_asset_bidirectional_live_checkpoint.py'
)
EPOCH = CohortAccountingEpoch("growth_5000_v49", "a" * 64, 1_786_579_200_000)


_CHECKPOINT_CONFIG = ["--config", "configs/multi_asset_bidirectional_canary.toml"]


def _load() -> ModuleType:
    spec = spec_from_file_location("accounting_epoch_checkpoint_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parser_accepts_one_explicit_accounting_epoch_bundle() -> None:
    module = _load()

    args = module.build_parser().parse_args(_CHECKPOINT_CONFIG + ["--accounting-epoch-bundle", "data/backups/epoch-v49"]
    )

    assert args.accounting_epoch_bundle == Path("data/backups/epoch-v49")


def test_accounting_epoch_requires_the_research_archive_worker() -> None:
    module = _load()
    args = module.build_parser().parse_args(_CHECKPOINT_CONFIG + ["--accounting-epoch-bundle", "data/backups/epoch-v49"]
    )

    with pytest.raises(ValueError, match="requires --research-database"):
        module._accounting_epoch(args)


def test_accounting_epoch_is_loaded_against_the_checkpoint_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load()
    args = module.build_parser().parse_args(
        [
            "--config",
            "v49.toml",
            "--research-database",
            "market.duckdb",
            "--accounting-epoch-bundle",
            "epoch-v49",
        ]
    )
    loaded: list[tuple[Path, object]] = []
    config = object()
    monkeypatch.setattr(
        module,
        "load_multi_asset_live_config",
        lambda path, *, mode: loaded.append((path, mode)) or config,
    )
    monkeypatch.setattr(
        module,
        "load_required_accounting_epoch",
        lambda bundle, successor: EPOCH
        if (bundle, successor) == (Path("epoch-v49"), config)
        else None,
    )

    assert module._accounting_epoch(args) == EPOCH
    assert loaded == [(Path("v49.toml"), "observe")]


def test_checkpoint_applies_required_epoch_policy_without_a_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load()
    args = module.build_parser().parse_args(
        ["--config", "v49.toml", "--research-database", "market.duckdb"]
    )
    config = object()
    monkeypatch.setattr(
        module,
        "load_multi_asset_live_config",
        lambda path, *, mode: config,
    )

    def required(bundle: Path | None, successor: object) -> None:
        assert bundle is None and successor is config
        raise ValueError("accounting epoch bundle is required")

    monkeypatch.setattr(module, "load_required_accounting_epoch", required)

    with pytest.raises(ValueError, match="accounting epoch bundle is required"):
        module._accounting_epoch(args)


def test_isolated_worker_receives_all_three_epoch_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load()
    calls: list[list[str]] = []
    archive = {
        "schema_version": 1,
        "mode": "cohort_live_portfolio_archive_v1",
        "projection_revision": PORTFOLIO_ARCHIVE_PROJECTION_REVISION,
        "accounting_epoch": EPOCH.to_dict(),
    }

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        payload = {
            "ok": True,
            "ingest": {"imported_events": 0},
            "portfolio_archive": archive,
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    monkeypatch.setattr(module.subprocess, "run", run)

    result = module._sync_research_database(
        tmp_path / "market.duckdb",
        tmp_path / "ledgers",
        accounting_epoch=EPOCH,
    )

    assert result["portfolio_archive"] == archive
    assert calls[0][-6:] == [
        "--accounting-epoch-id",
        EPOCH.epoch_id,
        "--accounting-epoch-profile-fingerprint",
        EPOCH.profile_fingerprint,
        "--accounting-epoch-start-ms",
        str(EPOCH.start_venue_timestamp_ms),
    ]
