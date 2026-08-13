"""Compare a predeclared margin-stop grid on faithful Hypervelocity decisions."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_archive_audit import (
    OxaArchiveAuditConfig,
    verified_archive_bundles,
)
from hypervector.data.oxa_storage import file_evidence, write_json
from hypervector.regime.composite import classify_multitimeframe
from hypervector.research.hypervelocity_margin_stop_compare import (
    bounded_target_ladder_candidate_configs,
    break_even_gross_margin_stop_pct,
    margin_stop_candidate_configs,
    mature_target_continuation_candidate_configs,
    maximum_hold_candidate_configs,
    source_hold_compatibility,
    summarize_margin_stop_grid,
    tight_margin_stop_candidate_configs,
)
from hypervector.research.hypervelocity_reentry_compare import (
    source_episode_compatibility,
)
from hypervector.research.hypervelocity_metalabel_report import (
    runtime_observe_contract,
)
from hypervector.research.maker_replay_context_io import (
    context_coverage_report,
    load_verified_replay_context,
)
from hypervector.research.maker_replay_stream import (
    archive_evidence_chunks,
    replay_maker_order_grid_chunks,
)
from hypervector.research.maker_replay_models import MakerReplayConfig
from hypervector.strategies.hypervelocity_profile import load_hypervelocity_profile

_CREATOR_SCORECARDS = ((42, 18), (43, 16))
_STOP_FAMILIES = frozenset({"margin-stop", "tight-margin-stop"})
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
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--start", type=_utc, required=True)
    parser.add_argument("--end", type=_utc, required=True)
    parser.add_argument("--price-context", type=Path, required=True)
    parser.add_argument("--funding-context", type=Path, required=True)
    parser.add_argument("--creator-positions", type=Path)
    parser.add_argument("--supplemental-positions", type=Path)
    parser.add_argument(
        "--candidate-family",
        choices=(
            "margin-stop",
            "tight-margin-stop",
            "max-hold",
            "target-ladder",
            "mature-continuation",
        ),
        default="margin-stop",
    )
    parser.add_argument("--initial-equity", type=float, default=10_000.0)
    parser.add_argument("--segment-days", type=int, default=30)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _bars(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"margin-stop bars are missing: {path}")
    frame = pd.read_parquet(path)
    if "timestamp" not in frame:
        raise ValueError("margin-stop bars require timestamp")
    frame.index = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True))
    if (
        frame.empty
        or frame.index.has_duplicates
        or not frame.index.is_monotonic_increasing
    ):
        raise ValueError(
            "margin-stop bars must be non-empty, unique, and chronological"
        )
    return frame


def _faithful_decisions(bars: pd.DataFrame, config_path: Path) -> pd.DataFrame:
    profile = load_hypervelocity_profile(config_path)
    return classify_multitimeframe(bars, config=profile.regime_config)


def _verify_faithful_config(path: Path) -> dict[str, object]:
    evidence = file_evidence(path)
    if evidence["sha256"] != _FAITHFUL_CONFIG_SHA256:
        raise ValueError(
            "faithful config checksum mismatch: "
            f"expected {_FAITHFUL_CONFIG_SHA256}, observed {evidence['sha256']}"
        )
    return evidence


def _replay_contract(args: argparse.Namespace) -> dict[str, object]:
    policy = (
        "candidate_specific"
        if args.candidate_family in {"target-ladder", "mature-continuation"}
        else "regime_reset"
    )
    return {
        "initial_equity": args.initial_equity,
        "allocation_fraction": 0.70,
        "leverage": 40.0,
        "gross_margin_target_pct": 8.0,
        "maker_fee_rate": 0.00015,
        "taker_fee_rate": 0.00045,
        "fill_rule": "trade-through",
        "entry_ttl_seconds": 300.0,
        "reentry_cooldown_seconds": 60.0,
        "same_direction_reentry_policy": policy,
    }


def _creator_calibration() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for wins, losses in _CREATOR_SCORECARDS:
        positions = wins + losses
        win_rate = wins / positions
        result.append(
            {
                "wins": wins,
                "losses": losses,
                "positions": positions,
                "win_rate": win_rate,
                "break_even_gross_margin_stop_pct": (
                    break_even_gross_margin_stop_pct(
                        win_rate=win_rate,
                        target_margin_pct=8.0,
                        leverage=40.0,
                        maker_fee_rate=0.00015,
                        taker_fee_rate=0.00045,
                    )
                ),
            }
        )
    return result


def _candidate_configs(args: argparse.Namespace) -> dict[str, MakerReplayConfig]:
    if args.candidate_family == "tight-margin-stop":
        return tight_margin_stop_candidate_configs(args.initial_equity)
    if args.candidate_family == "max-hold":
        return maximum_hold_candidate_configs(args.initial_equity)
    if args.candidate_family == "target-ladder":
        return bounded_target_ladder_candidate_configs(args.initial_equity)
    if args.candidate_family == "mature-continuation":
        return mature_target_continuation_candidate_configs(args.initial_equity)
    return margin_stop_candidate_configs(args.initial_equity)


def _experiment_identity(args: argparse.Namespace) -> str:
    if args.candidate_family == "tight-margin-stop":
        return "reverse_engineered_tight_margin_stop_grid_v1"
    if args.candidate_family == "max-hold":
        return "source_bounded_maximum_hold_grid_v1"
    if args.candidate_family == "target-ladder":
        return "source_bounded_target_ladder_v1"
    if args.candidate_family == "mature-continuation":
        return "source_mature_target_continuation_v1"
    return "creator_calibrated_fixed_margin_stop_grid_v1"


def _validate_family_args(args: argparse.Namespace) -> None:
    if args.candidate_family == "max-hold" and args.creator_positions is None:
        raise ValueError("max-hold candidate family requires --creator-positions")
    if args.candidate_family in {"target-ladder", "mature-continuation"}:
        if args.creator_positions is None:
            raise ValueError(
                "target-ladder candidate family requires --creator-positions"
            )
        if args.supplemental_positions is None:
            raise ValueError(
                "target-ladder candidate family requires --supplemental-positions"
            )


def _creator_context(
    args: argparse.Namespace,
    configs: dict[str, MakerReplayConfig],
    decisions: pd.DataFrame | None = None,
) -> dict[str, object]:
    if args.candidate_family in _STOP_FAMILIES:
        return {"creator_calibration": _creator_calibration()}
    if args.creator_positions is None:
        raise ValueError("candidate family requires --creator-positions")
    positions = pd.read_csv(args.creator_positions)
    if args.candidate_family == "max-hold":
        return {
            "source_hold_compatibility": source_hold_compatibility(positions, configs)
        }
    if decisions is None or args.supplemental_positions is None:
        raise ValueError(
            "target-ladder creator context requires decisions and supplemental"
        )
    supplemental = pd.read_csv(args.supplemental_positions)
    return {
        "source_episode_compatibility": source_episode_compatibility(
            positions,
            decisions,
            supplemental=supplemental,
        )
    }


def _source_evidence(args: argparse.Namespace) -> dict[str, object]:
    result = {
        "bars": file_evidence(args.bars),
        "runtime_config": _verify_faithful_config(args.config),
        "price_context": file_evidence(args.price_context),
        "funding_context": file_evidence(args.funding_context),
    }
    if args.creator_positions is not None:
        result["creator_positions"] = file_evidence(args.creator_positions)
    if args.supplemental_positions is not None:
        result["supplemental_positions"] = file_evidence(args.supplemental_positions)
    return result


def _archive_summary(
    args: argparse.Namespace,
    bundle_count: int,
    context: object,
) -> dict[str, object]:
    return {
        "start": args.start.isoformat(),
        "end": args.end.isoformat(),
        "bundle_count": bundle_count,
        "checksums_verified": True,
        "context_coverage": context_coverage_report(context),
    }


def _limitations(args: argparse.Namespace) -> list[str]:
    if args.candidate_family == "max-hold":
        execution_limit = "Time exits use the first BBO at or after the deadline with taker fees and no hidden depth."
        ordering_limit = (
            "Liquidation is evaluated before a time exit on the same event."
        )
    elif args.candidate_family in _STOP_FAMILIES:
        execution_limit = "Stop execution uses adverse BBO plus taker fees and cannot model hidden depth."
        ordering_limit = "Liquidation is evaluated before a stop on the same event."
    else:
        execution_limit = (
            "The observed source episode distribution does not prove a ladder counter."
        )
        ordering_limit = "Only a successful target can consume a ladder slot and rearm the same side."
    return [
        "All 90 days are a development comparison; no sealed holdout is claimed.",
        "Public trade-through cannot reveal private queue rank or cancellations.",
        execution_limit,
        ordering_limit,
        "The two creator scorecards conflict and cannot be one sequential ledger.",
    ]


def _report(args: argparse.Namespace) -> dict[str, object]:
    if args.end <= args.start:
        raise ValueError("margin-stop replay end must follow start")
    _validate_family_args(args)
    _verify_faithful_config(args.config)
    bars = _bars(args.bars)
    decisions = _faithful_decisions(bars, args.config)
    bundles = tuple(
        verified_archive_bundles(
            OxaArchiveAuditConfig("BTC", args.start, args.end, args.data_root)
        )
    )
    context = load_verified_replay_context(
        args.price_context,
        args.funding_context,
    )
    configs = _candidate_configs(args)
    reports = replay_maker_order_grid_chunks(
        archive_evidence_chunks(bundles, include_trades=True),
        decisions,
        configs,
        context=context,
    )
    comparison = summarize_margin_stop_grid(
        reports,
        configs,
        start=pd.Timestamp(args.start),
        end=pd.Timestamp(args.end),
        segment_days=args.segment_days,
    )
    return {
        "ok": True,
        "report_only": True,
        "experiment": _experiment_identity(args),
        "source_evidence": _source_evidence(args),
        **_creator_context(args, configs, decisions),
        "metalabel_policy": runtime_observe_contract(args.config),
        "archive": _archive_summary(args, len(bundles), context),
        "replay_contract": _replay_contract(args),
        "comparison": comparison,
        "runtime_strategy_changed": False,
        "limitations": _limitations(args),
    }


def _write_immutable_report(path: Path, payload: object) -> None:
    if path.exists():
        raise FileExistsError(f"margin-stop output exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        staging = Path(handle.name)
    try:
        write_json(staging, payload)
        os.link(staging, path)
    finally:
        staging.unlink(missing_ok=True)


def main() -> int:
    """Write one immutable faithful fixed-margin stop comparison."""
    args = _parser().parse_args()
    try:
        if args.out.exists():
            raise FileExistsError(f"margin-stop output exists: {args.out}")
        _write_immutable_report(args.out, _report(args))
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
