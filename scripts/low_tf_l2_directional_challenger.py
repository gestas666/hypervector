#!/usr/bin/env python3
"""Run the immutable report-only low-timeframe L2 challenger screen."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
import json
import math
from numbers import Integral, Real
from pathlib import Path
from typing import Sequence

import pandas as pd

from hypervector.ml.low_tf_directional_challenger import (
    LowTimeframeChallengerResult,
    evaluate_low_tf_directional_challengers,
)
from hypervector.research.low_tf_barriers import (
    DirectionalBarrierSpec,
    label_directional_barriers,
)
from hypervector.research.low_tf_duckdb import (
    LowTimeframeInputFrames,
    load_low_timeframe_inputs,
)
from hypervector.research.low_tf_l2_dataset import (
    FEATURE_NAMES,
    LowTimeframeDatasetConfig,
    build_low_timeframe_dataset,
)
from hypervector.research.low_tf_strategy_screen import (
    LowTimeframeScreenReport,
    LowTimeframeScreenTrial,
    screen_low_tf_strategies,
)


_SCHEMA_VERSION = "low_tf_l2_directional_challenger_v1"


def _parser() -> argparse.ArgumentParser:
    """Build the explicit, report-only command-line contract."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True, choices=("BTC", "SOL"))
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument(
        "--segment",
        required=True,
        choices=("development", "validation", "pseudo_holdout"),
    )
    parser.add_argument("--out", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Execute a bounded immutable research run and return its exit status."""
    args = _parser().parse_args(argv)
    output = Path(args.out)
    sidecar = output.with_suffix(".parquet")
    _ensure_outputs_available(output, sidecar)
    start = _timestamp(str(args.start))
    end = _timestamp(str(args.end))
    inputs = load_low_timeframe_inputs(
        Path(args.database), str(args.symbol), start, end
    )
    model_rows, excluded_signal_bars = _model_rows(inputs, str(args.symbol), start, end)
    evaluation = evaluate_low_tf_directional_challengers(model_rows)
    scored = _scored_rows(evaluation.predictions, model_rows)
    screen = screen_low_tf_strategies(scored)
    output.parent.mkdir(parents=True, exist_ok=True)
    scored.to_parquet(sidecar, index=False)
    report = _report(
        args=args,
        start=start,
        end=end,
        inputs=inputs,
        model_rows=model_rows,
        excluded_signal_bars=excluded_signal_bars,
        evaluation=evaluation,
        screen=screen,
        sidecar=sidecar,
    )
    output.write_text(
        json.dumps(_json_safe(report), indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote report-only challenger artifact: {output}")
    return 0


def _ensure_outputs_available(output: Path, sidecar: Path) -> None:
    existing = [path for path in (output, sidecar) if path.exists()]
    if existing:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"challenger output exists: {joined}")


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("challenger timestamps must include a timezone")
    return parsed.astimezone(UTC)


def _model_rows(
    inputs: LowTimeframeInputFrames,
    symbol: str,
    start: datetime,
    end: datetime,
) -> tuple[pd.DataFrame, int]:
    dataset = build_low_timeframe_dataset(
        inputs.bars,
        inputs.trades,
        inputs.books,
        LowTimeframeDatasetConfig(symbol=symbol),
    )
    features = dataset.rows.loc[
        dataset.rows["bar_open_at"].ge(start) & dataset.rows["bar_open_at"].lt(end),
        ["bar_open_at", *FEATURE_NAMES],
    ].copy()
    requested_signal_bars = inputs.bars["bar_open_at"].ge(start) & inputs.bars[
        "bar_open_at"
    ].lt(end)
    excluded_signal_bars = int(requested_signal_bars.sum()) - len(features)
    if features.empty:
        raise ValueError("challenger signal window contains no eligible rows")
    outcomes = label_directional_barriers(
        inputs.bars,
        pd.DatetimeIndex(features["bar_open_at"]),
        DirectionalBarrierSpec(),
    )
    outcomes = _drop_censored_signals(outcomes)
    rows = outcomes.merge(
        features,
        left_on="signal_time_utc",
        right_on="bar_open_at",
        validate="many_to_one",
    )
    rows["signal_ts_ms"] = rows["signal_time_utc"].map(_timestamp_ms)
    rows["outcome_ts_ms"] = rows["outcome_time_utc"].map(_timestamp_ms)
    rows["target_hit"] = rows["status"].eq("target").astype(int)
    columns = [
        "signal_ts_ms",
        "outcome_ts_ms",
        "side",
        "target_hit",
        *FEATURE_NAMES,
        "status",
        "entry_price",
        "exit_price",
        "gross_return_bps",
        "ambiguous",
    ]
    ordered = (
        rows.loc[:, columns]
        .sort_values(["signal_ts_ms", "side"])
        .reset_index(drop=True)
    )
    return ordered, excluded_signal_bars


def _drop_censored_signals(outcomes: pd.DataFrame) -> pd.DataFrame:
    complete = outcomes.groupby("signal_time_utc")["status"].transform(
        lambda values: values.ne("truncated").all()
    )
    filtered = outcomes.loc[complete].copy()
    if filtered.empty:
        raise ValueError("challenger outcomes are entirely censored")
    return filtered


def _timestamp_ms(value: object) -> int:
    return int(pd.Timestamp(value).timestamp() * 1_000)


def _scored_rows(predictions: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
    details = rows.loc[
        :,
        [
            "signal_ts_ms",
            "outcome_ts_ms",
            "side",
            "status",
            "gross_return_bps",
            "ambiguous",
            "entry_price",
            "exit_price",
        ],
    ]
    return predictions.merge(
        details,
        on=["signal_ts_ms", "outcome_ts_ms", "side"],
        how="left",
        validate="many_to_one",
    )


def _report(
    *,
    args: argparse.Namespace,
    start: datetime,
    end: datetime,
    inputs: LowTimeframeInputFrames,
    model_rows: pd.DataFrame,
    excluded_signal_bars: int,
    evaluation: LowTimeframeChallengerResult,
    screen: LowTimeframeScreenReport,
    sidecar: Path,
) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "symbol": str(args.symbol),
        "segment": str(args.segment),
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "report_only": screen.report_only,
        "execution_authority": screen.execution_authority,
        "place_attempted": screen.place_attempted,
        "selection_status": "unranked_frozen_grid",
        "input_identity": _input_identity(inputs),
        "row_counts": {
            "bars": len(inputs.bars),
            "trade_bars": len(inputs.trades),
            "book_bars": len(inputs.books),
            "missing_book_bars": inputs.missing_book_bars,
            "orphan_book_bars": inputs.orphan_book_bars,
            "excluded_signal_bars": excluded_signal_bars,
            "directional_labels": len(model_rows),
            "folds": len(evaluation.folds),
        },
        "model_metrics": evaluation.metrics,
        "fold_metrics": evaluation.fold_metrics.to_dict(orient="records"),
        "trials": [_trial_summary(trial) for trial in screen.trials],
        "prediction_sidecar": {
            "path": str(sidecar),
            "sha256": _file_sha256(sidecar),
        },
    }


def _input_identity(inputs: LowTimeframeInputFrames) -> dict[str, str]:
    return {
        "hash_method": "pandas_hash_rows_sha256_v1",
        "bars_sha256": _frame_sha256(inputs.bars),
        "trades_sha256": _frame_sha256(inputs.trades),
        "books_sha256": _frame_sha256(inputs.books),
    }


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


def _trial_summary(trial: LowTimeframeScreenTrial) -> dict[str, object]:
    payload = asdict(trial)
    payload.pop("trades")
    return payload


def _json_safe(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    if isinstance(value, (datetime, pd.Timestamp)):
        return pd.Timestamp(value).isoformat()
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
