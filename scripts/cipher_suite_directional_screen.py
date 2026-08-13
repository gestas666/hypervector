#!/usr/bin/env python3
"""Run the immutable report-only Cipher A/B/DBSI directional screen."""

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

from hypervector.research.backtest_lab_cipher_adapter import (
    compute_cipher_bundle_components,
    compute_cipher_component_states,
    inspect_backtest_lab_sources,
)
from hypervector.research.cipher_suite_screen import (
    FROZEN_15M_EXIT_GRID,
    CipherExitSpec,
    CipherScreenReport,
    CipherScreenConfig,
    CipherScreenTrial,
    screen_cipher_suite,
)
from hypervector.research.cipher_suite_signals import (
    ALL_CIPHER_VARIANTS,
    CIPHER_BUNDLE_VARIANTS,
    CIPHER_VARIANTS,
    compose_cipher_bundle_entries,
    compose_cipher_entries,
)
from hypervector.research.cipher_suite_timeframes import (
    align_cipher_bundle_timeframes,
    resample_cipher_bars,
)
from hypervector.research.cipher_suite_duckdb import (
    CipherOhlcvInputs,
    load_cipher_ohlcv,
)


_SCHEMA_VERSION = "cipher_suite_directional_screen_v3"


def _parser() -> argparse.ArgumentParser:
    """Build the explicit report-only command contract."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True, choices=("BTC", "SOL"))
    parser.add_argument("--timeframe", choices=("5m", "15m"), default="5m")
    parser.add_argument(
        "--workflow",
        choices=("legacy_vote", "documented_bundle"),
        default="legacy_vote",
    )
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--backtest-lab-root", required=True, type=Path)
    parser.add_argument("--candidate", choices=ALL_CIPHER_VARIANTS)
    parser.add_argument("--side", choices=("long", "short"))
    parser.add_argument("--target-bps", type=float)
    parser.add_argument("--stop-bps", type=float)
    parser.add_argument("--horizon-bars", type=int)
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
    """Execute one immutable bounded Cipher suite research run."""
    args = _parser().parse_args(argv)
    output = Path(args.out)
    signals_path = output.with_suffix(".signals.parquet")
    trades_path = output.with_suffix(".trades.parquet")
    _ensure_outputs_available(output, signals_path, trades_path)
    start = _timestamp(str(args.start))
    end = _timestamp(str(args.end))
    bar_minutes = int(str(args.timeframe).removesuffix("m"))
    multiplier = bar_minutes // 5
    config, candidate, side = _screen_selection(args, bar_minutes)
    max_horizon = max(spec.horizon_bars for spec in config.exit_specs)
    history_multiplier = 3 if args.workflow == "documented_bundle" else multiplier
    inputs = load_cipher_ohlcv(
        Path(args.database),
        str(args.symbol),
        start,
        end,
        history_bars=240 * history_multiplier,
        horizon_bars=max_horizon * multiplier,
    )
    strategy_bars = resample_cipher_bars(inputs.bars, bar_minutes=bar_minutes)
    states = _components(
        inputs.bars,
        strategy_bars,
        Path(args.backtest_lab_root),
        bar_minutes,
        str(args.workflow),
    )
    signals = _windowed_signals(states, start, end, candidate, side, str(args.workflow))
    screen = screen_cipher_suite(strategy_bars, signals, config)
    output.parent.mkdir(parents=True, exist_ok=True)
    signals.to_parquet(signals_path, index=False)
    _trade_rows(screen).to_parquet(trades_path, index=False)
    report = _report(
        args,
        start,
        end,
        inputs,
        strategy_bars,
        states,
        signals,
        screen,
        inspect_backtest_lab_sources(Path(args.backtest_lab_root)),
        signals_path,
        trades_path,
    )
    output.write_text(
        json.dumps(_json_safe(report), indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote report-only Cipher suite artifact: {output}")
    return 0


def _ensure_outputs_available(output: Path, *sidecars: Path) -> None:
    existing = [path for path in (output, *sidecars) if path.exists()]
    if existing:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Cipher output exists: {joined}")


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Cipher timestamps must include a timezone")
    return parsed.astimezone(UTC)


def _screen_config(bar_minutes: int, workflow: str) -> CipherScreenConfig:
    candidates = (
        CIPHER_BUNDLE_VARIANTS if workflow == "documented_bundle" else CIPHER_VARIANTS
    )
    if bar_minutes == 5:
        return CipherScreenConfig(candidates=candidates, bar_minutes=5)
    return CipherScreenConfig(
        candidates=candidates, exit_specs=FROZEN_15M_EXIT_GRID, bar_minutes=15
    )


def _screen_selection(
    args: argparse.Namespace,
    bar_minutes: int,
) -> tuple[CipherScreenConfig, str | None, str | None]:
    workflow = str(args.workflow)
    if workflow == "documented_bundle" and bar_minutes != 5:
        raise ValueError("documented Cipher bundle requires 5m execution")
    allowed = (
        CIPHER_BUNDLE_VARIANTS if workflow == "documented_bundle" else CIPHER_VARIANTS
    )
    if args.candidate is not None and args.candidate not in allowed:
        raise ValueError(f"candidate {args.candidate} is invalid for {workflow}")
    values = (
        args.candidate,
        args.side,
        args.target_bps,
        args.stop_bps,
        args.horizon_bars,
    )
    if all(value is None for value in values):
        return _screen_config(bar_minutes, workflow), None, None
    if any(value is None for value in values):
        raise ValueError(
            "frozen Cipher selection requires candidate, side, and exit spec"
        )
    spec = CipherExitSpec(
        float(args.target_bps), float(args.stop_bps), int(args.horizon_bars)
    )
    config = CipherScreenConfig(
        candidates=(str(args.candidate),),
        exit_specs=(spec,),
        bar_minutes=bar_minutes,
    )
    return config, str(args.candidate), str(args.side)


def _components(
    source_bars: pd.DataFrame,
    strategy_bars: pd.DataFrame,
    root: Path,
    bar_minutes: int,
    workflow: str,
) -> pd.DataFrame:
    """Compute either archived votes or the documented A15/B5 bundle."""
    if workflow == "legacy_vote":
        return compute_cipher_component_states(
            strategy_bars, root, bar_minutes=bar_minutes
        )
    execution = compute_cipher_bundle_components(
        strategy_bars, root, bar_minutes=bar_minutes
    )
    trend_bars = resample_cipher_bars(source_bars, bar_minutes=15)
    trend = compute_cipher_bundle_components(trend_bars, root, bar_minutes=15)
    return align_cipher_bundle_timeframes(execution, trend, trend_minutes=15)


def _windowed_signals(
    states: pd.DataFrame,
    start: datetime,
    end: datetime,
    candidate: str | None,
    side: str | None,
    workflow: str,
) -> pd.DataFrame:
    entries = (
        compose_cipher_bundle_entries(states)
        if workflow == "documented_bundle"
        else compose_cipher_entries(states)
    )
    eligible = entries["signal_time_utc"].ge(start) & entries["signal_time_utc"].lt(end)
    if candidate is not None:
        eligible &= entries["candidate"].eq(candidate)
    if side is not None:
        eligible &= entries["side"].eq(side)
    return (
        entries.loc[eligible]
        .sort_values(["signal_time_utc", "candidate", "side"])
        .reset_index(drop=True)
    )


def _trade_rows(screen: CipherScreenReport) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for trial in screen.trials:
        for trade in trial.trades:
            row = asdict(trade)
            row["candidate"] = trial.candidate
            row["exit_spec"] = trial.exit_spec.identity
            rows.append(row)
    columns = [
        "candidate",
        "exit_spec",
        "signal_ts_ms",
        "entry_ts_ms",
        "outcome_ts_ms",
        "side",
        "entry_price",
        "exit_price",
        "status",
        "gross_return_bps",
        "fee_bps",
        "net_return_bps",
        "ambiguous",
    ]
    return pd.DataFrame(rows, columns=columns)


def _report(
    args: argparse.Namespace,
    start: datetime,
    end: datetime,
    inputs: CipherOhlcvInputs,
    strategy_bars: pd.DataFrame,
    states: pd.DataFrame,
    signals: pd.DataFrame,
    screen: CipherScreenReport,
    source_identity: dict[str, str],
    signals_path: Path,
    trades_path: Path,
) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "symbol": str(args.symbol),
        "timeframe": str(args.timeframe),
        "workflow": str(args.workflow),
        "trend_timeframe": ("15m" if args.workflow == "documented_bundle" else None),
        "segment": str(args.segment),
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "report_only": screen.report_only,
        "execution_authority": screen.execution_authority,
        "place_attempted": screen.place_attempted,
        "selection_status": (
            "frozen_single_cell" if args.candidate else "frozen_grid_unpromoted"
        ),
        "frozen_selection": {
            "candidate": args.candidate,
            "side": args.side,
            "target_bps": args.target_bps,
            "stop_bps": args.stop_bps,
            "horizon_bars": args.horizon_bars,
        },
        "source_identity": source_identity,
        "fidelity_corrections": [
            "cipher_a_ema11_ema34_ribbon_is_trend_environment",
            "cipher_b_extreme_wavetrend_cross_is_entry_pulse",
            "closed_15m_a_context_aligned_to_5m_b_trigger",
            "cipher_b_wavetrend_9_12_3",
            "cipher_b_cross_direction_and_wt2_extremes",
            "dbsi_cci_uses_close",
            "dbsi_mfi_uses_close",
            "dbsi_aroon_uses_14_bars",
            "dbsi_keltner_basis_uses_ema20",
        ],
        "friction": {
            "maker_entry_bps": 1.5,
            "maker_target_exit_bps": 1.5,
            "taker_stop_timeout_exit_bps": 4.5,
        },
        "input_identity": {
            "bars_sha256": _frame_sha256(inputs.bars),
            "query_start_utc": inputs.query_start_utc.isoformat(),
            "query_end_utc": inputs.query_end_utc.isoformat(),
        },
        "row_counts": {
            "bars": len(inputs.bars),
            "strategy_bars": len(strategy_bars),
            "state_rows": len(states),
            "signals": len(signals),
            "signals_by_candidate": {
                str(key): int(value)
                for key, value in signals["candidate"].value_counts().items()
            },
            "trials": len(screen.trials),
        },
        "trials": [_trial_summary(trial) for trial in screen.trials],
        "leaders": _leaders(screen),
        "sidecars": {
            "signals": _sidecar(signals_path),
            "trades": _sidecar(trades_path),
        },
    }


def _trial_summary(trial: CipherScreenTrial) -> dict[str, object]:
    return {
        "candidate": trial.candidate,
        "exit_spec": asdict(trial.exit_spec),
        "exit_spec_id": trial.exit_spec.identity,
        "trade_count": trial.trade_count,
        "wins": trial.wins,
        "losses": trial.losses,
        "net_pnl_bps": trial.net_pnl_bps,
        "profit_factor": trial.profit_factor,
        "max_drawdown_bps": trial.max_drawdown_bps,
        "total_fee_bps": trial.total_fee_bps,
        "expired_occupied_signals": trial.expired_occupied_signals,
        "censored_signals": trial.censored_signals,
        "timeout_trades": trial.timeout_trades,
        "ambiguous_trades": trial.ambiguous_trades,
        "monthly_net_bps": trial.monthly_net_bps,
    }


def _leaders(screen: CipherScreenReport) -> list[dict[str, object]]:
    active = [trial for trial in screen.trials if trial.trade_count > 0]
    ranked = sorted(
        active,
        key=lambda trial: (
            trial.profit_factor if trial.profit_factor is not None else -math.inf,
            trial.net_pnl_bps,
            trial.trade_count,
        ),
        reverse=True,
    )
    return [_trial_summary(trial) for trial in ranked[:10]]


def _frame_sha256(frame: pd.DataFrame) -> str:
    digest = sha256()
    digest.update("\x1f".join(map(str, frame.columns)).encode())
    values = pd.util.hash_pandas_object(frame, index=False, categorize=True)
    digest.update(values.to_numpy().tobytes())
    return digest.hexdigest()


def _sidecar(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": _file_sha256(path)}


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        number = float(value)
        return number if math.isfinite(number) else None
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
