#!/usr/bin/env python3
"""Publish a report-only taker-entry parity screen for BTC sweep longs."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sys
from typing import Mapping

import duckdb
import pandas as pd

from hypervector.data.book_align import load_l2_jsonl
from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.btc_liquidity_sweep_taker_parity import (
    SignalPathObservation,
    TakerFriction,
    build_taker_parity_report,
    derive_signal_paths,
)

_TARGETS = (26.666666666666668, 40.0, 60.0, 80.0)
_DELAYS = (0, 15, 30, 60)
_STOP_BPS = 60.0
_DAY_MS = 86_400_000
_STRATEGY = "liquidity_sweep_long_1h_stop60_v1"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-report", type=Path, required=True)
    parser.add_argument("--forward-report", type=Path, required=True)
    parser.add_argument("--friction-report", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--database", type=Path)
    source.add_argument("--development-book-root", type=Path)
    parser.add_argument("--forward-books", type=Path, required=True)
    parser.add_argument("--forward-prices", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _development_books(
    database: Path, start_ms: int, end_ms: int
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Read one exact half-open BTC BBO window and bind its query rows."""
    if not database.is_file():
        raise FileNotFoundError(f"research database is missing: {database}")
    with duckdb.connect(str(database), read_only=True) as connection:
        rows = connection.execute(
            """
            SELECT ts_exchange_ms AS ts_ms, best_bid, best_ask
            FROM replay_book_snapshots
            WHERE symbol = 'BTC' AND ts_exchange_ms >= ? AND ts_exchange_ms < ?
            ORDER BY ts_exchange_ms
            """,
            [start_ms, end_ms],
        ).fetchdf()
    if rows.empty:
        raise ValueError("development BBO query returned no rows")
    return rows, _frame_evidence(rows)


def _archive_development_books(
    root: Path, start_ms: int, end_ms: int
) -> tuple[pd.DataFrame, dict[str, object]]:
    paths = _hourly_book_paths(root, start_ms, end_ms)
    frames = [
        load_l2_jsonl(path).loc[:, ["ts_ms", "best_bid", "best_ask"]] for path in paths
    ]
    rows = pd.concat(frames, ignore_index=True)
    rows = rows.loc[rows["ts_ms"].between(start_ms, end_ms, inclusive="left")]
    if rows.empty:
        raise ValueError("development archive returned no BBO rows")
    evidence = _frame_evidence(rows)
    evidence["hourly_files"] = [_path_evidence(path) for path in paths]
    return rows.reset_index(drop=True), evidence


def _hourly_book_paths(root: Path, start_ms: int, end_ms: int) -> tuple[Path, ...]:
    start = pd.Timestamp(start_ms, unit="ms", tz="UTC").floor("1h")
    end = pd.Timestamp(end_ms - 1, unit="ms", tz="UTC").floor("1h")
    paths = tuple(
        _hourly_book_path(root, hour) for hour in pd.date_range(start, end, freq="1h")
    )
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing exact hourly book: {missing[0]}")
    return paths


def _hourly_book_path(root: Path, hour: pd.Timestamp) -> Path:
    end = hour + pd.Timedelta(hours=1)
    window = f"{_archive_stamp(hour)}_{_archive_stamp(end)}_d20"
    return root / window / "books.jsonl.gz"


def _archive_stamp(value: pd.Timestamp) -> str:
    utc = value.tz_convert("UTC")
    return utc.strftime("%Y%m%dT%H%M%S") + f"{utc.microsecond:06d}Z"


def _frame_evidence(frame: pd.DataFrame) -> dict[str, object]:
    content = frame.to_csv(index=False, float_format="%.17g").encode()
    return {
        "row_count": len(frame),
        "first_ts_ms": int(frame.iloc[0]["ts_ms"]),
        "last_ts_ms": int(frame.iloc[-1]["ts_ms"]),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _friction(path: Path) -> TakerFriction:
    payload = _mapping(_read_json(path), "friction report")
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list):
        raise ValueError("friction report scenarios must be a list")
    route = _btc_long_route(scenarios)
    target = _number(route.get("target_bps"), "target bps")
    target_net = _number(
        route.get("stacked_target_net_before_funding_bps"), "target net bps"
    )
    stop = _number(route.get("stop_bps"), "stop bps")
    stop_loss = _number(route.get("stacked_p99_stop_loss_bps"), "stop loss bps")
    return TakerFriction(target - target_net, stop_loss - stop)


def _btc_long_route(scenarios: list[object]) -> Mapping[str, object]:
    for scenario_value in scenarios:
        scenario = _mapping(scenario_value, "friction scenario")
        if _number(scenario.get("account_value_usd"), "account value") != 500.0:
            continue
        assets = _mapping(scenario.get("asset_slots"), "asset slots")
        btc = _mapping(assets.get("BTC"), "BTC slot")
        routes = btc.get("routes")
        if not isinstance(routes, list):
            raise ValueError("BTC friction routes must be a list")
        for route_value in routes:
            route = _mapping(route_value, "BTC friction route")
            if route.get("strategy_id") == _STRATEGY:
                return route
    raise ValueError("friction report lacks the BTC liquidity-sweep route")


def _signal_times(payload: Mapping[str, object], label: str) -> tuple[str, ...]:
    values = payload.get("candidate_signal_times_utc")
    if not isinstance(values, list) or not values:
        raise ValueError(f"{label} must contain candidate signal times")
    if not all(isinstance(value, str) and value.strip() for value in values):
        raise ValueError(f"{label} signal times must be non-empty strings")
    return tuple(values)


def _verified_marks(
    report: Mapping[str, object], report_path: Path
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    contract = _mapping(report.get("replay_contract"), "replay contract")
    if contract.get("fill_rule") != "trade-through":
        raise ValueError("source replay must declare maker trade-through entry")
    source = _mapping(report.get("source_evidence"), "source evidence")
    values = source.get("price_context")
    if not isinstance(values, list) or not values:
        raise ValueError("source replay must declare price context")
    frames, evidence = [], []
    for value in values:
        expected = _mapping(value, "price context evidence")
        path = Path(str(expected.get("path")))
        observed = file_evidence(path)
        if any(observed.get(key) != expected.get(key) for key in ("bytes", "sha256")):
            raise RuntimeError(f"price context changed: {path}")
        frames.append(pd.read_parquet(path).loc[:, ["ts_ms", "mark_price"]])
        evidence.append({"path": str(path.resolve()), **observed})
    marks = pd.concat(frames, ignore_index=True).sort_values("ts_ms")
    evidence.append(
        {"report": str(report_path.resolve()), **file_evidence(report_path)}
    )
    return marks, evidence


def _development_paths(
    database: Path | None,
    book_root: Path | None,
    signal_times: tuple[str, ...],
    marks: pd.DataFrame,
) -> tuple[list[SignalPathObservation], list[dict[str, object]]]:
    paths, queries = [], []
    for signal in signal_times:
        start_ms = _timestamp_ms(signal)
        books, evidence = _development_source(
            database, book_root, start_ms, start_ms + _DAY_MS
        )
        paths.extend(
            derive_signal_paths(
                signal_time_utc=signal,
                partition="development",
                books=books,
                marks=marks,
                entry_delays_seconds=_DELAYS,
                target_grid_bps=_TARGETS,
                stop_bps=_STOP_BPS,
                evidence_end_ms=start_ms + _DAY_MS,
            )
        )
        queries.append({"signal_time_utc": signal, **evidence})
    return paths, queries


def _development_source(
    database: Path | None,
    book_root: Path | None,
    start_ms: int,
    end_ms: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    if database is not None:
        return _development_books(database, start_ms, end_ms)
    if book_root is None:
        raise ValueError("development source is unavailable")
    return _archive_development_books(book_root, start_ms, end_ms)


def _forward_paths(
    signal: str,
    books_path: Path,
    prices_path: Path,
) -> tuple[list[SignalPathObservation], list[dict[str, object]]]:
    books = load_l2_jsonl(books_path).loc[:, ["ts_ms", "best_bid", "best_ask"]]
    marks = pd.read_parquet(prices_path).loc[:, ["ts_ms", "mark_price"]]
    end_ms = min(
        _timestamp_ms(signal) + _DAY_MS,
        int(min(books["ts_ms"].max(), pd.to_numeric(marks["ts_ms"]).max())) + 1,
    )
    paths = derive_signal_paths(
        signal_time_utc=signal,
        partition="forward",
        books=books,
        marks=marks,
        entry_delays_seconds=_DELAYS,
        target_grid_bps=_TARGETS,
        stop_bps=_STOP_BPS,
        evidence_end_ms=end_ms,
    )
    evidence = [
        {"path": str(path.resolve()), **file_evidence(path)}
        for path in (books_path, prices_path)
    ]
    return list(paths), evidence


def _build_report(args: argparse.Namespace) -> dict[str, object]:
    development = _mapping(_read_json(args.development_report), "development report")
    forward = _mapping(_read_json(args.forward_report), "forward report")
    development_marks, price_evidence = _verified_marks(
        development, args.development_report
    )
    development_paths, queries = _development_paths(
        args.database,
        args.development_book_root,
        _signal_times(development, "development report"),
        development_marks,
    )
    forward_signals = _signal_times(forward, "forward report")
    if len(forward_signals) != 1:
        raise ValueError("forward parity screen requires exactly one frozen signal")
    forward_paths, forward_evidence = _forward_paths(
        forward_signals[0], args.forward_books, args.forward_prices
    )
    report = build_taker_parity_report(
        tuple(development_paths + forward_paths),
        target_grid_bps=_TARGETS,
        stop_bps=_STOP_BPS,
        friction=_friction(args.friction_report),
    )
    report["generated_at_utc"] = datetime.now(UTC).isoformat()
    report["path_observations"] = [
        asdict(path) for path in development_paths + forward_paths
    ]
    report["inputs"] = _input_evidence(args, price_evidence, queries, forward_evidence)
    return report


def _input_evidence(
    args: argparse.Namespace,
    price_evidence: list[dict[str, object]],
    queries: list[dict[str, object]],
    forward_evidence: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "development_report": _path_evidence(args.development_report),
        "forward_report": _path_evidence(args.forward_report),
        "friction_report": _path_evidence(args.friction_report),
        "database_path": (
            None if args.database is None else str(args.database.resolve())
        ),
        "development_book_root": (
            None
            if args.development_book_root is None
            else str(args.development_book_root.resolve())
        ),
        "development_book_queries": queries,
        "price_context": price_evidence,
        "forward_context": forward_evidence,
    }


def _path_evidence(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _timestamp_ms(value: str) -> int:
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None:
        raise ValueError("signal time must include a UTC offset")
    return int(parsed.tz_convert("UTC").timestamp() * 1_000)


def _read_json(path: Path) -> object:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not pd.notna(result):
        raise ValueError(f"{label} must be finite")
    return result


def main(argv: list[str] | None = None) -> int:
    """Publish one immutable authority-none parity report."""
    args = _parser().parse_args(argv)
    try:
        write_immutable_json(args.out, _build_report(args))
    except (OSError, RuntimeError, ValueError, duckdb.Error) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "out": str(args.out.resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
