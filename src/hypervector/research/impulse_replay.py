"""Reconstruct trades from the recorded Hypervelocity impulse decision tape."""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from hypervector.ml.feature_matrix import FEATURE_NAMES, build_feature_matrix
from hypervector.regime.detectors import detect_regime_ema

_REPLAY_EVENTS = (
    "WOULD_ENTER_LONG",
    "WOULD_ENTER_SHORT",
    "WOULD_EXIT_INVALIDATION",
    "WOULD_CLOSE_TP_10",
)
_JSON_FEATURES = (
    "obi_5",
    "obi_10",
    "obi_25",
    "obi_ema_1s",
    "obi_ema_5s",
    "obi_persistence_s",
    "spread_bps",
    "bid_depth_10",
    "ask_depth_10",
    "aggressor_ratio_5s",
    "cancel_rate_5s",
    "micro_price",
    "mid",
)
_LANES: dict[str, tuple[str, str]] = {
    "uptrend_long": ("up", "long"),
    "downtrend_short": ("down", "short"),
    "range_long": ("range", "long"),
    "range_short": ("range", "short"),
}


@dataclass(frozen=True)
class ReplayPairingStats:
    """Counts explaining how recorded decision events were paired."""

    source_events: int
    completed_trades: int
    unmatched_exits: int
    ignored_entries: int
    open_trade_at_end: bool


@contextmanager
def materialized_replay_database(source: Path | str) -> Iterator[Path]:
    """Yield a raw SQLite path, expanding a zstd archive into temporary storage."""
    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(f"impulse replay source not found: {path}")
    if path.suffix != ".zst":
        yield path
        return
    zstd = shutil.which("zstd") or "/opt/homebrew/bin/zstd"
    if not Path(zstd).is_file():
        raise RuntimeError("zstd executable is required to read replay archives")
    with tempfile.TemporaryDirectory(prefix="hypervector-replay-") as temp_dir:
        database = Path(temp_dir) / "impulse_calibration.sqlite"
        with database.open("wb") as output:
            result = subprocess.run(
                [zstd, "-dc", str(path)],
                stdout=output,
                stderr=subprocess.PIPE,
                check=False,
            )
        if result.returncode != 0:
            message = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"replay archive decompression failed: {message}")
        yield database


def load_decision_events(database: Path | str, *, coin: str) -> pd.DataFrame:
    """Load replay entry/exit decisions for one coin from a raw SQLite file."""
    path = Path(database)
    if not path.is_file():
        raise FileNotFoundError(f"impulse replay database not found: {path}")
    placeholders = ",".join("?" for _ in _REPLAY_EVENTS)
    query = f"""
        SELECT recorded_at, direction, event_type, current_mid,
               impulse_score, momentum_score, velocity_bps_1s,
               velocity_bps_3s, velocity_bps_5s, acceleration_bps,
               feature_age_ms, features_json
        FROM decision_samples
        WHERE coin = ? AND event_type IN ({placeholders})
        ORDER BY recorded_at
    """
    uri = f"file:{path.resolve()}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as connection:
        return pd.read_sql_query(
            query, connection, params=(coin.upper(), *_REPLAY_EVENTS)
        )


def load_completed_regimes(
    database: Path | str,
    *,
    coin: str,
    timeframe_minutes: int = 15,
    fast: int = 12,
    slow: int = 48,
    range_band: float = 0.001,
) -> pd.DataFrame:
    """Build causal regimes from each completed book-mid timeframe bucket."""
    path = Path(database)
    if not path.is_file():
        raise FileNotFoundError(f"impulse replay database not found: {path}")
    bucket_ms = int(timeframe_minutes) * 60_000
    query = """
        WITH bucket_last AS (
            SELECT CAST(feature_time / ? AS INTEGER) AS bucket, MAX(id) AS row_id
            FROM feature_samples
            WHERE coin = ?
            GROUP BY bucket
        )
        SELECT bucket_last.bucket * ? AS bucket_start_ms, samples.mid AS close
        FROM bucket_last
        JOIN feature_samples AS samples ON samples.id = bucket_last.row_id
        ORDER BY bucket_start_ms
    """
    uri = f"file:{path.resolve()}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as connection:
        frame = pd.read_sql_query(
            query,
            connection,
            params=(bucket_ms, coin.upper(), bucket_ms),
        )
    if frame.empty:
        return pd.DataFrame(columns=["available_ts_ms", "close", "regime"])
    frame["available_ts_ms"] = frame["bucket_start_ms"] + bucket_ms
    frame["regime"] = detect_regime_ema(
        frame["close"],
        fast=fast,
        slow=slow,
        range_band=range_band,
    )
    return frame[["available_ts_ms", "close", "regime"]]


def load_completed_mid_bars(
    database: Path | str,
    *,
    coin: str,
    timeframe_minutes: int = 1,
) -> pd.DataFrame:
    """Aggregate L2 mid snapshots into causal completed OHLC bars."""
    path = Path(database)
    if not path.is_file():
        raise FileNotFoundError(f"impulse replay database not found: {path}")
    bucket_ms = int(timeframe_minutes) * 60_000
    query = """
        WITH aggregates AS (
            SELECT CAST(feature_time / ? AS INTEGER) AS bucket,
                   MIN(id) AS open_id, MAX(id) AS close_id,
                   MIN(mid) AS low, MAX(mid) AS high
            FROM feature_samples WHERE coin = ? GROUP BY bucket
        )
        SELECT aggregates.bucket * ? AS bucket_start_ms,
               opening.mid AS open, aggregates.high, aggregates.low,
               closing.mid AS close
        FROM aggregates
        JOIN feature_samples AS opening ON opening.id = aggregates.open_id
        JOIN feature_samples AS closing ON closing.id = aggregates.close_id
        ORDER BY bucket_start_ms
    """
    uri = f"file:{path.resolve()}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as connection:
        bars = pd.read_sql_query(
            query,
            connection,
            params=(bucket_ms, coin.upper(), bucket_ms),
        )
    bars["available_ts_ms"] = bars["bucket_start_ms"] + bucket_ms
    bars["timestamp"] = pd.to_datetime(bars["available_ts_ms"], unit="ms", utc=True)
    bars["volume"] = 0.0
    return bars


def attach_completed_bar_features(
    trades: pd.DataFrame,
    bars: pd.DataFrame,
) -> pd.DataFrame:
    """Attach the last completed replay bar's runtime-compatible features."""
    required = {"available_ts_ms", "timestamp", "open", "high", "low", "close"}
    missing = required - set(bars.columns)
    if missing:
        raise ValueError(f"replay bars missing columns: {sorted(missing)}")
    ordered_bars = bars.sort_values("available_ts_ms").reset_index(drop=True)
    feature_matrix = build_feature_matrix(ordered_bars)
    causal_features = pd.concat(
        [ordered_bars[["available_ts_ms"]], feature_matrix[FEATURE_NAMES]],
        axis=1,
    )
    featured = pd.merge_asof(
        trades.sort_values("entry_ts_ms"),
        causal_features,
        left_on="entry_ts_ms",
        right_on="available_ts_ms",
        direction="backward",
    )
    if "exit_ts_ms" not in featured.columns:
        raise ValueError("replay trades missing exit_ts_ms")
    featured["outcome_ts_ms"] = featured["exit_ts_ms"].astype("int64")
    featured["label"] = (featured["net_margin_pct"].astype(float) > 0.0).astype(int)
    return featured


def _as_float(value: object, default: float = 0.0) -> float:
    """Convert a persisted numeric feature without accepting non-finite text."""
    try:
        converted = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return converted if pd.notna(converted) else default


def _json_features(raw: object) -> dict[str, float]:
    """Parse the recorder's JSON feature payload into stable numeric columns."""
    parsed = json.loads(str(raw)) if raw else {}
    if not isinstance(parsed, dict):
        raise ValueError("decision features_json must contain a JSON object")
    return {name: _as_float(parsed.get(name)) for name in _JSON_FEATURES}


def _trade_record(
    entry: pd.Series,
    exit_row: pd.Series,
    *,
    fee_bps_side: float,
    leverage: float,
) -> dict[str, object]:
    """Build one completed replay trade from a matched event pair."""
    direction = str(entry["direction"])
    entry_px = _as_float(entry["current_mid"])
    exit_px = _as_float(exit_row["current_mid"])
    signed_move = exit_px - entry_px if direction == "long" else entry_px - exit_px
    gross_price_pct = signed_move / entry_px * 100.0
    round_trip_cost_pct = 2.0 * float(fee_bps_side) / 100.0
    record: dict[str, object] = {
        "entry_ts_ms": round(_as_float(entry["recorded_at"]) * 1_000.0),
        "exit_ts_ms": round(_as_float(exit_row["recorded_at"]) * 1_000.0),
        "direction": direction,
        "exit_event": str(exit_row["event_type"]),
        "entry_px": entry_px,
        "exit_px": exit_px,
        "gross_price_pct": gross_price_pct,
        "net_price_pct": gross_price_pct - round_trip_cost_pct,
        "net_margin_pct": (gross_price_pct - round_trip_cost_pct) * leverage,
    }
    for name in (
        "impulse_score",
        "momentum_score",
        "velocity_bps_1s",
        "velocity_bps_3s",
        "velocity_bps_5s",
        "acceleration_bps",
        "feature_age_ms",
    ):
        record[name] = _as_float(entry[name])
    record.update(_json_features(entry["features_json"]))
    return record


def pair_replay_trades(
    events: pd.DataFrame,
    *,
    fee_bps_side: float,
    leverage: float,
) -> tuple[pd.DataFrame, ReplayPairingStats]:
    """Pair sequential recorded entries/exits without inventing fills."""
    open_entry: pd.Series | None = None
    records: list[dict[str, object]] = []
    unmatched_exits = 0
    ignored_entries = 0
    for _, row in events.sort_values("recorded_at").iterrows():
        event = str(row["event_type"])
        if event.startswith("WOULD_ENTER_"):
            if open_entry is None:
                open_entry = row
            else:
                ignored_entries += 1
            continue
        if open_entry is None or str(open_entry["direction"]) != str(row["direction"]):
            unmatched_exits += 1
            continue
        records.append(
            _trade_record(
                open_entry,
                row,
                fee_bps_side=fee_bps_side,
                leverage=leverage,
            )
        )
        open_entry = None
    trades = pd.DataFrame(records)
    stats = ReplayPairingStats(
        source_events=len(events),
        completed_trades=len(trades),
        unmatched_exits=unmatched_exits,
        ignored_entries=ignored_entries,
        open_trade_at_end=open_entry is not None,
    )
    return trades, stats


def assign_completed_regimes(
    trades: pd.DataFrame,
    regimes: pd.DataFrame,
) -> pd.DataFrame:
    """Attach only regime buckets whose availability precedes each entry."""
    required = {"available_ts_ms", "regime"}
    missing = required - set(regimes.columns)
    if missing:
        raise ValueError(f"regime frame missing columns: {sorted(missing)}")
    left = trades.sort_values("entry_ts_ms").copy()
    right = regimes.sort_values("available_ts_ms").copy()
    return pd.merge_asof(
        left,
        right,
        left_on="entry_ts_ms",
        right_on="available_ts_ms",
        direction="backward",
    )


def _replay_metrics(rows: pd.DataFrame) -> dict[str, float | int]:
    """Summarize selected replay rows without applying acceptance gates."""
    if rows.empty:
        return {
            "trade_count": 0,
            "net_margin_pct": 0.0,
            "gross_price_pct": 0.0,
            "win_pct": 0.0,
            "max_drawdown_margin_pct": 0.0,
        }
    net = rows["net_margin_pct"].astype(float).to_numpy()
    curve = np.cumsum(net)
    drawdown = curve - np.maximum.accumulate(np.insert(curve, 0, 0.0))[1:]
    return {
        "trade_count": len(rows),
        "net_margin_pct": float(net.sum()),
        "gross_price_pct": float(rows["gross_price_pct"].astype(float).sum()),
        "win_pct": float((net > 0.0).mean() * 100.0),
        "max_drawdown_margin_pct": float(min(0.0, drawdown.min())),
    }


def _sample_filter_params(
    rng: np.random.Generator,
    trial_number: int,
) -> dict[str, float]:
    """Sample an entry filter, retaining pass-all as trial zero."""
    if trial_number == 0:
        return {
            "min_impulse_score": 0.0,
            "min_momentum_score": 0.0,
            "min_abs_velocity_5s": 0.0,
            "max_spread_bps": 1_000_000_000.0,
            "min_signed_obi_10": -1.0,
            "max_feature_age_ms": 1_000_000_000.0,
        }
    grids = {
        "min_impulse_score": [0.6, 0.7, 0.8, 0.9, 1.0],
        "min_momentum_score": [0.0, 0.2, 0.4, 0.5, 0.6, 0.7],
        "min_abs_velocity_5s": [0.0, 0.1, 0.25, 0.5, 1.0],
        "max_spread_bps": [0.25, 0.5, 1.0, 2.0, 4.0, 8.0],
        "min_signed_obi_10": [-1.0, -0.5, -0.25, 0.0, 0.25, 0.5],
        "max_feature_age_ms": [500.0, 1_000.0, 2_000.0, 3_000.0],
    }
    return {
        name: float(values[int(rng.integers(0, len(values)))])
        for name, values in grids.items()
    }


def _apply_replay_filter(
    rows: pd.DataFrame,
    params: dict[str, float],
) -> pd.DataFrame:
    """Apply a sampled causal entry filter to one direction/regime lane."""
    direction_sign = np.where(rows["direction"] == "long", 1.0, -1.0)
    signed_obi = rows["obi_10"].astype(float).to_numpy() * direction_sign
    mask = (
        (rows["impulse_score"].astype(float) >= params["min_impulse_score"])
        & (rows["momentum_score"].astype(float) >= params["min_momentum_score"])
        & (rows["velocity_bps_5s"].astype(float).abs() >= params["min_abs_velocity_5s"])
        & (rows["spread_bps"].astype(float) <= params["max_spread_bps"])
        & (signed_obi >= params["min_signed_obi_10"])
        & (rows["feature_age_ms"].astype(float) <= params["max_feature_age_ms"])
    )
    return rows.loc[mask]


def run_replay_autotune(
    trades: pd.DataFrame,
    *,
    lane: str,
    n_trials: int = 100,
    seed: int = 42,
    train_fraction: float = 0.70,
) -> dict[str, object]:
    """Tune replay entry filters and measure the locked winner on later data."""
    if lane not in _LANES:
        raise ValueError(f"unknown replay lane: {lane}")
    if n_trials < 1:
        raise ValueError("n_trials must be positive")
    regime, direction = _LANES[lane]
    lane_rows = trades.loc[
        (trades["regime"] == regime) & (trades["direction"] == direction)
    ].sort_values("entry_ts_ms")
    split = max(1, min(len(lane_rows), int(len(lane_rows) * train_fraction)))
    train = lane_rows.iloc[:split]
    test = lane_rows.iloc[split:]
    rng = np.random.default_rng(seed)
    trials: list[dict[str, object]] = []
    for number in range(n_trials):
        params = _sample_filter_params(rng, number)
        metrics = _replay_metrics(_apply_replay_filter(train, params))
        trials.append(
            {
                "trial_number": number,
                "status": "ok",
                "params": params,
                "metrics": metrics,
            }
        )
    active = [trial for trial in trials if trial["metrics"]["trade_count"] > 0]  # type: ignore[index]
    best = max(active, key=lambda trial: trial["metrics"]["net_margin_pct"])  # type: ignore[index]
    best_params = best["params"]
    if not isinstance(best_params, dict):
        raise RuntimeError("autotune trial parameters are malformed")
    oos = _replay_metrics(_apply_replay_filter(test, best_params))
    return {
        "lane": lane,
        "source_trade_count": len(lane_rows),
        "train_trade_count": len(train),
        "oos_trade_count": len(test),
        "n_trials": n_trials,
        "best_params": best_params,
        "best_train_metrics": best["metrics"],
        "oos_metrics": oos,
        "trials": trials,
    }
