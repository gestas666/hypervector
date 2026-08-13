"""Backend-authoritative telemetry for the BTC source-follow live canary."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from hypervector.live.hyperliquid_protocol import HyperliquidOrderAck
from hypervector.live.sol_range_onset_live_telemetry import SolLiveTelemetry
from hypervector.live.source_follow_live_config import SourceFollowLiveConfig
from hypervector.live.source_follow_live_ledger import SourceFollowLiveLedger
from hypervector.regime.source_follow_runtime import SourceFollowDecision


class SourceFollowLiveTelemetry(SolLiveTelemetry):
    """Project BTC source decisions and venue facts into one durable ledger."""

    def __init__(
        self,
        *,
        config: SourceFollowLiveConfig,
        ledger: SourceFollowLiveLedger,
        now_fn: Callable[[], datetime],
    ) -> None:
        super().__init__(config=config, ledger=ledger, now_fn=now_fn)
        self._source_config = config

    def _configuration_identity(self) -> dict[str, object]:
        profile = self._source_config.profile
        return {
            "symbol": self._source_config.symbol,
            "network": self._source_config.network,
            "strategy_name": "hypervelocity_source_follow_5m",
            "capital_source": self._source_config.capital_source,
            "portfolio_purpose": self._source_config.portfolio_purpose,
            "backend_ledger_path": str(self._source_config.backend_ledger),
            "metalabel_mode": "observe",
            "metalabel_policy": self._metalabel_policy(),
            "wallet_configured": True,
            "signing_key_configured": True,
            "strategy_params": {
                "leverage": profile.leverage,
                "target_margin_pct": profile.target_margin_pct,
            },
            "position_policy": {
                "position_mode": "isolated_one_way",
                "max_positions_per_symbol": self._source_config.max_positions_per_symbol,
            },
            "risk": {
                "margin_fraction": profile.margin_fraction,
                "notional_fraction": profile.margin_fraction * profile.leverage,
                "max_notional_usd": self._source_config.max_notional_usd,
            },
            "regime_policy": profile.regime_policy(),
            "execution_sides": (
                ["long", "short"]
                if profile.direction_mode == "source_follow_bidirectional"
                else ["short"]
            ),
            "observer_policies": self._observer_policies(),
            "exits": {
                "mode": "target_or_maximum_hold_no_fixed_stop",
                "target_margin_pct": profile.target_margin_pct,
                "target_price_fraction": (
                    profile.target_margin_pct / profile.leverage / 100.0
                ),
                "target_basis": "gross_margin_return_before_fees_and_funding",
                "fixed_stop": "none",
                "maximum_hold_seconds": profile.maximum_hold_seconds,
                "range_policy": profile.open_position_range_policy,
            },
            "execution": {
                "order_type": "limit",
                "time_in_force": "post_only",
                "entry_ttl_seconds": profile.entry_ttl_seconds,
                "target_order_type": "reduce_only_post_only",
                "maximum_hold_exit": "first_fresh_bbo_taker",
            },
        }

    @staticmethod
    def _metalabel_policy() -> dict[str, object]:
        """Describe annotation collection without implying model inference."""
        return {
            "observation_type": "annotation_collection",
            "inference_active": False,
            "bundle_id": None,
            "probabilities_emitted": False,
            "may_filter": False,
            "may_scale": False,
            "execution_authority": "none",
        }

    @staticmethod
    def _observer_policies() -> dict[str, object]:
        return {
            "execution_authority": "none",
            "side": "long",
            "recipes": [
                "bk_up_asia_conf06",
                "fade_td_eu",
                "bk_up_24h_challenger",
                "trend_up_24h_challenger",
                "trend_down_24h_direction_challenger",
            ],
        }

    def emit_decision(self, decision: SourceFollowDecision) -> None:
        """Record the exact completed-5m source decision and entry authority."""
        self.emit("regime_decision", self._decision_payload(decision, executable=True))

    def emit_history(self, decision: SourceFollowDecision) -> None:
        """Record one measured warmup candle without granting entry authority."""
        self.emit("regime_history", self._decision_payload(decision, executable=False))

    def _decision_payload(
        self,
        decision: SourceFollowDecision,
        *,
        executable: bool,
    ) -> dict[str, object]:
        direction = decision.entry_direction
        eligible = (
            executable and decision.entry_eligible and direction in {"long", "short"}
        )
        routed_direction = direction if executable else None
        return {
            "feed_ts": decision.label_time_utc.isoformat(),
            "label_time_utc": decision.label_time_utc.isoformat(),
            "available_at_utc": decision.available_at_utc.isoformat(),
            "candle_timeframe": "5m",
            "market_data_source": "hyperliquid_candle_rest",
            "reference_price": decision.bar_close,
            "open": decision.bar_open,
            "high": decision.bar_high,
            "low": decision.bar_low,
            "close": decision.bar_close,
            "volume": decision.bar_volume,
            "primary_regime": decision.primary,
            "state_1m": "NOT_CLASSIFIED",
            "state_5m": decision.primary,
            "context_15m": "NOT_CLASSIFIED",
            "confidence": decision.confidence,
            "regime_score_source": "pinned_hypertrader_classifier_confidence",
            "primary_onset": decision.primary_onset,
            "source_event": decision.source_event,
            "source_follow_signal_range_bps": decision.signal_range_bps,
            "entry_pulse_expires_at_utc": self._pulse_expiry(decision),
            "structural_direction": routed_direction if decision.source_event else None,
            "entry_direction": routed_direction,
            "entry_allowed": eligible,
            "regime_admitted": eligible,
            "short_entry": eligible and direction == "short",
            "long_entry": eligible and direction == "long",
            "source_long_observer": self._source_long_payload(decision, executable),
            "decision_action": f"enter_{direction}"
            if eligible
            else self._hold_action(executable),
            "regime_reason": decision.exclusion_reason or "source_follow_entry_pulse",
            "regime_diagnostics": self._regime_diagnostics(decision),
        }

    @staticmethod
    def _regime_diagnostics(
        decision: SourceFollowDecision,
    ) -> dict[str, object] | None:
        diagnostics = decision.regime_diagnostics
        if diagnostics is None:
            return None
        return diagnostics.to_dict(confirmed_primary=decision.primary)

    def _pulse_expiry(self, decision: SourceFollowDecision) -> str:
        expires = decision.available_at_utc + timedelta(
            seconds=self._source_config.profile.entry_pulse_seconds
        )
        return expires.isoformat()

    @staticmethod
    def _hold_action(executable: bool) -> str:
        return "hold" if executable else "history_only"

    @staticmethod
    def _source_long_payload(
        decision: SourceFollowDecision,
        executable: bool,
    ) -> dict[str, object] | None:
        observation = decision.source_long_observation
        if not executable or observation is None:
            return None
        return {
            "authority": observation.authority,
            "recipe_id": observation.recipe_id,
            "side": observation.side,
            "maximum_hold_seconds": observation.maximum_hold_seconds,
        }

    def emit_order_intent(
        self,
        *,
        operation: str,
        side: str,
        quantity_or_notional: float,
        limit_price: float,
    ) -> None:
        """Record a secret-free backend order decision before submission."""
        self.emit(
            "order_intent",
            {
                "operation": operation,
                "side": side,
                "quantity_or_notional": quantity_or_notional,
                "limit_price": limit_price,
                "post_only": operation in {"entry", "target"},
                "reduce_only": operation != "entry",
            },
        )

    def emit_target_ack(self, ack: HyperliquidOrderAck, target_price: float) -> None:
        """Record the venue-confirmed target identity and intended price."""
        self.emit_ack("target", ack, event_type="target_order")

    def emit_lifecycle(
        self,
        *,
        state: str,
        entry_oid: int | None,
        target_oid: int | None,
        position_size_signed: float,
        opened_at_ms: int | None,
        last_fault: str | None = None,
    ) -> None:
        """Persist the complete source-follow execution lifecycle."""
        self.emit(
            "state_transition",
            {
                "state": state,
                "entry_oid": entry_oid,
                "target_oid": target_oid,
                "position_size_signed": position_size_signed,
                "opened_at_ms": opened_at_ms,
                "last_fault": last_fault,
            },
        )
