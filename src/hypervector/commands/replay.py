"""Replay command handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast
import pandas as pd
from hypervector.commands.common import _load_bars
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hypervector.data.oxa_archive_audit import OxaArchiveBundle
    from hypervector.research.maker_replay import MakerReplayConfig, MakerReplayReport


def cmd_hypervelocity_maker_replay(args: argparse.Namespace) -> int:
    """Replay backend decisions against recorded post-only book paths."""
    from hypervector.regime.composite import classify_multitimeframe
    from hypervector.regime.hypervelocity_candidates import (
        hypervelocity_candidate_matrix,
    )
    from hypervector.strategies.hypervelocity_contract import faithful_regime_config

    bars, provenance = _load_bars(args)
    indexed = bars.copy()
    if not isinstance(indexed.index, pd.DatetimeIndex):
        indexed.index = pd.DatetimeIndex(pd.to_datetime(indexed["timestamp"], utc=True))
    decisions = classify_multitimeframe(indexed, config=faithful_regime_config())
    bundles = _verified_replay_archive(args)
    trade_paths = args.trade_path or []
    book_paths = args.book_path or []
    archive: dict[str, object] | None = None
    if bundles is not None:
        report_objects = _archive_replay_reports(args, decisions, bundles)
        archive = _archive_replay_provenance(args, bundles)
    else:
        if not book_paths:
            raise ValueError("maker replay requires --book-path or an archive window")
        book, trades = _load_maker_replay_evidence(book_paths, trade_paths)
        report_objects = _explicit_replay_reports(args, decisions, book, trades)
    labels = None
    if args.labels_out is not None:
        labels = _write_replay_labels(report_objects, args.labels_out)
    out = {
        "ok": True,
        "report_only": True,
        "candidate": hypervelocity_candidate_matrix()[-1].to_dict(),
        "data_provenance": provenance,
        "book_paths": [str(Path(path)) for path in book_paths],
        "trade_paths": [str(Path(path)) for path in trade_paths],
        "archive": archive,
        "labels": labels,
        "reports": {rule: report.to_dict() for rule, report in report_objects.items()},
    }
    rendered = json.dumps(out, indent=2, default=str)
    if args.out:
        output_path = Path(args.out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


def _candidate_l2_replays(
    args: argparse.Namespace,
    indexed: pd.DataFrame,
    bundles: tuple[OxaArchiveBundle, ...],
    shortlist: tuple[dict[str, object], ...],
) -> dict[str, object]:
    from hypervector.regime.composite import classify_multitimeframe
    from hypervector.regime.hypervelocity_candidates import (
        hypervelocity_candidate_matrix,
    )
    from hypervector.research.hypervelocity_archive_compare import (
        summarize_execution_reports,
    )

    candidates = {
        candidate.candidate_id: candidate
        for candidate in hypervelocity_candidate_matrix()
    }
    results: dict[str, object] = {}
    for screening in shortlist:
        identity = cast(dict[str, object], screening["candidate"])
        candidate_id = str(identity["candidate_id"])
        candidate = candidates[candidate_id]
        decisions = classify_multitimeframe(indexed, config=candidate.config)
        reports = _archive_replay_reports(args, decisions, bundles)
        results[candidate_id] = {
            "candidate": candidate.to_dict(),
            "execution_summary": summarize_execution_reports(reports),
            "reports": {rule: report.to_dict() for rule, report in reports.items()},
        }
    return results


def cmd_hypervelocity_archive_compare(args: argparse.Namespace) -> int:
    """Compare bounded regime candidates using bars and verified L2 evidence."""
    from hypervector.research.hypervelocity_archive_compare import (
        screen_candidate_matrix,
        select_archive_shortlist,
    )

    bars, provenance = _load_bars(args)
    indexed = bars.copy()
    if not isinstance(indexed.index, pd.DatetimeIndex):
        indexed.index = pd.DatetimeIndex(pd.to_datetime(indexed["timestamp"], utc=True))
    positions_path = Path(args.positions)
    if not positions_path.is_file():
        raise FileNotFoundError(f"positions file not found: {positions_path}")
    screenings = screen_candidate_matrix(indexed, pd.read_csv(positions_path))
    shortlist = select_archive_shortlist(screenings)
    bundles = _verified_replay_archive(args)
    if bundles is None:
        raise ValueError("archive comparison requires an explicit archive window")
    output = {
        "ok": True,
        "report_only": True,
        "data_provenance": provenance,
        "archive": _archive_replay_provenance(args, bundles),
        "screenings": screenings,
        "shortlist": shortlist,
        "l2_replay": _candidate_l2_replays(args, indexed, bundles, shortlist),
        "limitations": {
            "funding": "not_available",
            "barrier_execution": "next_bar_open_diagnostic_not_l2_fill",
            "l2_liquidation": "bbo_mark_proxy_partial_liquidation_v1",
            "l2_drawdown": "event_marked_available",
            "liquidation_mark": "book_midpoint_proxy_not_venue_mark_price",
            "liquidation_depth": "bbo_execution_without_depth_optimistic",
            "queue_rank": "not_observable_from_public_history",
        },
    }
    rendered = json.dumps(output, indent=2, default=str)
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


def _replay_rules(fill_rule: str) -> tuple[str, ...]:
    return {
        "both": ("touch", "through"),
        "all": ("touch", "through", "trade-through"),
    }.get(fill_rule, (fill_rule,))


def _maker_replay_config(args: argparse.Namespace, fill_rule: str) -> MakerReplayConfig:
    from hypervector.research.maker_replay import MakerReplayConfig

    return MakerReplayConfig(
        initial_equity=args.initial_equity,
        maker_fee_rate=args.maker_fee_rate,
        taker_fee_rate=args.taker_fee_rate,
        fill_rule=fill_rule,
        tick_size=args.tick_size,
        entry_ttl_seconds=args.entry_ttl_seconds,
    )


def _explicit_replay_reports(
    args: argparse.Namespace,
    decisions: pd.DataFrame,
    book: pd.DataFrame,
    trades: pd.DataFrame | None,
) -> dict[str, MakerReplayReport]:
    from hypervector.research.maker_replay import replay_maker_orders

    return {
        rule: replay_maker_orders(
            book,
            decisions,
            _maker_replay_config(args, rule),
            trades=trades,
        )
        for rule in _replay_rules(args.fill_rule)
    }


def _verified_replay_archive(
    args: argparse.Namespace,
) -> tuple[OxaArchiveBundle, ...] | None:
    from hypervector.data.oxa_archive_audit import (
        OxaArchiveAuditConfig,
        verified_archive_bundles,
    )

    start = args.archive_start
    end = args.archive_end
    if start is None and end is None:
        return None
    if start is None or end is None:
        raise ValueError(
            "archive replay requires both --archive-start and --archive-end"
        )
    if getattr(args, "book_path", None) or getattr(args, "trade_path", None):
        raise ValueError(
            "archive replay cannot be combined with explicit evidence paths"
        )
    config = OxaArchiveAuditConfig(args.symbol, start, end, Path(args.data_root))
    return verified_archive_bundles(config)


def _archive_replay_reports(
    args: argparse.Namespace,
    decisions: pd.DataFrame,
    bundles: tuple[OxaArchiveBundle, ...],
) -> dict[str, MakerReplayReport]:
    from hypervector.research.maker_replay_stream import (
        archive_evidence_chunks,
        replay_maker_order_chunks,
    )

    return {
        rule: replay_maker_order_chunks(
            archive_evidence_chunks(bundles, include_trades=rule == "trade-through"),
            decisions,
            _maker_replay_config(args, rule),
        )
        for rule in _replay_rules(args.fill_rule)
    }


def _archive_replay_provenance(
    args: argparse.Namespace,
    bundles: tuple[OxaArchiveBundle, ...],
) -> dict[str, object]:
    return {
        "start": args.archive_start.isoformat(),
        "end": args.archive_end.isoformat(),
        "bundle_count": len(bundles),
        "empty_book_hours": sum(bundle.book_path is None for bundle in bundles),
        "empty_trade_hours": sum(bundle.trade_path is None for bundle in bundles),
        "checksums_verified": True,
    }


def _write_replay_labels(
    reports: dict[str, MakerReplayReport],
    output_path: Path,
) -> dict[str, object]:
    from hypervector.research.replay_labels import build_conservative_replay_labels

    result = build_conservative_replay_labels(reports)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.rows.to_parquet(output_path, index=False)
    return {**result.summary(), "path": str(output_path.resolve())}


def _load_maker_replay_evidence(
    book_paths: list[str], trade_paths: list[str]
) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    from hypervector.data.book_align import load_l2_jsonl
    from hypervector.data.oxa_trades import load_trade_jsonl

    books = [load_l2_jsonl(Path(path)) for path in book_paths]
    book = pd.concat(books, ignore_index=True).sort_values("ts_ms")
    trade_frames = [load_trade_jsonl(Path(path)) for path in trade_paths]
    if not trade_frames:
        return book, None
    trades = pd.concat(trade_frames, ignore_index=True).sort_values("ts_ms")
    return book, trades


def cmd_hypervelocity_shadow_compare(args: argparse.Namespace) -> int:
    """Reconcile explicit shadow run IDs with a same-window real log."""
    from hypervector.research.shadow_compare import (
        compare_shadow_to_positions,
        load_real_positions,
        load_shadow_ledger,
    )

    report = compare_shadow_to_positions(
        load_shadow_ledger(args.shadow_ledger),
        load_real_positions(args.positions),
        run_ids=tuple(args.run_id),
        entry_tolerance_seconds=args.entry_tolerance_seconds,
    )
    rendered = json.dumps(report, indent=2, default=str)
    if args.out:
        output_path = Path(args.out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0
