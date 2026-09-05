#!/usr/bin/env python3
"""Publish the V62 research-only HYPE aligned-route exit review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    write_immutable_json,
    write_immutable_parquet,
)
from hypervector.research.hype_breakout_exit_experiment import split_hype_exit_market
from hypervector.research.hype_breakout_exit_market import build_hype_exit_market
from hypervector.research.hype_breakout_exit_models import HypeExitReplayConfig
from hypervector.research.hype_compression_alignment_replay import (
    build_hype_compression_alignment_markets,
)
from hypervector.research.v62_hype_alignment_profit_lock import (
    V62HypeProfitLockReview,
    build_v62_hype_alignment_profit_lock,
    v62_candidate_orderbook_coverage,
)

_BARS = Path("data/cache/HYPE_1m_365d.parquet")
_FUNDING = Path(
    "data/cache/vendor/hyperliquid/HYPE/"
    "20250728T000000000000Z_20260728T000000000000Z_funding/funding.parquet"
)
_BOOK_AUDIT = Path(
    "data/logs/research/hype_breakout_l2_signal_windows_audit_v1/index.parquet"
)
_BOOK_RESEARCH = Path(
    "docs/research-journal/v53-hype-l2-ridge-prospective-closure-v1.json"
)
_TAPE_RESEARCH = Path("docs/research-journal/venue-native-1m-orderflow-impulse-v1.json")
_ALIGNMENT_POLICY = "compression_5m50_1m40_pullback"


def build_parser() -> argparse.ArgumentParser:
    """Build the immutable report-only command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, default=_BARS)
    parser.add_argument("--funding", type=Path, default=_FUNDING)
    parser.add_argument("--book-audit", type=Path, default=_BOOK_AUDIT)
    parser.add_argument("--book-research", type=Path, default=_BOOK_RESEARCH)
    parser.add_argument("--tape-research", type=Path, default=_TAPE_RESEARCH)
    parser.add_argument("--fold-count", type=int, default=5)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def execution_config() -> HypeExitReplayConfig:
    """Return the exact V61 HYPE aligned-route execution assumptions."""
    return HypeExitReplayConfig(
        stop_bps=80.0,
        maximum_hold_minutes=480,
        maximum_hold_policy="extend_while_regime_supported",
        hard_maximum_hold_minutes=1_440,
        exit_on_opposite_signal=True,
    )


def run(args: argparse.Namespace) -> dict[str, object]:
    """Recompute the candidate and bind local book/trade research evidence."""
    trade_path = _trade_path(args.out)
    _require_absent((args.out, trade_path))
    sources = _source_paths(args)
    for path in sources:
        _require_file(path)
    book_research = _json_object(args.book_research)
    tape_research = _json_object(args.tape_research)
    _validate_prior_research(book_research, tape_research)
    market, _ = build_hype_exit_market(
        pd.read_parquet(args.bars),
        pd.read_parquet(args.funding),
    )
    config = execution_config()
    development, _holdout, split = split_hype_exit_market(market, config, 60)
    alignment = build_hype_compression_alignment_markets(
        development,
        frozen_policy_id=_ALIGNMENT_POLICY,
    )
    review = build_v62_hype_alignment_profit_lock(
        alignment.markets["aligned_only"],
        config=config,
        fold_count=args.fold_count,
    )
    report = _complete_report(
        args,
        review,
        split,
        alignment.accounting,
        book_research,
        tape_research,
        sources,
    )
    write_immutable_parquet(trade_path, review.trade_rows)
    report["output_evidence"] = {
        "trade_rows": {"path": str(trade_path), **file_evidence(trade_path)}
    }
    write_immutable_json(args.out, report)
    return report


def _complete_report(
    args: argparse.Namespace,
    review: V62HypeProfitLockReview,
    split: dict[str, object],
    accounting: dict[str, int],
    book_research: dict[str, object],
    tape_research: dict[str, object],
    sources: tuple[Path, ...],
) -> dict[str, object]:
    report = dict(review.report)
    audit = pd.read_parquet(args.book_audit)
    report.update(
        {
            "research_approval": "approved_v62_research_only_build",
            "retirement_enforcement_required": True,
            "frozen_alignment_policy_id": _ALIGNMENT_POLICY,
            "development_split": split,
            "alignment_entry_accounting": accounting,
            "local_orderbook_backtest": {
                "source": "0xArchive Hyperliquid native L2 audit",
                **v62_candidate_orderbook_coverage(review.trade_rows, audit),
            },
            "local_trade_backtest": _tape_summary(tape_research),
            "prior_hype_l2_candidate": _book_summary(book_research),
            "source_evidence": {str(path): file_evidence(path) for path in sources},
        }
    )
    return report


def _book_summary(report: dict[str, object]) -> dict[str, object]:
    development = _record(report.get("development_evidence"), "L2 development")
    outcomes = _record(report.get("prospective_outcomes"), "L2 outcomes")
    return {
        "status": report.get("status"),
        "development_rows": development.get("rows"),
        "prospective_resolved": outcomes.get("resolved"),
        "prospective_net_return_bps": outcomes.get("net_return_bps"),
        "directional_sign_agreement_rate": outcomes.get(
            "directional_sign_agreement_rate"
        ),
        "live_change_approved": False,
    }


def _tape_summary(report: dict[str, object]) -> dict[str, object]:
    metrics = _record(report.get("metrics"), "order-flow metrics")
    return {
        "status": report.get("status"),
        "symbols": report.get("symbol"),
        "continuation_nominal_mean_bps": metrics.get("continuation_nominal_mean_bps"),
        "reversion_nominal_mean_bps": metrics.get("reversion_nominal_mean_bps"),
        "ridge_selected_net_bps": metrics.get("ridge_selected_net_bps"),
        "lightgbm_selected_net_bps": metrics.get("lightgbm_selected_net_bps"),
        "hype_trade_coverage_used": False,
        "limitation": "the indexed tape study has BTC/SOL, not HYPE, coverage",
        "live_change_approved": False,
    }


def _validate_prior_research(
    book_research: dict[str, object],
    tape_research: dict[str, object],
) -> None:
    if book_research.get("status") != "rejected_as_growth_candidate":
        raise ValueError("V62 HYPE L2 source disposition is not frozen rejected")
    if tape_research.get("status") != "reject":
        raise ValueError("V62 public-trade source disposition is not frozen reject")
    if book_research.get("execution_authority") != "none":
        raise ValueError("V62 HYPE L2 source has unexpected execution authority")
    if tape_research.get("execution_authority") != "none":
        raise ValueError("V62 public-trade source has unexpected execution authority")


def _source_paths(args: argparse.Namespace) -> tuple[Path, ...]:
    return (
        args.bars,
        args.funding,
        args.book_audit,
        args.book_research,
        args.tape_research,
    )


def _trade_path(out: Path) -> Path:
    if out.suffix != ".json":
        raise ValueError("V62 HYPE output must use .json")
    return out.with_suffix(".trades.parquet")


def _json_object(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return _record(raw, str(path))


def _record(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"V62 {label} must be an object")
    return value


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"V62 source does not exist: {path}")


def _require_absent(paths: tuple[Path, ...]) -> None:
    existing = tuple(path for path in paths if path.exists())
    if existing:
        raise FileExistsError(f"immutable V62 outputs already exist: {existing}")


def main() -> None:
    """Publish the report and exact lifecycle sidecar."""
    args = build_parser().parse_args()
    report = run(args)
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "disposition": report["disposition"],
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
