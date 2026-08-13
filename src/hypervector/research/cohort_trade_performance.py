"""Closed lifecycle performance summaries from authoritative trade journals."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from statistics import mean, median

from hypervector.research.cohort_live_audit_values import mapping, number, text

Record = Mapping[str, object]


def trade_economics(trade: Record, side: str) -> dict[str, float]:
    """Calculate explicit price and net-on-margin returns for one lifecycle."""
    if side not in {"long", "short"}:
        raise ValueError("trade economics side must be long or short")
    entry = mapping(trade.get("entry"), "trade entry")
    exit_leg = mapping(trade.get("exit"), "trade exit")
    entry_price = _positive(entry.get("price"), "entry price")
    exit_price = _positive(exit_leg.get("price"), "exit price")
    margin = _positive(trade.get("margin_used_usd"), "entry margin")
    leverage = _positive(trade.get("leverage"), "trade leverage")
    net_pnl = number(trade.get("net_pnl_usd"), "trade net PnL")
    direction = 1.0 if side == "long" else -1.0
    return {
        "entry_margin_used_usd": margin,
        "leverage": leverage,
        "price_return_pct": direction * (exit_price / entry_price - 1.0) * 100.0,
        "net_return_on_margin_pct": net_pnl / margin * 100.0,
    }


def build_trade_performance(
    trades: Sequence[Record],
    *,
    current_profile_fingerprint: str | None = None,
    current_run_id: str | None = None,
) -> dict[str, object]:
    """Aggregate W/L and returns using one declared, consistent denominator."""
    summaries = _performance_slice(trades)
    profile_partition = _profile_partition(trades, current_profile_fingerprint)
    run_partition = _run_partition(trades, current_run_id)
    return {
        "scope": "compatible_profile_history",
        "return_basis": "net_pnl_divided_by_sum_entry_margin",
        **summaries,
        **profile_partition,
        **run_partition,
        **_process_run_window_partition(trades),
        "limitations": [
            "net return uses summed entry margin across completed trade episodes",
            "overlapping positions share one portfolio and are not independent capital paths",
            "small trade counts do not establish strategy edge",
        ],
    }


def build_all_time_trade_performance(
    trades: Sequence[Record],
) -> dict[str, object]:
    """Aggregate every armed-live lifecycle without implying policy compatibility."""
    return {
        "scope": "all_live_history",
        "return_basis": "net_pnl_divided_by_sum_entry_margin",
        **_performance_slice(trades),
        "limitations": [
            "all-time live history may combine materially different strategy profiles",
            "net return uses summed entry margin across completed trade episodes",
            "all-time totals are descriptive and must not establish current-policy edge",
        ],
    }


def _run_partition(
    trades: Sequence[Record], current_run_id: str | None
) -> dict[str, object]:
    if current_run_id is None:
        return {}
    current = current_run_id.strip()
    if not current:
        raise ValueError("current run id must not be empty")
    run_ids = [trade.get("source_run_id") for trade in trades]
    if any(not isinstance(value, str) or not value.strip() for value in run_ids):
        raise ValueError("trade run identity coverage must be complete")
    selected = [
        trade
        for trade, run_id in zip(trades, run_ids, strict=True)
        if run_id == current
    ]
    return {"current_run": {"run_id": current, **_performance_slice(selected)}}


def _process_run_window_partition(trades: Sequence[Record]) -> dict[str, object]:
    run_ids = [trade.get("source_run_id") for trade in trades]
    if all(value is None for value in run_ids):
        return {}
    if any(not isinstance(value, str) or not value.strip() for value in run_ids):
        raise ValueError("trade run identity coverage must be complete")
    profiles = [trade.get("source_profile_fingerprint") for trade in trades]
    if any(not isinstance(value, str) or not value.strip() for value in profiles):
        raise ValueError("trade profile fingerprint coverage must be complete")
    grouped: dict[str, list[Record]] = {}
    for trade, raw_run in zip(trades, run_ids, strict=True):
        grouped.setdefault(str(raw_run), []).append(trade)
    by_run = {
        run_id: _run_window(run_id, values)
        for run_id, values in sorted(grouped.items())
    }
    totals = [
        mapping(value.get("total"), "run window total") for value in by_run.values()
    ]
    return {
        "process_run_windows": {
            "contract": {
                "report_only": True,
                "performance_gate": False,
                "balance_gate": False,
                "automatic_strategy_changes": False,
                "execution_authority": "none",
            },
            "window_basis": "backend_process_run_id",
            "statistical_independence_established": False,
            "run_count": len(by_run),
            **_run_outcome_counts(totals),
            "by_run": by_run,
            "by_provider_symbol": _provider_run_windows(trades),
            "limitations": [
                "a backend process restart creates a run window but not statistical independence",
                "profile changes remain visible and are not pooled as one policy generation",
                "run-window outcomes are descriptive and have no execution authority",
            ],
        }
    }


def _run_window(run_id: str, trades: Sequence[Record]) -> dict[str, object]:
    profiles = {
        text(trade.get("source_profile_fingerprint"), "trade profile fingerprint")
        for trade in trades
    }
    if len(profiles) != 1:
        raise ValueError("one process run has multiple profile fingerprints")
    return {
        "run_id": run_id,
        "profile_fingerprint": next(iter(profiles)),
        **_performance_slice(trades),
    }


def _provider_run_windows(trades: Sequence[Record]) -> dict[str, object]:
    grouped: dict[str, list[Record]] = {}
    for trade in trades:
        strategy = text(trade.get("strategy_id"), "trade strategy")
        symbol = text(trade.get("symbol"), "trade symbol")
        grouped.setdefault(f"{strategy}|{symbol}", []).append(trade)
    return {
        key: _provider_run_window(values) for key, values in sorted(grouped.items())
    }


def _provider_run_window(trades: Sequence[Record]) -> dict[str, object]:
    result = _run_outcomes_for_trades(trades)
    sides = [trade.get("side") for trade in trades]
    if all(value is None for value in sides):
        return result
    if any(value is None for value in sides):
        raise ValueError("trade side coverage must be complete or unavailable")
    grouped: dict[str, list[Record]] = {}
    for trade, raw_side in zip(trades, sides, strict=True):
        side = text(raw_side, "trade side")
        if side not in {"long", "short"}:
            raise ValueError("trade side must be long or short")
        grouped.setdefault(side, []).append(trade)
    return {
        **result,
        "by_side": {
            side: _run_outcomes_for_trades(values)
            for side, values in sorted(grouped.items())
        },
    }


def _run_outcomes_for_trades(trades: Sequence[Record]) -> dict[str, object]:
    pnl_by_run: dict[str, float] = {}
    for trade in trades:
        run_id = text(trade.get("source_run_id"), "trade run identity")
        pnl_by_run[run_id] = pnl_by_run.get(run_id, 0.0) + number(
            trade.get("net_pnl_usd"), "trade net PnL"
        )
    return _run_outcome_counts(
        [{"net_pnl_usd": value} for value in pnl_by_run.values()]
    )


def _run_outcome_counts(values: Sequence[Mapping[str, object]]) -> dict[str, object]:
    pnls = [number(value.get("net_pnl_usd"), "run net PnL") for value in values]
    return {
        "runs_with_closes": len(pnls),
        "positive_runs": sum(value > 0.0 for value in pnls),
        "negative_runs": sum(value < 0.0 for value in pnls),
        "breakeven_runs": sum(value == 0.0 for value in pnls),
        "positive_run_rate_pct": (
            sum(value > 0.0 for value in pnls) / len(pnls) * 100.0 if pnls else None
        ),
        "net_pnl_usd": sum(pnls),
    }


def _performance_slice(trades: Sequence[Record]) -> dict[str, object]:
    grouped: dict[str, list[Record]] = {}
    grouped_pairs: dict[str, list[Record]] = {}
    for trade in trades:
        strategy = text(trade.get("strategy_id"), "trade strategy")
        symbol = text(trade.get("symbol"), "trade symbol")
        grouped.setdefault(strategy, []).append(trade)
        grouped_pairs.setdefault(f"{strategy}|{symbol}", []).append(trade)
    return {
        "total": _summary(trades),
        "by_strategy": {
            strategy: _summary(values) for strategy, values in sorted(grouped.items())
        },
        "by_provider_symbol": {
            key: _pair_summary(values) for key, values in sorted(grouped_pairs.items())
        },
    }


def _profile_partition(
    trades: Sequence[Record],
    current_profile_fingerprint: str | None,
) -> dict[str, object]:
    if current_profile_fingerprint is None:
        return {}
    current = current_profile_fingerprint.strip()
    if not current:
        raise ValueError("current profile fingerprint must not be empty")
    fingerprints = [trade.get("source_profile_fingerprint") for trade in trades]
    if any(not isinstance(value, str) or not value.strip() for value in fingerprints):
        raise ValueError("trade profile fingerprint coverage must be complete")
    selected = [
        trade
        for trade, fingerprint in zip(trades, fingerprints, strict=True)
        if fingerprint == current
    ]
    distinct = {str(value) for value in fingerprints}
    return {
        "profile_fingerprint_count": len(distinct),
        "mixed_profile_history": len(distinct) > 1,
        "current_profile": {
            "profile_fingerprint": current,
            **_performance_slice(selected),
        },
    }


def _pair_summary(trades: Sequence[Record]) -> dict[str, object]:
    side_values = tuple(trade.get("side") for trade in trades)
    if all(value is None for value in side_values):
        return _summary(trades)
    if any(value is None for value in side_values):
        raise ValueError("trade side coverage must be complete or unavailable")
    grouped: dict[str, list[Record]] = {}
    for trade, raw_side in zip(trades, side_values, strict=True):
        side = text(raw_side, "trade side")
        if side not in {"long", "short"}:
            raise ValueError("trade side must be long or short")
        grouped.setdefault(side, []).append(trade)
    return {
        **_summary(trades),
        "by_side": {side: _summary(values) for side, values in sorted(grouped.items())},
    }


def _summary(trades: Sequence[Record]) -> dict[str, object]:
    pnls = [number(trade.get("net_pnl_usd"), "trade net PnL") for trade in trades]
    margins = [
        _positive(trade.get("entry_margin_used_usd"), "entry margin")
        for trade in trades
    ]
    returns = [
        number(trade.get("net_return_on_margin_pct"), "trade net return")
        for trade in trades
    ]
    fees = [number(trade.get("fees_usd"), "trade fees") for trade in trades]
    funding = [number(trade.get("funding_usd"), "trade funding") for trade in trades]
    closed = len(trades)
    net_pnl = sum(pnls)
    margin = sum(margins)
    gross_profit = sum(value for value in pnls if value > 0.0)
    gross_loss = -sum(value for value in pnls if value < 0.0)
    return {
        "closed_trades": closed,
        "wins": sum(value > 0.0 for value in pnls),
        "losses": sum(value < 0.0 for value in pnls),
        "breakeven": sum(value == 0.0 for value in pnls),
        "win_rate_pct": sum(value > 0.0 for value in pnls) / closed * 100.0
        if closed
        else None,
        "net_pnl_usd": net_pnl,
        "entry_margin_used_usd": margin,
        "net_return_on_margin_pct": net_pnl / margin * 100.0 if margin else None,
        "mean_trade_return_on_margin_pct": float(mean(returns)) if returns else None,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "fees_usd": sum(fees),
        "funding_usd": sum(funding),
        **_path_diagnostics(pnls, returns, fees, funding),
    }


def _path_diagnostics(
    pnls: Sequence[float],
    returns: Sequence[float],
    fees: Sequence[float],
    funding: Sequence[float],
) -> dict[str, float | None]:
    winners = [value for value in pnls if value > 0.0]
    largest = max(winners) if winners else None
    gross_profit = sum(winners)
    gross_market = [
        pnl + fee - funding_cash
        for pnl, fee, funding_cash in zip(pnls, fees, funding, strict=True)
    ]
    positive_gross_market = sum(value for value in gross_market if value > 0.0)
    execution_cash_drag = sum(fees) - sum(funding)
    return {
        "mean_trade_net_pnl_usd": float(mean(pnls)) if pnls else None,
        "median_trade_net_pnl_usd": float(median(pnls)) if pnls else None,
        "median_trade_return_on_margin_pct": (
            float(median(returns)) if returns else None
        ),
        "largest_winner_usd": largest,
        "largest_winner_share_of_gross_profit_pct": (
            largest / gross_profit * 100.0 if largest is not None else None
        ),
        "net_pnl_excluding_largest_winner_usd": (
            sum(pnls) - largest if largest is not None else None
        ),
        "maximum_closed_sequence_drawdown_usd": _closed_sequence_drawdown(pnls),
        "gross_market_pnl_usd": sum(gross_market),
        "fees_as_pct_of_positive_gross_market_pnl": (
            sum(fees) / positive_gross_market * 100.0
            if positive_gross_market > 0.0
            else None
        ),
        "execution_cash_drag_usd": execution_cash_drag,
        "execution_cash_drag_as_pct_of_positive_gross_market_pnl": (
            execution_cash_drag / positive_gross_market * 100.0
            if positive_gross_market > 0.0
            else None
        ),
    }


def _closed_sequence_drawdown(pnls: Sequence[float]) -> float:
    cumulative = 0.0
    peak = 0.0
    maximum = 0.0
    for value in pnls:
        cumulative += value
        peak = max(peak, cumulative)
        maximum = max(maximum, peak - cumulative)
    return maximum


def _positive(value: object, label: str) -> float:
    result = number(value, label)
    if result <= 0.0:
        raise ValueError(f"{label} must be positive")
    return result
