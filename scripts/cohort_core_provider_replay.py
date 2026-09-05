"""Extract current core-provider decisions without simulating account returns."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
import json

import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    publish_immutable_directory,
    write_immutable_json,
    write_immutable_parquet,
)
from hypervector.live.multi_asset_default_collectors import build_default_collector
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    StrategyProviderConfig,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_market_bars import merge_one_minute_bars
from hypervector.research.cohort_core_provider_replay import (
    CoreProviderBatch,
    CoreReplayWindow,
    evaluation_contract,
    iter_core_provider_batches,
)

_CONTRACTS = {
    "BTC": "liquidity_sweep_long_1h_stop60_target60_v2",
    "ETH": "eth_range_onset_long_dual_mtf_v2",
    "SOL": "sol_range_onset_short_dual_mtf_v2",
    "HYPE": "hype_breakout_compression_alignment_bidirectional_v2",
}
_MINUTE_MS = 60_000
_NOON_MINUTE = 12 * 60
_MINUTES_PER_DAY = 24 * 60


def main(argv: Sequence[str] | None = None) -> int:
    """Publish daily decisions, source hashes, and rolling-window parity checks."""
    args = _parser().parse_args(argv)
    config = load_multi_asset_live_config(args.config, mode="observe")
    window = CoreReplayWindow(
        pd.Timestamp(args.start), pd.Timestamp(args.end), config.lookback_days
    )
    providers = _providers(config)
    sources = _sources(args.config, args.data_root)

    def publish(staging: Path) -> None:
        reports = [
            _extract(
                symbol,
                provider,
                config,
                window,
                args.data_root,
                args.backtest_lab_root,
                staging,
            )
            for symbol, provider in providers.items()
        ]
        if _sources(args.config, args.data_root) != sources:
            raise ValueError("core replay source/code bytes changed during extraction")
        write_immutable_json(
            staging / "manifest.json",
            _manifest(config, window, sources, reports),
        )

    publish_immutable_directory(args.out_dir, publish)
    print(json.dumps({"artifact": str(args.out_dir.resolve())}), flush=True)
    return 0


def _manifest(
    config: MultiAssetLiveConfig,
    window: CoreReplayWindow,
    sources: dict[str, object],
    reports: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "execution_authority": "none",
        "profitability_evaluated": False,
        "profile_fingerprint": config.profile_fingerprint,
        "decision_bounds": {
            "start_exclusive": str(window.start),
            "end_inclusive": str(window.end),
        },
        "sources": sources,
        "routes": reports,
        "limitations": [
            "Daily batching can differ from rolling live history; consult parity.",
            "Parity covers every batch-actionable row and daily noon controls, not every minute.",
            "Gap-filled inputs are flagged, not represented as native execution evidence.",
            "No private fills, funding, marked portfolio returns or HIP-3 parity are inferred.",
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--backtest-lab-root", type=Path, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser


def _providers(config: MultiAssetLiveConfig) -> dict[str, StrategyProviderConfig]:
    output = {}
    for symbol, strategy_id in _CONTRACTS.items():
        selected = [row for row in config.providers if symbol in row.execution_symbols]
        if len(selected) != 1 or selected[0].strategy_id != strategy_id:
            raise ValueError(
                f"core replay requires the frozen current provider: {symbol}"
            )
        output[symbol] = selected[0]
    return output


def _sources(config: Path, data_root: Path) -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    paths = [config, Path(__file__), root / "uv.lock"]
    paths.extend(root.joinpath("src/hypervector").rglob("*.py"))
    paths.extend(
        data_root / "cache" / f"{symbol}_1m_365d.parquet" for symbol in _CONTRACTS
    )
    return {str(path.resolve()): file_evidence(path) for path in sorted(set(paths))}


def _extract(
    symbol: str,
    provider: StrategyProviderConfig,
    config: MultiAssetLiveConfig,
    window: CoreReplayWindow,
    data_root: Path,
    lab: Path,
    staging: Path,
) -> dict[str, object]:
    bars = pd.read_parquet(data_root / "cache" / f"{symbol}_1m_365d.parquet")
    collector = build_default_collector(provider, config, lab)
    batches = []
    parity = []
    for batch in iter_core_provider_batches(bars, symbol, window, collector):
        rows = [evaluation_contract(row) for row in batch.evaluations]
        relative = Path(symbol) / f"{batch.start.strftime('%Y%m%dT%H%M')}.parquet"
        write_immutable_parquet(staging / relative, pd.DataFrame(rows))
        batches.append(_batch_report(batch, relative, staging))
        parity.extend(_parity(batch, bars, symbol, provider, config, lab))
        print(
            json.dumps(
                {"symbol": symbol, "through": str(batch.end), "decisions": len(rows)}
            ),
            flush=True,
        )
    parity_path = Path(symbol) / "rolling_parity.json"
    write_immutable_json(staging / parity_path, parity)
    return {
        "symbol": symbol,
        "strategy_id": provider.strategy_id,
        "batches": batches,
        "parity_path": str(parity_path),
        "parity_checks": len(parity),
        "parity_mismatches": sum(bool(row["differences"]) for row in parity),
    }


def _batch_report(
    batch: CoreProviderBatch,
    relative: Path,
    staging: Path,
) -> dict[str, object]:
    return {
        "start_exclusive": str(batch.start),
        "end_inclusive": str(batch.end),
        "decisions": len(batch.evaluations),
        "eligible_entries": sum(row.eligible for row in batch.evaluations),
        "exit_evaluations": sum(bool(row.exit_sides) for row in batch.evaluations),
        "input_minutes": batch.input_minutes,
        "missing_input_minutes": batch.missing_input_minutes,
        "gap_filled_input_minutes": batch.gap_filled_input_minutes,
        "path": str(relative),
        **file_evidence(staging / relative),
    }


def _parity(
    batch: CoreProviderBatch,
    bars: pd.DataFrame,
    symbol: str,
    provider: StrategyProviderConfig,
    config: MultiAssetLiveConfig,
    lab: Path,
) -> list[dict[str, object]]:
    output = []
    for row in batch.evaluations:
        minute = row.decision_time_ms // _MINUTE_MS % _MINUTES_PER_DAY
        if not (row.eligible or row.exit_sides or minute == _NOON_MINUTE):
            continue
        at = pd.Timestamp(row.decision_time_ms, unit="ms", tz="UTC")
        inputs = merge_one_minute_bars(
            None,
            bars.loc[bars.timestamp.lt(at)],
            row.decision_time_ms,
            config.lookback_days,
        )
        collector = build_default_collector(provider, config, lab)
        live = collector(
            inputs,
            symbol=symbol,
            observed_at=at,
            after_decision_time_ms=row.decision_time_ms - 1,
        )
        expected = evaluation_contract(row)
        actual = (
            evaluation_contract(live.evaluations[0])
            if len(live.evaluations) == 1
            else {}
        )
        differences = [key for key in expected if expected[key] != actual.get(key)]
        output.append(
            {
                "at": str(at),
                "differences": differences,
                "batch": expected,
                "rolling": actual,
            }
        )
    return output


if __name__ == "__main__":
    raise SystemExit(main())
