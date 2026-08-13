"""Bounded deterministic development experiment for 1m order-flow impulse."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Mapping

import pandas as pd

from hypervector.research.market_cipher_data import load_verified_hourly_funding
from hypervector.research.orderflow_impulse_contract import OrderFlowImpulseConfig
from hypervector.research.orderflow_impulse_data import (
    audit_orderflow_coverage,
    load_orderflow_impulse_inputs,
)
from hypervector.research.orderflow_impulse_events import (
    build_orderflow_event_arms,
    build_orderflow_feature_rows,
)
from hypervector.research.orderflow_impulse_labels import (
    label_orderflow_arms,
    serialize_orderflow_outcomes,
)
from hypervector.research.orderflow_impulse_reporting import (
    summarize_orderflow_outcomes,
)


@dataclass(frozen=True)
class OrderFlowImpulseExperimentResult:
    """Report payload and complete arm-level lifecycle sidecar."""

    report: dict[str, object]
    outcomes: pd.DataFrame


def run_orderflow_impulse_experiment(
    database_path: Path,
    start_utc: datetime,
    end_utc: datetime,
    funding_paths: Mapping[str, Path],
    config: OrderFlowImpulseConfig,
) -> OrderFlowImpulseExperimentResult:
    """Run the fixed BTC/SOL deterministic development family report-only."""
    _validate_funding_paths(funding_paths, config)
    outcomes: list[pd.DataFrame] = []
    inputs_identity: dict[str, object] = {}
    row_counts: dict[str, object] = {}
    for symbol in config.symbols:
        symbol_outcomes, identity, counts = _run_symbol(
            database_path,
            symbol,
            start_utc,
            end_utc,
            funding_paths[symbol],
            config,
        )
        outcomes.append(symbol_outcomes)
        inputs_identity[symbol] = identity
        row_counts[symbol] = counts
    combined = pd.concat(outcomes, ignore_index=True)
    serialized = serialize_orderflow_outcomes(combined)
    serialized["fold_id"] = _fold_ids(serialized, start_utc, end_utc)
    report = _report(
        database_path,
        start_utc,
        end_utc,
        config,
        serialized,
        inputs_identity,
        row_counts,
    )
    return OrderFlowImpulseExperimentResult(report, serialized)


def _run_symbol(
    database_path: Path,
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
    funding_path: Path,
    config: OrderFlowImpulseConfig,
) -> tuple[pd.DataFrame, dict[str, str], dict[str, int]]:
    inputs = load_orderflow_impulse_inputs(
        database_path,
        symbol,
        start_utc,
        end_utc,
        warmup_minutes=config.warmup_minutes,
        horizon_minutes=config.maximum_hold_minutes + 1,
    )
    features = build_orderflow_feature_rows(
        inputs.bars, inputs.trades, inputs.books, config
    )
    scored = features.loc[
        features["bar_open_at"].ge(start_utc) & features["bar_open_at"].lt(end_utc)
    ].reset_index(drop=True)
    if scored.empty:
        raise ValueError(f"{symbol} contains no post-warmup feature rows")
    events = build_orderflow_event_arms(scored, symbol=symbol, config=config)
    funding = _funding_frame(funding_path, start_utc, end_utc, config)
    outcomes = label_orderflow_arms(inputs.bars, events, funding, config)
    identity = {
        "bars_sha256": _frame_sha256(inputs.bars),
        "trades_sha256": _frame_sha256(inputs.trades),
        "books_sha256": _frame_sha256(inputs.books),
        "funding_sha256": _file_sha256(funding_path),
    }
    counts = {
        "price_rows": len(inputs.bars),
        "trade_rows": len(inputs.trades),
        "book_rows": len(inputs.books),
        "scored_feature_rows": len(scored),
        "base_events": int(events["event_id"].nunique()),
        "arm_rows": len(events),
    }
    return outcomes, identity, counts


def _funding_frame(
    path: Path,
    start_utc: datetime,
    end_utc: datetime,
    config: OrderFlowImpulseConfig,
) -> pd.DataFrame:
    extended_end = pd.Timestamp(end_utc) + pd.Timedelta(
        minutes=config.maximum_hold_minutes + 1
    )
    series = load_verified_hourly_funding([path], pd.Timestamp(start_utc), extended_end)
    return series.rename_axis("timestamp").reset_index()


def _report(
    database_path: Path,
    start_utc: datetime,
    end_utc: datetime,
    config: OrderFlowImpulseConfig,
    outcomes: pd.DataFrame,
    input_identity: dict[str, object],
    row_counts: dict[str, object],
) -> dict[str, object]:
    coverage = audit_orderflow_coverage(database_path, ("BTC", "ETH", "SOL", "HYPE"))
    return {
        "schema_version": "orderflow_impulse_development_v1",
        "start_utc": pd.Timestamp(start_utc).isoformat(),
        "end_utc": pd.Timestamp(end_utc).isoformat(),
        "report_only": config.report_only,
        "execution_authority": config.execution_authority,
        "place_attempted": False,
        "config": asdict(config),
        "database_path": str(database_path),
        "input_identity": input_identity,
        "row_counts": row_counts,
        "archive_coverage": _records(coverage),
        "deterministic_summary": _records(summarize_orderflow_outcomes(outcomes)),
        "fold_summary": _fold_summary(outcomes),
        "accepted_rows": int(outcomes["accepted"].sum()),
        "displaced_rows": int((~outcomes["accepted"]).sum()),
        "ml_status": "pending_distinct_annotation_challenger",
    }


def _fold_summary(outcomes: pd.DataFrame) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for fold_id, rows in outcomes.groupby("fold_id", sort=True):
        summary = summarize_orderflow_outcomes(rows)
        selected = summary.loc[summary["scope"].eq("arm")].copy()
        selected.insert(0, "fold_id", int(fold_id))
        records.extend(_records(selected))
    return records


def _fold_ids(
    outcomes: pd.DataFrame, start_utc: datetime, end_utc: datetime
) -> pd.Series:
    start, end = pd.Timestamp(start_utc), pd.Timestamp(end_utc)
    elapsed = pd.to_datetime(outcomes["bar_open_at"], utc=True) - start
    fraction = elapsed / (end - start)
    return (fraction * 3).astype(int).clip(lower=0, upper=2)


def _validate_funding_paths(
    funding_paths: Mapping[str, Path], config: OrderFlowImpulseConfig
) -> None:
    if set(funding_paths) != set(config.symbols):
        raise ValueError("funding paths must exactly match configured symbols")
    missing = [str(path) for path in funding_paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"funding paths do not exist: {missing}")


def _frame_sha256(frame: pd.DataFrame) -> str:
    digest = sha256()
    digest.update("\x1f".join(map(str, frame.columns)).encode())
    values = pd.util.hash_pandas_object(frame, index=False, categorize=True)
    digest.update(values.to_numpy().tobytes())
    return digest.hexdigest()


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return frame.astype(object).where(pd.notna(frame), None).to_dict(orient="records")
