#!/usr/bin/env python3
"""Screen one causal consolidation-wick stop on the current source lead."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_candles import repair_candle_cadence
from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hypervelocity_candidate_eval import CandidateBarrierConfig
from hypervector.research.hypervelocity_stop_counterfactual import (
    evaluate_consolidation_wick_stops,
)
from hypervector.strategies.indicators import bbwp

_BBWP_LENGTH = 20
_BBWP_LOOKBACK = 240
_BBWP_THRESHOLD = 25.0
_MAX_GAP_FILL_MINUTES = 30
_CANDLE_COLUMNS = ("open", "high", "low", "close", "volume")
_REQUIRED_TRADE_FIELDS = {
    "direction",
    "signal_time_utc",
    "entry_time_utc",
    "exit_time_utc",
    "status",
    "entry_price",
    "entry_quantity",
    "liquidation_price",
    "net_pnl",
    "funding_cashflow",
}
_SOURCE_CONTRACT: dict[str, object] = {
    "candidate": "source_follow_minrange12_continuous_v1",
    "minimum_signal_range_bps": 12.0,
    "margin_fraction": 0.50,
    "leverage": 30.0,
    "gross_margin_target_pct": 8.0,
    "maximum_hold_seconds": 86_400.0,
    "execution_authority": "none",
    "model_authority": "observe",
}


def experiment_contract() -> dict[str, object]:
    """Return the immutable first-stage wick-screen identity."""
    return {
        "candidate": "source_follow_minrange12_consolidation_wick_screen_v1",
        "report_only": True,
        "runtime_strategy_changed": False,
        "execution_authority": "none",
        "model_authority": "observe",
        "stateful_replay_performed": False,
        "bbwp_length": _BBWP_LENGTH,
        "bbwp_lookback": _BBWP_LOOKBACK,
        "bbwp_threshold": _BBWP_THRESHOLD,
        "maximum_gap_fill_minutes": _MAX_GAP_FILL_MINUTES,
        "stop_buffer_bps": 0.0,
        "trigger_reference": "hyperliquid_mark_price",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-artifact", type=Path, required=True)
    parser.add_argument("--candles", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _read_payload(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("source artifact must contain a JSON object")
    _validate_source_payload(value)
    return value


def _validate_source_payload(payload: dict[str, object]) -> None:
    if payload.get("schema") != "hypervelocity_source_continuous_production_replay_v1":
        raise ValueError("source artifact must be a continuous production replay")
    if payload.get("report_only") is not True:
        raise ValueError("source artifact must be report-only")
    if payload.get("runtime_strategy_changed") is not False:
        raise ValueError("source artifact must not change runtime strategy")
    contract = payload.get("experiment_contract")
    if not isinstance(contract, dict):
        raise ValueError("source artifact is missing experiment_contract")
    mismatches = [
        key
        for key, expected in _SOURCE_CONTRACT.items()
        if contract.get(key) != expected
    ]
    if mismatches:
        raise ValueError(
            "source artifact does not match the frozen current lead: "
            + ", ".join(mismatches)
        )
    replay = payload.get("production_replay")
    if not isinstance(replay, dict) or replay.get("open_positions") != 0:
        raise ValueError("source artifact must finish with zero open positions")
    trades = replay.get("trades")
    if not isinstance(trades, list):
        raise ValueError("source artifact is missing production replay trades")
    for position, trade in enumerate(trades):
        if not isinstance(trade, dict):
            raise ValueError(f"source trade {position} must be a JSON object")
        missing = _REQUIRED_TRADE_FIELDS.difference(trade)
        if missing:
            raise ValueError(
                f"source trade {position} is missing fields: {sorted(missing)}"
            )


def _lifecycle_frame(payload: dict[str, object]) -> pd.DataFrame:
    replay = payload["production_replay"]
    if not isinstance(replay, dict):
        raise ValueError("source artifact is missing production_replay")
    trades = replay["trades"]
    if not isinstance(trades, list) or not trades:
        raise ValueError("source artifact requires at least one resolved trade")
    frame = pd.DataFrame(trades).rename(
        columns={
            "entry_quantity": "quantity",
            "exit_time_utc": "outcome_time_utc",
        }
    )
    return frame


def _qualification(screen: dict[str, object]) -> dict[str, object]:
    pnl_improved = float(screen["net_pnl_delta_usd"]) > 0.0
    liquidation_improved = int(screen["liquidations_avoided"]) > 0
    qualified = pnl_improved and liquidation_improved
    return {
        "qualified": qualified,
        "pnl_improved": pnl_improved,
        "liquidation_improved": liquidation_improved,
        "next_action": (
            "plan_stateful_mark_triggered_replay"
            if qualified
            else "reject_consolidation_wick_candidate"
        ),
    }


def _coverage(bars: pd.DataFrame, lifecycles: pd.DataFrame) -> dict[str, object]:
    signals = pd.to_datetime(lifecycles["signal_time_utc"], utc=True, format="ISO8601")
    outcomes = pd.to_datetime(
        lifecycles["outcome_time_utc"], utc=True, format="ISO8601"
    )
    required_warmup = pd.Timedelta(minutes=_BBWP_LENGTH + _BBWP_LOOKBACK)
    if bars.index[0] > signals.min() - required_warmup:
        raise ValueError("venue candles do not provide full BBWP warmup")
    if bars.index[-1] + pd.Timedelta(minutes=1) < outcomes.max():
        raise ValueError("venue candles end before the final lifecycle outcome")
    return {
        "first_candle_utc": bars.index[0].isoformat(),
        "last_candle_utc": bars.index[-1].isoformat(),
        "first_signal_utc": signals.min().isoformat(),
        "last_outcome_utc": outcomes.max().isoformat(),
        "candle_count": len(bars),
        "bbwp_warmup_minutes": int(required_warmup.total_seconds() / 60),
    }


def _load_repaired_candles(
    paths: list[Path],
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Load venue candles and explicitly repair bounded no-trade minutes."""
    if not paths:
        raise ValueError("at least one Hyperliquid candle file is required")
    frames: list[pd.DataFrame] = []
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"Hyperliquid candle file is missing: {path}")
        frame = pd.read_parquet(path)
        required = {"timestamp", "source", *_CANDLE_COLUMNS}
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"Hyperliquid candles missing: {sorted(missing)}")
        if not frame["source"].astype(str).isin(("hl", "hl_gap_fill")).all():
            raise ValueError(f"non-Hyperliquid candle source in {path}")
        frames.append(frame.loc[:, list(required)])
    combined = pd.concat(frames, ignore_index=True)
    timestamps = pd.to_datetime(combined["timestamp"], utc=True)
    if timestamps.duplicated().any():
        raise ValueError("Hyperliquid candle timestamps must be unique")
    start = timestamps.min().to_pydatetime()
    end = (timestamps.max() + pd.Timedelta(minutes=1)).to_pydatetime()
    repaired, gap_fills = repair_candle_cadence(
        combined,
        start=start,
        end=end,
        max_gap_minutes=_MAX_GAP_FILL_MINUTES,
    )
    bars = repaired.set_index("timestamp").loc[:, list(_CANDLE_COLUMNS)]
    return bars, {
        "native_candle_rows": len(combined),
        "gap_fill_rows": gap_fills,
    }


def _report(args: argparse.Namespace) -> dict[str, object]:
    payload = _read_payload(args.source_artifact)
    lifecycles = _lifecycle_frame(payload)
    bars, provenance = _load_repaired_candles(args.candles)
    coverage = {**_coverage(bars, lifecycles), **provenance}
    percentile, _ = bbwp(
        bars["close"],
        bb_length=_BBWP_LENGTH,
        lookback=_BBWP_LOOKBACK,
    )
    decisions = pd.DataFrame({"bbwp_percentile": percentile}, index=bars.index)
    config = CandidateBarrierConfig(
        initial_equity=15_000.0,
        margin_fraction=0.50,
        leverage=30.0,
        target_margin_pct=8.0,
        maker_fee_rate=0.00015,
        liquidation_fee_rate=0.00045,
    )
    screen = evaluate_consolidation_wick_stops(
        bars,
        decisions,
        lifecycles,
        threshold=_BBWP_THRESHOLD,
        config=config,
    ).to_dict()
    return {
        "schema": "hypervelocity_source_wick_screen_v1",
        "experiment_contract": experiment_contract(),
        "source_evidence": {
            "artifact": file_evidence(args.source_artifact),
            "candles": [file_evidence(path) for path in args.candles],
        },
        "coverage": coverage,
        "screen": screen,
        "qualification": _qualification(screen),
        "limitations": [
            "This fixed-lifecycle screen does not change stateful re-entry.",
            "Completed 1m highs cannot resolve intraminute mark/BBO ordering.",
            "Hyperliquid mark triggers and depth-aware stop slippage are not replayed.",
            "Counterfactual funding is retained only in the original lifecycle PnL.",
        ],
        "venue_semantics": {
            "trigger": "mark_price",
            "market_tpsl_slippage_tolerance_pct": 10.0,
            "source": (
                "https://hyperliquid.gitbook.io/hyperliquid-docs/trading/"
                "take-profit-and-stop-loss-orders-tp-sl"
            ),
        },
    }


def main(argv: list[str] | None = None) -> int:
    """Write one immutable current-lead consolidation-wick screen."""
    args = _parser().parse_args(argv)
    if args.out.exists():
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_immutable_json(args.out, _report(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
