#!/usr/bin/env python3
"""Run two frozen, report-only ETH/SOL low-timeframe challengers."""

from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.low_tf_bounded_challengers import (
    build_absorption_signals,
    build_three_drive_signals,
)
from hypervector.research.low_tf_bounded_screen import (
    BoundedCellResult,
    build_bounded_frozen_artifact,
)
from hypervector.research.low_tf_duckdb import load_low_timeframe_inputs
from hypervector.research.low_tf_l2_dataset import (
    LowTimeframeDatasetConfig,
    build_low_timeframe_dataset,
)
from hypervector.research.low_tf_multi_asset_contract import (
    LowTfResearchContract,
    complete_ohlcv_bars,
    default_low_tf_contract,
)
from hypervector.research.low_tf_multi_asset_features import build_low_tf_features
from hypervector.research.low_tf_multi_asset_replay import evaluate_low_tf_replay
from hypervector.research.low_tf_multi_asset_replay_models import (
    LowTfReplayConfig,
    LowTfReplayReport,
)
from hypervector.research.market_cipher_data import (
    attach_hourly_funding,
    load_verified_hourly_funding,
)

_FRICTION_SCENARIOS = {"nominal_13bps": 13.0, "stress_20bps": 20.0}
_SYMBOLS = {"ETH": 25.0, "SOL": 20.0}
_YEAR_ID = "20250728T000000000000Z_20260728T000000000000Z"
_GENERATOR_FILES = (
    "scripts/low_tf_bounded_development.py",
    "src/hypervector/data/oxa_storage.py",
    "src/hypervector/nautilus/hyperliquid_margin.py",
    "src/hypervector/research/low_tf_bounded_challengers.py",
    "src/hypervector/research/low_tf_bounded_screen.py",
    "src/hypervector/research/low_tf_duckdb.py",
    "src/hypervector/research/low_tf_l2_dataset.py",
    "src/hypervector/research/low_tf_multi_asset_contract.py",
    "src/hypervector/research/low_tf_multi_asset_features.py",
    "src/hypervector/research/low_tf_multi_asset_replay.py",
    "src/hypervector/research/low_tf_multi_asset_replay_exits.py",
    "src/hypervector/research/low_tf_multi_asset_replay_models.py",
    "src/hypervector/research/low_tf_multi_asset_replay_reporting.py",
    "src/hypervector/research/low_tf_multi_asset_replay_risk.py",
    "src/hypervector/research/low_tf_rsi_divergence.py",
    "src/hypervector/research/market_cipher_data.py",
    "src/hypervector/research/shared_portfolio_models.py",
    "src/hypervector/strategies/indicators.py",
    "pyproject.toml",
    "uv.lock",
)


def _parser() -> argparse.ArgumentParser:
    """Return the immutable report-only CLI contract."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument(
        "--database", type=Path, default=Path("data/research/market.duckdb")
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/logs/research/low_tf_bounded_development_20260812_v3"),
    )
    return parser


def main() -> int:
    """Evaluate fixed identities across all frozen partitions and publish once."""
    args = _parser().parse_args()
    output = Path(args.output).with_suffix(".json")
    if output.exists():
        raise FileExistsError(f"bounded challenger output exists: {output}")
    generator_identity = _generator_identity()
    contract = default_low_tf_contract()
    cells: list[BoundedCellResult] = []
    sources: dict[str, object] = {}
    for symbol, venue_max in _SYMBOLS.items():
        symbol_cells, source = _evaluate_symbol(
            symbol, venue_max, Path(args.data_root), Path(args.database), contract
        )
        cells.extend(symbol_cells)
        sources[symbol] = source
    start, _ = contract.segment("development")
    _, end = contract.segment("pseudo_holdout")
    artifact = build_bounded_frozen_artifact(
        run_id="low_tf_bounded_frozen_20260812_v3",
        start_utc=start.isoformat(),
        end_utc=end.isoformat(),
        cells=tuple(cells),
        source_identity=sources,
    )
    artifact["limitations"] = [
        "ETH absorption lacks continuous historical L2 and is not evaluated",
        "SOL absorption begins after the first complete 3h L2 warmup",
        "bar extrema do not encode intrabar stop/target ordering",
    ]
    artifact["generator_identity"] = generator_identity
    _require_unchanged_generator(generator_identity, _generator_identity())
    write_immutable_json(output, artifact)
    print(output.resolve())
    return 0


def _evaluate_symbol(
    symbol: str,
    venue_max: float,
    root: Path,
    database: Path,
    contract: LowTfResearchContract,
) -> tuple[list[BoundedCellResult], dict[str, object]]:
    """Evaluate one symbol without sharing portfolio state across partitions."""
    minute_path = root / "cache" / f"{symbol}_1m_365d.parquet"
    funding_path = _funding_path(root, symbol)
    minutes = pd.read_parquet(minute_path)
    features = build_low_tf_features(
        complete_ohlcv_bars(minutes, source_minutes=1, bar_minutes=5)
    )
    three_drive = build_three_drive_signals(features, symbol=symbol)
    absorption, absorption_source = _absorption_signals(symbol, database, contract)
    cells: list[BoundedCellResult] = []
    for partition in ("development", "validation", "pseudo_holdout"):
        start, end = contract.segment(partition)
        path = _replay_minutes(minutes, funding_path, start, end)
        for family_signals in (three_drive, absorption):
            cells.extend(
                _evaluate_family(
                    partition,
                    symbol,
                    venue_max,
                    path,
                    features,
                    _slice_signals(family_signals, start, end),
                )
            )
    source = {
        "bars_path": str(minute_path.resolve()),
        "bars_sha256": _file_sha256(minute_path),
        "funding_path": str(funding_path.resolve()),
        "funding_sha256": _file_sha256(funding_path),
        "absorption_source": absorption_source,
    }
    return cells, source


def _absorption_signals(
    symbol: str,
    database: Path,
    contract: LowTfResearchContract,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Build SOL L2 signals or return an explicit empty ETH identity."""
    if symbol != "SOL":
        return _empty_signals("l2_absorption_reversal_v1"), {
            "status": "unavailable_no_continuous_l2",
        }
    start, _ = contract.segment("development")
    _, end = contract.segment("pseudo_holdout")
    start = start + pd.Timedelta(hours=3)
    inputs = load_low_timeframe_inputs(
        database, symbol, start.to_pydatetime(), end.to_pydatetime()
    )
    dataset = build_low_timeframe_dataset(
        inputs.bars,
        inputs.trades,
        inputs.books,
        LowTimeframeDatasetConfig(symbol=symbol),
    )
    source = {
        "status": "resolved",
        "query_start_utc": inputs.query_start_utc.isoformat(),
        "query_end_utc": inputs.query_end_utc.isoformat(),
        "bars_rows": len(inputs.bars),
        "trades_rows": len(inputs.trades),
        "books_rows": len(inputs.books),
        "dataset_rows": len(dataset.rows),
        "excluded_book_bars": dataset.excluded_book_bars,
        "bars_sha256": _frame_sha256(inputs.bars),
        "trades_sha256": _frame_sha256(inputs.trades),
        "books_sha256": _frame_sha256(inputs.books),
    }
    return build_absorption_signals(dataset.rows, symbol=symbol), source


def _funding_path(root: Path, symbol: str) -> Path:
    """Return the exact verified one-year hourly funding bundle path."""
    return (
        root
        / "cache"
        / "vendor"
        / "hyperliquid"
        / symbol
        / f"{_YEAR_ID}_funding"
        / "funding.parquet"
    )


def _replay_minutes(
    minutes: pd.DataFrame,
    funding_path: Path,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Return one exact partition with verified hourly funding attached."""
    selected = minutes.loc[
        minutes["timestamp"].ge(start) & minutes["timestamp"].lt(end)
    ].copy()
    funding = load_verified_hourly_funding([funding_path], start, end)
    return attach_hourly_funding(selected.set_index("timestamp"), funding).reset_index()


def _slice_signals(
    signals: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Retain one half-open partition without changing signal identity."""
    if signals.empty:
        return signals
    decisions = pd.to_datetime(signals["decision_time_utc"], utc=True)
    return signals.loc[decisions.ge(start) & decisions.lt(end)].copy()


def _evaluate_family(
    partition: str,
    symbol: str,
    venue_max: float,
    minutes: pd.DataFrame,
    features: pd.DataFrame,
    signals: pd.DataFrame,
) -> list[BoundedCellResult]:
    """Return both sides and friction scenarios for one frozen family."""
    family = _family_identity(signals)
    cells: list[BoundedCellResult] = []
    for side in ("long", "short"):
        selected = signals.loc[signals["side"].eq(side)].copy()
        for friction, cost in _FRICTION_SCENARIOS.items():
            if selected.empty:
                cells.append(_empty_cell(partition, symbol, family, side, friction))
                continue
            config = LowTfReplayConfig(
                initial_equity=5_000.0,
                risk_fraction=0.005,
                maximum_margin_fraction=0.03,
                leverage=5.0,
                venue_max_leverage=venue_max,
                round_trip_cost_bps=cost,
                fee_round_trip_bps=9.0,
                reentry_cooldown_bars=1,
            )
            report = evaluate_low_tf_replay(minutes, features, selected, config)
            cells.append(
                _cell(partition, symbol, family, side, friction, len(selected), report)
            )
    return cells


def _cell(
    partition: str,
    symbol: str,
    family: str,
    side: str,
    friction: str,
    signals: int,
    report: LowTfReplayReport,
) -> BoundedCellResult:
    """Translate one replay into compact immutable metrics."""
    winners = [trade.net_pnl_usd for trade in report.trades if trade.net_pnl_usd > 0.0]
    without_largest = report.net_pnl_usd - (max(winners) if winners else 0.0)
    return BoundedCellResult(
        partition,
        symbol,
        family,
        side,
        friction,
        signals,
        report.completed_trades,
        report.wins,
        report.losses,
        report.net_pnl_usd,
        report.profit_factor,
        report.maximum_drawdown_pct,
        report.liquidations,
        len(report.rejections),
        without_largest,
    )


def _empty_cell(
    partition: str, symbol: str, family: str, side: str, friction: str
) -> BoundedCellResult:
    """Return an explicit zero-signal result without fabricating a replay."""
    return BoundedCellResult(
        partition,
        symbol,
        family,
        side,
        friction,
        0,
        0,
        0,
        0,
        0.0,
        None,
        0.0,
        0,
        0,
        0.0,
    )


def _family_identity(signals: pd.DataFrame) -> str:
    """Return the single family or its explicit empty placeholder identity."""
    if "family" not in signals or signals.empty:
        return str(signals.attrs.get("family", "l2_absorption_reversal_v1"))
    values = signals["family"].drop_duplicates().tolist()
    if len(values) != 1:
        raise ValueError("bounded signal frame must contain one family")
    return str(values[0])


def _empty_signals(family: str) -> pd.DataFrame:
    """Return an empty signal frame that preserves its family identity."""
    frame = pd.DataFrame(columns=["decision_time_utc", "family", "side"])
    frame.attrs["family"] = family
    return frame


def _file_sha256(path: Path) -> str:
    """Hash one immutable input without loading it into memory."""
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _generator_identity() -> dict[str, object]:
    """Return exact hashes for code and locked dependencies used by this run."""
    files: dict[str, dict[str, object]] = {}
    for name in _GENERATOR_FILES:
        path = Path(name)
        if not path.is_file():
            raise FileNotFoundError(f"generator dependency does not exist: {path}")
        files[name] = {"bytes": path.stat().st_size, "sha256": _file_sha256(path)}
    return {"method": "exact_loaded_dependency_files_sha256_v1", "files": files}


def _require_unchanged_generator(
    expected: dict[str, object], observed: dict[str, object]
) -> None:
    """Abort publication if any declared generator dependency changed."""
    if observed != expected:
        raise RuntimeError("generator changed during evaluation; output withheld")


def _frame_sha256(frame: pd.DataFrame) -> str:
    """Hash one ordered causal frame including labels and data types."""
    digest = sha256()
    digest.update("\x1f".join(map(str, frame.columns)).encode())
    digest.update("\x1f".join(map(str, frame.dtypes)).encode())
    values = pd.util.hash_pandas_object(frame, index=True, categorize=True)
    digest.update(values.to_numpy().tobytes())
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
