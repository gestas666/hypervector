"""Screen and optionally event-replay hard 5m BBWP range precedence."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_archive_audit import (
    OxaArchiveAuditConfig,
    verified_archive_bundles,
)
from hypervector.data.oxa_storage import file_evidence, write_json
from hypervector.regime.composite import _completed_context, classify_multitimeframe
from hypervector.regime.hypervelocity_eval import evaluate_entry_alignment
from hypervector.research.hypervelocity_bbwp_precedence import (
    apply_1m_bbwp_recovery_delay,
    apply_1m_trend_breakout_confirmation,
    apply_5m_compression_release_confirmation,
    apply_5m_bbwp_range_precedence,
    apply_breakout_onset_confirmation,
    apply_prefer_1m_direction_fusion,
    apply_regime_entry_age_limit,
    apply_regime_entry_minimum_age,
)
from hypervector.research.hypervelocity_portfolio_eval import (
    SerialPortfolioConfig,
    evaluate_serial_portfolio,
)
from hypervector.research.hypervelocity_reentry_compare import (
    evaluate_original_alignment,
    reentry_candidate_matrix,
)
from hypervector.research.hypervelocity_source_inputs import (
    source_positions as _source_positions,
)
from hypervector.research.maker_replay_models import MakerReplayConfig
from hypervector.research.maker_replay_context import MakerReplayContext
from hypervector.research.maker_replay_context_io import (
    context_coverage_report,
    load_verified_replay_context,
)
from hypervector.research.maker_replay_stream import (
    archive_evidence_chunks,
    replay_maker_order_chunks,
)
from hypervector.strategies.hypervelocity_profile import load_hypervelocity_profile

_THRESHOLDS = (15.0, 20.0, 25.0, 30.0)
_COOLDOWNS = ((60.0, 1), (120.0, 2), (300.0, 5))
_DEFAULT_ENTRY_TTL_SECONDS = 300.0
_DEFAULT_ENTRY_DEPTH_TICKS = 0
_DEFAULT_INITIAL_EQUITY = 10_000.0


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--positions", type=Path, required=True)
    parser.add_argument("--supplemental-positions", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--start", type=_utc, required=True)
    parser.add_argument("--end", type=_utc, required=True)
    parser.add_argument(
        "--event-base",
        choices=("hard-bbwp", "faithful"),
        default="hard-bbwp",
    )
    parser.add_argument("--event-recovery-age", type=int, default=0)
    parser.add_argument(
        "--event-breakout-confirmation",
        choices=(
            "strict-both-breakout",
            "1m-trend",
            "range-onset-1m-trend",
        ),
        default="strict-both-breakout",
    )
    parser.add_argument(
        "--event-direction-policy",
        choices=("canonical-5m", "prefer-1m-direction"),
        default="canonical-5m",
    )
    parser.add_argument("--event-release-confirmation-bars", type=int)
    age_group = parser.add_mutually_exclusive_group()
    age_group.add_argument("--event-maximum-regime-age", type=int)
    age_group.add_argument("--event-minimum-regime-age", type=int)
    parser.add_argument("--event-stop-fraction", type=float)
    parser.add_argument(
        "--event-entry-ttl-seconds",
        type=float,
        default=_DEFAULT_ENTRY_TTL_SECONDS,
    )
    parser.add_argument(
        "--event-entry-depth-ticks",
        type=int,
        default=_DEFAULT_ENTRY_DEPTH_TICKS,
    )
    parser.add_argument(
        "--event-initial-equity",
        type=float,
        default=_DEFAULT_INITIAL_EQUITY,
    )
    parser.add_argument("--event-price-context", type=Path)
    parser.add_argument("--event-funding-context", type=Path)
    parser.add_argument("--skip-event", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _bars(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"BBWP precedence bars are missing: {path}")
    frame = pd.read_parquet(path)
    if "timestamp" not in frame:
        raise ValueError("BBWP precedence bars require timestamp")
    frame.index = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True))
    if frame.empty or frame.index.has_duplicates:
        raise ValueError("BBWP precedence bars must be non-empty and unique")
    return frame


def _source_evidence(args: argparse.Namespace) -> dict[str, object]:
    evidence = {
        "bars": file_evidence(args.bars),
        "positions": file_evidence(args.positions),
        "runtime_config": file_evidence(args.config),
    }
    if args.supplemental_positions is not None:
        evidence["supplemental_positions"] = file_evidence(args.supplemental_positions)
    return evidence


def _serial_row(
    candidate_id: str,
    decisions: pd.DataFrame,
    bars: pd.DataFrame,
    positions: pd.DataFrame,
    cooldown_seconds: float,
    cooldown_bars: int,
) -> dict[str, object]:
    report = evaluate_serial_portfolio(
        bars,
        decisions,
        SerialPortfolioConfig(reentry_cooldown_bars=cooldown_bars),
    )
    serial = report.to_dict()
    serial.pop("trades")
    days = (bars.index[-1] - bars.index[0] + pd.Timedelta(minutes=1)).days
    serial["completed_trades_per_day"] = report.completed_trades / days
    return {
        "candidate_id": candidate_id,
        "cooldown_seconds": cooldown_seconds,
        "hard_range_bars": int(
            decisions.get(
                "bbwp_5m_hard_range", pd.Series(False, index=decisions.index)
            ).sum()
        ),
        "regime_entry_age_blocked_bars": int(
            decisions.get(
                "regime_entry_age_blocked", pd.Series(False, index=decisions.index)
            ).sum()
        ),
        "regime_entry_minimum_age_blocked_bars": int(
            decisions.get(
                "regime_entry_minimum_age_blocked",
                pd.Series(False, index=decisions.index),
            ).sum()
        ),
        "release_confirmation_bars": int(
            decisions.get(
                "bbwp_5m_release_wait", pd.Series(False, index=decisions.index)
            ).sum()
        ),
        "directional_bars": int(decisions["entry_direction"].notna().sum()),
        "serial": serial,
        "original_alignment": asdict(evaluate_entry_alignment(decisions, positions)),
    }


def _screen(
    bars: pd.DataFrame,
    positions: pd.DataFrame,
    control: pd.DataFrame,
    context_5m: pd.DataFrame,
) -> tuple[list[dict[str, object]], pd.DataFrame]:
    rows = [_serial_row("faithful_control", control, bars, positions, 60.0, 1)]
    decisions_25: pd.DataFrame | None = None
    for threshold in _THRESHOLDS:
        decisions = apply_5m_bbwp_range_precedence(
            control, context_5m, threshold=threshold
        )
        if threshold == 25.0:
            decisions_25 = decisions
        rows.append(
            _serial_row(
                f"5m_bbwp_hard_range_{threshold:g}",
                decisions,
                bars,
                positions,
                60.0,
                1,
            )
        )
    if decisions_25 is None:
        raise RuntimeError("BBWP screen omitted the configured 25 threshold")
    for cooldown_seconds, cooldown_bars in _COOLDOWNS[1:]:
        rows.append(
            _serial_row(
                f"5m_bbwp_hard_range_25_cooldown_{cooldown_seconds:g}s",
                decisions_25,
                bars,
                positions,
                cooldown_seconds,
                cooldown_bars,
            )
        )
    return rows, decisions_25


def _maker_replay_config(args: argparse.Namespace) -> MakerReplayConfig:
    return MakerReplayConfig(
        initial_equity=args.event_initial_equity,
        fill_rule="trade-through",
        entry_depth_ticks=args.event_entry_depth_ticks,
        entry_ttl_seconds=args.event_entry_ttl_seconds,
        reentry_cooldown_seconds=300.0,
        same_direction_reentry_policy="regime_reset",
        liquidation_proximity_stop_fraction=args.event_stop_fraction,
    )


def _apply_breakout_confirmation(
    decisions: pd.DataFrame,
    args: argparse.Namespace,
    candidate_id: str,
) -> tuple[pd.DataFrame, str]:
    if args.event_breakout_confirmation == "strict-both-breakout":
        return decisions, candidate_id
    if args.event_breakout_confirmation == "1m-trend":
        transformed = apply_1m_trend_breakout_confirmation(decisions)
        return transformed, f"{candidate_id}_breakout_confirm_1m_trend"
    transformed = apply_breakout_onset_confirmation(decisions)
    return transformed, f"{candidate_id}_breakout_confirm_range_onset_1m_trend"


def _apply_direction_policy(
    decisions: pd.DataFrame,
    args: argparse.Namespace,
    candidate_id: str,
) -> tuple[pd.DataFrame, str]:
    if args.event_direction_policy == "canonical-5m":
        return decisions, candidate_id
    transformed = apply_prefer_1m_direction_fusion(decisions)
    return transformed, f"{candidate_id}_prefer_1m_direction_else_5m"


def _event_replay(
    decisions: pd.DataFrame,
    args: argparse.Namespace,
) -> tuple[dict[str, object], dict[str, object]]:
    audit = OxaArchiveAuditConfig("BTC", args.start, args.end, args.data_root)
    bundles = verified_archive_bundles(audit)
    context = _replay_context(args)
    report = replay_maker_order_chunks(
        archive_evidence_chunks(bundles, include_trades=True),
        decisions,
        _maker_replay_config(args),
        context=context,
    )
    archive = {
        "start": args.start.isoformat(),
        "end": args.end.isoformat(),
        "bundle_count": len(bundles),
        "empty_book_hours": sum(bundle.book_rows == 0 for bundle in bundles),
        "empty_trade_hours": sum(bundle.trade_rows == 0 for bundle in bundles),
        "checksums_verified": True,
        "authentic_context": context is not None,
        "context_coverage": (
            context_coverage_report(context) if context is not None else None
        ),
    }
    return report.to_dict(), archive


def _replay_context(args: argparse.Namespace) -> MakerReplayContext | None:
    price_path = args.event_price_context
    funding_path = args.event_funding_context
    if (price_path is None) != (funding_path is None):
        raise ValueError("price and funding context paths must be supplied together")
    if price_path is None or funding_path is None:
        return None
    return load_verified_replay_context(price_path, funding_path)


def _limitations(authentic_context: bool) -> list[str]:
    context = (
        "Authentic mark/oracle and official settled funding are applied causally."
        if authentic_context
        else "Historical funding is unavailable and is not applied."
    )
    return [
        "Serial screening uses next-bar-open fills rather than public L2.",
        "Event replay cannot observe private queue position or cancellations.",
        context,
        "The event candidate exceeded the original-cadence shortlist band.",
    ]


def _event_base(
    args: argparse.Namespace,
    control: pd.DataFrame,
    decisions_25: pd.DataFrame,
) -> tuple[pd.DataFrame, str]:
    if args.event_base == "faithful":
        return control, "faithful_control_cooldown_300s"
    return decisions_25, "5m_bbwp_hard_range_25_cooldown_300s"


def _append_screening(
    screening: list[dict[str, object]],
    candidate: str,
    decisions: pd.DataFrame,
    bars: pd.DataFrame,
    positions: pd.DataFrame,
) -> None:
    screening.append(_serial_row(candidate, decisions, bars, positions, 300.0, 5))


def _apply_event_variants(
    args: argparse.Namespace,
    decisions: pd.DataFrame,
    candidate: str,
    screening: list[dict[str, object]],
    bars: pd.DataFrame,
    positions: pd.DataFrame,
    compression_threshold: float,
) -> tuple[pd.DataFrame, str]:
    decisions, candidate = _apply_breakout_confirmation(decisions, args, candidate)
    pre_direction_candidate = candidate
    decisions, candidate = _apply_direction_policy(decisions, args, candidate)
    if candidate != pre_direction_candidate:
        _append_screening(screening, candidate, decisions, bars, positions)
    if args.event_recovery_age:
        decisions = apply_1m_bbwp_recovery_delay(
            decisions,
            threshold=compression_threshold,
            minimum_age_bars=args.event_recovery_age,
        )
        candidate = candidate.replace(
            "cooldown_300s", f"recovery_{args.event_recovery_age}_cooldown_300s"
        )
        _append_screening(screening, candidate, decisions, bars, positions)
    decisions, candidate = _apply_release_variant(
        args, decisions, candidate, screening, bars, positions
    )
    return _apply_age_variant(args, decisions, candidate, screening, bars, positions)


def _apply_release_variant(
    args: argparse.Namespace,
    decisions: pd.DataFrame,
    candidate: str,
    screening: list[dict[str, object]],
    bars: pd.DataFrame,
    positions: pd.DataFrame,
) -> tuple[pd.DataFrame, str]:
    bars_required = args.event_release_confirmation_bars
    if bars_required is None:
        return decisions, candidate
    decisions = apply_5m_compression_release_confirmation(
        decisions, confirmation_bars=bars_required
    )
    candidate += f"_release_confirm_{bars_required}bars"
    _append_screening(screening, candidate, decisions, bars, positions)
    return decisions, candidate


def _apply_age_variant(
    args: argparse.Namespace,
    decisions: pd.DataFrame,
    candidate: str,
    screening: list[dict[str, object]],
    bars: pd.DataFrame,
    positions: pd.DataFrame,
) -> tuple[pd.DataFrame, str]:
    maximum_age = args.event_maximum_regime_age
    minimum_age = args.event_minimum_regime_age
    if maximum_age is not None:
        decisions = apply_regime_entry_age_limit(
            decisions, maximum_age_exclusive=maximum_age
        )
        candidate += f"_regime_age_lt_{maximum_age}"
    elif minimum_age is not None:
        decisions = apply_regime_entry_minimum_age(
            decisions, minimum_age_inclusive=minimum_age
        )
        candidate += f"_regime_age_gte_{minimum_age}"
    else:
        return decisions, candidate
    _append_screening(screening, candidate, decisions, bars, positions)
    return decisions, candidate


def _candidate_execution_suffix(args: argparse.Namespace, candidate: str) -> str:
    if args.event_stop_fraction is not None:
        candidate += f"_liquidation_stop_{100.0 * args.event_stop_fraction:g}pct"
    if args.event_entry_ttl_seconds != _DEFAULT_ENTRY_TTL_SECONDS:
        candidate += f"_entry_ttl_{args.event_entry_ttl_seconds:g}s"
    if args.event_entry_depth_ticks != _DEFAULT_ENTRY_DEPTH_TICKS:
        candidate += f"_entry_depth_{args.event_entry_depth_ticks}ticks"
    if args.event_initial_equity != _DEFAULT_INITIAL_EQUITY:
        candidate += f"_equity_{args.event_initial_equity:g}usd"
    return candidate


def _report(args: argparse.Namespace) -> dict[str, object]:
    profile = load_hypervelocity_profile(args.config)
    bars = _bars(args.bars)
    positions = _source_positions(args.positions, args.supplemental_positions)
    control = classify_multitimeframe(bars, config=profile.regime_config)
    context_5m = _completed_context(bars, bars.index, 5, profile.regime_config)
    screening, decisions_25 = _screen(bars, positions, control, context_5m)
    event_decisions, event_candidate = _event_base(args, control, decisions_25)
    event_decisions, event_candidate = _apply_event_variants(
        args,
        event_decisions,
        event_candidate,
        screening,
        bars,
        positions,
        profile.regime_config.bbwp_compression_threshold,
    )
    event_candidate = _candidate_execution_suffix(args, event_candidate)
    source = evaluate_original_alignment(
        positions, control, reentry_candidate_matrix()[0]
    )
    event: dict[str, object] | None = None
    archive: dict[str, object] | None = None
    if not args.skip_event:
        event, archive = _event_replay(event_decisions, args)
    return {
        "ok": True,
        "report_only": True,
        "experiment": "5m_bbwp_hard_range_precedence_v1",
        "source_evidence": _source_evidence(args),
        "source_positions_per_day": source["source_logical_positions_per_day"],
        "metalabel_policy": {
            "mode": profile.metalabel_mode,
            "may_filter": False,
            "may_scale": False,
        },
        "screening": screening,
        "event_candidate": event_candidate,
        "event_entry_ttl_seconds": args.event_entry_ttl_seconds,
        "event_entry_depth_ticks": args.event_entry_depth_ticks,
        "event_initial_equity": args.event_initial_equity,
        "event_replay": event,
        "archive": archive,
        "runtime_strategy_changed": False,
        "limitations": _limitations(bool(archive and archive["authentic_context"])),
    }


def main() -> int:
    """Write one immutable report-only BBWP precedence artifact."""
    args = _parser().parse_args()
    try:
        if args.out.exists():
            raise FileExistsError(f"BBWP precedence output exists: {args.out}")
        report = _report(args)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.out, report)
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
