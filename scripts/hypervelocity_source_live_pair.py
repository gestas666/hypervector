#!/usr/bin/env python3
"""Replay uniform and weak/choppy sizing on one identical live event tape."""

from __future__ import annotations

import argparse
import math
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import duckdb
import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.live_replay_context import database_live_replay_context
from hypervector.research.research_database_replay import (
    ResearchReplayConfig,
    canonical_trade_bars,
    live_database_replay_coverage,
)
from hypervector.research.source_follow_portfolio_artifact import (
    select_source_follow_signals,
)
from hypervector.research.source_follow_portfolio_io import (
    LiveSourcePortfolioArchive,
    LiveSourcePortfolioArchiveConfig,
)
from hypervector.research.source_follow_portfolio_models import (
    SourcePortfolioReplayConfig,
    SourceSignal,
)
from hypervector.research.source_follow_risk_scaling import (
    SourceSizingProfile,
    apply_source_sizing_profile,
    source_sizing_summary,
)
from hypervector.research.source_follow_sparse_replay import (
    replay_sparse_source_portfolio,
)

_PROFILES = ("uniform", "weak_choppy_half")
_MAXIMUM_CONTEXT_GAP_SECONDS = 15.0
_MAXIMUM_FUNDING_AGE_SECONDS = 5.0


def _utc_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid UTC timestamp: {value}") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0.0:
        raise argparse.ArgumentTypeError("timestamp must include UTC offset or Z")
    return parsed.astimezone(UTC)


def _margin_fraction(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid margin fraction: {value}") from exc
    if not math.isfinite(parsed) or not 0.0 < parsed <= 1.0:
        raise argparse.ArgumentTypeError("margin fraction must be within (0, 1]")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse immutable evidence and half-open replay bounds."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--start", type=_utc_datetime, required=True)
    parser.add_argument("--end", type=_utc_datetime, required=True)
    parser.add_argument("--margin-fraction", type=_margin_fraction, default=0.50)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args(argv)


def experiment_contract(margin_fraction: float = 0.50) -> dict[str, object]:
    """Return the immutable authority and candidate boundary."""
    return {
        "report_only": True,
        "runtime_strategy_changed": False,
        "execution_authority": "none",
        "model_authority": "observe",
        "receipt_timestamp_source": "recorded",
        "paired_profiles": list(_PROFILES),
        "maximum_context_gap_seconds": _MAXIMUM_CONTEXT_GAP_SECONDS,
        "maximum_funding_age_seconds": _MAXIMUM_FUNDING_AGE_SECONDS,
        "signal_policy": (
            "TREND_DOWN_onset_confidence_ge_0.70_range_12_to_100_bps_short_24x7"
        ),
        "initial_equity": 15_000.0,
        "margin_fraction": margin_fraction,
        "leverage": 30.0,
        "gross_margin_target_pct": 8.0,
    }


def _load_labels(path: Path, end: datetime) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"source labels are missing: {path}")
    labels = pd.read_parquet(path)
    if not isinstance(labels.index, pd.DatetimeIndex) or labels.index.tz is None:
        raise ValueError("source labels require a timezone-aware DatetimeIndex")
    available = pd.DatetimeIndex(pd.to_datetime(labels["available_at"], utc=True))
    if available.empty or available.max() < pd.Timestamp(end):
        raise ValueError("source labels do not cover the requested replay end")
    return labels


def _signals(
    database: Path,
    labels: pd.DataFrame,
    start: datetime,
    end: datetime,
) -> tuple[SourceSignal, ...]:
    bar_start, bar_end = _label_bar_bounds(labels)
    bars = canonical_trade_bars(
        database,
        "BTC",
        bar_start,
        bar_end,
    )
    return select_source_follow_signals(labels, bars, start, end)


def _label_bar_bounds(labels: pd.DataFrame) -> tuple[datetime, datetime]:
    """Return exact datetime.UTC bounds covering every completed label bar."""
    start = cast(pd.Timestamp, labels.index.min()).to_pydatetime().astimezone(UTC)
    last = cast(pd.Timestamp, labels.index.max()) + pd.Timedelta(minutes=5)
    return start, last.to_pydatetime().astimezone(UTC)


def _replay_profile(
    archive_config: LiveSourcePortfolioArchiveConfig,
    signals: tuple[SourceSignal, ...],
    labels: pd.DataFrame,
    profile: str,
    margin_fraction: float,
) -> dict[str, object]:
    selected = apply_source_sizing_profile(
        signals,
        cast(SourceSizingProfile, profile),
        labels if profile != "uniform" else None,
    )
    config = _portfolio_config(margin_fraction)
    with LiveSourcePortfolioArchive(archive_config) as archive:
        result = replay_sparse_source_portfolio(
            archive,
            archive_config.start,
            archive_config.end,
            selected,
            config,
        )
    return {
        "source_sizing": source_sizing_summary(selected),
        "sparse_execution_evidence": {
            "queried_intervals": result.queried_intervals,
            "queried_seconds": result.queried_seconds,
            "verified_window_seconds": result.window_seconds,
        },
        "production_replay": result.report.to_dict(),
    }


def _portfolio_config(margin_fraction: float) -> SourcePortfolioReplayConfig:
    return SourcePortfolioReplayConfig(
        margin_fraction=margin_fraction,
        receipt_timestamp_source="recorded",
    )


def _comparison(replays: dict[str, dict[str, object]]) -> dict[str, object]:
    control = _report(replays["uniform"])
    scaled = _report(replays["weak_choppy_half"])
    return {
        "scaled_minus_uniform_final_equity": (
            _number(scaled, "final_equity") - _number(control, "final_equity")
        ),
        "scaled_minus_uniform_maximum_drawdown_pct": (
            _number(scaled, "maximum_drawdown_pct")
            - _number(control, "maximum_drawdown_pct")
        ),
        "scaled_minus_uniform_liquidations": (
            _integer(scaled, "liquidations") - _integer(control, "liquidations")
        ),
        "scaled_minus_uniform_targets": (
            _integer(scaled, "target_completions")
            - _integer(control, "target_completions")
        ),
    }


def _report(row: dict[str, object]) -> dict[str, object]:
    value = row.get("production_replay")
    if not isinstance(value, dict):
        raise ValueError("paired replay report is missing")
    return cast(dict[str, object], value)


def _number(row: dict[str, object], key: str) -> float:
    value = row.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"paired replay {key} must be numeric")
    return float(value)


def _integer(row: dict[str, object], key: str) -> int:
    value = row.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"paired replay {key} must be an integer")
    return value


def _receipt_lag_quality(
    database: Path,
    start: datetime,
    end: datetime,
) -> dict[str, object]:
    with duckdb.connect(str(database), read_only=True) as connection:
        return {
            "book": _lag_row(connection, "replay_live_book_snapshots", start, end),
            "trade": _lag_row(connection, "replay_live_public_trades", start, end),
        }


def _lag_row(
    connection: duckdb.DuckDBPyConnection,
    table: str,
    start: datetime,
    end: datetime,
) -> dict[str, object]:
    if table not in {"replay_live_book_snapshots", "replay_live_public_trades"}:
        raise ValueError(f"unsupported receipt-lag table: {table}")
    row = connection.execute(
        f"""
        SELECT count(*), min(received_ts_ns / 1000000.0 - exchange_ts_ms),
               max(received_ts_ns / 1000000.0 - exchange_ts_ms),
               count(*) FILTER (
                   WHERE received_ts_ns / 1000000.0 - exchange_ts_ms < 0
               ),
               count(*) FILTER (
                   WHERE received_ts_ns / 1000000.0 - exchange_ts_ms > 6000
               )
        FROM {table}
        WHERE symbol = 'BTC' AND exchange_ts_ms >= epoch_ms(?)
          AND exchange_ts_ms < epoch_ms(?)
        """,
        [start, end],
    ).fetchone()
    if row is None or len(row) != 5:
        raise RuntimeError("invalid receipt-lag evidence")
    return {
        "rows": int(row[0]),
        "minimum_ms": float(row[1]),
        "maximum_ms": float(row[2]),
        "negative_rows": int(row[3]),
        "over_six_second_rows": int(row[4]),
    }


def _coverage(
    database: Path,
    start: datetime,
    end: datetime,
) -> tuple[dict[str, object], dict[str, object]]:
    replay = ResearchReplayConfig(database, "BTC", start, end)
    events = live_database_replay_coverage(replay, include_trades=True)
    _, context = database_live_replay_context(
        database,
        "BTC",
        start,
        end,
        maximum_price_gap_seconds=_MAXIMUM_CONTEXT_GAP_SECONDS,
        maximum_funding_age_seconds=_MAXIMUM_FUNDING_AGE_SECONDS,
    )
    return events, context


def main(argv: list[str] | None = None) -> int:
    """Run both profiles against one verified immutable database snapshot."""
    args = parse_args(argv)
    labels = _load_labels(args.labels, args.end)
    signals = _signals(args.database, labels, args.start, args.end)
    archive = LiveSourcePortfolioArchiveConfig(
        args.database,
        "BTC",
        args.start,
        args.end,
        maximum_price_gap_seconds=_MAXIMUM_CONTEXT_GAP_SECONDS,
        maximum_funding_age_seconds=_MAXIMUM_FUNDING_AGE_SECONDS,
    )
    replays = {
        profile: _replay_profile(
            archive,
            signals,
            labels,
            profile,
            args.margin_fraction,
        )
        for profile in _PROFILES
    }
    event_coverage, context_coverage = _coverage(args.database, args.start, args.end)
    payload = {
        "schema": "hypervelocity_source_live_pair_v1",
        "experiment_contract": experiment_contract(args.margin_fraction),
        "window": {
            "start_utc": args.start.isoformat(),
            "end_utc": args.end.isoformat(),
        },
        "database": str(args.database.resolve()),
        "source_labels": file_evidence(args.labels),
        "signals": [asdict(signal) for signal in signals],
        "signal_count": len(signals),
        "live_l2_trade_coverage": event_coverage,
        "live_mark_funding_coverage": context_coverage,
        "receipt_lag_quality": _receipt_lag_quality(
            args.database, args.start, args.end
        ),
        "replays": replays,
        "comparison": _comparison(replays),
        "limitations": [
            "Displayed public depth cannot reveal private cancellations.",
            (
                "Negative receipt lag reflects recorder/exchange clock skew "
                "and is fail-closed."
            ),
            "The 12-bps floor and half-size subtype were selected on development data.",
        ],
    }
    write_immutable_json(args.out, payload)
    print(f"wrote {args.out} signals={len(signals)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
