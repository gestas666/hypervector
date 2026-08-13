"""Replay one predeclared opposing-book-pressure Hypervelocity challenger."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pandas as pd

from hypervector.data.oxa_archive_audit import (
    OxaArchiveAuditConfig,
    OxaArchiveBundle,
    verified_archive_bundles,
)
from hypervector.data.oxa_storage import file_evidence, write_json
from hypervector.regime.composite import _completed_context, classify_multitimeframe
from hypervector.research.hypervelocity_bbwp_precedence import (
    apply_1m_bbwp_recovery_delay,
    apply_1m_trend_breakout_confirmation,
    apply_5m_bbwp_range_precedence,
    apply_fresh_opposed_context_confirmation,
    apply_weak_opposed_strength_delay,
)
from hypervector.research.hypervelocity_metalabel_report import (
    runtime_observe_contract,
)
from hypervector.research.hypervelocity_portfolio_eval import (
    SerialPortfolioConfig,
    evaluate_serial_portfolio,
)
from hypervector.research.hypervelocity_pressure_pullback import (
    apply_opposed_pressure_gate,
    decision_book_pressure,
    opposed_pressure_event_decisions,
)
from hypervector.research.hypervelocity_reentry_compare import (
    logical_source_positions,
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
from hypervector.strategies.hypervelocity_profile import load_hypervelocity_profile

RegimeBase = Literal[
    "hard-bbwp-recovery6",
    "canonical-breakout-confirmed",
]


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--positions", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--start", type=_utc, required=True)
    parser.add_argument("--end", type=_utc, required=True)
    parser.add_argument("--price-context", type=Path, required=True)
    parser.add_argument("--funding-context", type=Path, required=True)
    parser.add_argument("--initial-equity", type=float, default=120.0)
    parser.add_argument("--fixed-margin-stop-pct", type=float)
    parser.add_argument(
        "--fresh-opposed-confirmation-bars",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--minimum-opposed-strength-percentile",
        type=float,
    )
    parser.add_argument(
        "--pressure-timing",
        choices=("minute-boundary", "first-opposed-snapshot"),
        default="minute-boundary",
    )
    parser.add_argument(
        "--regime-base",
        choices=("hard-bbwp-recovery6", "canonical-breakout-confirmed"),
        default="hard-bbwp-recovery6",
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _bars(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    if "timestamp" not in frame:
        raise ValueError("pressure pullback bars require timestamp")
    frame.index = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True))
    if frame.empty or frame.index.has_duplicates:
        raise ValueError("pressure pullback bars must be non-empty and unique")
    return frame


def _base_decisions(
    bars: pd.DataFrame,
    config_path: Path,
    regime_base: RegimeBase,
) -> pd.DataFrame:
    profile = load_hypervelocity_profile(config_path)
    decisions = classify_multitimeframe(bars, config=profile.regime_config)
    if regime_base == "canonical-breakout-confirmed":
        return apply_1m_trend_breakout_confirmation(decisions)
    if regime_base != "hard-bbwp-recovery6":
        raise ValueError(f"unknown pressure replay regime base: {regime_base}")
    context = _completed_context(bars, bars.index, 5, profile.regime_config)
    decisions = apply_5m_bbwp_range_precedence(decisions, context, threshold=25.0)
    decisions = apply_1m_trend_breakout_confirmation(decisions)
    return apply_1m_bbwp_recovery_delay(
        decisions,
        threshold=profile.regime_config.bbwp_compression_threshold,
        minimum_age_bars=6,
    )


def _compact_serial(bars: pd.DataFrame, decisions: pd.DataFrame) -> dict[str, object]:
    report = evaluate_serial_portfolio(
        bars,
        decisions,
        SerialPortfolioConfig(reentry_cooldown_bars=5),
    ).to_dict()
    report.pop("trades")
    return report


def _exact_alignment(
    decisions: pd.DataFrame,
    logical: pd.DataFrame,
) -> dict[str, int]:
    entries = decisions["entry_direction"].astype(object).copy()
    entries.index = entries.index + pd.Timedelta(minutes=1)
    exact = 0
    for row in logical.itertuples(index=False):
        position = int(entries.index.searchsorted(row.open_ts, side="right")) - 1
        exact += int(position >= 0 and entries.iloc[position] == row.side)
    return {"positions": len(logical), "exact_direction": exact}


def _source_alignment(
    base: pd.DataFrame,
    gated: pd.DataFrame,
    positions_path: Path,
) -> dict[str, object]:
    logical = logical_source_positions(pd.read_csv(positions_path))
    trade_backed = logical.loc[logical["timestamp_provenance"].eq("trade_backed")]
    return {
        "all": {
            "base": _exact_alignment(base, logical),
            "challenger": _exact_alignment(gated, logical),
        },
        "trade_backed": {
            "base": _exact_alignment(base, trade_backed),
            "challenger": _exact_alignment(gated, trade_backed),
        },
    }


def _maker_replay_config(args: argparse.Namespace) -> MakerReplayConfig:
    return MakerReplayConfig(
        initial_equity=args.initial_equity,
        fill_rule="trade-through",
        entry_ttl_seconds=300.0,
        reentry_cooldown_seconds=300.0,
        same_direction_reentry_policy="regime_reset",
        fixed_margin_stop_pct=args.fixed_margin_stop_pct,
    )


def _event_replay(
    args: argparse.Namespace,
    bundles: tuple[OxaArchiveBundle, ...],
    decisions: pd.DataFrame,
    config: MakerReplayConfig,
) -> tuple[dict[str, object], dict[str, object]]:
    context = load_verified_replay_context(
        args.price_context,
        args.funding_context,
    )
    report = replay_maker_order_chunks(
        archive_evidence_chunks(bundles, include_trades=True),
        decisions,
        config,
        context=context,
    )
    archive = {
        "start": args.start.isoformat(),
        "end": args.end.isoformat(),
        "bundle_count": len(bundles),
        "checksums_verified": True,
        "context_coverage": context_coverage_report(context),
    }
    return report.to_dict(), archive


def _pressure_variant(
    base: pd.DataFrame,
    bundles: tuple[OxaArchiveBundle, ...],
    timing: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    eligible = base["entry_direction"].notna()
    if timing == "first-opposed-snapshot":
        events, evidence = opposed_pressure_event_decisions(base, bundles)
        return events, {
            "base_directional_bars": int(eligible.sum()),
            "opposed_snapshot_events": len(evidence),
            "event_decision_rows": len(events),
        }
    pressure = decision_book_pressure(base, bundles, max_age_ms=2_000)
    gated = apply_opposed_pressure_gate(base, pressure)
    alignments = gated.loc[eligible, "entry_pressure_alignment"].value_counts()
    return gated, {
        "observed_bars": int(pressure.notna().sum()),
        "missing_bars": int(pressure.isna().sum()),
        "base_directional_bars": int(eligible.sum()),
        "challenger_directional_bars": int(gated["entry_direction"].notna().sum()),
        "eligible_alignment_counts": {
            str(key): int(value) for key, value in alignments.items()
        },
    }


def _serial_comparison(
    bars: pd.DataFrame,
    base: pd.DataFrame,
    challenger: pd.DataFrame,
    timing: str,
) -> dict[str, object]:
    output: dict[str, object] = {"base": _compact_serial(bars, base)}
    if timing == "minute-boundary":
        output["challenger"] = _compact_serial(bars, challenger)
    else:
        output["challenger"] = None
        output["challenger_reason"] = (
            "irregular L2 event timestamps are not representable in the bar model"
        )
    return output


def _candidate_identity(args: argparse.Namespace) -> str:
    timing = (
        "opposed_obi5"
        if args.pressure_timing == "minute-boundary"
        else "first_opposed_obi5_snapshot"
    )
    base = str(args.regime_base).replace("-", "_")
    candidate = f"{base}_{timing}"
    confirmation = int(args.fresh_opposed_confirmation_bars)
    if confirmation > 0:
        candidate += f"_fresh_opposed_confirm_{confirmation}bar"
    strength = args.minimum_opposed_strength_percentile
    if strength is not None:
        candidate += f"_opposed_strength_ge_{format(float(strength), 'g')}pct"
    if args.fixed_margin_stop_pct is None:
        return candidate
    stop = format(float(args.fixed_margin_stop_pct), "g")
    return f"{candidate}_stop_{stop}pct_margin"


def _source_evidence(args: argparse.Namespace) -> dict[str, object]:
    return {
        "bars": file_evidence(args.bars),
        "positions": file_evidence(args.positions),
        "runtime_config": file_evidence(args.config),
        "price_context": file_evidence(args.price_context),
        "funding_context": file_evidence(args.funding_context),
    }


def _replay_contract(args: argparse.Namespace) -> dict[str, object]:
    return {
        "regime_base": args.regime_base,
        "initial_equity": args.initial_equity,
        "allocation_fraction": 0.70,
        "leverage": 40.0,
        "gross_margin_target_pct": 8.0,
        "entry_ttl_seconds": 300.0,
        "reentry_cooldown_seconds": 300.0,
        "same_direction_reentry_policy": "regime_reset",
        "fresh_opposed_confirmation_bars": (args.fresh_opposed_confirmation_bars),
        "minimum_opposed_strength_percentile": (
            args.minimum_opposed_strength_percentile
        ),
        "fixed_margin_stop_pct": args.fixed_margin_stop_pct,
        "fill_rule": "trade-through",
    }


def _limitations() -> list[str]:
    return [
        "Displayed OBI cannot observe hidden liquidity or private queue rank.",
        "The same archive motivated and evaluates this challenger.",
        "Displayed pressure can change before the maker order fills.",
        "Only a fresh venue-matched shadow window can confirm the effect.",
    ]


def _confirmed_decisions(
    args: argparse.Namespace,
    base: pd.DataFrame,
) -> pd.DataFrame:
    if args.fresh_opposed_confirmation_bars < 0:
        raise ValueError("fresh opposed confirmation bars cannot be negative")
    confirmed = base
    if args.fresh_opposed_confirmation_bars > 0:
        confirmed = apply_fresh_opposed_context_confirmation(
            base, confirmation_bars=args.fresh_opposed_confirmation_bars
        )
    if args.minimum_opposed_strength_percentile is not None:
        confirmed = apply_weak_opposed_strength_delay(
            confirmed,
            minimum_strength_percentile=args.minimum_opposed_strength_percentile,
        )
    return confirmed


def _pressure_contract(args: argparse.Namespace) -> dict[str, object]:
    maximum_age_ms = 2_000 if args.pressure_timing == "minute-boundary" else 0
    return {
        "depth": 5,
        "maximum_age_ms": maximum_age_ms,
        "entry_rule": "direction_normalized_obi5_lt_0",
        "timing": args.pressure_timing,
        "structural_direction_unchanged": True,
        "missing_evidence_policy": "no_entry",
    }


def _report(args: argparse.Namespace) -> dict[str, object]:
    if args.end <= args.start:
        raise ValueError("pressure pullback end must follow start")
    config = _maker_replay_config(args)
    bars = _bars(args.bars)
    base = _base_decisions(bars, args.config, args.regime_base)
    confirmed = _confirmed_decisions(args, base)
    bundles = verified_archive_bundles(
        OxaArchiveAuditConfig("BTC", args.start, args.end, args.data_root)
    )
    gated, pressure_coverage = _pressure_variant(
        confirmed,
        bundles,
        args.pressure_timing,
    )
    event, archive = _event_replay(args, bundles, gated, config)
    return {
        "ok": True,
        "report_only": True,
        "experiment": "structural_trend_opposed_obi5_pullback_v1",
        "candidate": _candidate_identity(args),
        "source_evidence": _source_evidence(args),
        "pressure_contract": _pressure_contract(args),
        "pressure_coverage": pressure_coverage,
        "serial": _serial_comparison(bars, confirmed, gated, args.pressure_timing),
        "source_alignment": _source_alignment(confirmed, gated, args.positions),
        "replay_contract": _replay_contract(args),
        "event_replay": event,
        "archive": archive,
        "metalabel_policy": runtime_observe_contract(args.config),
        "runtime_strategy_changed": False,
        "limitations": _limitations(),
    }


def main() -> int:
    """Write one immutable authentic pressure-pullback replay artifact."""
    args = _parser().parse_args()
    try:
        if args.out.exists():
            raise FileExistsError(f"pressure pullback output exists: {args.out}")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.out, _report(args))
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
