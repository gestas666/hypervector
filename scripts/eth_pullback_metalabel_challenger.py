#!/usr/bin/env python3
"""Evaluate fixed ETH pullback entry models without execution authority."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import asdict
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    write_immutable_json,
    write_immutable_parquet,
)
from hypervector.ml.eth_pullback_challenger import (
    EthPullbackMetalabelResult,
    build_eth_pullback_model_rows,
    evaluate_eth_pullback_metalabel,
)
from hypervector.research.eth_pullback_replay import (
    ETH_PULLBACK_STRATEGY,
    EthPullbackReplay,
    replay_eth_precompression_pullback,
)
from hypervector.research.hype_breakout_entry_research import (
    HypeEntryPolicyEvidence,
)
from hypervector.research.hype_breakout_exit_market import HypeExitMarketEvidence

_BARS = Path("data/cache/ETH_1m_365d.parquet")
_FUNDING = Path(
    "data/cache/vendor/hyperliquid/ETH/"
    "20250728T000000000000Z_20260728T000000000000Z_funding/funding.parquet"
)
_DEVELOPMENT_END = "2026-05-28T12:00:00Z"
_FINAL_START = "2026-05-29T00:00:00Z"
_FINAL_END = "2026-07-28T00:00:00Z"


def build_parser() -> argparse.ArgumentParser:
    """Return the immutable report-only command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, default=_BARS)
    parser.add_argument("--funding", type=Path, default=_FUNDING)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--predictions-out", type=Path, required=True)
    return parser


def run(args: argparse.Namespace) -> tuple[dict[str, object], pd.DataFrame]:
    """Replay ETH once and return immutable report and prediction payloads."""
    _require_absent(args.out)
    _require_absent(args.predictions_out)
    _require_file(args.bars)
    _require_file(args.funding)
    bars = _slice_bars(pd.read_parquet(args.bars), end_utc=_FINAL_END)
    funding = pd.read_parquet(args.funding)
    replay = replay_eth_precompression_pullback(bars, funding)
    rows = build_eth_pullback_model_rows(replay.market, replay.report.trades)
    result = evaluate_eth_pullback_metalabel(
        rows,
        development_end_utc=_DEVELOPMENT_END,
        opened_final_start_utc=_FINAL_START,
        opened_final_end_utc=_FINAL_END,
    )
    predictions = _prediction_rows(result, rows)
    artifact = _artifact(args, replay, rows, result, len(predictions))
    return artifact, predictions


def _prediction_rows(
    result: EthPullbackMetalabelResult,
    rows: pd.DataFrame,
) -> pd.DataFrame:
    development = result.development.predictions.copy()
    development["phase"] = "development_oos"
    confirmation = result.final_predictions.copy()
    confirmation["phase"] = "opened_final_confirmation"
    predictions = pd.concat((development, confirmation), ignore_index=True, sort=False)
    identity_fields = ("side_sign", "breakout_relation_aligned")
    predictions = predictions.drop(columns=list(identity_fields), errors="ignore")
    identity = rows[["signal_time_utc", *identity_fields]].copy()
    identity["signal_time_utc"] = pd.to_datetime(identity["signal_time_utc"], utc=True)
    predictions["signal_time_utc"] = pd.to_datetime(
        predictions["signal_time_utc"], utc=True
    )
    predictions = predictions.merge(
        identity, on="signal_time_utc", validate="many_to_one"
    )
    predictions["breakout_relation"] = predictions["breakout_relation_aligned"].map(
        {1.0: "aligned", 0.0: "opposed"}
    )
    if predictions[[*identity_fields, "breakout_relation"]].isna().any().any():
        raise ValueError("ETH metalabel prediction mechanism identity is incomplete")
    return predictions


def _artifact(
    args: argparse.Namespace,
    replay: EthPullbackReplay,
    rows: pd.DataFrame,
    result: EthPullbackMetalabelResult,
    prediction_rows: int,
) -> dict[str, object]:
    artifact = dict(result.report)
    artifact.update(
        {
            "strategy_id": ETH_PULLBACK_STRATEGY,
            "symbol": "ETH",
            "execution_authority": "none",
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
            "model_installed": False,
            "prediction_rows": prediction_rows,
            "source_replay": _replay_evidence(replay, len(rows)),
            "data_evidence": _data_evidence((args.bars, args.funding)),
            "decision": "annotation_only_no_runtime_selection",
        }
    )
    return artifact


def _replay_evidence(
    replay: EthPullbackReplay,
    model_rows: int,
) -> dict[str, object]:
    return {
        "market_evidence": _plain_evidence(replay.market_evidence),
        "policy_evidence": _plain_evidence(replay.policy_evidence),
        "resolved_trades": len(replay.report.trades),
        "model_rows": model_rows,
        "source_scope": "full_history_causal_warmup_then_fixed_boundary_selection",
    }


def _plain_evidence(
    value: Mapping[str, object] | HypeExitMarketEvidence | HypeEntryPolicyEvidence,
) -> dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    return asdict(value)


def _data_evidence(paths: tuple[Path, ...]) -> dict[str, object]:
    return {
        str(path): {"path": str(path.resolve()), **file_evidence(path)}
        for path in paths
    }


def _slice_bars(bars: pd.DataFrame, *, end_utc: str) -> pd.DataFrame:
    if "timestamp" not in bars:
        raise ValueError("ETH metalabel bars are missing timestamp")
    timestamps = pd.to_datetime(bars["timestamp"], utc=True, errors="coerce")
    if timestamps.isna().any():
        raise ValueError("ETH metalabel bars contain invalid timestamps")
    output = bars.loc[timestamps.lt(pd.Timestamp(end_utc))].copy()
    if output.empty:
        raise ValueError("ETH metalabel replay window has no bars")
    return output


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"ETH metalabel source is missing: {path}")


def _require_absent(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"immutable ETH metalabel output exists: {path}")


def main(argv: Sequence[str] | None = None) -> int:
    """Publish prediction evidence first and its hash-linked report last."""
    args = build_parser().parse_args(argv)
    artifact, predictions = run(args)
    write_immutable_parquet(args.predictions_out, predictions)
    artifact["prediction_evidence"] = {
        "path": str(args.predictions_out.resolve()),
        **file_evidence(args.predictions_out),
        "rows": len(predictions),
    }
    write_immutable_json(args.out, artifact)
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "predictions": str(args.predictions_out),
                "prediction_rows": len(predictions),
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
