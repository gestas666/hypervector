"""Venue-event replay for the post-hoc SOL range-onset challenger."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd

from hypervector.data.oxa_price_archive import (
    OxaPriceArchiveConfig,
    load_verified_price_archive,
)
from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.mark_stop_trigger import (
    MarkQueryGapError,
    SampledMarkSeries,
)
from hypervector.research.oracle_price_series import CausalOraclePriceSeries
from hypervector.research.market_depth_database import (
    DEFAULT_MAXIMUM_BOOK_DELAY_MS,
    TimedMarketDepthFill,
    market_fill_at_or_after,
)
from hypervector.research.market_depth_fill import MarketSide
from hypervector.research.range_onset_event_replay import (
    EventFunding,
    EventReplayConfig,
    EventReplayReport,
    EventSignal,
    MarketFill,
    StopCrossing,
    replay_range_onset_events,
)
from hypervector.research.range_onset_event_trials import (
    EventTrial,
    capacity_shape_midpoint_trial_grid,
    capacity_shape_trial_grid,
    capacity_trial_grid,
    event_trial_grid,
    latency_trial_grid,
    v49_target_trial_grid,
)
from hypervector.research.range_onset_event_drawdown import (
    with_mark_to_market_drawdown,
)
from hypervector.research.research_database_replay import (
    ResearchReplayConfig,
    database_replay_coverage,
)
from hypervector.research.shared_portfolio_models import Direction
from hypervector.research.stop_trigger_database import first_trade_stop_crossing
from multi_asset_range_onset_risk_surface import build_range_onset_signals
from shared_strategy_screen import load_causal_window

_MINUTE_MS = 60_000
_MAXIMUM_MARK_GAP_MS = 120_000


@dataclass(frozen=True)
class _EventSurfaceRequest:
    """One explicit report-only event-surface request."""

    symbol: str
    bars_path: Path
    funding_paths: tuple[Path, ...]
    database_path: Path
    price_data_root: Path | None
    development_start: datetime
    development_end: datetime
    validation_end: datetime
    pseudo_holdout_end: datetime
    trial_surface: str
    signal_warmup_start: datetime | None
    price_chunk_hours: int


class _DatabaseSources:
    """Bound canonical venue queries to one read-only connection and symbol."""

    def __init__(
        self,
        connection: duckdb.DuckDBPyConnection,
        symbol: str,
    ) -> None:
        self._connection = connection
        self._symbol = symbol

    def market_fill(
        self,
        event_time_ms: int,
        side: MarketSide,
        quantity: float,
    ) -> TimedMarketDepthFill:
        """Walk the first fresh canonical L2 snapshot."""
        return market_fill_at_or_after(
            self._connection,
            symbol=self._symbol,
            event_time_ms=event_time_ms,
            side=side,
            quantity=quantity,
        )

    def stop_crossing(
        self,
        direction: Direction,
        stop_price: float,
        start_time_ms: int,
        end_time_ms: int,
    ) -> int | None:
        """Return the conservative public-trade crossing bound."""
        crossing = first_trade_stop_crossing(
            self._connection,
            symbol=self._symbol,
            direction=direction,
            stop_price=stop_price,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
        )
        return None if crossing is None else crossing.timestamp_ms


class _SampledMarkStop:
    """Adapt a validated sampled mark series to the replay trigger contract."""

    def __init__(self, marks: SampledMarkSeries) -> None:
        self._marks = marks

    def stop_crossing(
        self,
        direction: Direction,
        stop_price: float,
        start_time_ms: int,
        end_time_ms: int,
    ) -> int | None:
        """Return the first sampled mark crossing timestamp."""
        crossing = self._marks.first_crossing(
            direction, stop_price, start_time_ms, end_time_ms
        )
        return None if crossing is None else crossing.timestamp_ms


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit chronological venue-event replay command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--funding", type=Path, action="append", required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--price-data-root", type=Path)
    parser.add_argument("--price-chunk-hours", type=_positive_int, default=24)
    parser.add_argument("--signal-warmup-start", type=_utc_datetime)
    parser.add_argument("--development-start", type=_utc_datetime, required=True)
    parser.add_argument("--development-end", type=_utc_datetime, required=True)
    parser.add_argument("--validation-end", type=_utc_datetime, required=True)
    parser.add_argument("--pseudo-holdout-end", type=_utc_datetime, required=True)
    parser.add_argument(
        "--surface",
        choices=(
            "standard",
            "capacity",
            "capacity-shape",
            "capacity-shape-midpoint-posthoc",
            "latency",
            "v49-target-exit-posthoc",
        ),
        default="standard",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def to_event_signals(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
) -> tuple[EventSignal, ...]:
    """Convert close-known minute rows into next-boundary event decisions."""
    if not bars.index.equals(signals.index):
        raise ValueError("bars and signals must share one index")
    columns = ("long_entry", "short_entry", "long_exit", "short_exit")
    missing = set(columns).difference(signals.columns)
    if missing or "close" not in bars:
        raise ValueError(f"event conversion is missing columns: {sorted(missing)}")
    active = signals.loc[:, columns].astype(bool).any(axis=1)
    events: list[EventSignal] = []
    for timestamp, row in signals.loc[active, columns].iterrows():
        events.append(
            EventSignal(
                _timestamp_ms(timestamp) + _MINUTE_MS,
                float(bars.at[timestamp, "close"]),
                bool(row["long_entry"]),
                bool(row["short_entry"]),
                bool(row["long_exit"]),
                bool(row["short_exit"]),
            )
        )
    return tuple(events)


def to_event_funding(
    bars: pd.DataFrame,
    oracle_prices: CausalOraclePriceSeries | None = None,
    *,
    minimum_timestamp_ms: int | None = None,
    potential_position_windows: Sequence[tuple[int, int]] | None = None,
) -> tuple[EventFunding, ...]:
    """Convert potentially payable funding rows with causal oracle evidence."""
    required = {"funding_rate"}
    missing = required.difference(bars.columns)
    if missing:
        raise ValueError(f"funding conversion is missing columns: {sorted(missing)}")
    active = bars["funding_rate"].astype(float).ne(0.0)
    if minimum_timestamp_ms is not None:
        if minimum_timestamp_ms < 0:
            raise ValueError("minimum funding timestamp must be non-negative")
        timestamps = pd.Series(
            [_timestamp_ms(index) for index in bars.index],
            index=bars.index,
        )
        active &= timestamps.ge(minimum_timestamp_ms)
    if potential_position_windows is not None:
        windows = _validated_position_windows(potential_position_windows)
        timestamps = pd.Series(
            [_timestamp_ms(index) for index in bars.index],
            index=bars.index,
        )
        active &= timestamps.map(
            lambda timestamp: any(
                start_ms <= int(timestamp) <= end_ms for start_ms, end_ms in windows
            )
        )
    if not active.any():
        return ()
    if oracle_prices is None:
        raise ValueError("oracle price evidence is required for funding conversion")
    events: list[EventFunding] = []
    for timestamp, row in bars.loc[active].iterrows():
        timestamp_ms = _timestamp_ms(timestamp)
        observation = oracle_prices.at_or_before(timestamp_ms)
        events.append(
            EventFunding(
                timestamp_ms,
                float(row["funding_rate"]),
                observation.oracle_price,
                observation.timestamp_ms,
                "oxa_oracle_last_at_or_before",
            )
        )
    return tuple(events)


def _funding_evidence(events: tuple[EventFunding, ...]) -> dict[str, object]:
    """Summarize the bound oracle observations used by funding settlements."""
    if not events:
        return {
            "event_count": 0,
            "source": "oxa_oracle_last_at_or_before",
            "maximum_staleness_ms": 0,
        }
    observed = [event.reference_observed_time_ms for event in events]
    if any(timestamp is None for timestamp in observed):
        raise ValueError("funding event is missing oracle observation provenance")
    gaps = [
        event.timestamp_ms - int(event.reference_observed_time_ms)
        for event in events
        if event.reference_observed_time_ms is not None
    ]
    sources = sorted({event.reference_source for event in events})
    return {
        "event_count": len(events),
        "sources": sources,
        "maximum_staleness_ms": max(gaps),
    }


def run_event_surface(
    *,
    symbol: str,
    bars_path: Path,
    funding_paths: list[Path],
    database_path: Path,
    price_data_root: Path | None,
    development_start: datetime,
    development_end: datetime,
    validation_end: datetime,
    pseudo_holdout_end: datetime,
    trial_surface: str = "standard",
    signal_warmup_start: datetime | None = None,
    price_chunk_hours: int = 24,
) -> dict[str, object]:
    """Run all fixed trials against one verified canonical venue tape."""
    return _run_event_surface(
        _EventSurfaceRequest(
            symbol,
            bars_path,
            tuple(funding_paths),
            database_path,
            price_data_root,
            development_start,
            development_end,
            validation_end,
            pseudo_holdout_end,
            trial_surface,
            signal_warmup_start,
            price_chunk_hours,
        )
    )


def _run_event_surface(request: _EventSurfaceRequest) -> dict[str, object]:
    """Execute a validated event-surface request."""
    trials = _trial_grid(request.trial_surface)
    signal_start = request.signal_warmup_start or request.development_start
    if signal_start > request.development_start:
        raise ValueError("signal_warmup_start must not follow development_start")
    mark_context = _mark_context(
        request.price_data_root,
        request.symbol,
        signal_start,
        request.pseudo_holdout_end,
        request.price_chunk_hours,
    )
    oracle_prices = None if mark_context is None else mark_context[1]
    evidence, signals, funding = _load_event_inputs(
        request.bars_path,
        list(request.funding_paths),
        signal_start,
        request.pseudo_holdout_end,
        oracle_prices,
        request.development_start,
        trials,
    )
    evidence = {**evidence, "funding_reference": _funding_evidence(funding)}
    coverage = _coverage(
        request.database_path,
        request.symbol,
        request.development_start,
        request.pseudo_holdout_end,
    )
    segments, mark_segments = _replay_surfaces(
        request.database_path,
        request.symbol,
        signals,
        funding,
        mark_context,
        request.development_start,
        request.development_end,
        request.validation_end,
        request.pseudo_holdout_end,
        trials,
    )
    return _artifact(
        request.symbol,
        evidence,
        coverage,
        segments,
        mark_segments,
        trials,
        request.trial_surface,
        signal_start,
    )


def _load_event_inputs(
    bars_path: Path,
    funding_paths: list[Path],
    start: datetime,
    end: datetime,
    oracle_prices: CausalOraclePriceSeries | None,
    funding_start: datetime,
    trials: tuple[EventTrial, ...],
) -> tuple[dict[str, object], tuple[EventSignal, ...], tuple[EventFunding, ...]]:
    """Load causal bars once and derive immutable event and funding rows."""
    bars, evidence = load_causal_window(bars_path, funding_paths, start, end)
    signals = to_event_signals(bars, build_range_onset_signals(bars))
    funding = to_event_funding(
        bars,
        oracle_prices,
        minimum_timestamp_ms=_datetime_ms(funding_start),
        potential_position_windows=_potential_position_windows(signals, trials),
    )
    return evidence, signals, funding


def _potential_position_windows(
    signals: Sequence[EventSignal],
    trials: Sequence[EventTrial],
) -> tuple[tuple[int, int], ...]:
    """Bound settlements to periods when any frozen trial could hold risk."""
    if not trials:
        raise ValueError("event replay requires at least one trial")
    horizon_ms = max(
        _event_config(trial).max_hold_ms
        + trial.decision_delay_ms
        + DEFAULT_MAXIMUM_BOOK_DELAY_MS
        for trial in trials
    )
    return tuple(
        (event.decision_time_ms, event.decision_time_ms + horizon_ms)
        for event in signals
        if event.long_entry or event.short_entry
    )


def _validated_position_windows(
    windows: Sequence[tuple[int, int]],
) -> tuple[tuple[int, int], ...]:
    """Validate inclusive causal windows used to scope funding evidence."""
    validated: list[tuple[int, int]] = []
    for start_ms, end_ms in windows:
        if (
            isinstance(start_ms, bool)
            or not isinstance(start_ms, int)
            or isinstance(end_ms, bool)
            or not isinstance(end_ms, int)
            or start_ms < 0
            or end_ms < start_ms
        ):
            raise ValueError("potential position windows require ordered timestamps")
        validated.append((start_ms, end_ms))
    return tuple(validated)


def _replay_surfaces(
    database_path: Path,
    symbol: str,
    signals: tuple[EventSignal, ...],
    funding: tuple[EventFunding, ...],
    mark_context: tuple[
        SampledMarkSeries,
        CausalOraclePriceSeries,
        dict[str, int | str],
    ]
    | None,
    development_start: datetime,
    development_end: datetime,
    validation_end: datetime,
    pseudo_holdout_end: datetime,
    trials: tuple[EventTrial, ...],
) -> tuple[dict[str, dict[str, object]], dict[str, object] | None]:
    """Replay public-trade and sampled-mark surfaces on one DB connection."""
    with duckdb.connect(str(database_path), read_only=True) as connection:
        sources = _DatabaseSources(connection, symbol)
        segments = _segments(
            signals,
            funding,
            sources.market_fill,
            sources.stop_crossing,
            development_start,
            development_end,
            validation_end,
            pseudo_holdout_end,
            trials,
        )
        mark_segments = _mark_segments(
            signals,
            funding,
            sources.market_fill,
            mark_context,
            development_start,
            development_end,
            validation_end,
            pseudo_holdout_end,
            trials,
        )
    return segments, mark_segments


def _trial_grid(surface: str) -> tuple[EventTrial, ...]:
    """Resolve one explicit immutable event-trial surface."""
    if surface == "standard":
        return event_trial_grid()
    if surface == "capacity":
        return capacity_trial_grid()
    if surface == "capacity-shape":
        return capacity_shape_trial_grid()
    if surface == "capacity-shape-midpoint-posthoc":
        return capacity_shape_midpoint_trial_grid()
    if surface == "latency":
        return latency_trial_grid()
    if surface == "v49-target-exit-posthoc":
        return v49_target_trial_grid()
    raise ValueError(
        "trial_surface must be standard|capacity|capacity-shape|"
        "capacity-shape-midpoint-posthoc|latency|v49-target-exit-posthoc"
    )


def _coverage(
    database_path: Path,
    symbol: str,
    start: datetime,
    end: datetime,
) -> dict[str, object]:
    """Load verified canonical database coverage for the replay window."""
    return database_replay_coverage(
        ResearchReplayConfig(database_path, symbol, start, end),
        include_trades=True,
    )


def _segments(
    signals: tuple[EventSignal, ...],
    funding: tuple[EventFunding, ...],
    market_fill: MarketFill,
    stop_crossing: StopCrossing,
    development_start: datetime,
    development_end: datetime,
    validation_end: datetime,
    pseudo_holdout_end: datetime,
    trials: tuple[EventTrial, ...],
    mark_series: SampledMarkSeries | None = None,
) -> dict[str, dict[str, object]]:
    boundaries = (
        ("development", development_start, development_end),
        ("validation", development_end, validation_end),
        ("pseudo_holdout", validation_end, pseudo_holdout_end),
        ("continuous", development_start, pseudo_holdout_end),
    )
    return {
        name: _segment(
            signals,
            funding,
            market_fill,
            stop_crossing,
            start,
            end,
            trials,
            mark_series,
        )
        for name, start, end in boundaries
    }


def _segment(
    signals: tuple[EventSignal, ...],
    funding: tuple[EventFunding, ...],
    market_fill: MarketFill,
    stop_crossing: StopCrossing,
    start: datetime,
    end: datetime,
    trials: tuple[EventTrial, ...],
    mark_series: SampledMarkSeries | None,
) -> dict[str, object]:
    start_ms, end_ms = _datetime_ms(start), _datetime_ms(end)
    segment_signals = tuple(
        event for event in signals if start_ms <= event.decision_time_ms < end_ms
    )
    segment_funding = tuple(
        event for event in funding if start_ms <= event.timestamp_ms < end_ms
    )
    reports = [
        _run_trial(
            trial,
            segment_signals,
            segment_funding,
            market_fill,
            stop_crossing,
            end_ms,
            mark_series,
        )
        for trial in trials
    ]
    return {
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "signal_events": len(segment_signals),
        "funding_events": len(segment_funding),
        "trials": reports,
    }


def _run_trial(
    trial: EventTrial,
    signals: tuple[EventSignal, ...],
    funding: tuple[EventFunding, ...],
    market_fill: MarketFill,
    stop_crossing: StopCrossing,
    end_ms: int,
    mark_series: SampledMarkSeries | None,
) -> dict[str, object]:
    config = _event_config(trial)
    report = replay_range_onset_events(
        signals,
        funding,
        config,
        market_fill=market_fill,
        stop_crossing=stop_crossing,
        end_time_ms=end_ms,
    )
    if mark_series is not None:
        report = with_mark_to_market_drawdown(report, funding, mark_series)
    return _trial_report(trial, config, report)


def _trial_report(
    trial: EventTrial,
    config: EventReplayConfig,
    report: EventReplayReport,
) -> dict[str, object]:
    trial_id = f"stop={trial.stop_bps:g}__exposure={trial.effective_exposure:g}"
    if trial.decision_delay_ms:
        trial_id += f"__delay_ms={trial.decision_delay_ms}"
    if trial.target_bps is not None:
        trial_id += f"__target_bps={trial.target_bps:g}"
    if trial.initial_equity != 15_000.0:
        trial_id += f"__equity={trial.initial_equity:g}"
    if trial.taker_fee_rate != 0.00045:
        trial_id += f"__fee_bps={trial.taker_fee_rate * 10_000:g}"
    return {
        "trial_id": trial_id,
        "trial": asdict(trial),
        "replay_config": asdict(config),
        "effective_exposure": trial.effective_exposure,
        "execution_authority": "none",
        "event_replay": report.to_dict(),
    }


def _event_config(trial: EventTrial) -> EventReplayConfig:
    """Translate one immutable surface row into its replay contract."""
    return EventReplayConfig(
        initial_equity=trial.initial_equity,
        margin_fraction=trial.margin_fraction,
        leverage=trial.leverage,
        stop_bps=trial.stop_bps,
        target_bps=trial.target_bps,
        taker_fee_rate=trial.taker_fee_rate,
        decision_delay_ms=trial.decision_delay_ms,
    )


def _artifact(
    symbol: str,
    evidence: dict[str, object],
    coverage: dict[str, object],
    segments: dict[str, dict[str, object]],
    mark_segments: dict[str, object] | None,
    trials: tuple[EventTrial, ...],
    trial_surface: str,
    signal_warmup_start: datetime,
) -> dict[str, object]:
    return {
        "schema_version": 3,
        "mode": "multi_asset_range_onset_event_replay_post_hoc",
        "symbol": symbol.strip().upper(),
        "execution_authority": "none",
        "model_authority": "none",
        "initial_equity": trials[0].initial_equity,
        "trial_count": len(trials),
        "trial_surface": trial_surface,
        "signal_warmup_start_utc": signal_warmup_start.isoformat(),
        "trigger_bound": "first_public_trade_crossing_then_first_fresh_L2",
        "data_evidence": evidence,
        "database_coverage": coverage,
        "sampled_mark_surface": mark_segments,
        **segments,
        "limitations": [
            "range-onset rule was discovered after inspecting the full-year baseline",
            "public-trade stop crossing may trigger earlier than venue mark price",
            "sampled marks can miss a crossing and recovery between observations",
            "visible depth does not guarantee liquidity survives until IOC matching",
            "maximum drawdown is realized-equity rather than intratrade mark-to-market",
            "funding uses the most conservative lifecycle liquidation boundary",
            "liquidation uses a full visible-depth exit, not partial/backstop transfer",
            "fresh forward shadow evidence is required before execution promotion",
            *(
                [
                    "v49 fixed-target candidates were declared after live giveback evidence"
                ]
                if trial_surface == "v49-target-exit-posthoc"
                else []
            ),
        ],
    }


def _mark_context(
    data_root: Path | None,
    symbol: str,
    start: datetime,
    end: datetime,
    partition_hours: int = 24,
) -> (
    tuple[
        SampledMarkSeries,
        CausalOraclePriceSeries,
        dict[str, int | str],
    ]
    | None
):
    if data_root is None:
        return None
    if partition_hours <= 0:
        raise ValueError("price partition hours must be positive")
    archive_start = start.astimezone(UTC).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    archive_end = end.astimezone(UTC).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    if archive_end < end:
        archive_end += timedelta(days=1)
    archive = load_verified_price_archive(
        OxaPriceArchiveConfig(
            symbol,
            archive_start,
            archive_end,
            data_root,
            chunk=timedelta(hours=partition_hours),
            maximum_gap=timedelta(days=1),
        )
    )
    marks = SampledMarkSeries(
        archive.frame.loc[:, ["ts_ms", "mark_price"]],
        maximum_gap_ms=_MAXIMUM_MARK_GAP_MS,
        query_scoped=True,
    )
    oracle_prices = CausalOraclePriceSeries(
        archive.frame.loc[:, ["ts_ms", "oracle_price"]],
        maximum_staleness_ms=_MAXIMUM_MARK_GAP_MS,
    )
    evidence = {
        "partition_count": archive.partition_count,
        "row_count": archive.row_count,
        "maximum_observed_gap_ms": archive.maximum_observed_gap_ms,
        "partition_hours": partition_hours,
        "funding_reference": "oxa_oracle_last_at_or_before",
        "maximum_funding_reference_staleness_ms": _MAXIMUM_MARK_GAP_MS,
    }
    return marks, oracle_prices, evidence


def _mark_segments(
    signals: tuple[EventSignal, ...],
    funding: tuple[EventFunding, ...],
    market_fill: MarketFill,
    context: tuple[
        SampledMarkSeries,
        CausalOraclePriceSeries,
        dict[str, int | str],
    ]
    | None,
    development_start: datetime,
    development_end: datetime,
    validation_end: datetime,
    pseudo_holdout_end: datetime,
    trials: tuple[EventTrial, ...],
) -> dict[str, object] | None:
    if context is None:
        return None
    marks, _oracle_prices, evidence = context
    stop = _SampledMarkStop(marks)
    try:
        segments = _segments(
            signals,
            funding,
            market_fill,
            stop.stop_crossing,
            development_start,
            development_end,
            validation_end,
            pseudo_holdout_end,
            trials,
            marks,
        )
    except MarkQueryGapError as exc:
        return {
            "price_archive": evidence,
            "mark_validation_status": "censored",
            "censor_reason": str(exc),
        }
    return {
        "price_archive": evidence,
        "mark_validation_status": "complete",
        **segments,
    }


def _timestamp_ms(value: object) -> int:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("event timestamps must be timezone-aware")
    return int(timestamp.timestamp() * 1_000)


def _datetime_ms(value: datetime) -> int:
    return int(value.timestamp() * 1_000)


def _utc_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != pd.Timedelta(0):
        raise argparse.ArgumentTypeError("timestamps must be UTC")
    return parsed.astimezone(UTC)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def main() -> int:
    """Run the event grid and write one immutable report-only artifact."""
    args = build_parser().parse_args()
    report = run_event_surface(
        symbol=args.symbol,
        bars_path=args.bars,
        funding_paths=args.funding,
        database_path=args.database,
        price_data_root=args.price_data_root,
        development_start=args.development_start,
        development_end=args.development_end,
        validation_end=args.validation_end,
        pseudo_holdout_end=args.pseudo_holdout_end,
        trial_surface=args.surface,
        signal_warmup_start=args.signal_warmup_start,
        price_chunk_hours=args.price_chunk_hours,
    )
    write_immutable_json(args.output, report)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
