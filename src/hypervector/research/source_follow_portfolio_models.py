"""Typed contracts for continuous source-follow portfolio replay."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import math
from typing import Literal

from hypervector.data.hl_events import L2SnapshotEvent, PublicTradeEvent

SourceDirection = Literal["long", "short"]
SourceTradeStatus = Literal["target_completed", "time_exited", "liquidated"]
SOURCE_FOLLOW_MAX_EVENT_AGE_MS = 6_000


@dataclass(frozen=True)
class SourceReplayMark:
    """One authentic Hyperliquid mark/oracle observation."""

    ts_ms: int
    mark_price: float
    oracle_price: float


@dataclass(frozen=True)
class SourceReplayFunding:
    """One official hourly funding settlement."""

    ts_ms: int
    funding_rate: float


SourcePortfolioEvent = (
    L2SnapshotEvent | PublicTradeEvent | SourceReplayMark | SourceReplayFunding
)


@dataclass(frozen=True)
class SourceSignal:
    """One already-validated source-follow decision timestamp and direction."""

    decision_time_utc: str
    confidence: float | None = None
    signal_range_bps: float | None = None
    direction: SourceDirection = "short"
    allocation_multiplier: float = 1.0

    def __post_init__(self) -> None:
        utc_ms(self.decision_time_utc)
        if self.confidence is not None and (
            not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0
        ):
            raise ValueError("source signal confidence must be within [0, 1]")
        if self.signal_range_bps is not None and (
            not math.isfinite(self.signal_range_bps) or self.signal_range_bps < 0.0
        ):
            raise ValueError("source signal range must be finite and non-negative")
        if self.direction not in {"long", "short"}:
            raise ValueError("source signal direction must be long or short")
        if (
            not math.isfinite(self.allocation_multiplier)
            or not 0.0 < self.allocation_multiplier <= 1.0
        ):
            raise ValueError(
                "source signal allocation multiplier must be within (0, 1]"
            )


@dataclass(frozen=True)
class SourcePortfolioReplayConfig:
    """Execution and portfolio assumptions shared with the shadow profile."""

    initial_equity: float = 15_000.0
    margin_fraction: float = 0.50
    leverage: float = 30.0
    target_price_fraction: float = 8.0 / 30.0 / 100.0
    entry_pulse_seconds: float = 60.0
    entry_ttl_seconds: float = 60.0
    maximum_hold_seconds: float = 86_400.0
    maker_fee_rate: float = 0.00015
    taker_fee_rate: float = 0.00045
    submit_latency_ms: int = 50
    cancel_latency_ms: int = 50
    max_event_age_ms: int = SOURCE_FOLLOW_MAX_EVENT_AGE_MS
    size_decimals: int = 5
    price_tick: float = 1.0
    maximum_oracle_age_ms: int = 120_000
    receipt_timestamp_source: Literal["synthetic_exchange", "recorded"] = (
        "synthetic_exchange"
    )

    def __post_init__(self) -> None:
        """Reject execution assumptions outside the candidate contract."""
        _positive(self.initial_equity, "initial_equity")
        if not 0.0 < self.margin_fraction <= 1.0:
            raise ValueError("margin_fraction must be within (0, 1]")
        if not 0.0 < self.leverage <= 40.0:
            raise ValueError("leverage must be within (0, 40]")
        for name in (
            "target_price_fraction",
            "entry_pulse_seconds",
            "maximum_hold_seconds",
            "price_tick",
        ):
            _positive(float(getattr(self, name)), name)
        if self.entry_ttl_seconds < 0.0:
            raise ValueError("entry_ttl_seconds must be non-negative")
        self._validate_fees()
        self._validate_integers()
        if self.receipt_timestamp_source not in {"synthetic_exchange", "recorded"}:
            raise ValueError("unsupported receipt timestamp source")

    def _validate_fees(self) -> None:
        for name in ("maker_fee_rate", "taker_fee_rate"):
            value = float(getattr(self, name))
            if not 0.0 <= value < 1.0:
                raise ValueError(f"{name} must be within [0, 1)")

    def _validate_integers(self) -> None:
        for name in (
            "submit_latency_ms",
            "cancel_latency_ms",
            "max_event_age_ms",
            "maximum_oracle_age_ms",
        ):
            if int(getattr(self, name)) < 0:
                raise ValueError(f"{name} must be non-negative")
        if not 0 <= self.size_decimals <= 18:
            raise ValueError("size_decimals must be within [0, 18]")


@dataclass(frozen=True)
class SourcePortfolioTrade:
    """One flat-to-flat realized portfolio outcome."""

    direction: SourceDirection
    signal_time_utc: str
    entry_time_utc: str
    exit_time_utc: str
    status: SourceTradeStatus
    entry_price: float
    entry_quantity: float
    liquidation_price: float
    net_pnl: float
    funding_cashflow: float


@dataclass(frozen=True)
class SourcePortfolioReport:
    """Auditable continuous production-matcher replay summary."""

    initial_equity: float
    final_equity: float
    signal_count: int
    submitted_entries: int
    entry_filled_quantity: float
    completed_trades: int
    target_completions: int
    time_exits: int
    liquidations: int
    partial_liquidations: int
    open_positions: int
    maker_fees: float
    taker_fees: float
    funding_cashflow: float
    profit_factor: float | None
    maximum_drawdown_pct: float
    missing_oracle_settlements: int
    stale_oracle_settlements: int
    execution_uncertainty_annotations: int
    trades: tuple[SourcePortfolioTrade, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible report."""
        return asdict(self)


def utc_ms(value: str) -> int:
    """Parse a UTC ISO timestamp as epoch milliseconds."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0.0:
        raise ValueError("source signal timestamps must be UTC")
    return int(parsed.astimezone(UTC).timestamp() * 1_000)


def _positive(value: float, name: str) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
