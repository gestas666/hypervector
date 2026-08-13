"""Replay reconciled source entries against authentic Hyperliquid evidence."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_archive_audit import (
    OxaArchiveBundle,
    OxaArchiveAuditConfig,
    verified_archive_bundles,
)
from hypervector.data.oxa_storage import file_evidence, write_json
from hypervector.research.hypervelocity_metalabel_report import (
    runtime_observe_contract,
)
from hypervector.research.hypervelocity_reentry_compare import (
    logical_source_positions,
)
from hypervector.research.hypervelocity_source_schedule import (
    merge_supplemental_positions,
    source_schedule_decisions,
)
from hypervector.research.maker_replay_context_io import (
    context_coverage_report,
    load_verified_replay_context,
)
from hypervector.research.maker_replay_models import MakerReplayConfig
from hypervector.research.maker_replay_stream import (
    archive_evidence_chunks,
    replay_maker_order_chunks,
)


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positions", type=Path, required=True)
    parser.add_argument("--supplemental-positions", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--start", type=_utc, required=True)
    parser.add_argument("--end", type=_utc, required=True)
    parser.add_argument("--price-context", type=Path, required=True)
    parser.add_argument("--funding-context", type=Path, required=True)
    parser.add_argument("--initial-equity", type=float, default=120.0)
    parser.add_argument(
        "--provenance",
        choices=("all", "trade-backed"),
        default="all",
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _selected_positions(args: argparse.Namespace) -> pd.DataFrame:
    records = pd.read_csv(args.positions)
    logical = logical_source_positions(records)
    if args.supplemental_positions is not None:
        logical = merge_supplemental_positions(
            logical,
            pd.read_csv(args.supplemental_positions),
        )
    mask = logical["open_ts"].between(args.start, args.end, inclusive="left")
    if args.provenance == "trade-backed":
        mask &= logical["timestamp_provenance"].isin(
            ("trade_backed", "screenshot_outcome_backed")
        )
    selected = logical.loc[mask].reset_index(drop=True)
    if selected.empty:
        raise ValueError("source schedule has no positions in the replay window")
    return selected


def _archive(args: argparse.Namespace) -> tuple[OxaArchiveBundle, ...]:
    config = OxaArchiveAuditConfig("BTC", args.start, args.end, args.data_root)
    return tuple(verified_archive_bundles(config))


def _source_evidence(args: argparse.Namespace) -> dict[str, object]:
    evidence = {
        "positions": file_evidence(args.positions),
        "runtime_config": file_evidence(args.config),
        "price_context": file_evidence(args.price_context),
        "funding_context": file_evidence(args.funding_context),
    }
    if args.supplemental_positions is not None:
        evidence["supplemental_positions"] = file_evidence(args.supplemental_positions)
    return evidence


def _source_schedule(logical: pd.DataFrame, provenance: pd.Series) -> dict[str, object]:
    return {
        "logical_positions": len(logical),
        "trade_backed": int(provenance.get("trade_backed", 0)),
        "screenshot_outcome_backed": int(
            provenance.get("screenshot_outcome_backed", 0)
        ),
        "tracker_only": int(provenance.get("tracker_only", 0)),
        "first_entry_utc": logical["open_ts"].min().isoformat(),
        "last_entry_utc": logical["open_ts"].max().isoformat(),
    }


def _replay_contract(args: argparse.Namespace) -> dict[str, object]:
    return {
        "initial_equity": args.initial_equity,
        "allocation_fraction": 0.70,
        "leverage": 40.0,
        "gross_margin_target_pct": 8.0,
        "entry_ttl_seconds": 300.0,
        "reentry_cooldown_seconds": 60.0,
        "same_direction_reentry_policy": "cooldown_only",
    }


def _limitations() -> list[str]:
    return [
        "Source timestamps prescribe entries and do not identify their trigger.",
        "Tracker-only timestamps are first observations, not authoritative fills.",
        "A five-second source-event rearm supersedes prior unfilled intent.",
        "Public trade-through volume cannot reveal private queue rank.",
        "Source venue prices and Hyperliquid execution prices can differ.",
    ]


def _report(args: argparse.Namespace) -> dict[str, object]:
    if args.end <= args.start:
        raise ValueError("source replay end must follow start")
    logical = _selected_positions(args)
    decisions = source_schedule_decisions(logical)
    bundles = _archive(args)
    context = load_verified_replay_context(args.price_context, args.funding_context)
    replay = replay_maker_order_chunks(
        archive_evidence_chunks(bundles, include_trades=True),
        decisions,
        MakerReplayConfig(
            initial_equity=args.initial_equity,
            fill_rule="trade-through",
            entry_ttl_seconds=300.0,
            reentry_cooldown_seconds=60.0,
            same_direction_reentry_policy="cooldown_only",
        ),
        context=context,
    )
    provenance = logical["timestamp_provenance"].value_counts()
    source_schedule = _source_schedule(logical, provenance)
    source_schedule["provenance_filter"] = args.provenance
    return {
        "ok": True,
        "report_only": True,
        "experiment": "source_schedule_authentic_replay_v1",
        "source_schedule": source_schedule,
        "source_evidence": _source_evidence(args),
        "metalabel_policy": runtime_observe_contract(args.config),
        "archive": {
            "start": args.start.isoformat(),
            "end": args.end.isoformat(),
            "bundle_count": len(bundles),
            "checksums_verified": True,
            "context_coverage": context_coverage_report(context),
        },
        "replay_contract": _replay_contract(args),
        "event_replay": replay.to_dict(),
        "runtime_strategy_changed": False,
        "limitations": _limitations(),
    }


def main() -> int:
    """Write one immutable authentic source-schedule replay artifact."""
    args = _parser().parse_args()
    try:
        if args.out.exists():
            raise FileExistsError(f"source schedule output exists: {args.out}")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.out, _report(args))
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
