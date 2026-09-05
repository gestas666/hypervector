"""Immutable audit publication for BTC liquidation covariate acquisition."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
import json
from pathlib import Path

from hypervector.data.oxa_backfill import OxaBackfillResult, OxaBackfillTask
from hypervector.data.oxa_storage import (
    file_evidence,
    gzip_text_writer,
    open_text_reader,
    publish_immutable_directory,
    verify_file_evidence,
    write_json,
)
from hypervector.data.oxa_trades import TRADE_NORMALIZATION_VERSION


def verify_covariate_acquisition_audit(bundle: Path) -> Mapping[str, object]:
    """Re-verify the plan, task evidence, manifests, and transitive data files."""
    report_path = bundle / "audit.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report, Mapping):
        raise ValueError("covariate acquisition audit must be a JSON object")
    contract = report.get("contract")
    if (
        report.get("mode") != "v58_btc_liquidation_covariate_archive_audit"
        or report.get("coverage_complete") is not True
        or not isinstance(contract, Mapping)
        or contract.get("execution_authority") != "none"
        or contract.get("strategy_outcomes_computed") is not False
    ):
        raise ValueError("covariate acquisition audit contract is invalid")
    plan, records = _verified_audit_evidence(bundle, report)
    _verify_plan_task_identity(plan, records)
    _verify_audit_counts(report, records)
    return report


def publish_covariate_acquisition_audit(
    output: Path,
    *,
    plan_path: Path,
    symbol: str,
    tasks: tuple[OxaBackfillTask, ...],
    results: tuple[OxaBackfillResult, ...],
) -> Path:
    """Validate exact task coverage and publish a hash-linked audit bundle."""
    records = _validated_records(symbol, tasks, results)

    def writer(staging: Path) -> None:
        task_evidence = staging / "task_evidence.jsonl.gz"
        _write_records(task_evidence, records)
        report = _audit_report(plan_path, task_evidence, results)
        write_json(staging / "audit.json", report)

    publish_immutable_directory(output, writer)
    return output


def _verified_audit_evidence(
    bundle: Path,
    report: Mapping[str, object],
) -> tuple[Mapping[str, object], tuple[Mapping[str, object], ...]]:
    evidence = report.get("evidence")
    if not isinstance(evidence, Mapping):
        raise ValueError("covariate acquisition audit evidence is missing")
    task_file = bundle / "task_evidence.jsonl.gz"
    _verify_expected_file(task_file, evidence.get("task_evidence"))
    plan_path = Path(str(evidence.get("plan_path")))
    _verify_expected_file(plan_path, evidence.get("plan"))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if not isinstance(plan, Mapping):
        raise ValueError("covariate acquisition plan must be a JSON object")
    records = _load_task_records(task_file)
    for record in records:
        _verify_record_sources(record)
    return plan, records


def _verify_expected_file(path: Path, expected: object) -> None:
    if not isinstance(expected, Mapping):
        raise ValueError(f"covariate audit file evidence is malformed: {path}")
    observed = file_evidence(path)
    if observed["bytes"] != expected.get("bytes"):
        raise ValueError(f"covariate audit byte count mismatch: {path}")
    if observed["sha256"] != expected.get("sha256"):
        raise ValueError(f"covariate audit checksum mismatch: {path}")


def _load_task_records(path: Path) -> tuple[Mapping[str, object], ...]:
    records: list[Mapping[str, object]] = []
    with open_text_reader(path) as handle:
        for line in handle:
            row = json.loads(line)
            if not isinstance(row, Mapping):
                raise ValueError("covariate task evidence row is malformed")
            records.append(row)
    return tuple(records)


def _verify_record_sources(record: Mapping[str, object]) -> None:
    directory = Path(str(record.get("directory")))
    manifest_record = record.get("manifest")
    if not isinstance(manifest_record, Mapping):
        raise ValueError("covariate task manifest evidence is malformed")
    manifest_path = Path(str(manifest_record.get("path")))
    if manifest_path.parent.resolve() != directory.resolve():
        raise ValueError("covariate task directory and manifest path differ")
    _verify_expected_file(manifest_path, manifest_record)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or payload.get("files") != record.get("files"):
        raise ValueError("covariate task manifest files differ from frozen audit")
    verify_file_evidence(directory, payload.get("files"))


def _verify_plan_task_identity(
    plan: Mapping[str, object],
    records: tuple[Mapping[str, object], ...],
) -> None:
    tasks = plan.get("tasks")
    if not isinstance(tasks, list) or any(
        not isinstance(row, Mapping) for row in tasks
    ):
        raise ValueError("covariate acquisition plan tasks are malformed")
    expected = {
        (row.get("kind"), row.get("start_utc"), row.get("end_utc")) for row in tasks
    }
    observed = {
        (row.get("kind"), row.get("start_utc"), row.get("end_utc")) for row in records
    }
    if expected != observed or len(tasks) != len(records):
        raise ValueError("covariate audit tasks differ from frozen plan")


def _verify_audit_counts(
    report: Mapping[str, object],
    records: tuple[Mapping[str, object], ...],
) -> None:
    acquisition = report.get("acquisition")
    if not isinstance(acquisition, Mapping):
        raise ValueError("covariate acquisition counts are missing")
    expected = {
        "tasks": len(records),
        "book_tasks": sum(row.get("kind") == "book" for row in records),
        "trade_tasks": sum(row.get("kind") == "trade" for row in records),
        "downloaded": sum(row.get("skipped_existing") is False for row in records),
        "resumed": sum(row.get("skipped_existing") is True for row in records),
        "rows": sum(_integer(row, "rows") for row in records),
        "pages": sum(_integer(row, "pages") for row in records),
    }
    if dict(acquisition) != expected:
        raise ValueError("covariate acquisition counts do not reconcile")


def _integer(value: Mapping[str, object], key: str) -> int:
    result = value.get(key)
    if isinstance(result, bool) or not isinstance(result, int):
        raise ValueError(f"covariate task {key} is invalid")
    return result


def _validated_records(
    symbol: str,
    tasks: tuple[OxaBackfillTask, ...],
    results: tuple[OxaBackfillResult, ...],
) -> tuple[dict[str, object], ...]:
    expected = {_identity(task) for task in tasks}
    observed = [_identity(result.task) for result in results]
    if len(observed) != len(set(observed)):
        raise ValueError("covariate acquisition returned duplicate task results")
    if set(observed) != expected or len(results) != len(tasks):
        raise ValueError("covariate acquisition results do not cover the frozen plan")
    ordered = sorted(results, key=lambda row: (row.task.start, row.task.kind))
    return tuple(_result_record(symbol, result) for result in ordered)


def _result_record(symbol: str, result: OxaBackfillResult) -> dict[str, object]:
    manifest_path = result.directory / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"covariate task manifest is malformed: {manifest_path}")
    _validate_manifest_identity(symbol, result, payload)
    verify_file_evidence(result.directory, payload.get("files"))
    rows_key = "trade_count" if result.task.kind == "trade" else "row_count"
    if (
        payload.get(rows_key) != result.rows
        or payload.get("page_count") != result.pages
    ):
        raise ValueError(f"covariate task counts differ from result: {manifest_path}")
    return {
        **_task_payload(result.task),
        "directory": str(result.directory.resolve()),
        "skipped_existing": result.skipped,
        "rows": result.rows,
        "pages": result.pages,
        "manifest": {
            "path": str(manifest_path.resolve()),
            **file_evidence(manifest_path),
        },
        "files": payload["files"],
    }


def _validate_manifest_identity(
    symbol: str,
    result: OxaBackfillResult,
    payload: Mapping[str, object],
) -> None:
    task = result.task
    source = {
        "book": "0xarchive_hyperliquid_native_l2",
        "trade": "0xarchive_hyperliquid_public_trades",
    }.get(task.kind)
    identity_matches = (
        source is not None
        and payload.get("source") == source
        and payload.get("symbol") == symbol
        and payload.get("requested_start") == task.start.isoformat()
        and payload.get("requested_end") == task.end.isoformat()
        and payload.get("complete") is True
        and payload.get("continuation_cursor") is None
    )
    if not identity_matches:
        raise ValueError(
            f"covariate task manifest identity mismatch: {result.directory}"
        )
    if (
        task.kind == "trade"
        and payload.get("normalization_version") != TRADE_NORMALIZATION_VERSION
    ):
        raise ValueError(f"covariate trade normalization is stale: {result.directory}")


def _audit_report(
    plan_path: Path,
    task_evidence: Path,
    results: tuple[OxaBackfillResult, ...],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "v58_btc_liquidation_covariate_archive_audit",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "coverage_complete": True,
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_promotion": False,
            "strategy_mutation": False,
            "strategy_outcomes_computed": False,
        },
        "evidence": {
            "plan_path": str(plan_path.resolve()),
            "plan": file_evidence(plan_path),
            "task_evidence": file_evidence(task_evidence),
        },
        "acquisition": _result_summary(results),
    }


def _result_summary(results: tuple[OxaBackfillResult, ...]) -> dict[str, int]:
    return {
        "tasks": len(results),
        "book_tasks": sum(row.task.kind == "book" for row in results),
        "trade_tasks": sum(row.task.kind == "trade" for row in results),
        "downloaded": sum(not row.skipped for row in results),
        "resumed": sum(row.skipped for row in results),
        "rows": sum(row.rows for row in results),
        "pages": sum(row.pages for row in results),
    }


def _identity(task: OxaBackfillTask) -> tuple[str, datetime, datetime]:
    return task.kind, task.start, task.end


def _task_payload(task: OxaBackfillTask) -> dict[str, str]:
    return {
        "kind": task.kind,
        "start_utc": task.start.isoformat(),
        "end_utc": task.end.isoformat(),
    }


def _write_records(path: Path, records: tuple[dict[str, object], ...]) -> None:
    with gzip_text_writer(path) as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")))
            handle.write("\n")
