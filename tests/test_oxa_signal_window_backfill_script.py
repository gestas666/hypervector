"""Operator-contract tests for targeted HYPE L2 signal-window acquisition."""

from __future__ import annotations

import gzip
import json
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pandas as pd
import pytest

from hypervector.data.oxa_backfill import (
    OxaBackfillConfig,
    OxaBackfillResult,
    OxaBackfillTask,
)
from hypervector.data.oxa_history import OxaBookRequest, output_directory
from hypervector.data.oxa_storage import file_evidence

_SCRIPT = Path(__file__).parents[1] / "scripts" / "oxa_signal_window_backfill.py"


def _load() -> object:
    spec = spec_from_file_location("oxa_signal_window_backfill_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load targeted HYPE L2 backfill script")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _features(path: Path) -> None:
    pd.DataFrame(
        {
            "side": ["long", "short"],
            "signal_time_utc": [
                "2025-07-29T07:49:00+00:00",
                "2025-07-29T08:19:00+00:00",
            ],
            "entry_time_utc": [
                "2025-07-29T07:50:00+00:00",
                "2025-07-29T08:20:00+00:00",
            ],
        }
    ).to_parquet(path, index=False)


def test_defaults_freeze_the_full_causal_hype_scope() -> None:
    """The operator command must default to all frozen labeled HYPE entries."""
    module = _load()
    args = module.build_parser().parse_args([])

    assert args.symbol == "HYPE"
    assert "development_v2" in args.features.name
    assert args.pre_seconds == 60
    assert args.post_seconds == 10
    assert args.depth == 20
    assert args.workers == 4
    assert args.retries == 5
    assert args.book_max_pages == 2
    assert args.plan_only is False
    assert args.plan_out.suffix == ".json"
    assert args.out.name.endswith("_v1")


def test_immutable_plan_exists_before_any_credit_bearing_request(
    tmp_path: Path,
) -> None:
    """A failed downloader must still leave the exact predeclared request plan."""
    module = _load()
    features = tmp_path / "features.parquet"
    plan = tmp_path / "plan.json"
    output = tmp_path / "audit_bundle"
    _features(features)
    args = module.build_parser().parse_args(
        [
            "--features",
            str(features),
            "--data-root",
            str(tmp_path / "data"),
            "--plan-out",
            str(plan),
            "--out",
            str(output),
        ]
    )

    def fail_after_plan(
        config: OxaBackfillConfig,
        *,
        tasks: tuple[OxaBackfillTask, ...],
        api_key: str,
        progress: object,
    ) -> tuple[object, ...]:
        assert plan.is_file()
        assert api_key == "configured-but-secret"
        assert config.symbol == "HYPE"
        assert [task.kind for task in tasks] == ["book", "book"]
        raise RuntimeError("synthetic downloader failure")

    with pytest.raises(RuntimeError, match="synthetic downloader failure"):
        module.run(args, api_key="configured-but-secret", task_runner=fail_after_plan)

    payload = json.loads(plan.read_text(encoding="utf-8"))
    assert payload["contract"]["execution_authority"] == "none"
    assert payload["summary"]["signal_windows"] == 2
    assert payload["summary"]["aggregate_requested_seconds"] == 140.0
    assert len(payload["windows"]) == 2
    assert not output.exists()


def test_existing_plan_must_match_exactly_before_resume(tmp_path: Path) -> None:
    """A changed feature identity cannot silently reuse a prior credit plan."""
    module = _load()
    plan = tmp_path / "plan.json"
    plan.write_text('{"wrong": true}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="existing signal-window plan differs"):
        module.ensure_plan(plan, {"expected": True})


def test_complete_fake_acquisition_publishes_one_hash_linked_bundle(
    tmp_path: Path,
) -> None:
    """Only fully timed and checksummed windows may create the final audit."""
    module = _load()
    features = tmp_path / "features.parquet"
    plan = tmp_path / "plan.json"
    output = tmp_path / "audit_bundle"
    _features(features)
    args = module.build_parser().parse_args(
        [
            "--features",
            str(features),
            "--data-root",
            str(tmp_path / "data"),
            "--plan-out",
            str(plan),
            "--out",
            str(output),
        ]
    )

    def complete_runner(
        config: OxaBackfillConfig,
        *,
        tasks: tuple[OxaBackfillTask, ...],
        api_key: str,
        progress: object,
    ) -> tuple[OxaBackfillResult, ...]:
        results = tuple(_write_task_bundle(config, task) for task in tasks)
        for result in results:
            progress(result)
        return results

    audit = module.run(
        args,
        api_key="configured-but-secret",
        task_runner=complete_runner,
    )

    assert audit.complete is True
    assert (output / "audit.json").is_file()
    assert len(pd.read_parquet(output / "index.parquet")) == 2
    report = json.loads((output / "audit.json").read_text(encoding="utf-8"))
    assert report["coverage"]["complete"] is True
    assert report["acquisition"]["tasks"] == 2
    assert report["contract"]["execution_authority"] == "none"
    assert report["evidence"]["index"] == file_evidence(output / "index.parquet")


def test_incomplete_vendor_coverage_is_published_without_success_shape(
    tmp_path: Path,
) -> None:
    """A complete request audit must retain vendor holes as explicit evidence."""
    module = _load()
    features = tmp_path / "features.parquet"
    output = tmp_path / "audit_bundle"
    _features(features)
    args = module.build_parser().parse_args(
        [
            "--features",
            str(features),
            "--data-root",
            str(tmp_path / "data"),
            "--plan-out",
            str(tmp_path / "plan.json"),
            "--out",
            str(output),
        ]
    )

    def incomplete_runner(
        config: OxaBackfillConfig,
        *,
        tasks: tuple[OxaBackfillTask, ...],
        api_key: str,
        progress: object,
    ) -> tuple[OxaBackfillResult, ...]:
        return tuple(
            _write_task_bundle(config, task, include_rows=index == 0)
            for index, task in enumerate(tasks)
        )

    audit = module.run(
        args,
        api_key="configured-but-secret",
        task_runner=incomplete_runner,
    )

    assert audit.complete is False
    report = json.loads((output / "audit.json").read_text(encoding="utf-8"))
    assert report["coverage_complete"] is False
    assert report["coverage"]["complete"] is False
    assert report["coverage"]["summary"]["bundles_complete"] == 2
    assert report["coverage"]["summary"]["causal_covered"] == 1


def _write_task_bundle(
    config: OxaBackfillConfig,
    task: OxaBackfillTask,
    *,
    include_rows: bool = True,
) -> OxaBackfillResult:
    request = OxaBookRequest(config.symbol, task.start, task.end, config.depth)
    directory = output_directory(config.data_root, request)
    directory.mkdir(parents=True)
    entry_ms = int((task.start.timestamp() + 60) * 1_000)
    rows = (
        [_book_row(entry_ms - 500), _book_row(entry_ms + 300)] if include_rows else []
    )
    books = directory / "books.jsonl.gz"
    with gzip.open(books, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    manifest = {
        "source": "0xarchive_hyperliquid_native_l2",
        "symbol": config.symbol,
        "requested_start": task.start.isoformat(),
        "requested_end": task.end.isoformat(),
        "requested_depth": config.depth,
        "complete": True,
        "continuation_cursor": None,
        "row_count": len(rows),
        "page_count": 1,
        "files": {"books.jsonl.gz": file_evidence(books)},
    }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return OxaBackfillResult(task, directory, False, len(rows), 1)


def _book_row(timestamp_ms: int) -> dict[str, object]:
    return {
        "ts_exchange_ms": timestamp_ms,
        "bids": [{"px": "50.0", "sz": "2.0", "n": 1}],
        "asks": [{"px": "50.1", "sz": "2.0", "n": 1}],
    }
