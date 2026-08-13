"""Reusable exact-v39 checkpoint fixtures for forward-evidence tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.research.cohort_trade_performance import build_trade_performance

CONFIG = Path(
    "configs/"
    "multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml"
)
NOW = datetime(2026, 8, 11, 10, 0, 30, tzinfo=UTC)
RUN_ID = "bidirectional-live-v39"


def config() -> MultiAssetLiveConfig:
    """Load the frozen v39 fixture configuration."""
    return load_multi_asset_live_config(
        CONFIG,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )


def routes(value: MultiAssetLiveConfig) -> list[str]:
    """Return exact provider-symbol route identities."""
    return sorted(
        f"{provider}|{symbol}" for provider, symbol in value.executable_provider_symbols
    )


def checkpoint(value: MultiAssetLiveConfig) -> dict[str, object]:
    """Build a complete report-only zero-trade checkpoint."""
    route_ids = routes(value)
    return {
        "generated_at_utc": "2026-08-11T10:00:00+00:00",
        "checkpoint_contract": _checkpoint_contract(),
        "audit": {
            "run": _run(value, list(route_ids)),
            "routing": {"executable_provider_symbols": list(route_ids)},
            "signal_outcomes": _signal_outcomes(route_ids),
            "trade_reflections": {
                "contract": _reflection_contract(),
                "performance": {
                    "current_run": current_run(),
                    "all_time_live": {"by_provider_symbol": {}},
                },
                "trades": [],
            },
            "open_trade_reflections": {
                "contract": _reflection_contract(),
                "open_lifecycles": 0,
                "trades": [],
            },
        },
    }


def current_run(route: str | None = None) -> dict[str, object]:
    """Build authoritative current-run performance for zero or one trade."""
    trades = [] if route is None else [trade_row(route)]
    performance = build_trade_performance(trades, current_run_id=RUN_ID)
    return performance["current_run"]


def install_current_run(
    target: dict[str, object],
    route: str,
) -> dict[str, object]:
    """Install one raw lifecycle and its authoritative aggregate."""
    current = current_run(route)
    reflections = target["audit"]["trade_reflections"]
    reflections["performance"]["current_run"] = current
    reflections["trades"] = [trade_row(route)]
    return current


def trade_row(route: str) -> dict[str, object]:
    """Build one internally consistent closed lifecycle row."""
    strategy, symbol = route.split("|", 1)
    profile_fingerprint = config().profile_fingerprint
    return {
        "lifecycle_id": f"{symbol}:321",
        "source_run_id": RUN_ID,
        "source_profile_fingerprint": profile_fingerprint,
        "strategy_id": strategy,
        "symbol": symbol,
        "side": "long",
        "net_pnl_usd": 1.25,
        "fees_usd": 0.1,
        "funding_usd": -0.01,
        "entry_margin_used_usd": 10.0,
        "net_return_on_margin_pct": 12.5,
        "entry": {"venue_timestamp_ms": 100},
        "exit": {"venue_timestamp_ms": 200},
    }


def route_performance(*, net: float) -> dict[str, object]:
    """Build a compact mixed-history row ignored by current-run evidence."""
    closed = int(net != 0.0)
    return {
        "closed_trades": closed,
        "wins": int(net > 0.0),
        "losses": int(net < 0.0),
        "breakeven": 0,
        "net_pnl_usd": net,
    }


def open_row(strategy: str, symbol: str, side: str) -> dict[str, object]:
    """Build one exact-symbol provisional open lifecycle."""
    return {
        "lifecycle_id": f"{symbol}:123",
        "source_run_id": RUN_ID,
        "strategy_id": strategy,
        "symbol": symbol,
        "side": side,
        "entry": {"venue_timestamp_ms": 150},
        "open_profit_lock_challenger": {"as_of_timestamp_ms": 300},
        "marked_economics": {
            "active_lifecycle_marked_net_pnl_usd": 1.0,
            "status": "provisional_open",
            "symbol": symbol,
            "side": side,
        },
    }


def current_summary_rows(
    current: dict[str, object],
    route: str,
) -> tuple[dict[str, object], ...]:
    """Return total, route, and route-side summary records."""
    route_row = current["by_provider_symbol"][route]
    return current["total"], route_row, route_row["by_side"]["long"]


def _checkpoint_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "performance_gate": False,
        "automatic_retuning": False,
        "automatic_pause": False,
        "balance_gate": False,
        "final": False,
    }


def _reflection_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
    }


def _run(value: MultiAssetLiveConfig, route_ids: list[str]) -> dict[str, object]:
    return {
        "run_id": RUN_ID,
        "profile_id": value.profile_id,
        "profile_fingerprint": value.profile_fingerprint,
        "last_observed_at_utc": "2026-08-11T09:59:59+00:00",
        "maximum_concurrent_positions": 10,
        "executable_provider_symbols": route_ids,
        "observe_only_provider_symbols": [],
    }


def _signal_outcomes(route_ids: list[str]) -> dict[str, object]:
    return {
        "by_provider_symbol": {
            route: {
                "evaluations": 3,
                "eligible_evaluations": 0,
                "no_direction": 1,
                "by_side": {
                    "long": {"evaluations": 1, "eligible_evaluations": 0},
                    "short": {"evaluations": 1, "eligible_evaluations": 0},
                },
            }
            for route in route_ids
        }
    }
