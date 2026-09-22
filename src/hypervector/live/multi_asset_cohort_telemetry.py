"""Authoritative shared-account and intent projection for the cohort TUI."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone

from hypervector.live.bidirectional_intents import (
    IntentRoutingReport,
    StrategyIntent,
)
from hypervector.live.canonical_regime_telemetry import (
    CANONICAL_REGIME_TELEMETRY_STRATEGY,
)
from hypervector.live.cohort_backup_evidence import prestart_backup_payload
from hypervector.live.cohort_durable_decision_recovery import durable_decision_records
from hypervector.live.cohort_durable_decisions import CohortDurableDecisionJournal
from hypervector.live.cohort_adaptive_exit_journal import AdaptiveExitJournal
from hypervector.live.cohort_funding_recovery import recover_funding_cursor
from hypervector.live.cohort_funding_window import CohortFundingWindow
from hypervector.live.cohort_prestart_backup import CohortPrestartBackupResult
from hypervector.live.cohort_regime_routing import routing_policy_payload
from hypervector.live.cohort_runtime_fault import runtime_fault_payload
from hypervector.live.cohort_startup_candle_recorder import CohortStartupCandleRecorder
from hypervector.live.cohort_transition_drain import CohortTransitionDrain
from hypervector.live.hyperliquid_protocol import SolBookSnapshot
from hypervector.live.multi_asset_cohort_history import (
    asset_costs,
    current_run_rows,
    fill_payloads,
    latest_book,
)
from hypervector.live.multi_asset_cohort_history_cache import CohortAssetHistoryCache
from hypervector.live.multi_asset_cohort_models import (
    AssetCohortSnapshot,
    SharedAccountFacts,
)
from hypervector.live.multi_asset_cohort_payloads import (
    asset_config_payload,
    intent_payload,
    provider_config_payload,
)
from hypervector.live.multi_asset_cohort_payloads import (
    routing_action_payload as _routing_action_payload,
)
from hypervector.live.multi_asset_cohort_payloads import (
    withheld_intent_payload as _withheld_payload,
)
from hypervector.live.multi_asset_intent_poller import CohortMarketBar
from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.live.multi_asset_market_telemetry import (
    unseen_market_candle_payload,
)
from hypervector.live.multi_asset_signal_source import ProviderEvaluation
from hypervector.live.multi_asset_strategy_evidence import (
    strategy_evidence_payloads,
)
from hypervector.live.sol_range_onset_ledger import SolLiveLedger


class MultiAssetCohortTelemetry:
    """Append complete cohort truth without strategy inference or secrets."""

    def __init__(
        self,
        *,
        config: MultiAssetLiveConfig,
        ledger: SolLiveLedger,
        now_fn: Callable[[], datetime],
        asset_ledgers: Mapping[str, SolLiveLedger] | None = None,
        prestart_backup: CohortPrestartBackupResult | None = None,
        transition_drain: CohortTransitionDrain | None = None,
    ) -> None:
        self._config = config
        self._ledger = ledger
        self._now_fn = now_fn
        self._asset_ledgers = dict(asset_ledgers or {})
        self._prestart_backup = prestart_backup
        self._transition_drain = transition_drain
        self._market_bar_boundaries: dict[str, int] = {}
        self._expected_provider_symbols = frozenset(
            (provider.strategy_id, symbol)
            for provider in config.providers
            for symbol in provider.symbols
        )
        self._observed_provider_symbols: set[tuple[str, str]] = set()
        self._live_armed = (
            config.mode == "live" and config.enabled and config.accepts_live_risk
        )
        records = durable_decision_records(ledger)
        self._adaptive_exit_journal = AdaptiveExitJournal(records, self._emit)
        self._maximum_hold_decisions = CohortDurableDecisionJournal(
            records=records,
            event_type="maximum_hold_decision",
            label="maximum-hold",
            emit=self._emit,
        )
        self._provider_exit_decisions = CohortDurableDecisionJournal(
            records=records,
            event_type="provider_exit_decision",
            label="provider-exit",
            emit=self._emit,
        )
        self._profit_lock_decisions = CohortDurableDecisionJournal(
            records=records,
            event_type="profit_lock_decision",
            label="profit-lock",
            emit=self._emit,
        )
        if self._asset_ledgers and set(self._asset_ledgers) != set(config.symbols):
            raise ValueError("asset ledgers must cover every configured symbol")
        self._asset_history_cache = _history_cache(self._asset_ledgers)

    @property
    def adaptive_exit_journal(self) -> AdaptiveExitJournal:
        """Return entry-bound durable observations for adaptive exit control."""
        return self._adaptive_exit_journal

    def startup_input_observer(self) -> CohortStartupCandleRecorder:
        """Bind exact startup evidence to this ledger's run and publication path."""
        return CohortStartupCandleRecorder(
            self._config,
            self._ledger.path.parent,
            self._ledger.run_id,
            self._emit,
        )

    @property
    def funding_recovery_start_ms(self) -> int | None:
        """Return the exact-profile durable funding boundary for a new owner."""
        return recover_funding_cursor(self._ledger, self._config.profile_fingerprint)

    def emit_configuration(self) -> None:
        """Publish enabled symbols, both sides, providers, and portfolio policy."""
        payload: dict[str, object] = {
            "symbol": "MULTI",
            "strategy_name": "multi_asset_bidirectional_cohort",
            "profile_fingerprint": self._config.profile_fingerprint,
            "config_source_path": str(self._config.source_path),
            "enabled_symbols": list(self._config.symbols),
            "assets": [asset_config_payload(asset) for asset in self._config.assets],
            "providers": [
                provider_config_payload(provider) for provider in self._config.providers
            ],
            "strategy_evidence": strategy_evidence_payloads(self._config.providers),
            "position_policy": {
                "max_positions_per_symbol": 1,
                "maximum_concurrent_positions": self._config.maximum_positions,
            },
            "routing_policy": routing_policy_payload(),
            "runtime": {
                "poll_seconds": self._config.poll_seconds,
                "lookback_days": self._config.lookback_days,
            },
            "backend_ledger_path": str(self._ledger.path),
        }
        if self._prestart_backup is not None:
            payload["prestart_backup"] = prestart_backup_payload(self._prestart_backup)
        self._emit(
            "configuration_identity",
            payload,
        )

    def emit_routing(
        self,
        intents: tuple[StrategyIntent, ...],
        report: IntentRoutingReport,
        evaluations: tuple[ProviderEvaluation, ...] = (),
    ) -> None:
        """Publish provider evaluations, intents, and deterministic outcomes."""
        observed = {(value.strategy_id, value.symbol) for value in evaluations}
        unknown = observed.difference(self._expected_provider_symbols)
        if unknown:
            raise ValueError(
                f"cohort evaluations contain unknown setups: {sorted(unknown)}"
            )
        self._observed_provider_symbols.update(observed)
        for intent in intents:
            self._emit("strategy_intent", intent_payload(intent))
        self._emit(
            "intent_routing",
            {
                "evaluations": [evaluation.as_payload() for evaluation in evaluations],
                "setup_coverage": self._setup_coverage_payload(),
                "actions": [
                    _routing_action_payload(action) for action in report.actions
                ],
                "withheld": [_withheld_payload(item) for item in report.withheld],
            },
        )

    def _setup_coverage_payload(self) -> dict[str, object]:
        """Return cumulative setup coverage without converting absence to readiness."""
        missing = sorted(
            self._expected_provider_symbols.difference(self._observed_provider_symbols)
        )
        return {
            "expected_provider_symbols": len(self._expected_provider_symbols),
            "observed_provider_symbols": len(self._observed_provider_symbols),
            "missing_provider_symbols": [
                f"{strategy}|{symbol}" for strategy, symbol in missing
            ],
            "complete": not missing,
        }

    def emit_canonical_regimes(
        self,
        evaluations: tuple[ProviderEvaluation, ...],
    ) -> None:
        """Publish independent canonical evidence with no route or intent authority."""
        _validate_canonical_evaluations(evaluations, frozenset(self._config.symbols))
        self._emit(
            "canonical_regime_evaluations",
            {
                "contract": {
                    "execution_authority": "none",
                    "intents_emitted": False,
                    "configured_route": False,
                },
                "evaluations": [value.as_payload() for value in evaluations],
            },
        )

    def emit_snapshot(
        self,
        *,
        account: SharedAccountFacts,
        assets: tuple[AssetCohortSnapshot, ...],
    ) -> None:
        """Publish shared capital and every symbol lifecycle in one row."""
        if tuple(asset.symbol for asset in assets) != self._config.symbols:
            raise ValueError("cohort snapshot symbols differ from configuration")
        histories = (
            {}
            if self._asset_history_cache is None
            else self._asset_history_cache.refresh()
        )
        self._emit(
            "cohort_snapshot",
            {
                "account_value_usd": account.account_value_usd,
                "withdrawable_usd": account.withdrawable_usd,
                "total_margin_used_usd": account.total_margin_used_usd,
                "total_notional_position_usd": account.total_notional_position_usd,
                "account_balance_source": account.balance_source,
                "open_position_count": sum(
                    asset.position_side is not None for asset in assets
                ),
                "assets": [self._asset_payload(asset, histories) for asset in assets],
                "recent_fills": self._recent_fills(histories),
                "books": self._latest_books(histories),
                "transition_drain": (
                    None
                    if self._transition_drain is None
                    else self._transition_drain.as_payload()
                ),
            },
        )

    def emit_market_bars(
        self,
        bars: Mapping[str, tuple[CohortMarketBar, ...]],
    ) -> None:
        """Publish initial candle history and only later unseen completed bars."""
        payload, boundaries = unseen_market_candle_payload(
            symbols=self._config.symbols,
            bars=bars,
            boundaries=self._market_bar_boundaries,
        )
        if payload is not None:
            self._emit("market_candles", payload)
            self._market_bar_boundaries = boundaries

    def emit_market_books(
        self,
        books: Mapping[str, SolBookSnapshot],
    ) -> None:
        """Publish current public L2 snapshots without execution authority."""
        if set(books) != set(self._config.symbols):
            raise ValueError("cohort market books must cover every configured symbol")
        self._emit(
            "market_books",
            {
                "books": {
                    symbol: _book_payload(symbol, book, recv_ts_ms=self._now_ms())
                    for symbol, book in books.items()
                }
            },
        )

    def emit_heartbeat(self) -> None:
        """Publish process liveness without inventing market state."""
        self._emit("heartbeat", {"status": "running"})

    def emit_stopped(self, *, reason: str) -> None:
        """Publish explicit normal termination under the same backend identity."""
        if reason not in {"bounded_run_complete", "operator_stop"}:
            raise ValueError("unsupported observer stop reason")
        self._emit("runtime_stopped", {"reason": reason})

    def emit_funding_reconciliation_window(self, window: CohortFundingWindow) -> None:
        """Publish the exact committed funding cursor for one poll cycle."""
        self._emit("funding_reconciliation_window", window.as_payload())

    def emit_breakeven_stop_attempt(
        self, event: str, payload: Mapping[str, object]
    ) -> None:
        """Publish one bounded attempt to move a venue stop to break-even."""
        if event != "breakeven_stop_attempt":
            raise ValueError("unsupported break-even stop event")
        self._emit(event, dict(payload))

    def emit_poll_degraded(self, *, source: str, reason: str) -> None:
        """Publish one skipped transient-read cycle without claiming success."""
        if not source.strip() or not reason.strip():
            raise ValueError("degraded poll source and reason are required")
        self._emit(
            "heartbeat",
            {
                "status": "degraded",
                "source": source.strip(),
                "reason": reason.strip(),
                "orders_attempted": False,
            },
        )

    def emit_runtime_fault(
        self,
        *,
        exception_type: str,
        failure_stage: str | None = None,
    ) -> None:
        """Persist a terminal runtime fault class without leaking exception data."""
        self._emit(
            "runtime_fault",
            runtime_fault_payload(exception_type, failure_stage=failure_stage),
        )

    def emit_operator_command(self, payload: Mapping[str, object]) -> None:
        """Publish one audited manual-command lifecycle transition."""
        self._emit("operator_command", payload)

    def recorded_maximum_hold_decision(
        self, decision_id: str
    ) -> Mapping[str, object] | None:
        """Return a durable boundary decision so recovery remains idempotent."""
        if not isinstance(decision_id, str) or not decision_id.strip():
            raise ValueError("maximum-hold decision_id must be non-empty")
        return self._maximum_hold_decisions.recorded(decision_id)

    def emit_maximum_hold_decision(self, payload: Mapping[str, object]) -> None:
        """Publish one causal soft-deadline lifecycle decision."""
        self._maximum_hold_decisions.append_once(payload)

    def recorded_provider_exit_decision(
        self, decision_id: str
    ) -> Mapping[str, object] | None:
        """Return a durable provider exit so recovery cannot lose a one-bar event."""
        return self._provider_exit_decisions.recorded(decision_id)

    def emit_provider_exit_decision(self, payload: Mapping[str, object]) -> None:
        """Persist one lifecycle-bound provider recipe exit before execution."""
        self._provider_exit_decisions.append_once(payload)

    def recorded_profit_lock_decision(
        self, decision_id: str
    ) -> Mapping[str, object] | None:
        """Return a durable profit-lock exit for restart-safe enforcement."""
        return self._profit_lock_decisions.recorded(decision_id)

    def emit_profit_lock_decision(self, payload: Mapping[str, object]) -> None:
        """Persist one causal completed-bar lock exit before execution."""
        self._profit_lock_decisions.append_once(payload)

    def _emit(self, event_type: str, payload: Mapping[str, object]) -> None:
        self._ledger.append(
            event_type=event_type,
            observed_at_utc=self._now_utc(),
            live_armed=self._live_armed,
            execution_authority=("hyperliquid_mainnet" if self._live_armed else "none"),
            payload=payload,
        )

    def _now_utc(self) -> str:
        observed = self._now_fn()
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise ValueError("cohort telemetry clock must be timezone-aware")
        return observed.astimezone(timezone.utc).isoformat()

    def _now_ms(self) -> int:
        observed = self._now_fn()
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise ValueError("cohort telemetry clock must be timezone-aware")
        return int(observed.timestamp() * 1_000)

    def _asset_payload(
        self,
        asset: AssetCohortSnapshot,
        histories: Mapping[str, list[dict[str, object]]],
    ) -> dict[str, object]:
        payload = asset.as_payload()
        rows = histories.get(asset.symbol)
        payload.update(
            asset_costs(rows)
            if rows is not None
            else {
                "fees_net_usd": None,
                "funding_net_usd": None,
                "realized_pnl_usd": None,
                "fill_count": None,
                "cost_scope": None,
            }
        )
        return payload

    def _recent_fills(
        self,
        histories: Mapping[str, list[dict[str, object]]],
    ) -> list[dict[str, object]]:
        fills: list[dict[str, object]] = []
        for symbol, rows in histories.items():
            fills.extend(fill_payloads(symbol, rows))
        return sorted(
            fills,
            key=_fill_timestamp,
        )[-50:]

    def _latest_books(
        self,
        histories: Mapping[str, list[dict[str, object]]],
    ) -> list[dict[str, object]]:
        books: list[dict[str, object]] = []
        for symbol, ledger in self._asset_ledgers.items():
            current = current_run_rows(
                histories.get(symbol, []),
                ledger.run_id,
            )
            book = latest_book(symbol, current)
            if book is not None:
                books.append(book)
        return books


def _history_cache(
    ledgers: Mapping[str, SolLiveLedger],
) -> CohortAssetHistoryCache | None:
    return CohortAssetHistoryCache(ledgers) if ledgers else None


def _validate_canonical_evaluations(
    evaluations: tuple[ProviderEvaluation, ...],
    symbols: frozenset[str],
) -> None:
    identities: set[tuple[str, str, int]] = set()
    prior_time = -1
    for value in evaluations:
        identity = (value.strategy_id, value.symbol, value.decision_time_ms)
        if identity in identities:
            raise ValueError("duplicate canonical regime evaluation")
        identities.add(identity)
        if value.decision_time_ms < prior_time:
            raise ValueError("canonical regime evaluations are unordered")
        prior_time = value.decision_time_ms
        telemetry_only = (
            value.strategy_id == CANONICAL_REGIME_TELEMETRY_STRATEGY
            and value.symbol in symbols
            and value.eligible is False
            and value.side is None
            and value.decision_action == "regime_observation"
            and value.reason == "canonical_regime_observation"
            and value.backend_non_action_reason
            == "telemetry_only_no_execution_authority"
        )
        if not telemetry_only:
            raise ValueError("canonical regime evaluations are structurally invalid")


def _book_payload(
    symbol: str,
    book: SolBookSnapshot,
    *,
    recv_ts_ms: int,
) -> dict[str, object]:
    """Convert one parsed official-SDK book into the cohort ledger schema."""
    if book.ask_depth <= 0.0:
        raise ValueError(f"{symbol} L2 ask depth must be positive")
    return {
        "symbol": symbol,
        "source": "hyperliquid_mainnet_l2_rest",
        "exchange_ts_ms": book.exchange_timestamp_ms,
        "recv_ts_ms": recv_ts_ms,
        "mid_px": book.mid_price,
        "spread_bps": book.spread_bps,
        "bid_depth_ratio": book.bid_depth / book.ask_depth,
        "opi": book.order_pressure,
        "bids": [
            {"price": level.price, "size": level.size, "orders": level.order_count}
            for level in book.bids
        ],
        "asks": [
            {"price": level.price, "size": level.size, "orders": level.order_count}
            for level in book.asks
        ],
    }


def _fill_timestamp(fill: Mapping[str, object]) -> int:
    value = fill.get("venue_timestamp_ms")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("cohort fill venue_timestamp_ms must be an integer")
    return value
