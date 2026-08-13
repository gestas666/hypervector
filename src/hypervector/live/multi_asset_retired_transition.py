"""Fail-closed venue reconciliation for assets removed by a candidate profile."""

from __future__ import annotations

from collections.abc import Mapping
import math

from hypervector.live.multi_asset_live_config import AssetLiveConfig
from hypervector.live.multi_asset_read_only_preflight import (
    AssetLedgerExpectation,
    MultiAssetReadOnlyReaderProtocol,
)


def collect_retired_asset_report(
    asset: AssetLiveConfig,
    reader: MultiAssetReadOnlyReaderProtocol,
    ledger: AssetLedgerExpectation,
) -> dict[str, object]:
    """Read current venue state for one asset absent from the candidate roster."""
    maximum_leverage = _integer_leverage(asset.venue_max_leverage)
    preflight = reader.preflight(expected_max_leverage=maximum_leverage)
    if preflight.market.symbol != asset.symbol:
        raise ValueError(f"{asset.symbol} retired reader returned another symbol")
    orders = reader.open_orders()
    venue_oids = frozenset(order.oid for order in orders)
    tolerance = max(preflight.size_step / 2.0, 1e-12)
    position_matches = math.isclose(
        preflight.position.size_signed,
        ledger.position_size_signed,
        rel_tol=0.0,
        abs_tol=tolerance,
    )
    orders_match = venue_oids == ledger.owned_order_ids
    return {
        "symbol": asset.symbol,
        "position_size_signed": preflight.position.size_signed,
        "open_order_ids": tuple(sorted(venue_oids)),
        "ledger_position_size_signed": ledger.position_size_signed,
        "ledger_owned_order_ids": tuple(sorted(ledger.owned_order_ids)),
        "ledger_reconciled": position_matches and orders_match,
        "flat_no_orders": preflight.position.size_signed == 0.0 and not venue_oids,
    }


def apply_retired_asset_reports(
    report: dict[str, object],
    retired_assets: tuple[dict[str, object], ...],
) -> dict[str, object]:
    """Add removed-asset venue blockers without changing candidate sizing evidence."""
    if not retired_assets:
        updated = dict(report)
        updated["retired_assets"] = ()
        return updated
    portfolio = dict(_mapping(report.get("portfolio"), "preflight portfolio"))
    existing_blockers = _strings(
        portfolio.get("transition_blocking_assets"),
        "transition blockers",
    )
    retired_blockers = tuple(
        _symbol(asset)
        for asset in retired_assets
        if asset.get("flat_no_orders") is not True
    )
    blockers = tuple(dict.fromkeys((*existing_blockers, *retired_blockers)))
    ledger_reconciled = bool(portfolio.get("ledger_reconciled")) and all(
        asset.get("ledger_reconciled") is True for asset in retired_assets
    )
    sizing_ready = portfolio.get("sizing_technically_ready") is True
    portfolio.update(
        {
            "open_positions": _count_positions(report, retired_assets),
            "open_orders": _count_orders(report, retired_assets),
            "flat_no_orders": not blockers,
            "transition_blocking_assets": blockers,
            "ledger_reconciled": ledger_reconciled,
            "technically_ready_for_profile_transition": (
                not blockers and ledger_reconciled and sizing_ready
            ),
            "readiness_reasons": _readiness_reasons(
                blockers,
                ledger_reconciled,
                sizing_ready,
            ),
        }
    )
    updated = dict(report)
    updated["portfolio"] = portfolio
    updated["retired_assets"] = retired_assets
    return updated


def _count_positions(
    report: Mapping[str, object],
    retired: tuple[dict[str, object], ...],
) -> int:
    assets = _rows(report.get("assets"), "preflight assets")
    candidate = sum(
        float(_mapping(asset.get("position"), "asset position")["size_signed"]) != 0.0
        for asset in assets
    )
    return candidate + sum(
        float(asset["position_size_signed"]) != 0.0 for asset in retired
    )


def _count_orders(
    report: Mapping[str, object],
    retired: tuple[dict[str, object], ...],
) -> int:
    assets = _rows(report.get("assets"), "preflight assets")
    candidate = sum(
        len(_rows(asset.get("open_orders"), "asset orders")) for asset in assets
    )
    return candidate + sum(len(_ids(asset["open_order_ids"])) for asset in retired)


def _readiness_reasons(
    blockers: tuple[str, ...],
    ledger_reconciled: bool,
    sizing_ready: bool,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if blockers:
        reasons.append("venue is not flat with no open orders")
    if not ledger_reconciled:
        reasons.append("backend ledger and venue position/order identity differ")
    if not sizing_ready:
        reasons.append(
            "planned sizing lacks minimum-lot, visible-depth, or effective fee support"
        )
    return tuple(reasons)


def _integer_leverage(value: float) -> int:
    if not math.isfinite(value) or value <= 0.0 or not value.is_integer():
        raise ValueError("retired venue maximum leverage must be a positive integer")
    return int(value)


def _symbol(value: Mapping[str, object]) -> str:
    symbol = value.get("symbol")
    if not isinstance(symbol, str) or not symbol:
        raise ValueError("retired asset symbol is invalid")
    return symbol


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _rows(value: object, label: str) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{label} must be a list or tuple")
    return tuple(_mapping(row, label) for row in value)


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(
        not isinstance(item, str) for item in value
    ):
        raise ValueError(f"{label} must be a string list")
    return tuple(value)


def _ids(value: object) -> tuple[int, ...]:
    if not isinstance(value, (list, tuple)) or any(
        isinstance(item, bool) or not isinstance(item, int) or item <= 0
        for item in value
    ):
        raise ValueError("retired open order ids must be positive integers")
    return tuple(value)
