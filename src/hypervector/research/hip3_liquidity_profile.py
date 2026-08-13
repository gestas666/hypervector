"""Point-in-time visible-liquidity measurements for HIP-3 order books."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from math import ceil, floor, isfinite
from pathlib import Path

import duckdb

from hypervector.data.oxa_api import validate_hip3_symbol
from hypervector.research.hip3_fee_model import (
    EffectiveHip3Fees,
    Hip3FeeInputs,
    effective_hip3_fees,
)
from hypervector.research.hip3_market_sessions import (
    SCHEDULED_EXTERNAL_REFERENCE,
    SCHEDULED_INTERNAL_OR_CLOSED,
    oracle_session_contract,
    scheduled_oracle_session,
)
from hypervector.research.market_depth_fill import (
    depth_levels_from_records,
    walk_market_order,
)

_REQUIRED_RELATIONS = frozenset(
    {
        "archive_bundles",
        "archive_bundle_provenance",
        "replay_book_snapshots",
        "replay_public_trades",
    }
)


@dataclass(frozen=True)
class DistributionSummary:
    """Count and selected empirical quantiles for one finite metric."""

    count: int
    p50: float | None
    p90: float | None
    p99: float | None


@dataclass(frozen=True)
class LiquidityCoverage:
    """Archive and causal sampling coverage for one exact market identity."""

    archive_start_utc: datetime
    archive_end_utc: datetime
    archive_bundles: int
    archive_book_rows: int
    expected_boundaries: int
    observed_boundaries: int
    timely_samples: int
    late_boundaries: int
    missing_boundaries: int


@dataclass(frozen=True)
class SessionLiquidity:
    """Spread distribution for one descriptive scheduled-session partition."""

    session: str
    samples: int
    spread_bps: DistributionSummary


@dataclass(frozen=True)
class NotionalLiquidity:
    """Finite visible-depth capacity and costs for one requested USD size."""

    notional_usd: float
    samples: int
    buy_complete_rate: float
    sell_complete_rate: float
    both_complete_rate: float
    buy_visible_cost_bps: DistributionSummary
    sell_visible_cost_bps: DistributionSummary
    round_trip_visible_cost_bps: DistributionSummary
    round_trip_taker_total_cost_bps: DistributionSummary


@dataclass(frozen=True)
class Hip3LiquidityProfile:
    """Read-only HIP-3 liquidity evidence without profitability claims."""

    symbol: str
    sample_interval_minutes: int
    maximum_boundary_delay_ms: int
    coverage: LiquidityCoverage
    spread_bps: DistributionSummary
    sessions: tuple[SessionLiquidity, ...]
    notionals: tuple[NotionalLiquidity, ...]
    public_trade_rows: int
    fee_status: str
    fees: EffectiveHip3Fees | None
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable mapping except for ISO conversion."""
        return asdict(self)


@dataclass(frozen=True)
class _BookSample:
    boundary_utc: datetime
    delay_ms: int
    mid_price: float
    spread_bps: float
    bids: object
    asks: object


def build_liquidity_profile(
    database_path: Path,
    *,
    symbol: str,
    notionals_usd: tuple[float, ...],
    sample_interval_minutes: int = 5,
    maximum_boundary_delay_ms: int = 15_000,
    fee_inputs: Hip3FeeInputs | None = None,
) -> Hip3LiquidityProfile:
    """Measure delay-bounded HIP-3 spread and visible-depth capacity."""
    _validate_request(
        database_path,
        symbol,
        notionals_usd,
        sample_interval_minutes,
        maximum_boundary_delay_ms,
    )
    with duckdb.connect(str(database_path), read_only=True) as connection:
        connection.execute("SET TimeZone='UTC'")
        _validate_schema(connection)
        archive = _archive_metadata(connection, symbol)
        first_boundary = _first_boundary(archive[0], sample_interval_minutes)
        rows = _load_boundary_samples(
            connection,
            symbol,
            first_boundary,
            archive[1],
            sample_interval_minutes,
        )
        public_trade_rows = _public_trade_count(connection, symbol)
    samples = tuple(row for row in rows if row.delay_ms <= maximum_boundary_delay_ms)
    if not samples:
        raise ValueError("no timely HIP-3 book samples satisfy the delay contract")
    coverage = _coverage(
        archive, first_boundary, rows, samples, sample_interval_minutes
    )
    fees = effective_hip3_fees(fee_inputs) if fee_inputs is not None else None
    return Hip3LiquidityProfile(
        symbol=symbol,
        sample_interval_minutes=sample_interval_minutes,
        maximum_boundary_delay_ms=maximum_boundary_delay_ms,
        coverage=coverage,
        spread_bps=_distribution([sample.spread_bps for sample in samples]),
        sessions=_session_profiles(samples, symbol),
        notionals=tuple(
            _notional_profile(samples, value, fees) for value in notionals_usd
        ),
        public_trade_rows=public_trade_rows,
        fee_status="modeled_current_inputs"
        if fees is not None
        else "unresolved_excluded",
        fees=fees,
        limitations=_limitations(public_trade_rows, fees),
    )


def _validate_request(
    database_path: Path,
    symbol: str,
    notionals_usd: tuple[float, ...],
    sample_interval_minutes: int,
    maximum_boundary_delay_ms: int,
) -> None:
    if not database_path.is_file():
        raise FileNotFoundError(
            f"HIP-3 research database does not exist: {database_path}"
        )
    validate_hip3_symbol(symbol)
    if not notionals_usd or len(set(notionals_usd)) != len(notionals_usd):
        raise ValueError("notionals_usd must contain unique positive finite values")
    if any(not isfinite(value) or value <= 0.0 for value in notionals_usd):
        raise ValueError("notionals_usd must contain unique positive finite values")
    if isinstance(sample_interval_minutes, bool) or sample_interval_minutes <= 0:
        raise ValueError("sample_interval_minutes must be a positive integer")
    if isinstance(maximum_boundary_delay_ms, bool) or maximum_boundary_delay_ms <= 0:
        raise ValueError("maximum_boundary_delay_ms must be a positive integer")


def _validate_schema(connection: duckdb.DuckDBPyConnection) -> None:
    observed = {str(row[0]) for row in connection.execute("SHOW TABLES").fetchall()}
    missing = sorted(_REQUIRED_RELATIONS.difference(observed))
    if missing:
        raise ValueError(f"HIP-3 liquidity database is missing relations: {missing}")


def _archive_metadata(
    connection: duckdb.DuckDBPyConnection,
    symbol: str,
) -> tuple[datetime, datetime, int, int]:
    row = connection.execute(
        """
        SELECT min(b.start_utc), max(b.end_utc), count(*), sum(b.book_rows),
               count(*) FILTER (WHERE p.market_family = 'hip3')
        FROM archive_bundles AS b
        LEFT JOIN archive_bundle_provenance AS p USING (bundle_id)
        WHERE b.symbol = ?
        """,
        [symbol],
    ).fetchone()
    if row is None or row[0] is None or int(row[2]) != int(row[4]):
        raise ValueError(f"{symbol} does not have complete HIP-3 provenance")
    return _utc(row[0]), _utc(row[1]), int(row[2]), int(row[3])


def _load_boundary_samples(
    connection: duckdb.DuckDBPyConnection,
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
    interval_minutes: int,
) -> tuple[_BookSample, ...]:
    interval = f"INTERVAL '{interval_minutes} minutes'"
    rows = connection.execute(
        f"""
        WITH bucketed AS (
            SELECT *, time_bucket({interval}, ts_utc) AS boundary_utc
            FROM replay_book_snapshots
            WHERE symbol = ? AND ts_utc >= ? AND ts_utc < ?
        )
        SELECT boundary_utc, epoch_ms(ts_utc) - epoch_ms(boundary_utc),
               mid_price, spread_bps, bids, asks
        FROM bucketed
        QUALIFY row_number() OVER (
            PARTITION BY boundary_utc ORDER BY ts_exchange_ms
        ) = 1
        ORDER BY boundary_utc
        """,
        [symbol, start_utc, end_utc],
    ).fetchall()
    return tuple(_sample(row) for row in rows)


def _sample(row: tuple[object, ...]) -> _BookSample:
    boundary = _utc(row[0])
    delay = _integer(row[1], "boundary delay")
    mid = _positive_float(row[2], "mid_price")
    spread = _nonnegative_float(row[3], "spread_bps")
    return _BookSample(boundary, delay, mid, spread, row[4], row[5])


def _coverage(
    archive: tuple[datetime, datetime, int, int],
    first_boundary: datetime,
    rows: tuple[_BookSample, ...],
    samples: tuple[_BookSample, ...],
    interval_minutes: int,
) -> LiquidityCoverage:
    seconds = max((archive[1] - first_boundary).total_seconds(), 0.0)
    expected = ceil(seconds / (interval_minutes * 60))
    return LiquidityCoverage(
        archive[0],
        archive[1],
        archive[2],
        archive[3],
        expected,
        len(rows),
        len(samples),
        len(rows) - len(samples),
        max(expected - len(rows), 0),
    )


def _session_profiles(
    samples: tuple[_BookSample, ...], symbol: str
) -> tuple[SessionLiquidity, ...]:
    contract = oracle_session_contract(symbol)
    labels = (
        (SCHEDULED_EXTERNAL_REFERENCE, SCHEDULED_INTERNAL_OR_CLOSED)
        if contract["status"] == "classified"
        else ("unclassified_schedule",)
    )
    grouped: dict[str, list[float]] = {label: [] for label in labels}
    for sample in samples:
        label = _liquidity_session(symbol, sample.boundary_utc, contract)
        grouped[label].append(sample.spread_bps)
    return tuple(
        SessionLiquidity(name, len(values), _distribution(values))
        for name, values in grouped.items()
    )


def _liquidity_session(
    symbol: str, timestamp: datetime, contract: dict[str, object]
) -> str:
    if contract["status"] != "classified":
        return "unclassified_schedule"
    return scheduled_oracle_session(symbol, timestamp)


def _notional_profile(
    samples: tuple[_BookSample, ...],
    notional_usd: float,
    fees: EffectiveHip3Fees | None,
) -> NotionalLiquidity:
    buys: list[float] = []
    sells: list[float] = []
    round_trips: list[float] = []
    taker_totals: list[float] = []
    buy_complete = 0
    sell_complete = 0
    for sample in samples:
        buy, sell = _fills(sample, notional_usd)
        if buy is not None:
            buy_complete += 1
            buys.append(buy)
        if sell is not None:
            sell_complete += 1
            sells.append(sell)
        if buy is not None and sell is not None:
            round_trips.append(buy + sell)
            if fees is not None:
                taker_totals.append(buy + sell + fees.round_trip_taker_fee_bps)
    count = len(samples)
    return NotionalLiquidity(
        notional_usd,
        count,
        buy_complete / count,
        sell_complete / count,
        len(round_trips) / count,
        _distribution(buys),
        _distribution(sells),
        _distribution(round_trips),
        _distribution(taker_totals),
    )


def _fills(
    sample: _BookSample, notional_usd: float
) -> tuple[float | None, float | None]:
    quantity = notional_usd / sample.mid_price
    bids = depth_levels_from_records(sample.bids, label="bids")
    asks = depth_levels_from_records(sample.asks, label="asks")
    buy = walk_market_order(asks, side="buy", quantity=quantity)
    sell = walk_market_order(bids, side="sell", quantity=quantity)
    buy_cost = (buy.vwap / sample.mid_price - 1.0) * 10_000.0 if buy.complete else None
    sell_cost = (
        (1.0 - sell.vwap / sample.mid_price) * 10_000.0 if sell.complete else None
    )
    return buy_cost, sell_cost


def _distribution(values: list[float]) -> DistributionSummary:
    finite = sorted(value for value in values if isfinite(value))
    if not finite:
        return DistributionSummary(0, None, None, None)
    return DistributionSummary(
        len(finite),
        _quantile(finite, 0.50),
        _quantile(finite, 0.90),
        _quantile(finite, 0.99),
    )


def _quantile(values: list[float], probability: float) -> float:
    position = (len(values) - 1) * probability
    lower = floor(position)
    upper = ceil(position)
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


def _first_boundary(start_utc: datetime, interval_minutes: int) -> datetime:
    interval_seconds = interval_minutes * 60
    epoch_seconds = start_utc.timestamp()
    boundary_seconds = ceil(epoch_seconds / interval_seconds) * interval_seconds
    return datetime.fromtimestamp(boundary_seconds, tz=UTC)


def _public_trade_count(connection: duckdb.DuckDBPyConnection, symbol: str) -> int:
    row = connection.execute(
        "SELECT count(*) FROM replay_public_trades WHERE symbol = ?", [symbol]
    ).fetchone()
    if row is None:
        raise RuntimeError("public-trade count query returned no row")
    return _integer(row[0], "public trade count")


def _limitations(
    public_trade_rows: int,
    fees: EffectiveHip3Fees | None,
) -> tuple[str, ...]:
    limitations = [
        "visible_l2_only_no_queue_or_fill_probability",
        "funding_latency_after_sample_and_adverse_selection_excluded",
        "usd_notional_assumes_price_times_visible_size",
        "scheduled_session_is_not_observed_oracle_mode",
        "scheduled_session_partition_is_descriptive_not_an_execution_gate",
    ]
    if fees is None:
        limitations.append("fees_unresolved_and_excluded")
    else:
        limitations.append("fee_model_uses_current_inputs_not_historical_fee_state")
    if public_trade_rows == 0:
        limitations.append("public_trades_unavailable")
    return tuple(limitations)


def _utc(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise RuntimeError("archive timestamp must be a datetime")
    if value.tzinfo is None:
        raise RuntimeError("archive timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(f"{label} must be an integer")
    return value


def _positive_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise RuntimeError(f"{label} must be numeric")
    converted = float(value)
    if not isfinite(converted) or converted <= 0.0:
        raise RuntimeError(f"{label} must be positive and finite")
    return converted


def _nonnegative_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise RuntimeError(f"{label} must be numeric")
    converted = float(value)
    if not isfinite(converted) or converted < 0.0:
        raise RuntimeError(f"{label} must be non-negative and finite")
    return converted
