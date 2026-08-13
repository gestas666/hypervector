"""Compare TP-only holding with a source-faithful opposite-5m regime exit."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

import pandas as pd

from hypervector.data.oxa_archive_audit import (
    OxaArchiveAuditConfig,
    verified_archive_bundles,
)
from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hypervelocity_metalabel_features import (
    candidate_decisions,
    load_model_bars,
)
from hypervector.research.hypervelocity_metalabel_report import runtime_observe_contract
from hypervector.research.hypervelocity_regime_exit_compare import (
    opposite_regime_exit_candidate_configs,
    source_regime_exit_compatibility,
    summarize_opposite_regime_exit,
)
from hypervector.research.hypervelocity_replay_evidence import (
    decision_identity,
    replay_archive_summary,
)
from hypervector.research.hypervelocity_source_inputs import source_positions
from hypervector.research.maker_replay_context_io import load_verified_replay_context
from hypervector.research.maker_replay_stream import (
    archive_evidence_chunks,
    replay_maker_order_grid_chunks,
)

_FAITHFUL_CONFIG_SHA256 = (
    "801d2c7af3c1211c13fea49dda673fdb8ed40ff0909692e9cebad070c0e3246f"
)


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--positions", type=Path, required=True)
    parser.add_argument("--supplemental-positions", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--start", type=_utc, required=True)
    parser.add_argument("--end", type=_utc, required=True)
    parser.add_argument("--price-context", type=Path, required=True)
    parser.add_argument("--funding-context", type=Path, required=True)
    parser.add_argument("--segment-days", type=int, default=30)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _metalabel_policy(config: Path) -> dict[str, object]:
    policy = runtime_observe_contract(config)
    return {name: policy[name] for name in ("mode", "may_filter", "may_scale")}


def _experiment_contract(args: argparse.Namespace) -> dict[str, object]:
    return {
        "report_only": True,
        "runtime_strategy_changed": False,
        "decision_profile": "5m_bbwp_hard_range_25_recovery_6",
        "window_start_utc": args.start.isoformat(),
        "window_end_utc": args.end.isoformat(),
        "allocation_fraction": 0.70,
        "leverage": 40.0,
        "gross_margin_target_pct": 8.0,
    }


def _verify_config(path: Path) -> dict[str, object]:
    evidence = file_evidence(path)
    if evidence["sha256"] != _FAITHFUL_CONFIG_SHA256:
        raise ValueError("faithful config checksum mismatch")
    return evidence


def _source_evidence(args: argparse.Namespace) -> dict[str, object]:
    return {
        "bars": file_evidence(args.bars),
        "positions": file_evidence(args.positions),
        "supplemental_positions": file_evidence(args.supplemental_positions),
        "runtime_config": _verify_config(args.config),
        "price_context": file_evidence(args.price_context),
        "funding_context": file_evidence(args.funding_context),
    }


def _report(args: argparse.Namespace) -> dict[str, object]:
    if args.end <= args.start:
        raise ValueError("regime-exit replay end must follow start")
    _verify_config(args.config)
    bars = load_model_bars(args.bars, args.start, args.end)
    decisions, _, _ = candidate_decisions(bars, args.config, "recovery6")
    audit = OxaArchiveAuditConfig("BTC", args.start, args.end, args.data_root)
    bundles = verified_archive_bundles(audit)
    context = load_verified_replay_context(args.price_context, args.funding_context)
    configs = opposite_regime_exit_candidate_configs()
    reports = replay_maker_order_grid_chunks(
        archive_evidence_chunks(bundles, include_trades=True),
        decisions,
        configs,
        context=context,
    )
    comparison = summarize_opposite_regime_exit(
        reports,
        configs,
        start=pd.Timestamp(args.start),
        end=pd.Timestamp(args.end),
        segment_days=args.segment_days,
    )
    positions = source_positions(args.positions, args.supplemental_positions)
    return {
        "ok": True,
        "experiment": "opposite_5m_structural_exit_v1",
        **_experiment_contract(args),
        "source_evidence": _source_evidence(args),
        "decision_identity_sha256": decision_identity(decisions),
        "candidate_configs": {name: asdict(value) for name, value in configs.items()},
        "metalabel_policy": _metalabel_policy(args.config),
        "archive": replay_archive_summary(bundles, context),
        "source_compatibility": source_regime_exit_compatibility(positions, decisions),
        "comparison": comparison,
        "limitations": [
            "All 90 days are development evidence; no sealed holdout is claimed.",
            "Public trade-through cannot reveal private queue rank or cancellation.",
            "Regime exits use adverse BBO plus taker fees without hidden depth.",
            "Liquidation has priority over regime exit at the same snapshot.",
            "Sparse creator screenshots may omit losses and exact exit reasons.",
        ],
    }


def _write_immutable_report(path: Path, payload: object) -> None:
    write_immutable_json(path, payload)


def main() -> int:
    """Write one immutable opposite-5m-regime exit comparison."""
    args = _parser().parse_args()
    try:
        _write_immutable_report(args.out, _report(args))
    except (OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
