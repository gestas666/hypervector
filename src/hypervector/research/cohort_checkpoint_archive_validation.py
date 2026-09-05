"""Portfolio-archive reconciliation for live cohort checkpoints."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import math

from hypervector.research.cohort_live_portfolio_archive import (
    reconcile_accounting_epoch_archive,
)


def refresh_accounting_epoch_archive(
    audit: dict[str, object], observed_at: datetime
) -> None:
    """Refresh an epoch archive from the checkpoint's complete reflections."""
    archive = audit.get("portfolio_archive")
    if not isinstance(archive, Mapping) or archive.get("accounting_epoch") is None:
        return
    reflections = _mapping(audit.get("trade_reflections"), "trade reflections")
    all_time = _mapping(reflections.get("all_time_live"), "all-time reflections")
    audit["portfolio_archive"] = reconcile_accounting_epoch_archive(
        archive,
        all_time,
        observed_through_utc=observed_at,
    )


def reconcile_equal_coverage_archive(audit: Mapping[str, object]) -> None:
    """Reject archive PnL that differs from equal-coverage reflections."""
    archive = _mapping(audit.get("portfolio_archive"), "portfolio archive")
    archive_performance = archive.get("performance")
    if not isinstance(archive_performance, Mapping):
        return
    archive_total = archive_performance.get("total")
    if not isinstance(archive_total, Mapping):
        return
    reflections = _mapping(audit.get("trade_reflections"), "trade reflections")
    all_time = _mapping(reflections.get("all_time_live"), "all-time reflections")
    reflected_total = _mapping(
        _mapping(all_time.get("performance"), "all-time performance").get("total"),
        "all-time total",
    )
    if archive_total.get("closed_trades") != reflected_total.get("closed_trades"):
        return
    for field in ("net_pnl_usd", "maximum_closed_sequence_drawdown_usd"):
        archive_value = _finite_number(archive_total.get(field), f"archive {field}")
        reflected_value = _finite_number(
            reflected_total.get(field), f"all-time {field}"
        )
        if not math.isclose(archive_value, reflected_value, abs_tol=1e-9):
            raise ValueError(f"archive {field} differs from all-time reflections")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result
