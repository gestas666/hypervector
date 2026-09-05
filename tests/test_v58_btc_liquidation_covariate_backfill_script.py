"""Tests for the frozen BTC liquidation covariate acquisition command."""

from __future__ import annotations

from datetime import UTC, datetime
import gzip
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys

import pytest

from hypervector.data.oxa_backfill import (
    OxaBackfillConfig,
    OxaBackfillResult,
    OxaBackfillTask,
)
from hypervector.data.oxa_storage import file_evidence
from hypervector.data.oxa_trades import TRADE_NORMALIZATION_VERSION


_SCRIPT = Path("scripts/v58_btc_liquidation_covariate_backfill.py")


def test_covariate_backfill_script_exists() -> None:
    """The frozen research acquisition must have a reproducible entry point."""
    assert _SCRIPT.is_file()


def test_defaults_bind_frozen_report_only_sources() -> None:
    """Defaults must target the frozen preregistration and treatment cohort."""
    module = _load()

    args = module.build_parser().parse_args([])

    assert args.symbol == "BTC"
    assert args.preregistration.name.endswith("20260822-v4.json")
    assert args.treatment_journal.name.endswith("20260822-v7.json")
    assert args.treatment_bundle.name.endswith("treatment_episodes_20260822_v1")
    assert args.depth == 20
    assert args.workers == 4
    assert args.plan_only is False
    assert args.plan_out.suffix == ".json"
    assert args.out.name.endswith("_v1")
    defaults = module.run.__kwdefaults__
    assert defaults["task_runner"].__name__ == (
        "run_oxa_tasks_with_trade_renormalization"
    )


def test_prepare_publishes_exact_paired_plan_without_market_outcomes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Planning must bind frozen sources before any credential-bearing work."""
    module = _load()
    preregistration, journal, bundle = _frozen_sources(tmp_path)
    plan_path = tmp_path / "plan.json"
    monkeypatch.setattr(
        module,
        "_FROZEN_PREREGISTRATION_SHA256",
        file_evidence(preregistration)["sha256"],
    )
    monkeypatch.setattr(
        module,
        "_FROZEN_TREATMENT_JOURNAL_SHA256",
        file_evidence(journal)["sha256"],
    )
    monkeypatch.setattr(
        module,
        "verify_liquidation_episode_bundle",
        lambda path: json.loads((path / "manifest.json").read_text(encoding="utf-8")),
    )
    args = module.build_parser().parse_args(
        [
            "--preregistration",
            str(preregistration),
            "--treatment-journal",
            str(journal),
            "--treatment-bundle",
            str(bundle),
            "--data-root",
            str(tmp_path / "data"),
            "--plan-out",
            str(plan_path),
            "--out",
            str(tmp_path / "audit"),
        ]
    )

    prepared = module.prepare(args)

    assert plan_path.is_file()
    assert len(prepared.plan.windows) == 2
    assert len(prepared.hours) == 2
    assert [task.kind for task in prepared.tasks] == [
        "book",
        "trade",
        "book",
        "trade",
    ]
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    assert payload["contract"]["execution_authority"] == "none"
    assert payload["contract"]["strategy_outcomes_inspected"] is False
    assert payload["summary"]["eligible_episodes"] == 2
    assert payload["summary"]["vendor_hours"] == 2
    assert payload["summary"]["tasks"] == 4
    assert set(payload) == {
        "contract",
        "frozen_experiment",
        "mode",
        "partitions",
        "schema_version",
        "source",
        "summary",
        "tasks",
        "vendor_hours",
        "windows",
    }


def test_run_publishes_plan_before_credential_bearing_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A downloader failure must leave the exact immutable request plan."""
    module = _load()
    args, plan_path = _arguments(module, tmp_path, monkeypatch)

    def fail_after_plan(
        config: OxaBackfillConfig,
        *,
        tasks: tuple[OxaBackfillTask, ...],
        api_key: str,
        progress: object,
    ) -> tuple[object, ...]:
        assert plan_path.is_file()
        assert config.symbol == "BTC"
        assert len(tasks) == 4
        assert api_key == "configured-but-secret"
        raise RuntimeError("synthetic acquisition failure")

    with pytest.raises(RuntimeError, match="synthetic acquisition failure"):
        module.run(
            args,
            api_key="configured-but-secret",
            task_runner=fail_after_plan,
        )

    assert not args.out.exists()


def test_complete_acquisition_publishes_hash_linked_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every exact paired task must be checksummed before audit publication."""
    module = _load()
    args, plan_path = _arguments(module, tmp_path, monkeypatch)

    def complete_runner(
        config: OxaBackfillConfig,
        *,
        tasks: tuple[OxaBackfillTask, ...],
        api_key: str,
        progress: object,
    ) -> tuple[OxaBackfillResult, ...]:
        results = tuple(
            _write_task_bundle(config, task, index) for index, task in enumerate(tasks)
        )
        for result in results:
            progress(result)
        return results

    published = module.run(
        args,
        api_key="configured-but-secret",
        task_runner=complete_runner,
    )

    assert published == args.out
    progress = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip()
    ]
    assert progress[-1]["completed"] == 4
    assert progress[-1]["expected"] == 4
    report = json.loads((args.out / "audit.json").read_text(encoding="utf-8"))
    assert report["coverage_complete"] is True
    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["strategy_outcomes_computed"] is False
    assert report["acquisition"] == {
        "book_tasks": 2,
        "downloaded": 4,
        "pages": 4,
        "resumed": 0,
        "rows": 4,
        "tasks": 4,
        "trade_tasks": 2,
    }
    assert report["evidence"]["plan"] == file_evidence(plan_path)
    with gzip.open(
        args.out / "task_evidence.jsonl.gz", "rt", encoding="utf-8"
    ) as handle:
        rows = [json.loads(line) for line in handle]
    assert len(rows) == 4
    assert {row["kind"] for row in rows} == {"book", "trade"}
    assert all(row["manifest"]["sha256"] for row in rows)


def test_published_audit_detects_later_source_file_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Audit verification must follow task manifests to their declared files."""
    from hypervector.research.btc_liquidation_covariate_audit import (
        verify_covariate_acquisition_audit,
    )

    module = _load()
    args, _ = _arguments(module, tmp_path, monkeypatch)

    def complete_runner(
        config: OxaBackfillConfig,
        *,
        tasks: tuple[OxaBackfillTask, ...],
        api_key: str,
        progress: object,
    ) -> tuple[OxaBackfillResult, ...]:
        return tuple(
            _write_task_bundle(config, task, index) for index, task in enumerate(tasks)
        )

    module.run(
        args,
        api_key="configured-but-secret",
        task_runner=complete_runner,
    )
    report = verify_covariate_acquisition_audit(args.out)
    assert report["coverage_complete"] is True
    with gzip.open(
        args.out / "task_evidence.jsonl.gz", "rt", encoding="utf-8"
    ) as handle:
        first = json.loads(next(handle))
    directory = Path(first["directory"])
    data_path = next(
        path for path in directory.iterdir() if path.name != "manifest.json"
    )
    data_path.write_bytes(b"tampered")

    with pytest.raises(ValueError, match="(byte count|checksum) mismatch"):
        verify_covariate_acquisition_audit(args.out)


def test_plan_only_main_needs_no_api_key_or_task_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Outcome-blind planning must be inspectable without vendor credentials."""
    module = _load()
    args, plan_path = _arguments(module, tmp_path, monkeypatch)
    monkeypatch.delenv("OXA_API_KEY", raising=False)
    monkeypatch.setattr(
        module,
        "run",
        lambda *values, **keywords: pytest.fail("plan-only entered acquisition"),
    )

    status = module.main(
        [
            "--preregistration",
            str(args.preregistration),
            "--treatment-journal",
            str(args.treatment_journal),
            "--treatment-bundle",
            str(args.treatment_bundle),
            "--data-root",
            str(args.data_root),
            "--plan-out",
            str(plan_path),
            "--out",
            str(args.out),
            "--plan-only",
        ]
    )

    assert status == 0
    assert plan_path.is_file()
    assert not args.out.exists()


def _load() -> object:
    spec = spec_from_file_location("btc_liquidation_covariate_backfill", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load acquisition script: {_SCRIPT}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _frozen_sources(tmp_path: Path) -> tuple[Path, Path, Path]:
    preregistration = tmp_path / "preregistration.json"
    preregistration.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "hypothesis_id": (
                    "v58-btc-short-liquidation-continuation-long-data-preflight"
                ),
                "revision_number": 4,
                "status": "candidate",
                "execution_authority": "none",
                "automatic_promotion": False,
                "experiment_contract": {
                    "data_start_utc": "2026-01-01T00:00:00Z",
                    "development_end_exclusive_utc": "2026-01-02T00:00:00Z",
                    "validation_start_utc": "2026-01-02T00:00:00Z",
                    "validation_end_exclusive_utc": "2026-01-03T00:00:00Z",
                    "pseudo_holdout_start_utc": "2026-01-03T00:00:00Z",
                    "pseudo_holdout_end_exclusive_utc": "2026-01-04T00:00:00Z",
                },
            }
        ),
        encoding="utf-8",
    )
    bundle = tmp_path / "treatment"
    bundle.mkdir()
    end_times = (
        _milliseconds("2026-01-01T01:10:00+00:00"),
        _milliseconds("2026-01-02T01:10:00+00:00"),
    )
    eligible = bundle / "eligible_episodes.jsonl.gz"
    with gzip.open(eligible, "wt", encoding="utf-8") as handle:
        for index, end_ms in enumerate(end_times):
            handle.write(
                json.dumps(
                    {
                        "episode_id": f"episode-{index}",
                        "end_ms": end_ms,
                        "eligible_arms": ["5s_p95"],
                    }
                )
                + "\n"
            )
    episodes = bundle / "episodes.jsonl.gz"
    with gzip.open(episodes, "wt", encoding="utf-8") as handle:
        handle.write("{}\n")
    manifest = bundle / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "btc_liquidation_treatment_episode_bundle_v1",
                "symbol": "BTC",
                "report_only": True,
                "execution_authority": "none",
                "strategy_outcomes_inspected": False,
                "market_covariates_acquired": False,
                "counts": {"eligible_episodes": 2},
            }
        ),
        encoding="utf-8",
    )
    journal = tmp_path / "treatment-journal.json"
    journal.write_text(
        json.dumps(
            {
                "revision_number": 7,
                "execution_authority": "none",
                "metrics": {
                    "stage": "treatment_episodes_complete_covariates_pending",
                    "eligible_unique_episode_count": 2,
                    "strategy_outcomes_inspected": False,
                    "market_covariates_acquired": False,
                },
                "evidence": [
                    {"path": str(path), **file_evidence(path)}
                    for path in (manifest, episodes, eligible)
                ],
            }
        ),
        encoding="utf-8",
    )
    return preregistration, journal, bundle


def _arguments(
    module: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[object, Path]:
    preregistration, journal, bundle = _frozen_sources(tmp_path)
    plan_path = tmp_path / "plan.json"
    monkeypatch.setattr(
        module,
        "_FROZEN_PREREGISTRATION_SHA256",
        file_evidence(preregistration)["sha256"],
    )
    monkeypatch.setattr(
        module,
        "_FROZEN_TREATMENT_JOURNAL_SHA256",
        file_evidence(journal)["sha256"],
    )
    monkeypatch.setattr(
        module,
        "verify_liquidation_episode_bundle",
        lambda path: json.loads((path / "manifest.json").read_text(encoding="utf-8")),
    )
    args = module.build_parser().parse_args(
        [
            "--preregistration",
            str(preregistration),
            "--treatment-journal",
            str(journal),
            "--treatment-bundle",
            str(bundle),
            "--data-root",
            str(tmp_path / "data"),
            "--plan-out",
            str(plan_path),
            "--out",
            str(tmp_path / "audit"),
        ]
    )
    return args, plan_path


def _milliseconds(value: str) -> int:
    return int(datetime.fromisoformat(value).astimezone(UTC).timestamp() * 1_000)


def _write_task_bundle(
    config: OxaBackfillConfig,
    task: OxaBackfillTask,
    index: int,
) -> OxaBackfillResult:
    directory = config.data_root / f"fixture_{index}_{task.kind}"
    directory.mkdir(parents=True)
    filename = "books.jsonl.gz" if task.kind == "book" else "trades.jsonl.gz"
    data_path = directory / filename
    with gzip.open(data_path, "wt", encoding="utf-8") as handle:
        handle.write("{}\n")
    manifest = {
        "source": (
            "0xarchive_hyperliquid_native_l2"
            if task.kind == "book"
            else "0xarchive_hyperliquid_public_trades"
        ),
        "symbol": config.symbol,
        "requested_start": task.start.isoformat(),
        "requested_end": task.end.isoformat(),
        "complete": True,
        "continuation_cursor": None,
        "row_count" if task.kind == "book" else "trade_count": 1,
        "page_count": 1,
        "files": {filename: file_evidence(data_path)},
    }
    if task.kind == "trade":
        manifest["normalization_version"] = TRADE_NORMALIZATION_VERSION
    manifest_path = directory / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return OxaBackfillResult(task, directory, False, 1, 1)
