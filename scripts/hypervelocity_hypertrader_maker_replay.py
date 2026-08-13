#!/usr/bin/env python3
"""Replay exact Hypertrader B/C events on authentic Hyperliquid evidence."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
import math
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.maker_replay_context import MakerReplayContext
from hypervector.research.maker_replay_context_io import (
    context_coverage_report,
    load_verified_replay_context_parts,
)
from hypervector.research.maker_replay_models import FillRule, MakerReplayConfig
from hypervector.research.maker_replay_stream import (
    replay_maker_order_decision_grid_chunks,
    replay_maker_order_grid_chunks,
    replay_maker_order_chunks,
)
from hypervector.research.research_evidence_source import (
    MakerReplayEvidence,
    maker_replay_evidence,
)
from hypervector.research.hypervelocity_margin_stop_compare import (
    margin_stop_candidate_configs,
    wide_margin_stop_candidate_configs,
)
from hypervector.research.hypertrader_exit_decisions import (
    selective_recipe_source_exit_decisions,
)
from hypervector.research.hypertrader_creator_breakout_short import (
    CREATOR_LEVERAGE,
    CREATOR_MARGIN_FRACTION,
    CREATOR_MAXIMUM_HOLD_SECONDS,
    CREATOR_MINIMUM_CONFIDENCE,
    CREATOR_RECIPE_REVISION,
    CREATOR_RESEARCH_REVISION,
    CREATOR_TARGET_MARGIN_PCT,
    CREATOR_TARGET_PRICE_POINTS,
    creator_breakout_short_leverage_configs,
    extract_creator_breakout_short_events,
)
from hypervector.research.hypertrader_source_adapter import (
    PINNED_HYPERTRADER_REVISION,
    annotate_signal_range_eligibility,
    extract_source_breakout_events,
    extract_four_hour_long_trend_events,
    extract_selective_recipe_events,
    extract_source_fade_events,
    extract_source_follow_all_day_events,
    extract_source_follow_asia_events,
    extract_source_follow_events,
    extract_source_follow_session_06_15_events,
    extract_source_follow_session_08_17_events,
    extract_source_follow_us_events,
    extract_symmetric_trend_events,
    load_hyperliquid_candles,
    range_split_recipe_c_events,
    resample_hyperliquid_5m,
    selective_recipe_maker_decisions,
    source_recipe_event_policy,
    trend_aligned_selective_recipe_events,
)
from hypervector.research.hypertrader_label_evidence import (
    HypertraderLabelEvidence,
    load_label_evidence,
)
from hypervector.research.hypertrader_source_confidence import (
    MINIMUM_SOURCE_CONFIDENCE,
    extract_source_follow_all_day_confidence_70_events,
    extract_source_follow_session_05_14_confidence_70_events,
    extract_source_follow_session_06_15_confidence_70_events,
    extract_source_follow_session_07_16_confidence_70_events,
    extract_source_follow_session_08_17_confidence_70_events,
)
from hypervector.research.replay_window import (
    add_replay_window_arguments,
    partition_replay_events as _partition_events,
    validate_replay_window,
)

_ENTRY_ELIGIBILITY_GRID = (30.0, 60.0, 90.0, 120.0, 180.0, 240.0, 300.0)
_CREATOR_EXACT_FAMILY = "creator-breakout-down-confidence-70"
_CREATOR_SURFACE_FAMILY = "creator-breakout-down-leverage-surface"
_CREATOR_FAMILIES = frozenset({_CREATOR_EXACT_FAMILY, _CREATOR_SURFACE_FAMILY})


def _positive_seconds(value: str) -> float:
    seconds = float(value)
    if not math.isfinite(seconds) or seconds <= 0.0:
        raise argparse.ArgumentTypeError("seconds must be finite and positive")
    return seconds


def _positive_equity(value: str) -> float:
    equity = float(value)
    if not math.isfinite(equity) or equity <= 0.0:
        raise argparse.ArgumentTypeError("initial equity must be finite and positive")
    return equity


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--labels-metadata", type=Path)
    parser.add_argument("--candles", action="append", type=Path, default=[])
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--research-database", type=Path)
    parser.add_argument("--initial-equity", type=_positive_equity, default=10_000.0)
    add_replay_window_arguments(parser)
    parser.add_argument(
        "--development-price-context", action="append", type=Path, required=True
    )
    parser.add_argument(
        "--development-funding-context", action="append", type=Path, required=True
    )
    parser.add_argument(
        "--fresh-price-context", action="append", type=Path, required=True
    )
    parser.add_argument(
        "--fresh-funding-context", action="append", type=Path, required=True
    )
    parser.add_argument(
        "--candidate-family",
        choices=(
            "baseline",
            "margin-stop",
            "trend-aligned",
            "trend-aligned-ttl-grid",
            "symmetric-trend-aligned",
            "symmetric-trend-aligned-long4h",
            "source-breakout-only",
            _CREATOR_EXACT_FAMILY,
            _CREATOR_SURFACE_FAMILY,
            "source-fade-only",
            "source-follow-all-day",
            "source-follow-all-day-confidence-70",
            "source-follow-all-day-margin-stop",
            "source-follow-all-day-wide-margin-stop",
            "source-follow-all-day-opposite-exit",
            "source-follow-asia-only",
            "source-follow-only",
            "source-follow-session-06-15",
            "source-follow-session-05-14-confidence-70",
            "source-follow-session-06-15-confidence-70",
            "source-follow-session-06-15-confidence-70-peak-activation7",
            "source-follow-session-06-15-confidence-70-peak-tier0",
            "source-follow-session-06-15-confidence-70-spread-1",
            "source-follow-session-07-16-confidence-70",
            "source-follow-session-08-17",
            "source-follow-session-08-17-confidence-70",
            "source-follow-us-only",
            "source-follow-margin-stop",
            "source-follow-wide-margin-stop",
            "source-range-direction",
        ),
        default="baseline",
    )
    parser.add_argument(
        "--entry-eligibility-seconds",
        type=_positive_seconds,
        default=300.0,
    )
    parser.add_argument(
        "--maximum-signal-range-bps",
        type=_positive_seconds,
    )
    parser.add_argument(
        "--fill-rule",
        choices=("touch", "through", "trade-through"),
        default="trade-through",
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _experiment_contract(
    candidate_family: str = "baseline",
    *,
    entry_eligibility_seconds: float = 300.0,
    maximum_signal_range_bps: float | None = None,
    fill_rule: FillRule = "trade-through",
    upstream_revision: str = PINNED_HYPERTRADER_REVISION,
    initial_equity: float = 10_000.0,
) -> dict[str, object]:
    creator_short = candidate_family in _CREATOR_FAMILIES
    creator_surface = candidate_family == _CREATOR_SURFACE_FAMILY
    eligibility: float | list[float] = entry_eligibility_seconds
    if candidate_family == "trend-aligned-ttl-grid":
        eligibility = list(_ENTRY_ELIGIBILITY_GRID)
    event_policy = source_recipe_event_policy(candidate_family)
    return {
        "upstream_revision": upstream_revision,
        "report_only": True,
        "runtime_strategy_changed": False,
        "initial_equity": initial_equity,
        "allocation_fraction": (CREATOR_MARGIN_FRACTION if creator_short else 0.70),
        "leverage": CREATOR_LEVERAGE if creator_short else 40.0,
        "leverage_surface": (
            [20.0, 25.0, 30.0, 35.0, 40.0] if creator_surface else None
        ),
        "gross_margin_target_pct": (
            CREATOR_TARGET_MARGIN_PCT if creator_short else 8.0
        ),
        "absolute_target_points": (
            CREATOR_TARGET_PRICE_POINTS if creator_short else None
        ),
        "maximum_hold_seconds": (
            CREATOR_MAXIMUM_HOLD_SECONDS if creator_short else None
        ),
        "creator_recipe_revision": CREATOR_RECIPE_REVISION if creator_short else None,
        "creator_research_revision": (
            CREATOR_RESEARCH_REVISION if creator_short else None
        ),
        "margin_mode": "isolated",
        "one_position_per_symbol": True,
        "entry": f"post-only maker {fill_rule}",
        "fill_rule": fill_rule,
        "entry_ttl_seconds": eligibility,
        "signal_eligibility_seconds": eligibility,
        "maximum_signal_range_bps": maximum_signal_range_bps,
        "signal_range_policy": (
            "completed_5m_high_low_range_direction_split"
            if candidate_family == "source-range-direction"
            else (
                "completed_5m_high_low_range"
                if maximum_signal_range_bps is not None
                else "none"
            )
        ),
        "stop_policy": (
            "fixed margin grid: none, 25%, 35%, 45%"
            if candidate_family
            in {
                "source-follow-wide-margin-stop",
                "source-follow-all-day-wide-margin-stop",
            }
            else (
                "fixed margin grid: none, 6%, 10%, 14%, 18%"
                if candidate_family
                in {
                    "margin-stop",
                    "source-follow-margin-stop",
                    "source-follow-all-day-margin-stop",
                }
                else "none"
            )
        ),
        "candidate_family": candidate_family,
        "event_policy": (
            "creator_breakout_down_onset_minimum_confidence_0_70"
            if creator_short
            else event_policy
        ),
        "minimum_source_confidence": (
            CREATOR_MINIMUM_CONFIDENCE
            if creator_short
            else MINIMUM_SOURCE_CONFIDENCE
            if candidate_family
            in {
                "source-follow-all-day-confidence-70",
                "source-follow-session-05-14-confidence-70",
                "source-follow-session-06-15-confidence-70",
                "source-follow-session-06-15-confidence-70-peak-activation7",
                "source-follow-session-06-15-confidence-70-peak-tier0",
                "source-follow-session-06-15-confidence-70-spread-1",
                "source-follow-session-07-16-confidence-70",
                "source-follow-session-08-17-confidence-70",
            }
            else None
        ),
        "maximum_entry_spread_bps": (
            1.0
            if candidate_family == "source-follow-session-06-15-confidence-70-spread-1"
            else None
        ),
        "peak_protection_policy": (
            "source sensitivity: +7% peak, lock 55%"
            if candidate_family
            == "source-follow-session-06-15-confidence-70-peak-activation7"
            else (
                "source tier0: +6% peak, lock 55%"
                if candidate_family
                == "source-follow-session-06-15-confidence-70-peak-tier0"
                else None
            )
        ),
        "selection_is_promotion": False,
        "model_authority": "observe",
        "opposite_regime_exit": (
            candidate_family == "source-follow-all-day-opposite-exit"
        ),
    }


def _tail_candidate_configs(
    entry_eligibility_seconds: float = 300.0,
    fill_rule: FillRule = "trade-through",
    *,
    wide: bool = False,
    initial_equity: float = 10_000.0,
) -> dict[str, MakerReplayConfig]:
    factory = (
        wide_margin_stop_candidate_configs if wide else margin_stop_candidate_configs
    )
    configs = factory(initial_equity=initial_equity)
    return {
        name: replace(
            config,
            entry_ttl_seconds=entry_eligibility_seconds,
            fill_rule=fill_rule,
        )
        for name, config in configs.items()
    }


def _entry_eligibility_candidate_configs(
    fill_rule: FillRule = "trade-through",
    *,
    initial_equity: float = 10_000.0,
) -> dict[str, MakerReplayConfig]:
    return {
        f"ttl_{int(seconds)}s": MakerReplayConfig(
            initial_equity=initial_equity,
            fill_rule=fill_rule,
            entry_ttl_seconds=seconds,
            reentry_cooldown_seconds=60.0,
            same_direction_reentry_policy="regime_reset",
        )
        for seconds in _ENTRY_ELIGIBILITY_GRID
    }


def _source_follow_config(
    entry_eligibility_seconds: float,
    fill_rule: FillRule,
    *,
    opposite_regime_exit: bool = False,
    maximum_entry_spread_bps: float | None = None,
    initial_equity: float = 10_000.0,
) -> MakerReplayConfig:
    return MakerReplayConfig(
        initial_equity=initial_equity,
        fill_rule=fill_rule,
        entry_ttl_seconds=entry_eligibility_seconds,
        reentry_cooldown_seconds=60.0,
        same_direction_reentry_policy="regime_reset",
        opposite_regime_exit=opposite_regime_exit,
        maximum_entry_spread_bps=maximum_entry_spread_bps,
    )


def _creator_breakout_short_config(
    entry_eligibility_seconds: float,
    fill_rule: FillRule,
    *,
    initial_equity: float = 10_000.0,
) -> MakerReplayConfig:
    return MakerReplayConfig(
        initial_equity=initial_equity,
        margin_fraction=CREATOR_MARGIN_FRACTION,
        leverage=CREATOR_LEVERAGE,
        target_margin_pct=CREATOR_TARGET_MARGIN_PCT,
        target_price_points=CREATOR_TARGET_PRICE_POINTS,
        fill_rule=fill_rule,
        entry_ttl_seconds=entry_eligibility_seconds,
        reentry_cooldown_seconds=60.0,
        same_direction_reentry_policy="regime_reset",
    )


def _peak_candidate_configs(
    entry_eligibility_seconds: float,
    fill_rule: FillRule,
    *,
    activation_margin_pct: float = 6.0,
    candidate_name: str = "source_peak_tier0",
    initial_equity: float = 10_000.0,
) -> dict[str, MakerReplayConfig]:
    control = _source_follow_config(
        entry_eligibility_seconds,
        fill_rule,
        initial_equity=initial_equity,
    )
    return {
        "no_peak_control": control,
        candidate_name: replace(
            control,
            peak_protection_activation_margin_pct=activation_margin_pct,
            peak_protection_lock_ratio=0.55,
            peak_protection_minimum_price_move_fraction=0.0005,
            peak_protection_update_cooldown_seconds=60.0,
        ),
    }


def _entry_eligibility_decision_grid(
    events: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    return {
        f"ttl_{int(seconds)}s": selective_recipe_maker_decisions(
            events,
            entry_eligibility_seconds=seconds,
        )
        for seconds in _ENTRY_ELIGIBILITY_GRID
    }


def _events(
    path: Path,
    candle_paths: list[Path],
    maximum_signal_range_bps: float | None,
    candidate_family: str = "baseline",
) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"pinned Hypertrader labels are missing: {path}")
    labels = pd.read_parquet(path)
    if not isinstance(labels.index, pd.DatetimeIndex):
        raise ValueError("pinned Hypertrader labels require a DatetimeIndex")
    labels.index = pd.DatetimeIndex(pd.to_datetime(labels.index, utc=True))
    ordered = labels.sort_index(kind="stable")
    extractors = {
        "symmetric-trend-aligned": extract_symmetric_trend_events,
        "symmetric-trend-aligned-long4h": extract_four_hour_long_trend_events,
        "source-breakout-only": extract_source_breakout_events,
        _CREATOR_EXACT_FAMILY: extract_creator_breakout_short_events,
        _CREATOR_SURFACE_FAMILY: extract_creator_breakout_short_events,
        "source-fade-only": extract_source_fade_events,
        "source-follow-all-day": extract_source_follow_all_day_events,
        "source-follow-all-day-confidence-70": (
            extract_source_follow_all_day_confidence_70_events
        ),
        "source-follow-all-day-margin-stop": extract_source_follow_all_day_events,
        "source-follow-all-day-wide-margin-stop": (
            extract_source_follow_all_day_events
        ),
        "source-follow-all-day-opposite-exit": extract_source_follow_all_day_events,
        "source-follow-asia-only": extract_source_follow_asia_events,
        "source-follow-only": extract_source_follow_events,
        "source-follow-session-06-15": extract_source_follow_session_06_15_events,
        "source-follow-session-05-14-confidence-70": (
            extract_source_follow_session_05_14_confidence_70_events
        ),
        "source-follow-session-06-15-confidence-70": (
            extract_source_follow_session_06_15_confidence_70_events
        ),
        "source-follow-session-06-15-confidence-70-peak-activation7": (
            extract_source_follow_session_06_15_confidence_70_events
        ),
        "source-follow-session-06-15-confidence-70-peak-tier0": (
            extract_source_follow_session_06_15_confidence_70_events
        ),
        "source-follow-session-06-15-confidence-70-spread-1": (
            extract_source_follow_session_06_15_confidence_70_events
        ),
        "source-follow-session-07-16-confidence-70": (
            extract_source_follow_session_07_16_confidence_70_events
        ),
        "source-follow-session-08-17": extract_source_follow_session_08_17_events,
        "source-follow-session-08-17-confidence-70": (
            extract_source_follow_session_08_17_confidence_70_events
        ),
        "source-follow-us-only": extract_source_follow_us_events,
        "source-follow-margin-stop": extract_source_follow_events,
        "source-follow-wide-margin-stop": extract_source_follow_events,
        "source-range-direction": extract_source_fade_events,
    }
    extractor = extractors.get(candidate_family, extract_selective_recipe_events)
    events = extractor(ordered)
    if maximum_signal_range_bps is None:
        if candidate_family == "source-range-direction":
            raise ValueError("source range direction requires an explicit range split")
        return events
    if not candle_paths:
        raise ValueError("signal range candidate requires --candles evidence")
    candles = load_hyperliquid_candles(candle_paths)
    bars = resample_hyperliquid_5m(candles)
    if candidate_family == "source-range-direction":
        return range_split_recipe_c_events(
            events, bars, split_bps=maximum_signal_range_bps
        )
    return annotate_signal_range_eligibility(
        events,
        bars,
        maximum_range_bps=maximum_signal_range_bps,
    )


def _event_outcomes(
    events: pd.DataFrame,
    replay_payload: dict[str, object],
) -> list[dict[str, object]]:
    lifecycles = replay_payload.get("lifecycles")
    if not isinstance(lifecycles, (list, tuple)):
        raise RuntimeError("maker replay lifecycles are unavailable")
    by_signal = {
        pd.Timestamp(item["signal_time_utc"]): item
        for item in lifecycles
        if isinstance(item, dict)
    }
    rows: list[dict[str, object]] = []
    for event in events.to_dict(orient="records"):
        signal = pd.Timestamp(event["decision_time_utc"])
        lifecycle = by_signal.get(signal)
        serialized_event = {
            str(key): value.isoformat()
            if isinstance(value, (datetime, pd.Timestamp))
            else value
            for key, value in event.items()
        }
        rows.append(
            {
                **serialized_event,
                "lifecycle": lifecycle,
                "admission": (
                    "submitted"
                    if lifecycle
                    else (
                        "filtered"
                        if event.get("entry_eligible") is False
                        else "not_submitted"
                    )
                ),
            }
        )
    return rows


def _run_window(
    events: pd.DataFrame,
    evidence: MakerReplayEvidence,
    price_context: Sequence[Path],
    funding_context: Sequence[Path],
    entry_eligibility_seconds: float,
    fill_rule: FillRule,
    *,
    maximum_entry_spread_bps: float | None = None,
    initial_equity: float = 10_000.0,
    replay_config: MakerReplayConfig | None = None,
) -> dict[str, object]:
    decisions = selective_recipe_maker_decisions(
        events,
        entry_eligibility_seconds=entry_eligibility_seconds,
    )
    context = _load_context_parts(price_context, funding_context)
    config = replay_config or _source_follow_config(
        entry_eligibility_seconds,
        fill_rule,
        maximum_entry_spread_bps=maximum_entry_spread_bps,
        initial_equity=initial_equity,
    )
    replay = replay_maker_order_chunks(
        evidence.chunks,
        decisions,
        config,
        context=context,
    )
    payload = replay.to_dict()
    return {
        "events": len(events),
        "archive": evidence.summary,
        "context": context_coverage_report(context),
        "event_outcomes": _event_outcomes(events, payload),
        "replay": payload,
    }


def _source_labels(path: Path) -> pd.DataFrame:
    labels = pd.read_parquet(path)
    if not isinstance(labels.index, pd.DatetimeIndex):
        raise ValueError("pinned Hypertrader labels require a DatetimeIndex")
    labels.index = pd.DatetimeIndex(pd.to_datetime(labels.index, utc=True))
    return labels.sort_index(kind="stable")


def _run_source_exit_window(
    events: pd.DataFrame,
    evidence: MakerReplayEvidence,
    price_context: Sequence[Path],
    funding_context: Sequence[Path],
    entry_eligibility_seconds: float,
    fill_rule: FillRule,
    labels_path: Path,
    *,
    initial_equity: float = 10_000.0,
) -> dict[str, object]:
    decisions = selective_recipe_source_exit_decisions(
        events,
        _source_labels(labels_path),
        entry_eligibility_seconds=entry_eligibility_seconds,
    )
    context = _load_context_parts(price_context, funding_context)
    replay = replay_maker_order_chunks(
        evidence.chunks,
        decisions,
        _source_follow_config(
            entry_eligibility_seconds,
            fill_rule,
            opposite_regime_exit=True,
            initial_equity=initial_equity,
        ),
        context=context,
    )
    payload = replay.to_dict()
    return {
        "events": len(events),
        "archive": evidence.summary,
        "context": context_coverage_report(context),
        "event_outcomes": _event_outcomes(events, payload),
        "replay": payload,
    }


def _run_tail_window(
    events: pd.DataFrame,
    evidence: MakerReplayEvidence,
    price_context: Sequence[Path],
    funding_context: Sequence[Path],
    entry_eligibility_seconds: float,
    fill_rule: FillRule,
    *,
    wide: bool = False,
    initial_equity: float = 10_000.0,
) -> dict[str, object]:
    decisions = selective_recipe_maker_decisions(
        events,
        entry_eligibility_seconds=entry_eligibility_seconds,
    )
    context = _load_context_parts(price_context, funding_context)
    configs = _tail_candidate_configs(
        entry_eligibility_seconds,
        fill_rule,
        wide=wide,
        initial_equity=initial_equity,
    )
    reports = replay_maker_order_grid_chunks(
        evidence.chunks,
        decisions,
        configs,
        context=context,
    )
    candidates: dict[str, object] = {}
    for name, report in reports.items():
        payload = report.to_dict()
        candidates[name] = {
            "fixed_margin_stop_pct": configs[name].fixed_margin_stop_pct,
            "event_outcomes": _event_outcomes(events, payload),
            "replay": payload,
        }
    return {
        "events": len(events),
        "archive": evidence.summary,
        "context": context_coverage_report(context),
        "candidates": candidates,
    }


def _run_creator_leverage_window(
    events: pd.DataFrame,
    evidence: MakerReplayEvidence,
    price_context: Sequence[Path],
    funding_context: Sequence[Path],
    entry_eligibility_seconds: float,
    fill_rule: FillRule,
    *,
    initial_equity: float = 10_000.0,
) -> dict[str, object]:
    decisions = selective_recipe_maker_decisions(
        events,
        entry_eligibility_seconds=entry_eligibility_seconds,
    )
    context = _load_context_parts(price_context, funding_context)
    configs = creator_breakout_short_leverage_configs(
        initial_equity=initial_equity,
        entry_eligibility_seconds=entry_eligibility_seconds,
        fill_rule=fill_rule,
    )
    reports = replay_maker_order_grid_chunks(
        evidence.chunks,
        decisions,
        configs,
        context=context,
    )
    candidates = {
        name: {
            "margin_fraction": configs[name].margin_fraction,
            "leverage": configs[name].leverage,
            "target_margin_pct": configs[name].target_margin_pct,
            "target_price_points": configs[name].target_price_points,
            "event_outcomes": _event_outcomes(events, report.to_dict()),
            "replay": report.to_dict(),
        }
        for name, report in reports.items()
    }
    return {
        "events": len(events),
        "archive": evidence.summary,
        "context": context_coverage_report(context),
        "candidates": candidates,
    }


def _run_peak_window(
    events: pd.DataFrame,
    evidence: MakerReplayEvidence,
    price_context: Sequence[Path],
    funding_context: Sequence[Path],
    entry_eligibility_seconds: float,
    fill_rule: FillRule,
    *,
    activation_margin_pct: float = 6.0,
    candidate_name: str = "source_peak_tier0",
    initial_equity: float = 10_000.0,
) -> dict[str, object]:
    decisions = selective_recipe_maker_decisions(
        events,
        entry_eligibility_seconds=entry_eligibility_seconds,
    )
    context = _load_context_parts(price_context, funding_context)
    configs = _peak_candidate_configs(
        entry_eligibility_seconds,
        fill_rule,
        activation_margin_pct=activation_margin_pct,
        candidate_name=candidate_name,
        initial_equity=initial_equity,
    )
    reports = replay_maker_order_grid_chunks(
        evidence.chunks,
        decisions,
        configs,
        context=context,
    )
    candidates: dict[str, object] = {}
    for name, report in reports.items():
        payload = report.to_dict()
        config = configs[name]
        candidates[name] = {
            "peak_protection_activation_margin_pct": (
                config.peak_protection_activation_margin_pct
            ),
            "peak_protection_lock_ratio": config.peak_protection_lock_ratio,
            "peak_protection_minimum_price_move_fraction": (
                config.peak_protection_minimum_price_move_fraction
            ),
            "peak_protection_update_cooldown_seconds": (
                config.peak_protection_update_cooldown_seconds
            ),
            "event_outcomes": _event_outcomes(events, payload),
            "replay": payload,
        }
    return {
        "events": len(events),
        "archive": evidence.summary,
        "context": context_coverage_report(context),
        "candidates": candidates,
    }


def _run_wide_tail_window(
    events: pd.DataFrame,
    evidence: MakerReplayEvidence,
    price_context: Sequence[Path],
    funding_context: Sequence[Path],
    entry_eligibility_seconds: float,
    fill_rule: FillRule,
    *,
    initial_equity: float = 10_000.0,
) -> dict[str, object]:
    """Replay the wider emergency-stop grid without changing entry events."""
    return _run_tail_window(
        events,
        evidence,
        price_context,
        funding_context,
        entry_eligibility_seconds,
        fill_rule,
        wide=True,
        initial_equity=initial_equity,
    )


def _run_entry_eligibility_window(
    events: pd.DataFrame,
    evidence: MakerReplayEvidence,
    price_context: Sequence[Path],
    funding_context: Sequence[Path],
    entry_eligibility_seconds: float,
    fill_rule: FillRule,
    *,
    initial_equity: float = 10_000.0,
) -> dict[str, object]:
    if entry_eligibility_seconds != 300.0:
        raise ValueError("TTL grid does not accept one eligibility override")
    decisions = _entry_eligibility_decision_grid(events)
    configs = _entry_eligibility_candidate_configs(
        fill_rule,
        initial_equity=initial_equity,
    )
    context = _load_context_parts(price_context, funding_context)
    reports = replay_maker_order_decision_grid_chunks(
        evidence.chunks,
        decisions,
        configs,
        context=context,
    )
    candidates: dict[str, object] = {}
    for name, report in reports.items():
        payload = report.to_dict()
        candidates[name] = {
            "entry_eligibility_seconds": configs[name].entry_ttl_seconds,
            "event_outcomes": _event_outcomes(events, payload),
            "replay": payload,
        }
    return {
        "events": len(events),
        "archive": evidence.summary,
        "context": context_coverage_report(context),
        "candidates": candidates,
    }


def _source_evidence(
    args: argparse.Namespace,
    labels: HypertraderLabelEvidence,
) -> dict[str, object]:
    paths = {
        "development_prices": args.development_price_context,
        "development_funding": args.development_funding_context,
        "fresh_prices": args.fresh_price_context,
        "fresh_funding": args.fresh_funding_context,
    }
    evidence: dict[str, object] = dict(labels.files)
    evidence.update(
        {
            name: [file_evidence(path) for path in context_paths]
            for name, context_paths in paths.items()
        }
    )
    evidence["labels_metadata_verified"] = labels.metadata_verified
    evidence["candles"] = [file_evidence(path) for path in args.candles]
    return evidence


def _window_evidence(
    args: argparse.Namespace,
) -> tuple[MakerReplayEvidence, MakerReplayEvidence]:
    include_trades = args.fill_rule == "trade-through"
    common = (args.data_root, "BTC")
    development = maker_replay_evidence(
        *common,
        args.data_start,
        args.fresh_start,
        include_trades=include_trades,
        database_path=args.research_database,
    )
    fresh = maker_replay_evidence(
        *common,
        args.fresh_start,
        args.data_end,
        include_trades=include_trades,
        database_path=args.research_database,
    )
    return development, fresh


def _run_partition(
    args: argparse.Namespace,
    events: pd.DataFrame,
    evidence: MakerReplayEvidence,
    price_context: Sequence[Path],
    funding_context: Sequence[Path],
) -> dict[str, object]:
    if args.candidate_family == _CREATOR_SURFACE_FAMILY:
        return _run_creator_leverage_window(
            events,
            evidence,
            price_context,
            funding_context,
            args.entry_eligibility_seconds,
            args.fill_rule,
            initial_equity=args.initial_equity,
        )
    if args.candidate_family == _CREATOR_EXACT_FAMILY:
        config = _creator_breakout_short_config(
            args.entry_eligibility_seconds,
            args.fill_rule,
            initial_equity=args.initial_equity,
        )
        return _run_window(
            events,
            evidence,
            price_context,
            funding_context,
            args.entry_eligibility_seconds,
            args.fill_rule,
            initial_equity=args.initial_equity,
            replay_config=config,
        )
    if args.candidate_family == "source-follow-session-06-15-confidence-70-spread-1":
        return _run_window(
            events,
            evidence,
            price_context,
            funding_context,
            args.entry_eligibility_seconds,
            args.fill_rule,
            maximum_entry_spread_bps=1.0,
            initial_equity=args.initial_equity,
        )
    if args.candidate_family == "source-follow-all-day-opposite-exit":
        return _run_source_exit_window(
            events,
            evidence,
            price_context,
            funding_context,
            args.entry_eligibility_seconds,
            args.fill_rule,
            args.labels,
            initial_equity=args.initial_equity,
        )
    if (
        args.candidate_family
        == "source-follow-session-06-15-confidence-70-peak-activation7"
    ):
        return _run_peak_window(
            events,
            evidence,
            price_context,
            funding_context,
            args.entry_eligibility_seconds,
            args.fill_rule,
            activation_margin_pct=7.0,
            candidate_name="source_peak_activation7",
            initial_equity=args.initial_equity,
        )
    run_window = {
        "margin-stop": _run_tail_window,
        "source-follow-all-day-margin-stop": _run_tail_window,
        "source-follow-margin-stop": _run_tail_window,
        "source-follow-all-day-wide-margin-stop": _run_wide_tail_window,
        "source-follow-wide-margin-stop": _run_wide_tail_window,
        "source-follow-session-06-15-confidence-70-peak-tier0": _run_peak_window,
        "trend-aligned-ttl-grid": _run_entry_eligibility_window,
    }.get(args.candidate_family, _run_window)
    return run_window(
        events,
        evidence,
        price_context,
        funding_context,
        args.entry_eligibility_seconds,
        args.fill_rule,
        initial_equity=args.initial_equity,
    )


def _load_context_parts(
    price_context: Sequence[Path], funding_context: Sequence[Path]
) -> MakerReplayContext:
    if len(price_context) != len(funding_context):
        raise ValueError("price and funding context part counts must match")
    return load_verified_replay_context_parts(
        tuple(zip(price_context, funding_context, strict=True))
    )


def _report(args: argparse.Namespace) -> dict[str, object]:
    window = validate_replay_window(args)
    label_evidence = load_label_evidence(args.labels, args.labels_metadata)
    events = _events(
        args.labels,
        args.candles,
        args.maximum_signal_range_bps,
        args.candidate_family,
    )
    if args.candidate_family in {"trend-aligned", "trend-aligned-ttl-grid"}:
        events = trend_aligned_selective_recipe_events(events)
    development, fresh = _partition_events(events, args)
    development_evidence, fresh_evidence = _window_evidence(args)
    development_result = _run_partition(
        args,
        development,
        development_evidence,
        args.development_price_context,
        args.development_funding_context,
    )
    fresh_result = _run_partition(
        args,
        fresh,
        fresh_evidence,
        args.fresh_price_context,
        args.fresh_funding_context,
    )
    return {
        **_experiment_contract(
            args.candidate_family,
            entry_eligibility_seconds=args.entry_eligibility_seconds,
            maximum_signal_range_bps=args.maximum_signal_range_bps,
            fill_rule=args.fill_rule,
            upstream_revision=label_evidence.revision,
            initial_equity=args.initial_equity,
        ),
        "replay_window": window.to_dict(),
        "source_evidence": _source_evidence(args, label_evidence),
        "development": development_result,
        "fresh_20260727": fresh_result,
        "limitations": [
            "Public trade-through volume cannot identify private queue rank.",
            "Twenty-one development archive hours contain no book snapshots.",
            "Fresh and development windows start with separate "
            f"${args.initial_equity:,.0f} portfolios.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Write one immutable authentic maker replay artifact."""
    args = _parser().parse_args(argv)
    write_immutable_json(args.out, _report(args))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
