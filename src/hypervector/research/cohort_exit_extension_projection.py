"""Shared protected price-path projection for report-only exit observers."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.research.cohort_live_audit_values import mapping, number, text

Record = Mapping[str, object]


def project_incremental_gross_pnl(
    trade: Record, path: Record
) -> tuple[float, bool] | None:
    """Project incremental gross PnL while retaining the recorded venue stop."""
    exit_leg = mapping(trade.get("exit"), "trade exit")
    exit_price = number(exit_leg.get("price"), "trade exit price")
    exit_size = number(exit_leg.get("size"), "trade exit size")
    if exit_price <= 0.0 or exit_size <= 0.0:
        raise ValueError("extension projection requires positive exit price and size")
    protection = trade.get("protective_stop")
    if protection is None:
        return None
    trigger = number(
        mapping(protection, "trade protective stop").get("trigger_price"),
        "protective-stop trigger",
    )
    side = text(trade.get("side"), "trade side")
    if trigger <= 0.0 or side not in {"long", "short"}:
        raise ValueError("extension projection has invalid protective-stop evidence")
    lowest = number(path.get("lowest_price"), "post-exit lowest price")
    highest = number(path.get("highest_price"), "post-exit highest price")
    stop_hit = lowest <= trigger if side == "long" else highest >= trigger
    if stop_hit:
        direction = 1.0 if side == "long" else -1.0
        return direction * (trigger - exit_price) * exit_size, True
    directional_bps = number(
        path.get("directional_close_return_bps"), "directional close return"
    )
    return exit_price * exit_size * directional_bps / 10_000.0, False
