"""Validated evidence models for the v51 SOL route-native shadow."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class MarkObservation:
    """One receipt-timestamped official Hyperliquid mark observation."""

    observed_ts_ms: int
    mark_price: float
    source: str = "hyperliquid_ws_activeAssetCtx"
    timestamp_source: str = "local_receive_no_exchange_timestamp"
    received_ts_ns: int | None = None

    def __post_init__(self) -> None:
        """Reject timestamps or marks that cannot support causal stop replay."""
        if (
            isinstance(self.observed_ts_ms, bool)
            or not isinstance(self.observed_ts_ms, int)
            or self.observed_ts_ms < 0
        ):
            raise ValueError("mark observation time must be nonnegative")
        if not math.isfinite(self.mark_price) or self.mark_price <= 0.0:
            raise ValueError("mark price must be positive and finite")
        if self.source != "hyperliquid_ws_activeAssetCtx":
            raise ValueError("mark source must be hyperliquid_ws_activeAssetCtx")
        if self.timestamp_source != "local_receive_no_exchange_timestamp":
            raise ValueError("mark timestamp source must remain local-receipt explicit")
        if self.received_ts_ns is not None:
            if (
                isinstance(self.received_ts_ns, bool)
                or not isinstance(self.received_ts_ns, int)
                or self.received_ts_ns < 0
            ):
                raise ValueError("mark receipt time must be nonnegative")
            if self.received_ts_ns // 1_000_000 != self.observed_ts_ms:
                raise ValueError("mark millisecond and nanosecond receipts disagree")

    @property
    def causal_receipt_ns(self) -> int:
        """Return the finest available causal local-receipt identity."""
        if self.received_ts_ns is not None:
            return self.received_ts_ns
        return self.observed_ts_ms * 1_000_000


@dataclass(frozen=True)
class SolRouteNativeShadowSpec:
    """Frozen v51 identity and point-in-time execution assumptions."""

    source_run_id: str
    source_profile_id: str
    source_profile_fingerprint: str
    cutoff_time_ms: int
    notional_usd: float
    taker_fee_rate: float

    def __post_init__(self) -> None:
        """Fail closed on malformed identity, cutoff, or economic evidence."""
        if not self.source_run_id.strip() or not self.source_profile_id.strip():
            raise ValueError("SOL shadow source identity must be non-empty")
        if len(self.source_profile_fingerprint) != 64:
            raise ValueError("SOL shadow profile fingerprint must be SHA-256 text")
        if self.cutoff_time_ms <= 0:
            raise ValueError("SOL shadow cutoff must be positive")
        if not math.isfinite(self.notional_usd) or self.notional_usd <= 0.0:
            raise ValueError("SOL shadow notional must be positive and finite")
        if (
            not math.isfinite(self.taker_fee_rate)
            or not 0.0 <= self.taker_fee_rate < 0.01
        ):
            raise ValueError(
                "SOL shadow taker fee must be finite and below one percent"
            )


@dataclass(frozen=True)
class SolFundingEvidence:
    """One complete official Hyperliquid funding-history response window."""

    requested_start_ms: int
    requested_end_ms: int
    events: tuple[tuple[int, float], ...]
    source: str = "hyperliquid_info_fundingHistory"

    def __post_init__(self) -> None:
        """Validate official identity, coverage bounds, and ordered settlements."""
        if self.source != "hyperliquid_info_fundingHistory":
            raise ValueError("SOL funding source must be official fundingHistory")
        if (
            self.requested_start_ms < 0
            or self.requested_end_ms < self.requested_start_ms
        ):
            raise ValueError("SOL funding coverage bounds are invalid")
        times: list[int] = []
        for timestamp_ms, rate in self.events:
            if isinstance(timestamp_ms, bool) or not isinstance(timestamp_ms, int):
                raise ValueError("SOL funding timestamp must be an integer")
            if not self.requested_start_ms <= timestamp_ms <= self.requested_end_ms:
                raise ValueError("SOL funding event is outside requested bounds")
            if not math.isfinite(rate):
                raise ValueError("SOL funding rate must be finite")
            times.append(timestamp_ms)
        if times != sorted(times) or len(times) != len(set(times)):
            raise ValueError("SOL funding timestamps must be ordered and unique")
