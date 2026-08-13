"""Synthetic loss sensitivity for technically unresolved HIP-3 paths."""

from __future__ import annotations

import math

from hypervector.research.shared_portfolio_models import (
    SharedPortfolioReport,
    SharedPortfolioTrade,
)


def conservative_gap_loss_sensitivity(
    nominal: SharedPortfolioReport,
    stress: SharedPortfolioReport,
    threshold_evidence: dict[str, object],
    *,
    threshold_ms: int,
    forced_loss_bps: float = 100.0,
) -> dict[str, object]:
    """Replace unresolved outcomes with a synthetic notional loss diagnostic."""
    if isinstance(threshold_ms, bool) or threshold_ms <= 0:
        raise ValueError("HIP-3 sensitivity threshold_ms must be positive")
    if not math.isfinite(forced_loss_bps) or forced_loss_bps <= 0.0:
        raise ValueError("HIP-3 sensitivity forced_loss_bps must be positive")
    unresolved = _mapping(
        threshold_evidence.get("unresolved_lifecycles"), "unresolved lifecycles"
    )
    return {
        "status": "diagnostic_only_unresolved_paths_remain",
        "qualification_authority": "none",
        "qualification_path_resolved": False,
        "validation_accessed": False,
        "threshold_ms": threshold_ms,
        "forced_loss_bps_of_notional": forced_loss_bps,
        "nominal": _scenario(
            nominal,
            threshold_evidence,
            unresolved,
            "nominal",
            forced_loss_bps,
        ),
        "stress": _scenario(
            stress,
            threshold_evidence,
            unresolved,
            "stress",
            forced_loss_bps,
        ),
        "limitations": [
            "forced losses are synthetic accounting, not observed venue fills",
            "the sensitivity does not resolve missing mark evidence",
            "validation and holdout remain unopened",
        ],
    }


def _scenario(
    report: SharedPortfolioReport,
    threshold: dict[str, object],
    unresolved: dict[str, object],
    name: str,
    forced_loss_bps: float,
) -> dict[str, object]:
    rows = _sequence(unresolved.get(name), name)
    expected = int(_mapping(threshold.get(name), name)["affected_trades"])
    if len(rows) != expected:
        raise ValueError("HIP-3 sensitivity affected lifecycle count disagrees")
    trades = _unique_trades(report)
    keys = [str(_mapping(row, name).get("lifecycle_key")) for row in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("HIP-3 unresolved lifecycle identities must be unique")
    missing = [key for key in keys if key not in trades]
    if missing:
        raise ValueError("HIP-3 unresolved lifecycle does not match one trade")
    replacements = {
        key: -trades[key].notional_usd * forced_loss_bps / 10_000.0 for key in keys
    }
    pnls = [
        replacements.get(_lifecycle_key(trade), trade.net_pnl_usd)
        for trade in report.trades
    ]
    metrics = _metrics(pnls)
    return {
        "affected_trades": len(keys),
        "original_affected_net_usd": sum(trades[key].net_pnl_usd for key in keys),
        "forced_loss_total_usd": sum(replacements.values()),
        **metrics,
    }


def _unique_trades(report: SharedPortfolioReport) -> dict[str, SharedPortfolioTrade]:
    output = {_lifecycle_key(trade): trade for trade in report.trades}
    if len(output) != len(report.trades):
        raise ValueError("HIP-3 report lifecycle identities must be unique")
    return output


def _metrics(values: list[float]) -> dict[str, float | None]:
    gross_profit = sum(max(value, 0.0) for value in values)
    gross_loss = -sum(min(value, 0.0) for value in values)
    ex_largest = list(values)
    winners = [value for value in ex_largest if value > 0.0]
    if winners:
        ex_largest.remove(max(winners))
    ex_profit = sum(max(value, 0.0) for value in ex_largest)
    ex_loss = -sum(min(value, 0.0) for value in ex_largest)
    return {
        "net_pnl_usd": sum(values),
        "profit_factor": _profit_factor(gross_profit, gross_loss),
        "net_without_largest_winner_usd": sum(ex_largest),
        "profit_factor_without_largest_winner": _profit_factor(ex_profit, ex_loss),
    }


def _profit_factor(gross_profit: float, gross_loss: float) -> float | None:
    if gross_loss > 0.0:
        return gross_profit / gross_loss
    return None


def _lifecycle_key(trade: SharedPortfolioTrade) -> str:
    return (
        f"{trade.direction}|{trade.signal_time_utc}|"
        f"{trade.entry_time_utc}|{trade.exit_time_utc}"
    )


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"HIP-3 sensitivity {name} must be an object")
    return value


def _sequence(value: object, name: str) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"HIP-3 sensitivity {name} lifecycles must be a sequence")
    return tuple(value)
