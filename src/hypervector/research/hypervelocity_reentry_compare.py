"""Bounded report-only comparison of Hypervelocity re-entry policies."""

from __future__ import annotations

from statistics import median

import pandas as pd

from hypervector.data.source_position_records import (
    reconcile_source_position_records,
)
from hypervector.regime.models import BreakoutDirection
from hypervector.research.hypervelocity_portfolio_eval import (
    SerialPortfolioConfig,
    SerialPortfolioReport,
    evaluate_serial_portfolio,
)
from hypervector.research.hypervelocity_reentry_candidates import (
    ReentryCandidate,
    bounded_target_ladder_candidate_matrix,
    mature_target_continuation_candidate_matrix,
    reentry_candidate_matrix,
    target_continuation_candidate_matrix,
    target_rsi_candidate_matrix,
)
from hypervector.research.hypervelocity_source_episodes import (
    summarize_source_episodes,
)
from hypervector.research.hypervelocity_source_schedule import (
    merge_supplemental_positions,
)


def source_episode_compatibility(
    positions: pd.DataFrame,
    decisions: pd.DataFrame,
    *,
    supplemental: pd.DataFrame | None = None,
    limits: tuple[int, ...] = (2, 3, 6),
) -> dict[str, object]:
    """Measure creator entry counts within causal structural episodes."""
    logical = logical_source_positions(positions)
    if supplemental is not None:
        logical = merge_supplemental_positions(logical, supplemental)
    return summarize_source_episodes(
        logical,
        decisions,
        source_rows=len(positions),
        supplemental_rows=0 if supplemental is None else len(supplemental),
        limits=limits,
    )


def _validate_positions(positions: pd.DataFrame) -> pd.DataFrame:
    required = {"open_time_utc", "close_time_utc", "side", "entry_price", "status"}
    missing = required.difference(positions.columns)
    if missing:
        raise ValueError(f"original positions missing columns: {sorted(missing)}")
    frame = positions.copy()
    frame["open_ts"] = pd.to_datetime(
        frame["open_time_utc"], utc=True, format="ISO8601"
    )
    frame["close_ts"] = pd.to_datetime(
        frame["close_time_utc"], utc=True, errors="coerce", format="ISO8601"
    )
    if frame["open_ts"].isna().any():
        raise ValueError("original positions contain invalid open timestamps")
    if not frame["side"].isin(("long", "short")).all():
        raise ValueError("original position sides must be long|short")
    frame["entry_price"] = pd.to_numeric(frame["entry_price"], errors="coerce")
    if frame["entry_price"].isna().any():
        raise ValueError("original positions contain invalid entry prices")
    if "exit_price" not in frame:
        frame["exit_price"] = float("nan")
    frame["exit_price"] = pd.to_numeric(frame["exit_price"], errors="coerce")
    return frame.sort_values("open_ts").reset_index(drop=True)


def _same_split(first: pd.Series, second: pd.Series) -> bool:
    delay = abs((second["open_ts"] - first["open_ts"]).total_seconds())
    return bool(
        first["side"] == second["side"]
        and float(first["entry_price"]) == float(second["entry_price"])
        and delay <= 1.0
    )


def logical_source_positions(positions: pd.DataFrame) -> pd.DataFrame:
    """Collapse duplicate tracker rows and true split exits into positions."""
    frame = _validate_positions(reconcile_source_position_records(positions))
    groups: list[int] = []
    group_id = -1
    previous: pd.Series | None = None
    for _, row in frame.iterrows():
        if previous is None or not _same_split(previous, row):
            group_id += 1
        groups.append(group_id)
        previous = row
    frame["logical_id"] = groups
    rows: list[dict[str, object]] = []
    for _, group in frame.groupby("logical_id", sort=True):
        exit_prices = group["exit_price"].dropna()
        trade_backed = (
            group["trade_id"].notna().any()
            if "trade_id" in group
            else group.get("record_source", pd.Series(dtype=str))
            .astype(str)
            .str.contains("trade")
            .any()
        )
        rows.append(
            {
                "open_ts": group["open_ts"].min(),
                "close_ts": group["close_ts"].max(),
                "side": str(group["side"].iloc[0]),
                "entry_price": float(group["entry_price"].iloc[0]),
                "exit_price": (
                    float(exit_prices.iloc[-1]) if not exit_prices.empty else None
                ),
                "source_rows": len(group),
                "timestamp_provenance": (
                    "trade_backed" if trade_backed else "tracker_only"
                ),
            }
        )
    return pd.DataFrame(rows)


def _available_structure(decisions: pd.DataFrame) -> pd.Series:
    if "structural_direction" not in decisions:
        raise ValueError("alignment decisions require structural_direction")
    if not isinstance(decisions.index, pd.DatetimeIndex):
        raise ValueError("alignment decisions require a DatetimeIndex")
    structural = decisions["structural_direction"].astype(object).copy()
    structural.index = structural.index + pd.Timedelta(minutes=1)
    return structural


def _available_entry_directions(decisions: pd.DataFrame) -> pd.Series:
    if "entry_direction" not in decisions:
        raise ValueError("alignment decisions require entry_direction")
    entries = decisions["entry_direction"].astype(object).copy()
    entries.index = entries.index + pd.Timedelta(minutes=1)
    return entries


def _direction_at(entries: pd.Series, timestamp: pd.Timestamp) -> object:
    position = int(entries.index.searchsorted(timestamp, side="right")) - 1
    return None if position < 0 else entries.iloc[position]


def _available_rsi_crosses(decisions: pd.DataFrame) -> pd.Series:
    if "rsi_cross_direction" not in decisions:
        raise ValueError("RSI alignment requires rsi_cross_direction")
    crosses = decisions["rsi_cross_direction"].astype(object).copy()
    crosses.index = crosses.index + pd.Timedelta(minutes=1)
    return crosses


def _reset_observed(
    structural: pd.Series,
    side: str,
    previous_close: pd.Timestamp,
    current_open: pd.Timestamp,
) -> bool:
    window = structural.loc[
        (structural.index > previous_close) & (structural.index <= current_open)
    ]
    return bool(window.ne(side).any())


def _source_days(logical: pd.DataFrame) -> float:
    elapsed = logical["open_ts"].max() - logical["open_ts"].min()
    return max(elapsed.total_seconds() / 86_400.0, 1.0 / 1_440.0)


def _target_continuation_allowed(
    previous: pd.Series,
    current: pd.Series,
    candidate: ReentryCandidate,
) -> tuple[bool, bool]:
    reference = previous["exit_price"]
    if pd.isna(reference):
        return False, True
    clearance = candidate.clearance_bps / 10_000.0
    entry_price = float(current["entry_price"])
    if current["side"] == "long":
        return entry_price >= float(reference) * (1.0 + clearance), False
    return entry_price <= float(reference) * (1.0 - clearance), False


def _rsi_reconfirmation_observed(
    crosses: pd.Series,
    previous: pd.Series,
    current: pd.Series,
) -> bool:
    window = crosses.loc[
        (crosses.index > previous["close_ts"]) & (crosses.index <= current["open_ts"])
    ]
    expected = (
        BreakoutDirection.UPWARD.value
        if current["side"] == "long"
        else BreakoutDirection.DOWNWARD.value
    )
    return bool(window.eq(expected).any())


def _policy_allows_reentry(
    structural: pd.Series,
    rsi_crosses: pd.Series | None,
    previous: pd.Series,
    current: pd.Series,
    candidate: ReentryCandidate,
) -> tuple[bool, bool]:
    if candidate.policy == "cooldown_only":
        return True, False
    if candidate.policy == "target_continuation":
        return _target_continuation_allowed(previous, current, candidate)
    if candidate.policy == "target_rsi_reconfirmation":
        if rsi_crosses is None:
            raise ValueError("RSI re-entry policy requires causal RSI crosses")
        return _rsi_reconfirmation_observed(rsi_crosses, previous, current), False
    return (
        _reset_observed(
            structural,
            str(current["side"]),
            previous["close_ts"],
            current["open_ts"],
        ),
        False,
    )


def _same_side_alignment(
    logical: pd.DataFrame,
    structural: pd.Series,
    entries: pd.Series,
    rsi_crosses: pd.Series | None,
    candidate: ReentryCandidate,
) -> tuple[list[float], int, int, int, int, int]:
    eligible_delays: list[float] = []
    same_side = overlaps = missing_references = policy_eligible = mismatches = 0
    for position in range(1, len(logical)):
        previous, current = logical.iloc[position - 1], logical.iloc[position]
        if current["side"] != previous["side"] or pd.isna(previous["close_ts"]):
            continue
        delay = (current["open_ts"] - previous["close_ts"]).total_seconds()
        if delay < 0.0:
            overlaps += 1
            continue
        same_side += 1
        policy_ok, missing = _policy_allows_reentry(
            structural, rsi_crosses, previous, current, candidate
        )
        missing_references += int(missing)
        if delay < candidate.cooldown_seconds or not policy_ok:
            continue
        policy_eligible += 1
        if _direction_at(entries, current["open_ts"]) == current["side"]:
            eligible_delays.append(delay)
        else:
            mismatches += 1
    return (
        eligible_delays,
        same_side,
        overlaps,
        missing_references,
        policy_eligible,
        mismatches,
    )


def evaluate_original_alignment(
    positions: pd.DataFrame,
    decisions: pd.DataFrame,
    candidate: ReentryCandidate,
) -> dict[str, object]:
    """Measure which original same-side re-entries a policy would permit."""
    logical = logical_source_positions(positions)
    structural = _available_structure(decisions)
    entries = _available_entry_directions(decisions)
    rsi_crosses = (
        _available_rsi_crosses(decisions)
        if candidate.policy == "target_rsi_reconfirmation"
        else None
    )
    (
        eligible_delays,
        same_side,
        overlaps,
        missing_references,
        policy_eligible,
        direction_mismatches,
    ) = _same_side_alignment(logical, structural, entries, rsi_crosses, candidate)
    return {
        "source_rows": len(positions),
        "logical_positions": len(logical),
        "source_logical_positions_per_day": len(logical) / _source_days(logical),
        "same_side_reentries": same_side,
        "overlapping_same_side_positions": overlaps,
        "missing_continuation_reference": missing_references,
        "source_target_outcomes_available": False,
        "policy_eligible_same_side_reentries": policy_eligible,
        "direction_mismatched_same_side_reentries": direction_mismatches,
        "eligible_same_side_reentries": len(eligible_delays),
        "eligible_same_side_reentry_pct": (
            100.0 * len(eligible_delays) / same_side if same_side else 0.0
        ),
        "median_eligible_delay_seconds": (
            float(median(eligible_delays)) if eligible_delays else None
        ),
    }


def _duration_days(bars: pd.DataFrame) -> float:
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.empty:
        raise ValueError("re-entry screening requires non-empty datetime-indexed bars")
    elapsed = bars.index[-1] - bars.index[0] + pd.Timedelta(minutes=1)
    return elapsed.total_seconds() / 86_400.0


def _serial_summary(
    report: SerialPortfolioReport, duration_days: float
) -> dict[str, object]:
    values = report.to_dict()
    values.pop("trades")
    completed = int(values["completed_trades"])
    values["completed_trades_per_day"] = completed / duration_days
    return values


def _screen_candidates(
    bars: pd.DataFrame,
    decisions: pd.DataFrame,
    positions: pd.DataFrame,
    candidates: tuple[ReentryCandidate, ...],
) -> tuple[dict[str, object], ...]:
    duration = _duration_days(bars)
    rows: list[dict[str, object]] = []
    for candidate in candidates:
        config = SerialPortfolioConfig(
            reentry_cooldown_bars=candidate.cooldown_bars,
            same_direction_reentry_policy=candidate.policy,
            same_direction_reentry_clearance_bps=candidate.clearance_bps,
            target_continuation_limit_per_episode=(candidate.target_limit_per_episode),
            target_continuation_minimum_episode_bars=(candidate.minimum_episode_bars),
        )
        report = evaluate_serial_portfolio(bars, decisions, config)
        rows.append(
            {
                "candidate": candidate.to_dict(),
                "serial": _serial_summary(report, duration),
                "original_alignment": evaluate_original_alignment(
                    positions, decisions, candidate
                ),
            }
        )
    return tuple(rows)


def screen_reentry_candidates(
    bars: pd.DataFrame,
    decisions: pd.DataFrame,
    positions: pd.DataFrame,
) -> tuple[dict[str, object], ...]:
    """Retain results for the previously executed cooldown-only matrix."""
    return _screen_candidates(bars, decisions, positions, reentry_candidate_matrix())


def screen_target_continuation_candidates(
    bars: pd.DataFrame,
    decisions: pd.DataFrame,
    positions: pd.DataFrame,
) -> tuple[dict[str, object], ...]:
    """Retain results for the fixed outcome-aware continuation matrix."""
    return _screen_candidates(
        bars, decisions, positions, target_continuation_candidate_matrix()
    )


def screen_bounded_target_ladder_candidates(
    bars: pd.DataFrame,
    decisions: pd.DataFrame,
    positions: pd.DataFrame,
) -> tuple[dict[str, object], ...]:
    """Retain every frozen bounded target-ladder serial result."""
    return _screen_candidates(
        bars, decisions, positions, bounded_target_ladder_candidate_matrix()
    )


def screen_mature_target_continuation_candidates(
    bars: pd.DataFrame,
    decisions: pd.DataFrame,
    positions: pd.DataFrame,
) -> tuple[dict[str, object], ...]:
    """Retain the control, cap-2 reference, and mature challenger."""
    return _screen_candidates(
        bars,
        decisions,
        positions,
        mature_target_continuation_candidate_matrix(),
    )


def screen_target_rsi_candidates(
    bars: pd.DataFrame,
    decisions: pd.DataFrame,
    positions: pd.DataFrame,
) -> tuple[dict[str, object], ...]:
    """Retain results for the fixed target/RSI reconfirmation matrix."""
    return _screen_candidates(bars, decisions, positions, target_rsi_candidate_matrix())
