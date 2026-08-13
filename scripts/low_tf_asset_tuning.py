#!/usr/bin/env python3
"""Tune ETH/SOL bidirectional 5m/15m candidates without execution authority."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.low_tf_asset_tuning import (
    declared_tuning_trials,
    evaluate_tuning_trial,
    feature_config_for_entry,
    order_trial_results,
    screen_tuning_trial,
    select_development_trials,
    summarize_development_results,
)
from hypervector.research.low_tf_asset_tuning_journal import LowTfTuningJournal
from hypervector.research.low_tf_asset_tuning_models import (
    LowTfAssetTrial,
    TrendEntryShape,
    TuningTrialResult,
    TuningWindow,
    default_tuning_scenarios,
    default_tuning_windows,
)
from hypervector.research.low_tf_asset_tuning_reporting import build_tuning_artifact
from hypervector.research.low_tf_multi_asset_contract import (
    complete_ohlcv_bars,
    ordered_frame_sha256,
)
from hypervector.research.low_tf_multi_asset_features import build_low_tf_features
from hypervector.research.market_cipher_data import (
    attach_hourly_funding,
    load_verified_hourly_funding,
)

_YEAR_ID = "20250728T000000000000Z_20260728T000000000000Z"
_DEFAULT_RUN_ID = "eth_sol_bidirectional_5m15m_tuning_v1_20260805"


@dataclass(frozen=True)
class TuningAssetInput:
    """Explicit venue data and leverage identity for one tuned asset."""

    symbol: str
    venue_max_leverage: float
    bars_path: Path
    funding_path: Path


@dataclass(frozen=True)
class TuningAssetData:
    """Validated one-year source loaded once for all trials."""

    asset: TuningAssetInput
    minute_bars: pd.DataFrame
    five_minute_bars: pd.DataFrame
    source_identity: dict[str, object]


class _AppendSymbol(argparse.Action):
    """Replace default symbols on first explicit --symbol and then append."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str,
        option_string: str | None = None,
    ) -> None:
        current = getattr(namespace, self.dest)
        selected = [] if current == ["ETH", "SOL"] else list(current)
        selected.append(values)
        setattr(namespace, self.dest, selected)


def default_asset_inputs(
    data_root: Path,
    symbols: tuple[str, ...],
) -> tuple[TuningAssetInput, ...]:
    """Return year-matched Hyperliquid bars and funding for selected assets."""
    leverage = {"ETH": 25.0, "SOL": 20.0}
    normalized = tuple(symbol.upper() for symbol in symbols)
    if not normalized or len(set(normalized)) != len(normalized):
        raise ValueError("tuning symbols must be non-empty and unique")
    unsupported = sorted(set(normalized).difference(leverage))
    if unsupported:
        raise ValueError(f"unsupported tuning symbols: {unsupported}")
    return tuple(
        TuningAssetInput(
            symbol,
            leverage[symbol],
            data_root / "cache" / f"{symbol}_1m_365d.parquet",
            data_root
            / "cache"
            / "vendor"
            / "hyperliquid"
            / symbol
            / f"{_YEAR_ID}_funding"
            / "funding.parquet",
        )
        for symbol in normalized
    )


def build_parser() -> argparse.ArgumentParser:
    """Return the immutable report-only tuning argument parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--symbol",
        action=_AppendSymbol,
        choices=("ETH", "SOL"),
        default=["ETH", "SOL"],
    )
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--run-id", default=_DEFAULT_RUN_ID)
    parser.add_argument("--selected-per-group", type=int, default=3)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--reuse-development-run-id")
    parser.add_argument(
        "--journal",
        type=Path,
        default=Path("data/research/strategy_trials.duckdb"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(f"data/logs/research/{_DEFAULT_RUN_ID}.json"),
    )
    return parser


def load_asset_data(asset: TuningAssetInput) -> TuningAssetData:
    """Load and validate one complete venue year exactly once."""
    start, end = _full_window()
    source = _validated_source_bars(asset.bars_path, start, end)
    funding = load_verified_hourly_funding([asset.funding_path], start, end)
    minutes = attach_hourly_funding(
        source.set_index("timestamp"), funding
    ).reset_index()
    five = complete_ohlcv_bars(source, source_minutes=1, bar_minutes=5)
    five = attach_hourly_funding(five.set_index("bar_open_at"), funding).reset_index()
    identity = _source_identity(asset, source, funding, five)
    return TuningAssetData(asset, minutes, five, identity)


def run_tuning(
    inputs: tuple[TuningAssetInput, ...],
    *,
    run_id: str,
    selected_per_group: int,
    workers: int = 4,
) -> tuple[
    dict[str, object],
    tuple[LowTfAssetTrial, ...],
    tuple[TuningTrialResult, ...],
    tuple[LowTfAssetTrial, ...],
    tuple[TuningTrialResult, ...],
]:
    """Evaluate the frozen development matrix and later selected replays."""
    data = tuple(load_asset_data(asset) for asset in inputs)
    symbols = {item.asset.symbol for item in data}
    trials = tuple(
        trial for trial in declared_tuning_trials() if trial.symbol in symbols
    )
    _validate_workers(workers)
    development = _development_screen(data, trials, workers)
    summaries = summarize_development_results(trials, development)
    selected = select_development_trials(
        trials, summaries, per_group=selected_per_group
    )
    replay = _chronological_replays(data, selected, workers)
    sources = {item.asset.symbol: item.source_identity for item in data}
    artifact = build_tuning_artifact(
        run_id=run_id,
        source_identity=sources,
        trials=trials,
        development_results=development,
        development_summaries=summaries,
        selected_trials=selected,
        replay_results=replay,
    )
    return artifact, trials, development, selected, replay


def run_tuning_from_development(
    inputs: tuple[TuningAssetInput, ...],
    *,
    run_id: str,
    selected_per_group: int,
    workers: int,
    journal: LowTfTuningJournal,
    development_run_id: str,
) -> tuple[
    dict[str, object],
    tuple[LowTfAssetTrial, ...],
    tuple[TuningTrialResult, ...],
    tuple[LowTfAssetTrial, ...],
    tuple[TuningTrialResult, ...],
]:
    """Rerank immutable development evidence and replay new selections."""
    _validate_workers(workers)
    prior_sources, trials, development = journal.load_development_run(
        development_run_id
    )
    data = tuple(load_asset_data(asset) for asset in inputs)
    current_sources = {item.asset.symbol: item.source_identity for item in data}
    _validate_reused_sources(prior_sources, current_sources, trials)
    summaries = summarize_development_results(trials, development)
    selected = select_development_trials(
        trials, summaries, per_group=selected_per_group
    )
    replay = _chronological_replays(data, selected, workers)
    sources = {
        **current_sources,
        "_development_evidence": {
            "run_id": development_run_id,
            "reuse_scope": "immutable_broad_screen_metrics_and_trade_ledger",
        },
    }
    artifact = build_tuning_artifact(
        run_id=run_id,
        source_identity=sources,
        trials=trials,
        development_results=development,
        development_summaries=summaries,
        selected_trials=selected,
        replay_results=replay,
    )
    return artifact, trials, development, selected, replay


def _development_screen(
    data: tuple[TuningAssetData, ...],
    trials: tuple[LowTfAssetTrial, ...],
    workers: int,
) -> tuple[TuningTrialResult, ...]:
    jobs = tuple(
        (
            item,
            tuple(
                trial
                for trial in trials
                if trial.symbol == item.asset.symbol and trial.side == side
            ),
        )
        for item in data
        for side in ("long", "short")
    )
    if workers == 1:
        groups = tuple(_screen_asset_side(job) for job in jobs)
    else:
        with ProcessPoolExecutor(max_workers=min(workers, len(jobs))) as executor:
            groups = tuple(executor.map(_screen_asset_side, jobs))
    unordered = tuple(result for group in groups for result in group)
    return order_trial_results(trials, unordered)


def _screen_asset_side(
    job: tuple[TuningAssetData, tuple[LowTfAssetTrial, ...]],
) -> tuple[TuningTrialResult, ...]:
    asset_data, trials = job
    window = default_tuning_windows()[0]
    scenario = default_tuning_scenarios()[0]
    results: list[TuningTrialResult] = []
    cache = _feature_cache(asset_data.five_minute_bars, trials)
    bars = _scored_five_minute_bars(asset_data.five_minute_bars, window)
    for index, trial in enumerate(trials, start=1):
        features = _scored_features(cache[trial.entry], window)
        results.append(
            screen_tuning_trial(
                bars=bars,
                features=features,
                trial=trial,
                segment=window.name,
                scenario=scenario,
                venue_max_leverage=asset_data.asset.venue_max_leverage,
            )
        )
        if index % 144 == 0:
            print(
                f"development {trial.symbol} {trial.side}: {index}/{len(trials)}",
                flush=True,
            )
    return tuple(results)


def _chronological_replays(
    data: tuple[TuningAssetData, ...],
    selected: tuple[LowTfAssetTrial, ...],
    workers: int,
) -> tuple[TuningTrialResult, ...]:
    indexed = {item.asset.symbol: item for item in data}
    jobs = tuple((indexed[trial.symbol], trial) for trial in selected)
    if workers == 1:
        groups = tuple(_replay_trial(job) for job in jobs)
    else:
        with ProcessPoolExecutor(max_workers=min(workers, len(jobs))) as executor:
            groups = tuple(executor.map(_replay_trial, jobs))
    return tuple(result for group in groups for result in group)


def _replay_trial(
    job: tuple[TuningAssetData, LowTfAssetTrial],
) -> tuple[TuningTrialResult, ...]:
    item, trial = job
    features_all = build_low_tf_features(
        item.five_minute_bars,
        feature_config_for_entry(trial.entry),
    )
    results: list[TuningTrialResult] = []
    for window in default_tuning_windows():
        minutes = _scored_minutes(item.minute_bars, window)
        features = _scored_features(features_all, window)
        for scenario in default_tuning_scenarios():
            results.append(
                evaluate_tuning_trial(
                    minute_bars=minutes,
                    features=features,
                    trial=trial,
                    segment=window.name,
                    scenario=scenario,
                    venue_max_leverage=item.asset.venue_max_leverage,
                )
            )
    print(f"minute replay complete: {trial.trial_id}", flush=True)
    return tuple(results)


def _feature_cache(
    bars: pd.DataFrame,
    trials: tuple[LowTfAssetTrial, ...],
) -> dict[TrendEntryShape, pd.DataFrame]:
    entries = tuple(dict.fromkeys(trial.entry for trial in trials))
    return {
        entry: build_low_tf_features(bars, feature_config_for_entry(entry))
        for entry in entries
    }


def _validated_source_bars(
    path: Path,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"tuning bars do not exist: {path}")
    frame = pd.read_parquet(path)
    required = {"timestamp", "open", "high", "low", "close", "volume", "source"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"tuning bars missing columns: {missing}")
    times = pd.DatetimeIndex(frame["timestamp"])
    expected = pd.date_range(start, end, freq="1min", inclusive="left")
    if times.tz is None or not times.equals(expected):
        raise ValueError("tuning bars must exactly cover the frozen venue year")
    if not frame["source"].isin({"hl", "hl_gap_fill"}).all():
        raise ValueError("tuning bars contain a non-Hyperliquid source")
    return frame.reset_index(drop=True)


def _source_identity(
    asset: TuningAssetInput,
    minutes: pd.DataFrame,
    funding: pd.Series,
    five: pd.DataFrame,
) -> dict[str, object]:
    return {
        "symbol": asset.symbol,
        "bars_path": str(asset.bars_path.resolve()),
        "bars_sha256": _file_sha256(asset.bars_path),
        "funding_path": str(asset.funding_path.resolve()),
        "funding_sha256": _file_sha256(asset.funding_path),
        "minute_rows": len(minutes),
        "five_minute_rows": len(five),
        "gap_fill_rows": int(minutes["source"].eq("hl_gap_fill").sum()),
        "funding_events": len(funding),
        "ordered_minute_sha256": ordered_frame_sha256(minutes, time_column="timestamp"),
        "execution_authority": "none",
    }


def _scored_five_minute_bars(
    bars: pd.DataFrame,
    window: TuningWindow,
) -> pd.DataFrame:
    times = pd.DatetimeIndex(bars["bar_open_at"])
    selected = bars.loc[(times >= window.start_utc) & (times < window.end_utc)].copy()
    return selected.set_index("bar_open_at")


def _scored_features(
    features: pd.DataFrame,
    window: TuningWindow,
) -> pd.DataFrame:
    times = pd.DatetimeIndex(features["bar_open_at"])
    return features.loc[
        (times >= window.start_utc) & (times < window.end_utc)
    ].reset_index(drop=True)


def _scored_minutes(
    minutes: pd.DataFrame,
    window: TuningWindow,
) -> pd.DataFrame:
    times = pd.DatetimeIndex(minutes["timestamp"])
    return minutes.loc[
        (times >= window.start_utc) & (times < window.end_utc)
    ].reset_index(drop=True)


def _full_window() -> tuple[pd.Timestamp, pd.Timestamp]:
    windows = default_tuning_windows()
    return windows[0].start_utc, windows[-1].end_utc


def _validate_workers(workers: int) -> None:
    if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
        raise ValueError("tuning workers must be a positive integer")


def _validate_reused_sources(
    prior: dict[str, object],
    current: dict[str, dict[str, object]],
    trials: tuple[LowTfAssetTrial, ...],
) -> None:
    if {trial.symbol for trial in trials} != set(current):
        raise ValueError("reused development symbols do not match requested inputs")
    for symbol, identity in current.items():
        old = prior.get(symbol)
        if not isinstance(old, dict):
            raise ValueError(f"reused development source is missing {symbol}")
        for field in ("bars_sha256", "funding_sha256"):
            if old.get(field) != identity.get(field):
                raise ValueError(f"reused development {symbol} {field} mismatch")


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    """Persist one immutable artifact and append-only DuckDB experiment."""
    args = build_parser().parse_args()
    if args.output.exists():
        raise FileExistsError(f"tuning artifact already exists: {args.output}")
    symbols = tuple(args.symbol)
    inputs = default_asset_inputs(args.data_root, symbols)
    journal = LowTfTuningJournal(args.journal)
    if args.reuse_development_run_id is None:
        output = run_tuning(
            inputs,
            run_id=args.run_id,
            selected_per_group=args.selected_per_group,
            workers=args.workers,
        )
    else:
        output = run_tuning_from_development(
            inputs,
            run_id=args.run_id,
            selected_per_group=args.selected_per_group,
            workers=args.workers,
            journal=journal,
            development_run_id=args.reuse_development_run_id,
        )
    artifact, trials, development, selected, replay = output
    journal.write_run(
        run_id=args.run_id,
        source_identity=artifact["source_identity"],
        trials=trials,
        development_results=development,
        selected_trial_ids=tuple(trial.trial_id for trial in selected),
        replay_results=replay,
    )
    write_immutable_json(args.output, artifact)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
