#!/usr/bin/env python3
"""Publish the preregistered BTC OI-expansion cadence-only preflight."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path

import duckdb
import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    publish_immutable_directory,
    write_json,
)
from hypervector.research.btc_oi_expansion_continuation import (
    build_oi_expansion_preflight,
)
from hypervector.research.oi_deleveraging_inputs import (
    load_oi_deleveraging_minutes,
)


_HYPOTHESIS = "V58_BTC_OI_EXPANSION_FLOW_CONTINUATION_LONG_PREFLIGHT_V1"
_PREREGISTRATION_SCHEMA = (
    "v58_btc_oi_expansion_flow_continuation_preflight_preregistration_v1"
)
_REGISTRATION_SCHEMA = (
    "v58_btc_oi_expansion_flow_continuation_preflight_input_registration_v1"
)
_REGISTRATION_STATUS = "inputs_hash_bound_before_preflight_count_query"
_PREREGISTRATION = Path(
    "docs/research-journal/"
    "v58-btc-oi-expansion-flow-continuation-preflight-"
    "preregistration-20260821-v1.json"
)
_INPUT_REGISTRATION = Path(
    "docs/research-journal/"
    "v58-btc-oi-expansion-flow-continuation-preflight-"
    "input-registration-20260821-v2.json"
)
_DEFAULT_OUTPUT = Path(
    "data/logs/research/bidirectional_cohort/"
    "v58_btc_oi_expansion_flow_continuation_preflight_20260821_v2"
)
_QUANTILES = (0.75, 0.8, 0.9)
_ARMS = (
    "positive_price_shock",
    "positive_price_and_oi_expansion",
    "positive_price_oi_and_trade_flow",
    "full_price_oi_trade_and_book_candidate",
)
_CANDIDATE_ARM = "full_price_oi_trade_and_book_candidate"
_PARTITIONS = (
    ("development", "2026-07-28T00:00:00Z", "2026-08-04T00:00:00Z"),
    ("validation", "2026-08-04T00:00:00Z", "2026-08-10T00:00:00Z"),
    ("pseudo_holdout", "2026-08-16T00:00:00Z", "2026-08-21T00:00:00Z"),
)
_WARMUP_START = "2026-07-26T23:41:00Z"
_GENERATORS = (
    "scripts/v58_btc_oi_expansion_preflight.py",
    "src/hypervector/research/btc_oi_expansion_continuation.py",
    "src/hypervector/research/oi_deleveraging_inputs.py",
)


def build_parser() -> argparse.ArgumentParser:
    """Return the fixed, report-only cadence preflight parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--preregistration", type=Path, default=_PREREGISTRATION)
    parser.add_argument("--input-registration", type=Path, default=_INPUT_REGISTRATION)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    return parser


def run_command(args: argparse.Namespace) -> Path:
    """Count frozen causal onsets and publish no forward outcomes."""
    if args.output.exists():
        raise FileExistsError(f"BTC OI-expansion output already exists: {args.output}")
    project_root = Path(__file__).resolve().parents[1]
    preregistration = _validated_preregistration(args.preregistration)
    generators = _generator_identity(project_root)
    start, end = _analysis_bounds()
    sources = source_evidence(args.database, start, end)
    registration = _validated_registration(
        args.input_registration, preregistration, generators, sources
    )
    minutes = load_oi_deleveraging_minutes(args.database, "BTC", start, end)
    rows = _evaluate_all_quantiles(minutes)
    counts = summarize_count_only_rows(rows)
    disposition = select_cadence_disposition(counts)
    _require_unchanged(args, project_root, preregistration, generators, sources)
    report = _build_report(
        preregistration,
        registration,
        generators,
        sources,
        minutes,
        rows,
        counts,
        disposition,
    )
    publish_count_bundle(args.output, report)
    return args.output


def source_evidence(
    database: Path, start: datetime, end: datetime
) -> dict[str, object]:
    """Return exact source-file identities through a read-only database handle."""
    if not database.is_file():
        raise FileNotFoundError(f"BTC OI-expansion database is missing: {database}")
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("BTC OI-expansion source-evidence window is invalid")
    lower = int(start.timestamp() * 1_000_000_000)
    upper = int(end.timestamp() * 1_000_000_000)
    with duckdb.connect(str(database), read_only=True) as connection:
        rows = connection.execute(
            _SOURCE_EVIDENCE_QUERY,
            [lower, upper, lower, upper, lower, upper],
        ).fetchall()
    files = [_source_record(row) for row in rows]
    _validate_source_tables(files)
    return {
        "database_path": str(database.resolve()),
        "window_start_utc": start.astimezone(UTC).isoformat(),
        "window_end_exclusive_utc": end.astimezone(UTC).isoformat(),
        "aggregate_sha256": _canonical_sha(files),
        "files": files,
        "execution_authority": "none",
    }


def summarize_count_only_rows(rows: pd.DataFrame) -> dict[str, object]:
    """Reduce attributed rows to partition, quantile, and arm onset counts."""
    required = {"partition", "quantile", "arm", "onset"}
    missing = sorted(required.difference(rows.columns))
    if missing:
        raise ValueError(f"BTC OI-expansion count rows missing columns: {missing}")
    invalid_arms = set(rows["arm"].astype(str)).difference(_ARMS)
    if invalid_arms:
        raise ValueError(
            f"BTC OI-expansion count rows contain unknown arms: {invalid_arms}"
        )
    grouped = (
        rows.assign(onset=rows["onset"].astype(bool))
        .groupby(["partition", "quantile", "arm"], sort=True)["onset"]
        .sum()
    )
    records = [
        {
            "partition": str(partition),
            "quantile": float(quantile),
            "arm": str(arm),
            "onset_count": int(count),
        }
        for (partition, quantile, arm), count in grouped.items()
    ]
    return {"rows": records, "outcomes_computed": False}


def select_cadence_disposition(counts: dict[str, object]) -> dict[str, object]:
    """Select only from development, then apply frozen OOS count minima."""
    rows = counts.get("rows")
    if not isinstance(rows, list):
        raise ValueError("BTC OI-expansion count summary lacks rows")
    selected = next(
        (
            quantile
            for quantile in sorted(_QUANTILES, reverse=True)
            if _count(rows, "development", quantile, _CANDIDATE_ARM) >= 20
        ),
        None,
    )
    status = _disposition_status(rows, selected)
    return {
        "status": status,
        "selected_quantile": selected,
        "selection_partition": "development",
        "outcomes_computed": False,
        "execution_authority": "none",
        "live_change_authorized": False,
    }


def publish_count_bundle(output: Path, report: dict[str, object]) -> None:
    """Atomically publish a report-only count bundle once."""

    def writer(staging: Path) -> None:
        report_path = staging / "report.json"
        write_json(report_path, report)
        manifest = {
            "schema_version": "immutable_evidence_manifest_v1",
            "files": {"report.json": file_evidence(report_path)},
        }
        write_json(staging / "manifest.json", manifest)

    publish_immutable_directory(output, writer)


def main(argv: Sequence[str] | None = None) -> int:
    """Publish the immutable cadence-only result and print its path."""
    output = run_command(build_parser().parse_args(argv))
    print(output.resolve())
    return 0


def _validated_preregistration(path: Path) -> dict[str, object]:
    payload = _load_json_object(path, "preregistration")
    if payload.get("schema_version") != _PREREGISTRATION_SCHEMA:
        raise ValueError("BTC OI-expansion preregistration schema drifted")
    if payload.get("hypothesis_id") != _HYPOTHESIS:
        raise ValueError("BTC OI-expansion preregistration identity drifted")
    authority = payload.get("authority")
    if (
        not isinstance(authority, dict)
        or authority.get("execution_authority") != "none"
    ):
        raise ValueError("BTC OI-expansion preregistration acquired authority")
    if authority.get("outcomes_computed") is not False:
        raise ValueError("BTC OI-expansion preregistration contains outcomes")
    return {"path": str(path.resolve()), **file_evidence(path.resolve())}


def _validated_registration(
    path: Path,
    preregistration: dict[str, object],
    generators: dict[str, object],
    sources: dict[str, object],
) -> dict[str, object]:
    payload = _load_json_object(path, "input registration")
    _validate_registration_contract(payload)
    expected = {
        "preregistration": preregistration,
        "generator_identity": generators,
        "source_evidence": sources,
    }
    for name, value in expected.items():
        if payload.get(name) != value:
            raise ValueError(f"BTC OI-expansion registered {name} drifted")
    return {"path": str(path.resolve()), **file_evidence(path.resolve())}


def _validate_registration_contract(payload: dict[str, object]) -> None:
    if payload.get("schema_version") != _REGISTRATION_SCHEMA:
        raise ValueError("BTC OI-expansion input registration schema drifted")
    if payload.get("hypothesis_id") != _HYPOTHESIS:
        raise ValueError("BTC OI-expansion input registration identity drifted")
    if payload.get("status") != _REGISTRATION_STATUS:
        raise ValueError("BTC OI-expansion input registration status drifted")
    authority = payload.get("authority")
    scope = payload.get("change_scope")
    if (
        not isinstance(authority, dict)
        or authority.get("execution_authority") != "none"
    ):
        raise ValueError("BTC OI-expansion input registration acquired authority")
    if (
        authority.get("outcomes_computed") is not False
        or authority.get("report_only") is not True
    ):
        raise ValueError("BTC OI-expansion input registration is not count-only")
    if (
        not isinstance(scope, dict)
        or scope.get("candidate_counts_inspected") is not False
    ):
        raise ValueError(
            "BTC OI-expansion inputs were registered after count inspection"
        )


def _generator_identity(project_root: Path) -> dict[str, object]:
    files: dict[str, dict[str, object]] = {}
    digest = hashlib.sha256()
    for relative in _GENERATORS:
        evidence = file_evidence(project_root / relative)
        files[relative] = evidence
        digest.update(f"{relative}:{evidence['sha256']}\n".encode())
    return {"aggregate_sha256": digest.hexdigest(), "files": files}


def _evaluate_all_quantiles(minutes: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for quantile in _QUANTILES:
        frame = build_oi_expansion_preflight(minutes, quantile=quantile)
        frames.append(_attach_partitions(frame))
    if not frames:
        raise RuntimeError("BTC OI-expansion quantile contract is empty")
    return pd.concat(frames, ignore_index=True)


def _attach_partitions(rows: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    decisions = pd.DatetimeIndex(rows["decision_at"])
    for name, raw_start, raw_end in _PARTITIONS:
        start, end = _parse_utc(raw_start), _parse_utc(raw_end)
        selected = rows.loc[(decisions >= start) & (decisions < end)].copy()
        selected.insert(0, "partition", name)
        frames.append(selected)
    return pd.concat(frames, ignore_index=True) if frames else rows.iloc[0:0]


def _build_report(
    preregistration: dict[str, object],
    registration: dict[str, object],
    generators: dict[str, object],
    sources: dict[str, object],
    minutes: pd.DataFrame,
    rows: pd.DataFrame,
    counts: dict[str, object],
    disposition: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": "v58_btc_oi_expansion_preflight_count_report_v2",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "hypothesis_id": _HYPOTHESIS,
        "authority": _authority(),
        "preregistration": preregistration,
        "input_registration": registration,
        "generator_identity": generators,
        "source_evidence": sources,
        "partition_bounds": _partition_records(),
        "input_counts": _input_counts(minutes, rows),
        "onset_counts": counts,
        "disposition": disposition,
    }


def _require_unchanged(
    args: argparse.Namespace,
    project_root: Path,
    preregistration: dict[str, object],
    generators: dict[str, object],
    sources: dict[str, object],
) -> None:
    if _validated_preregistration(args.preregistration) != preregistration:
        raise RuntimeError("BTC OI-expansion preregistration changed during counting")
    if _generator_identity(project_root) != generators:
        raise RuntimeError("BTC OI-expansion generator changed during counting")
    start, end = _analysis_bounds()
    if source_evidence(args.database, start, end) != sources:
        raise RuntimeError("BTC OI-expansion sources changed during counting")
    _validated_registration(
        args.input_registration, preregistration, generators, sources
    )


def _input_counts(minutes: pd.DataFrame, rows: pd.DataFrame) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for name, raw_start, raw_end in _PARTITIONS:
        start, end = _parse_utc(raw_start), _parse_utc(raw_end)
        minute_count = int(
            minutes["minute"].between(start, end, inclusive="left").sum()
        )
        partition = rows.loc[rows["partition"].eq(name)]
        bars = int(partition["decision_at"].nunique())
        evaluable = partition["price_threshold_bps"].map(math.isfinite)
        evaluable_bars = int(partition.loc[evaluable, "decision_at"].nunique())
        records.append(
            {
                "partition": name,
                "common_minute_count": minute_count,
                "complete_five_minute_bar_count": bars,
                "evaluable_five_minute_bar_count": evaluable_bars,
            }
        )
    return records


def _count(rows: list[object], partition: str, quantile: float, arm: str) -> int:
    for value in rows:
        if not isinstance(value, dict):
            raise ValueError("BTC OI-expansion count row is malformed")
        if (
            value.get("partition") == partition
            and value.get("quantile") == quantile
            and value.get("arm") == arm
        ):
            count = value.get("onset_count")
            if isinstance(count, bool) or not isinstance(count, int):
                raise ValueError("BTC OI-expansion onset count is malformed")
            return count
    return 0


def _disposition_status(rows: list[object], selected: float | None) -> str:
    if selected is None:
        return "data_insufficient_development"
    if any(
        _count(rows, name, selected, _CANDIDATE_ARM) < 10
        for name in ("validation", "pseudo_holdout")
    ):
        return "data_insufficient_oos"
    return "cadence_qualified_requires_outcome_preregistration"


def _source_record(row: tuple[object, ...]) -> dict[str, object]:
    ingested = row[9]
    return {
        "source_table": str(row[0]),
        "file_id": str(row[1]),
        "symbol": str(row[2]),
        "utc_date": str(row[3]),
        "dataset": str(row[4]),
        "source_path": str(row[5]),
        "byte_count": _required_int(row[6], "byte_count"),
        "row_count": _required_int(row[7], "row_count"),
        "sha256": str(row[8]),
        "ingested_at": ingested.isoformat()
        if isinstance(ingested, datetime)
        else str(ingested),
    }


def _validate_source_tables(files: list[dict[str, object]]) -> None:
    expected = {
        "live_asset_contexts",
        "replay_live_public_trades",
        "replay_live_book_snapshots",
    }
    observed = {str(value["source_table"]) for value in files}
    if observed != expected:
        raise ValueError(
            f"BTC OI-expansion source coverage mismatch: {sorted(observed)}"
        )


def _required_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"BTC OI-expansion source {label} is not an integer")
    return value


def _load_json_object(path: Path, label: str) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"BTC OI-expansion {label} is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"BTC OI-expansion {label} must be a JSON object")
    return payload


def _analysis_bounds() -> tuple[datetime, datetime]:
    return _parse_utc(_WARMUP_START), _parse_utc(_PARTITIONS[-1][2])


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != pd.Timedelta(0):
        raise ValueError(f"BTC OI-expansion timestamp is not UTC: {value}")
    return parsed


def _partition_records() -> list[dict[str, str]]:
    return [
        {"name": name, "start_utc": start, "end_exclusive_utc": end}
        for name, start, end in _PARTITIONS
    ]


def _authority() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "outcomes_computed": False,
        "live_change": False,
        "orders_supported": False,
    }


def _canonical_sha(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


_SOURCE_EVIDENCE_QUERY = """
WITH referenced AS (
    SELECT DISTINCT 'live_asset_contexts' AS source_table, file_id
    FROM live_asset_contexts
    WHERE symbol = 'BTC' AND received_ts_ns >= ? AND received_ts_ns < ?
    UNION ALL
    SELECT DISTINCT 'replay_live_public_trades' AS source_table, file_id
    FROM replay_live_public_trades
    WHERE symbol = 'BTC' AND received_ts_ns >= ? AND received_ts_ns < ?
    UNION ALL
    SELECT DISTINCT 'replay_live_book_snapshots' AS source_table, file_id
    FROM replay_live_book_snapshots
    WHERE symbol = 'BTC' AND received_ts_ns >= ? AND received_ts_ns < ?
)
SELECT referenced.source_table, files.file_id, files.symbol, files.utc_date,
       files.dataset, files.source_path, files.byte_count, files.row_count,
       files.sha256, files.ingested_at
FROM referenced
JOIN live_event_files AS files USING (file_id)
WHERE files.symbol = 'BTC'
ORDER BY referenced.source_table, files.file_id
"""


if __name__ == "__main__":
    raise SystemExit(main())
