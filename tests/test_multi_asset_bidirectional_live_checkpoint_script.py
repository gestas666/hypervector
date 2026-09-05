"""CLI boundary tests for the cohort's read-only checkpoint sidecar."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import ModuleType

import pytest
from requests import RequestException

from hypervector.research.cohort_checkpoint_history import (
    HistoricalProjectionStale,
)
from hypervector.research.cohort_live_portfolio_archive import (
    PORTFOLIO_ARCHIVE_PROJECTION_REVISION,
)
import hypervector.runtime_lock as runtime_lock

SCRIPT = (
    Path(__file__).parents[1]
    / "scripts"
    / "multi_asset_bidirectional_live_checkpoint.py"
)


def _load_module() -> ModuleType:
    spec = spec_from_file_location("multi_asset_live_checkpoint_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_once_publishes_one_read_only_checkpoint(tmp_path: Path) -> None:
    """The deterministic CLI path forwards no execution or mutation authority."""
    module = _load_module()
    output = tmp_path / "latest.json"
    calls: list[tuple[Path, Path, str | None, Path]] = []

    def publish(
        root: Path,
        out: Path,
        *,
        run_id: str | None,
        config_path: Path,
        venue_portfolio: dict[str, object] | None,
    ) -> dict[str, object]:
        assert venue_portfolio is None
        calls.append((root, out, run_id, config_path))
        out.write_text('{"status":"ready"}\n', encoding="utf-8")
        return {"status": "ready"}

    args = module.build_parser().parse_args(
        [
            "--ledger-root",
            str(tmp_path / "ledgers"),
            "--out",
            str(output),
            "--run-id",
            "run-a",
            "--once",
        ]
    )

    assert module.run_checkpoint_loop(args, publish_fn=publish) == 0
    assert calls == [
        (
            tmp_path / "ledgers",
            output,
            "run-a",
            Path("configs/multi_asset_bidirectional_canary.toml"),
        )
    ]
    source = SCRIPT.read_text(encoding="utf-8")
    assert "submit_market" not in source
    assert "create_armed" not in source
    assert "private_key" not in source


def test_checkpoint_loop_refuses_a_second_writer_for_the_same_output(
    tmp_path: Path,
) -> None:
    """A stale-looking artifact cannot acquire two concurrent publishers."""
    module = _load_module()
    output = tmp_path / "latest.json"
    args = module.build_parser().parse_args(["--out", str(output), "--once"])
    lock_fn = getattr(runtime_lock, "cohort_checkpoint_runtime_lock", None)
    assert lock_fn is not None

    with lock_fn(output):
        with pytest.raises(RuntimeError, match="checkpoint writer already running"):
            module.run_checkpoint_loop(
                args,
                publish_fn=lambda *_args, **_kwargs: {"status": "ready"},
            )


def test_parser_accepts_repeated_supplemental_observer_paths() -> None:
    """Each explicitly configured report-only observer remains addressable."""
    module = _load_module()

    args = module.build_parser().parse_args(
        [
            "--supplemental-opportunity-matrix",
            "btc.json",
            "--supplemental-opportunity-matrix",
            "eth.json",
        ]
    )

    assert args.supplemental_opportunity_matrix == [
        Path("btc.json"),
        Path("eth.json"),
    ]


def test_parser_can_enable_exact_eligible_policy_forward_journal() -> None:
    """The report-only ETH lifecycle observer is an explicit sidecar option."""
    module = _load_module()

    args = module.build_parser().parse_args(["--eligible-policy-forward"])

    assert args.eligible_policy_forward is True


def test_parser_can_disable_profile_specific_asymmetric_observer() -> None:
    """A successor sidecar can refuse inheritance of the frozen v25 observer."""
    module = _load_module()

    args = module.build_parser().parse_args(["--disable-asymmetric-forward-observer"])

    assert args.disable_asymmetric_forward_observer is True


def test_real_publisher_receives_exact_policy_observer_flag(
    tmp_path: Path,
) -> None:
    """The sidecar forwards the explicit observer request only to its real writer."""
    module = _load_module()
    forwarded: list[tuple[bool, object, object]] = []

    def funding_fn(_symbol: str, _start_ms: int, _end_ms: int) -> None:
        return None

    def publish(
        _root: Path,
        _out: Path,
        **kwargs: object,
    ) -> dict[str, object]:
        forwarded.append(
            (
                bool(kwargs.get("eligible_policy_forward")),
                kwargs.get("funding_evidence_fn"),
                kwargs.get("asymmetric_forward_journal_path"),
            )
        )
        return {"status": "ready"}

    module.publish_live_checkpoint = publish
    args = module.build_parser().parse_args(
        ["--eligible-policy-forward", "--once", "--out", str(tmp_path / "out.json")]
    )

    module._publish_snapshot(args, publish, None, funding_fn)

    assert forwarded == [
        (
            True,
            funding_fn,
            Path("docs/research-journal/cohort-asymmetric-shared-portfolio-v1.json"),
        )
    ]


def test_real_publisher_omits_disabled_asymmetric_observer(tmp_path: Path) -> None:
    """The profile-bound disable flag must reach the real checkpoint writer."""
    module = _load_module()
    forwarded: list[object] = []

    def publish(
        _root: Path,
        _out: Path,
        **kwargs: object,
    ) -> dict[str, object]:
        forwarded.append(kwargs.get("asymmetric_forward_journal_path"))
        return {"status": "ready"}

    module.publish_live_checkpoint = publish
    args = module.build_parser().parse_args(
        [
            "--disable-asymmetric-forward-observer",
            "--once",
            "--out",
            str(tmp_path / "out.json"),
        ]
    )

    module._publish_snapshot(args, publish, None, None)

    assert forwarded == [None]


def test_public_funding_failure_does_not_suppress_core_checkpoint(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Funding transport failure returns unavailable evidence, never fake zero."""
    module = _load_module()

    class BrokenReader:
        def read(self, _symbol: str, _start_ms: int, _end_ms: int) -> object:
            raise RequestException("rate limited")

    funding_fn = module._failure_isolated_funding_fn(BrokenReader())

    assert funding_fn("ETH", 1, 60_000) is None
    error = capsys.readouterr().err
    assert "eligible-policy funding unavailable" in error
    assert "RequestException" in error


def test_once_syncs_cohort_evidence_when_database_is_explicit(tmp_path: Path) -> None:
    """A configured sidecar durably imports evidence without execution authority."""
    module = _load_module()
    ledger_root = tmp_path / "ledgers"
    database_path = tmp_path / "research.duckdb"
    output = tmp_path / "latest.json"
    sync_calls: list[tuple[Path, Path]] = []

    def publish(
        _root: Path,
        out: Path,
        *,
        run_id: str | None,
        config_path: Path,
        venue_portfolio: dict[str, object] | None,
    ) -> dict[str, object]:
        del run_id, config_path, venue_portfolio
        out.write_text('{"status":"ready"}\n', encoding="utf-8")
        return {"status": "ready"}

    def sync(database: Path, root: Path) -> dict[str, int]:
        sync_calls.append((database, root))
        return {"imported_events": 3}

    args = module.build_parser().parse_args(
        [
            "--ledger-root",
            str(ledger_root),
            "--out",
            str(output),
            "--research-database",
            str(database_path),
            "--once",
        ]
    )

    assert module.run_checkpoint_loop(args, publish_fn=publish, sync_fn=sync) == 0
    assert sync_calls == [(database_path, ledger_root)]


def test_research_sync_precedes_archive_checkpoint_publication(tmp_path: Path) -> None:
    """A completed lifecycle reaches DuckDB before its all-time view is rendered."""
    module = _load_module()
    order: list[str] = []

    def publish(
        _root: Path,
        _out: Path,
        *,
        run_id: str | None,
        config_path: Path,
        venue_portfolio: dict[str, object] | None,
    ) -> dict[str, object]:
        del run_id, config_path, venue_portfolio
        order.append("publish")
        return {"status": "ready"}

    def sync(_database: Path, _root: Path) -> dict[str, int]:
        order.append("sync")
        return {"imported_events": 1}

    args = module.build_parser().parse_args(
        [
            "--research-database",
            str(tmp_path / "market.duckdb"),
            "--out",
            str(tmp_path / "latest.json"),
            "--once",
        ]
    )

    assert module.run_checkpoint_loop(args, publish_fn=publish, sync_fn=sync) == 0
    assert order == ["sync", "publish"]


def test_research_sync_forwards_worker_archive_without_in_process_database_read(
    tmp_path: Path,
) -> None:
    """The persistent reporter reuses the isolated worker's archive payload."""
    module = _load_module()
    archive = {
        "schema_version": 1,
        "mode": "cohort_live_portfolio_archive_v1",
        "projection_revision": PORTFOLIO_ARCHIVE_PROJECTION_REVISION,
    }
    forwarded: list[object] = []

    def publish(_root: Path, _out: Path, **kwargs: object) -> dict[str, object]:
        forwarded.append(kwargs.get("portfolio_archive"))
        return {"status": "ready"}

    def sync(_database: Path, _root: Path) -> dict[str, object]:
        return {"imported_events": 3, "portfolio_archive": archive}

    module.publish_live_checkpoint = publish
    args = module.build_parser().parse_args(
        [
            "--research-database",
            str(tmp_path / "market.duckdb"),
            "--out",
            str(tmp_path / "latest.json"),
            "--once",
        ]
    )

    assert module.run_checkpoint_loop(args, publish_fn=publish, sync_fn=sync) == 0
    assert forwarded == [archive]


def test_research_sync_runs_database_work_in_isolated_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The persistent reporter never opens the large DuckDB file itself."""
    module = _load_module()
    database = tmp_path / "market.duckdb"
    ledger_root = tmp_path / "ledgers"
    archive = {
        "schema_version": 1,
        "mode": "cohort_live_portfolio_archive_v1",
        "projection_revision": PORTFOLIO_ARCHIVE_PROJECTION_REVISION,
    }
    calls: list[list[str]] = []

    def run(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["timeout"] == 300.0
        payload = {
            "ok": True,
            "ingest": {"imported_events": 7, "source_files": 10},
            "archive_status": "reused_by_fill_identity",
            "fill_identity": {"fill_events": 61, "sha256": "a" * 64},
            "portfolio_archive": archive,
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    monkeypatch.setattr(module.subprocess, "run", run)

    cached_checkpoint = tmp_path / "latest.json"
    result = module._sync_research_database(
        database,
        ledger_root,
        cached_checkpoint_path=cached_checkpoint,
    )

    assert result == {
        "imported_events": 7,
        "source_files": 10,
        "archive_status": "reused_by_fill_identity",
        "fill_identity": {"fill_events": 61, "sha256": "a" * 64},
        "portfolio_archive": archive,
    }
    assert len(calls) == 1
    assert calls[0][0] == sys.executable
    assert calls[0][1].endswith("multi_asset_bidirectional_research_import.py")
    assert calls[0][-6:] == [
        "--database",
        str(database),
        "--ledger-root",
        str(ledger_root),
        "--cached-checkpoint",
        str(cached_checkpoint),
    ]


def test_background_research_sync_does_not_block_checkpoint_publication(
    tmp_path: Path,
) -> None:
    """A slow archive worker cannot delay the fast checkpoint loop."""
    module = _load_module()
    started = threading.Event()
    release = threading.Event()
    archive = {
        "schema_version": 1,
        "mode": "cohort_live_portfolio_archive_v1",
    }

    def slow_sync(_database: Path, _root: Path) -> dict[str, object]:
        started.set()
        assert release.wait(timeout=2.0)
        return {"imported_events": 4, "portfolio_archive": archive}

    args = module.build_parser().parse_args(
        [
            "--research-database",
            str(tmp_path / "market.duckdb"),
            "--research-sync-interval-seconds",
            "120",
        ]
    )
    controller = module.BackgroundResearchSync(
        args.research_database,
        args.ledger_root,
        args.research_sync_interval_seconds,
        slow_sync,
        minimum_free_bytes=0,
    )
    before = time.monotonic()

    controller.poll(now=0.0)

    assert time.monotonic() - before < 0.1
    assert started.wait(timeout=1.0)
    assert controller.portfolio_archive is None
    release.set()
    controller.wait_for_completion(timeout=2.0)
    controller.poll(now=1.0)
    assert controller.portfolio_archive == archive
    controller.close()


def test_real_publisher_receives_durable_portfolio_archive(tmp_path: Path) -> None:
    """Only the read-only checkpoint writer receives database archive evidence."""
    module = _load_module()
    archive = {
        "schema_version": 1,
        "mode": "cohort_live_portfolio_archive_v1",
    }
    forwarded: list[object] = []

    def publish(_root: Path, _out: Path, **kwargs: object) -> dict[str, object]:
        forwarded.append(kwargs.get("portfolio_archive"))
        return {"status": "ready"}

    module.publish_live_checkpoint = publish
    args = module.build_parser().parse_args(
        [
            "--research-database",
            str(tmp_path / "market.duckdb"),
            "--once",
        ]
    )

    module._publish_snapshot(args, publish, None, None, archive)

    assert forwarded == [archive]


def test_continuous_real_publisher_uses_cached_complete_history(
    tmp_path: Path,
) -> None:
    """The hot loop requests bounded ledgers and retains exact all-time lineage."""
    module = _load_module()
    output = tmp_path / "latest.json"
    cached = {
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": "2026-08-08T10:00:00+00:00",
        "checkpoint_contract": {
            "report_only": True,
            "execution_authority": "none",
        },
        "lifecycle": {"state": "running_consistent"},
        "audit": {
            "mode": "multi_asset_bidirectional_live_audit",
            "run": {"run_id": "run-current"},
        },
    }
    output.write_text(json.dumps(cached), encoding="utf-8")
    forwarded: list[dict[str, object]] = []

    def publish(_root: Path, _out: Path, **kwargs: object) -> dict[str, object]:
        forwarded.append(dict(kwargs))
        return {"status": "ready"}

    module.publish_live_checkpoint = publish
    args = module.build_parser().parse_args(["--out", str(output)])

    module._publish_snapshot(args, publish, None, None, None)

    assert len(forwarded) == 1
    assert forwarded[0]["run_id"] == "run-current"
    assert forwarded[0]["compatible_execution_history"] is True
    assert forwarded[0]["complete_historical_checkpoint"] == cached


def test_continuous_publisher_refreshes_full_history_after_new_fill(
    tmp_path: Path,
) -> None:
    """A changed fill signature gets one exact full-ledger refresh, not stale data."""
    module = _load_module()
    output = tmp_path / "latest.json"
    cached = {
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": "2026-08-08T10:00:00+00:00",
        "checkpoint_contract": {
            "report_only": True,
            "execution_authority": "none",
        },
        "lifecycle": {"state": "running_consistent"},
        "audit": {
            "mode": "multi_asset_bidirectional_live_audit",
            "run": {"run_id": "run-current"},
        },
    }
    output.write_text(json.dumps(cached), encoding="utf-8")
    snapshot_modes: list[bool] = []

    def publish(_root: Path, _out: Path, **kwargs: object) -> dict[str, object]:
        bounded = bool(kwargs.get("compatible_execution_history"))
        snapshot_modes.append(bounded)
        if bounded:
            raise HistoricalProjectionStale("execution history changed: fill signature")
        return {"status": "ready"}

    module.publish_live_checkpoint = publish
    args = module.build_parser().parse_args(["--out", str(output)])

    module._publish_snapshot(args, publish, None, None, None)

    assert snapshot_modes == [True, False]


def test_venue_portfolio_flag_adds_read_only_value_to_each_checkpoint(
    tmp_path: Path,
) -> None:
    """The optional public observer forwards no execution authority."""
    module = _load_module()
    observed = {
        "status": "observed",
        "portfolio_value_usd": 507.08,
        "execution_collateral_value_usd": 504.11,
    }
    forwarded: list[dict[str, object] | None] = []

    def publish(
        _root: Path,
        _out: Path,
        *,
        run_id: str | None,
        config_path: Path,
        venue_portfolio: dict[str, object] | None,
    ) -> dict[str, object]:
        del run_id, config_path
        forwarded.append(venue_portfolio)
        return {"status": "ready"}

    args = module.build_parser().parse_args(
        [
            "--venue-portfolio",
            "--out",
            str(tmp_path / "latest.json"),
            "--once",
        ]
    )

    assert (
        module.run_checkpoint_loop(
            args,
            publish_fn=publish,
            portfolio_fn=lambda: observed,
        )
        == 0
    )
    assert forwarded == [observed]


def test_once_reports_research_sync_failure_without_masking_it(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A configured database failure is explicit and returns nonzero."""
    module = _load_module()
    output = tmp_path / "latest.json"

    def publish(
        _root: Path,
        out: Path,
        *,
        run_id: str | None,
        config_path: Path,
        venue_portfolio: dict[str, object] | None,
    ) -> dict[str, object]:
        del run_id, config_path, venue_portfolio
        out.write_text('{"status":"ready"}\n', encoding="utf-8")
        return {"status": "ready"}

    def fail(_database: Path, _root: Path) -> dict[str, int]:
        raise module.ResearchSyncError("database locked")

    args = module.build_parser().parse_args(
        [
            "--ledger-root",
            str(tmp_path / "ledgers"),
            "--out",
            str(output),
            "--research-database",
            str(tmp_path / "research.duckdb"),
            "--once",
        ]
    )

    assert module.run_checkpoint_loop(args, publish_fn=publish, sync_fn=fail) == 2
    assert "cohort research sync failed: database locked" in capsys.readouterr().err


def test_once_publishes_explicit_unavailable_status(tmp_path: Path) -> None:
    """Missing startup evidence is observable and returns a failing status."""
    module = _load_module()
    output = tmp_path / "latest.json"

    def missing(
        _root: Path,
        _out: Path,
        *,
        run_id: str | None,
        config_path: Path,
        venue_portfolio: dict[str, object] | None,
    ) -> dict[str, object]:
        del run_id, config_path, venue_portfolio
        raise FileNotFoundError("asset ledgers not ready")

    args = module.build_parser().parse_args(
        ["--ledger-root", str(tmp_path / "ledgers"), "--out", str(output), "--once"]
    )

    assert module.run_checkpoint_loop(args, publish_fn=missing) == 2
    status = json.loads(output.read_text(encoding="utf-8"))
    assert status["status"] == {
        "state": "unavailable",
        "technical_issue": "asset ledgers not ready",
    }
    assert status["checkpoint_contract"]["execution_authority"] == "none"


def test_once_retries_a_transient_cross_ledger_snapshot(
    tmp_path: Path,
) -> None:
    """A brief cross-file append boundary must not zero a valid checkpoint."""
    module = _load_module()
    output = tmp_path / "latest.json"
    calls = 0
    delays: list[float] = []

    def transient(
        _root: Path,
        out: Path,
        *,
        run_id: str | None,
        config_path: Path,
        venue_portfolio: dict[str, object] | None,
    ) -> dict[str, object]:
        nonlocal calls
        del run_id, config_path, venue_portfolio
        calls += 1
        if calls == 1:
            raise ValueError("HYPE open lifecycle lacks a current position")
        out.write_text('{"status":"ready"}\n', encoding="utf-8")
        return {"status": "ready"}

    args = module.build_parser().parse_args(
        ["--ledger-root", str(tmp_path / "ledgers"), "--out", str(output), "--once"]
    )

    assert (
        module.run_checkpoint_loop(
            args,
            publish_fn=transient,
            sleep_fn=delays.append,
        )
        == 0
    )
    assert calls == 2
    assert delays == [module._SNAPSHOT_RETRY_SECONDS]
    assert json.loads(output.read_text(encoding="utf-8")) == {"status": "ready"}


def test_failed_refresh_retains_last_complete_live_checkpoint(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A transient refresh failure must not replace complete TUI telemetry."""
    module = _load_module()
    output = tmp_path / "latest.json"
    complete = {
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": "2026-08-06T06:30:00+00:00",
        "lifecycle": {"state": "running_consistent"},
        "audit": {"execution": {"closed_trades": 15}},
    }
    output.write_text(json.dumps(complete), encoding="utf-8")

    def inconsistent(
        _root: Path,
        _out: Path,
        *,
        run_id: str | None,
        config_path: Path,
        venue_portfolio: dict[str, object] | None,
    ) -> dict[str, object]:
        del run_id, config_path, venue_portfolio
        raise ValueError("HYPE open lifecycle lacks a current position")

    args = module.build_parser().parse_args(
        ["--ledger-root", str(tmp_path / "ledgers"), "--out", str(output), "--once"]
    )

    assert module.run_checkpoint_loop(args, publish_fn=inconsistent) == 2
    assert json.loads(output.read_text(encoding="utf-8")) == complete
    assert "retaining last complete checkpoint" in capsys.readouterr().err
