"""Rolling research-import cache tests for the report-only checkpoint worker."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

from hypervector.data.research_database import ResearchDatabase
from hypervector.research import cohort_live_portfolio_archive as archive_module
from hypervector.research.cohort_live_portfolio_archive import CohortAccountingEpoch

SCRIPT = (
    Path(__file__).parents[1]
    / "src" / "hypervector" / "operations" / 'multi_asset_bidirectional_research_import.py'
)


def _load_module() -> ModuleType:
    spec = spec_from_file_location("multi_asset_research_import_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_rolling_import_reuses_archive_when_fill_identity_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-fill appends must not rebuild the multi-gigabyte archive projection."""
    module = _load_module()
    ledger_root, database_path = _ingested_fill_fixture(tmp_path)
    identity = archive_module.cohort_live_fill_identity(database_path).to_dict()
    archive = _archive(identity)
    checkpoint = tmp_path / "latest.json"
    checkpoint.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mode": "multi_asset_bidirectional_live_checkpoint",
                "checkpoint_contract": {
                    "report_only": True,
                    "execution_authority": "none",
                },
                "lifecycle": {"state": "running_consistent"},
                "audit": {"portfolio_archive": archive},
            }
        ),
        encoding="utf-8",
    )
    with (ledger_root / "decisions.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_event(2, "heartbeat")) + "\n")

    def forbidden_rebuild(_path: Path) -> dict[str, object]:
        raise AssertionError("unchanged fill identity rebuilt the archive")

    monkeypatch.setattr(
        module,
        "load_cohort_live_portfolio_archive",
        forbidden_rebuild,
    )

    report = module.build_import_report(
        database_path,
        ledger_root,
        cached_checkpoint_path=checkpoint,
    )

    assert report["archive_status"] == "reused_by_fill_identity"
    assert report["portfolio_archive"] == archive
    assert "summary" not in report


def test_accounting_epoch_is_forwarded_and_prevents_cross_epoch_cache_reuse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A clean epoch must rebuild and bind its exact profile/time scope."""
    module = _load_module()
    ledger_root, database_path = _ingested_fill_fixture(tmp_path)
    identity = archive_module.cohort_live_fill_identity(database_path).to_dict()
    checkpoint = tmp_path / "latest.json"
    checkpoint.write_text(json.dumps(_checkpoint(_archive(identity))), encoding="utf-8")
    epoch = CohortAccountingEpoch("growth_5000_v49", "a" * 64, 123)
    observed: list[CohortAccountingEpoch | None] = []

    def rebuild(
        _path: Path,
        *,
        source: archive_module.CohortLiveArchiveSource,
        accounting_epoch: CohortAccountingEpoch | None,
    ) -> dict[str, object]:
        observed.append(accounting_epoch)
        value = _archive(source.identity.to_dict())
        value["accounting_epoch"] = epoch.to_dict()
        return value

    monkeypatch.setattr(module, "load_cohort_live_portfolio_archive", rebuild)

    report = module.build_import_report(
        database_path,
        ledger_root,
        cached_checkpoint_path=checkpoint,
        accounting_epoch=epoch,
    )

    assert report["archive_status"] == "rebuilt_after_fill_identity_change"
    assert report["portfolio_archive"]["accounting_epoch"] == epoch.to_dict()
    assert observed == [epoch]


def test_accounting_epoch_cli_reconstructs_exact_profile_lineage() -> None:
    """Repeated lineage arguments must survive the worker process boundary."""
    module = _load_module()
    args = module.parse_args(
        [
            "--accounting-epoch-id",
            "growth_5000_v58_v59",
            "--accounting-epoch-profile-fingerprint",
            "b" * 64,
            "--accounting-epoch-start-ms",
            "1786164729837",
            "--accounting-epoch-included-profile-fingerprint",
            "a" * 64,
            "--accounting-epoch-included-profile-fingerprint",
            "b" * 64,
        ]
    )

    assert module._accounting_epoch(args) == CohortAccountingEpoch(
        "growth_5000_v58_v59",
        "b" * 64,
        1_786_164_729_837,
        included_profile_fingerprints=("a" * 64, "b" * 64),
    )


def test_rolling_import_rebuilds_archive_after_new_fill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A new fill must invalidate cached all-time projections fail-closed."""
    module = _load_module()
    ledger_root, database_path = _ingested_fill_fixture(tmp_path)
    old_identity = archive_module.cohort_live_fill_identity(database_path).to_dict()
    checkpoint = tmp_path / "latest.json"
    checkpoint.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mode": "multi_asset_bidirectional_live_checkpoint",
                "checkpoint_contract": {
                    "report_only": True,
                    "execution_authority": "none",
                },
                "lifecycle": {"state": "running_consistent"},
                "audit": {"portfolio_archive": _archive(old_identity)},
            }
        ),
        encoding="utf-8",
    )
    with (ledger_root / "decisions.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_event(2, "fill")) + "\n")
    rebuilds: list[Path] = []
    rebuilt_archives: list[dict[str, object]] = []

    def rebuild(
        path: Path,
        *,
        source: archive_module.CohortLiveArchiveSource,
    ) -> dict[str, object]:
        rebuilds.append(path)
        rebuilt = _archive(source.identity.to_dict())
        rebuilt_archives.append(rebuilt)
        return rebuilt

    monkeypatch.setattr(module, "load_cohort_live_portfolio_archive", rebuild)

    report = module.build_import_report(
        database_path,
        ledger_root,
        cached_checkpoint_path=checkpoint,
    )

    assert report["archive_status"] == "rebuilt_after_fill_identity_change"
    assert report["portfolio_archive"] == rebuilt_archives[0]
    assert rebuilds == [database_path]


def test_rolling_import_rebuilds_after_late_close_attribution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A post-fill cohort snapshot must invalidate an incomplete archive."""
    module = _load_module()
    ledger_root, database_path = _ingested_fill_fixture(tmp_path)
    old_identity = archive_module.cohort_live_fill_identity(database_path).to_dict()
    checkpoint = tmp_path / "latest.json"
    checkpoint.write_text(
        json.dumps(_checkpoint(_archive(old_identity))),
        encoding="utf-8",
    )
    with (ledger_root / "decisions.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_attributed_close_snapshot(2)) + "\n")
    rebuilt: list[dict[str, object]] = []

    def rebuild(
        _path: Path,
        *,
        source: archive_module.CohortLiveArchiveSource,
    ) -> dict[str, object]:
        value = _archive(source.identity.to_dict())
        rebuilt.append(value)
        return value

    monkeypatch.setattr(module, "load_cohort_live_portfolio_archive", rebuild)

    report = module.build_import_report(
        database_path,
        ledger_root,
        cached_checkpoint_path=checkpoint,
    )

    assert report["archive_status"] == "rebuilt_after_fill_identity_change"
    assert report["portfolio_archive"] == rebuilt[0]


def test_rolling_import_rebuilds_archive_after_projection_revision_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unchanged fills cannot reuse results produced by older projection math."""
    module = _load_module()
    ledger_root, database_path = _ingested_fill_fixture(tmp_path)
    identity = archive_module.cohort_live_fill_identity(database_path).to_dict()
    stale = _archive(identity)
    del stale["projection_revision"]
    checkpoint = tmp_path / "latest.json"
    checkpoint.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mode": "multi_asset_bidirectional_live_checkpoint",
                "checkpoint_contract": {
                    "report_only": True,
                    "execution_authority": "none",
                },
                "lifecycle": {"state": "running_consistent"},
                "audit": {"portfolio_archive": stale},
            }
        ),
        encoding="utf-8",
    )
    rebuilt = _archive(identity)
    monkeypatch.setattr(
        module,
        "load_cohort_live_portfolio_archive",
        lambda _path, *, source: rebuilt,
    )

    report = module.build_import_report(
        database_path,
        ledger_root,
        cached_checkpoint_path=checkpoint,
    )

    assert report["archive_status"] == "rebuilt_after_fill_identity_change"
    assert report["portfolio_archive"] == rebuilt


def test_rebuild_reuses_the_identity_archive_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One expensive source projection must serve identity and archive rebuild."""
    module = _load_module()
    ledger_root, database_path = _ingested_fill_fixture(tmp_path)
    source = archive_module.load_cohort_live_archive_source(database_path)
    checkpoint = tmp_path / "latest.json"
    checkpoint.write_text(
        json.dumps(_checkpoint(_archive({"fill_events": 0, "sha256": "0" * 64}))),
        encoding="utf-8",
    )
    source_loads: list[Path] = []
    rebuild_sources: list[object] = []

    def load_source(path: Path) -> archive_module.CohortLiveArchiveSource:
        source_loads.append(path)
        return source

    def rebuild(
        path: Path,
        *,
        source: archive_module.CohortLiveArchiveSource,
    ) -> dict[str, object]:
        rebuild_sources.append(source)
        return _archive(source.identity.to_dict())

    monkeypatch.setattr(module, "load_cohort_live_archive_source", load_source)
    monkeypatch.setattr(module, "load_cohort_live_portfolio_archive", rebuild)

    report = module.build_import_report(
        database_path,
        ledger_root,
        cached_checkpoint_path=checkpoint,
    )

    assert report["archive_status"] == "rebuilt_after_fill_identity_change"
    assert source_loads == [database_path]
    assert rebuild_sources == [source]


def _ingested_fill_fixture(tmp_path: Path) -> tuple[Path, Path]:
    ledger_root = tmp_path / "cohort"
    _write(ledger_root / "decisions.jsonl", [_event(1, "fill")])
    database_path = tmp_path / "market.duckdb"
    ResearchDatabase(database_path).ingest_cohort_live_ledger(ledger_root)
    return ledger_root, database_path


def _archive(identity: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "cohort_live_portfolio_archive_v1",
        "projection_revision": archive_module.PORTFOLIO_ARCHIVE_PROJECTION_REVISION,
        "source_execution": identity,
        "performance": {"total": {"closed_trades": 0}},
    }


def _checkpoint(archive: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "checkpoint_contract": {
            "report_only": True,
            "execution_authority": "none",
        },
        "lifecycle": {"state": "running_consistent"},
        "audit": {"portfolio_archive": archive},
    }


def _attributed_close_snapshot(sequence: int) -> dict[str, object]:
    event = _event(sequence, "cohort_snapshot")
    event["payload"] = {
        "recent_fills": [
            {
                "trade_id": 10,
                "symbol": "HYPE",
                "strategy_id": "hype_breakout_onset_bidirectional_v1",
                "origin_run_id": "run-1",
                "operation": "entry",
                "oid": 10,
                "venue_timestamp_ms": 1_000,
                "price": 20.0,
                "size": 1.0,
                "side": "B",
                "direction": "Open Long",
            },
            {
                "trade_id": 11,
                "symbol": "HYPE",
                "strategy_id": "hype_breakout_onset_bidirectional_v1",
                "origin_run_id": "run-1",
                "operation": "reduce_only_close",
                "oid": 11,
                "venue_timestamp_ms": 2_000,
                "price": 21.0,
                "size": 1.0,
                "side": "A",
                "direction": "Close Long",
                "entry_venue_timestamp_ms": 1_000,
                "net_pnl_usd": 0.9,
                "lifecycle_fees_usd": 0.1,
                "lifecycle_funding_usd": 0.0,
            },
        ]
    }
    return event


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _event(sequence: int, event_type: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "sequence": sequence,
        "event_type": event_type,
        "observed_at_utc": "2026-08-08T11:00:00+00:00",
        "execution_mode": "live",
        "effective_mode": "LIVE ARMED",
        "live_armed": True,
        "execution_authority": "hyperliquid_mainnet",
        "profile_id": "cohort-v25",
        "profile_fingerprint": "a" * 64,
        "run_fingerprint": "b" * 64,
        "run_id": "run-1",
        "payload": {"trade_id": sequence},
    }
