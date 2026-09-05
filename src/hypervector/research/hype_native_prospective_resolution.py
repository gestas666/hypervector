"""Exact post-close resolution for HYPE-native v54 prospective lifecycles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

import numpy as np
import pandas as pd

from hypervector.data.hl_funding_evidence import HlFundingEvidence
from hypervector.research.cohort_exact_depth_books import visible_depth_fill
from hypervector.research.hype_funding_events import build_hype_funding_events

Record = Mapping[str, object]
_MODE = "hype_native_v54_prospective_lifecycle_report_only"
_PROFILE = "multi_asset_growth_first_5000_hype_native_long_challenger_v54"
_PROFILE_FINGERPRINT = (
    "1c0beafb19ef1b8c5594d3bf1aa6a23eeff12f28f540d958953cc25e8bff1643"
)
_STRATEGY = "hype_native_breakout_onset_long_v3"


class HypeProxyExitUnconfirmedError(ValueError):
    """Report a terminal BBO-proxy exit that exact mark evidence rejects."""

    def __init__(self, mark_evidence: Record) -> None:
        """Retain the exact mark-path evidence for a rejection artifact."""
        super().__init__("HYPE BBO stop lacks exact mark confirmation")
        self.mark_evidence = dict(mark_evidence)


def resolve_hype_native_prospective_lifecycles(
    report: Record,
    funding: HlFundingEvidence,
    prices: pd.DataFrame,
    *,
    mark_prices: pd.DataFrame | None = None,
    stop_books: Sequence[Record] | None = None,
    maximum_oracle_staleness_ms: int,
    maximum_mark_gap_ms: int,
) -> dict[str, object]:
    """Attach exact funding and mark-stop truth to every resolved v54 path."""
    _require_report(report)
    frame = _prices(prices)
    marks = _marks(frame.loc[:, ["ts_ms", "mark_price"]])
    if mark_prices is not None:
        marks = _marks(mark_prices)
    execution = _execution(report)
    lifecycles = _closed_lifecycles(report)
    resolved = [
        _resolve_lifecycle(
            row,
            funding,
            frame,
            marks,
            stop_books,
            execution,
            maximum_oracle_staleness_ms,
            maximum_mark_gap_ms,
        )
        for row in lifecycles
    ]
    return _resolution_payload(report, resolved, mark_prices, stop_books)


def _resolution_payload(
    source: Record,
    resolved: Sequence[Record],
    mark_prices: pd.DataFrame | None,
    stop_books: Sequence[Record] | None,
) -> dict[str, object]:
    """Serialize exact resolved economics and source identities."""
    net = sum(float(row["net_pnl_usd_after_funding"]) for row in resolved)
    return {
        "schema_version": 1,
        "mode": "hype_native_v54_exact_post_close_resolution_report_only",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "funding_source": "hl_funding_history",
            "mark_source": (
                "0xarchive_hyperliquid_prices"
                if mark_prices is None
                else "hyperliquid_ws_activeAssetCtx_local_receipt"
            ),
            "oracle_source": "0xarchive_hyperliquid_prices",
            "stop_execution_source": (
                "unmodified_reported_exit"
                if stop_books is None
                else "hyperliquid_ws_l2Book_local_receipt_finite_depth"
            ),
        },
        "identity": dict(_mapping(source.get("identity"), "HYPE identity")),
        "lifecycles": list(resolved),
        "summary": {
            "trades": len(resolved),
            "net_pnl_usd_after_funding": net,
            "wins": sum(
                float(row["net_pnl_usd_after_funding"]) > 0 for row in resolved
            ),
            "losses": sum(
                float(row["net_pnl_usd_after_funding"]) <= 0 for row in resolved
            ),
        },
    }


def _resolve_lifecycle(
    lifecycle: Record,
    funding: HlFundingEvidence,
    oracle_prices: pd.DataFrame,
    mark_prices: pd.DataFrame,
    stop_books: Sequence[Record] | None,
    execution: Record,
    maximum_oracle_staleness_ms: int,
    maximum_mark_gap_ms: int,
) -> dict[str, object]:
    entry = _integer(lifecycle.get("entry_book_time_ms"), "entry time")
    exit_time = _integer(lifecycle.get("exit_book_time_ms"), "exit time")
    if exit_time <= entry:
        raise ValueError("HYPE prospective exit must follow entry")
    quantity = _positive(lifecycle.get("entry_quantity"), "entry quantity")
    side = _side(lifecycle.get("side"))
    stop = _positive(lifecycle.get("stop_price"), "stop price")
    mark = _mark_resolution(
        mark_prices, side, stop, entry, exit_time, maximum_mark_gap_ms
    )
    _require_exit_mark_consistency(lifecycle, mark)
    exit_economics = _stop_execution(lifecycle, mark, stop_books, execution)
    resolved_exit = int(exit_economics["exit_book_time_ms"])
    events = build_hype_funding_events(
        funding,
        oracle_prices.loc[:, ["ts_ms", "oracle_price"]].dropna(),
        side=side,
        quantity=quantity,
        entry_time_ms=entry,
        exit_time_ms=resolved_exit,
        maximum_oracle_staleness_ms=maximum_oracle_staleness_ms,
    )
    before = _number(exit_economics["net_pnl_usd_before_funding"], "pre-funding PnL")
    cashflow = sum(float(row["cashflow_usd"]) for row in events)
    return {
        "decision_time_ms": _integer(lifecycle.get("decision_time_ms"), "decision"),
        "side": side,
        "entry_book_time_ms": entry,
        **exit_economics,
        "funding_event_count": len(events),
        "funding_events": events,
        "funding_cashflow_usd": cashflow,
        "net_pnl_usd_before_funding": before,
        "net_pnl_usd_after_funding": before + cashflow,
        **mark,
    }


def _mark_resolution(
    prices: pd.DataFrame,
    side: str,
    stop: float,
    entry: int,
    exit_time: int,
    maximum_gap_ms: int,
) -> dict[str, object]:
    _positive_integer(maximum_gap_ms, "maximum mark gap")
    window = prices.loc[
        prices["ts_ms"].between(entry, exit_time, inclusive="both")
        & prices["mark_price"].notna(),
        ["ts_ms", "received_ts_ns", "mark_price"],
    ]
    if window.empty:
        raise ValueError("HYPE lifecycle has no exact mark observations")
    times = window["ts_ms"].to_numpy(dtype=np.int64)
    receipt_times = window["received_ts_ns"].to_numpy(dtype=np.int64)
    marks = window["mark_price"].to_numpy(dtype=float)
    gaps = np.diff(np.concatenate(([entry], times, [exit_time])))
    maximum_gap = int(gaps.max())
    if maximum_gap > maximum_gap_ms:
        raise ValueError("HYPE mark path gap exceeds the declared bound")
    crossed = marks <= stop if side == "long" else marks >= stop
    cross_index = int(np.argmax(crossed)) if crossed.any() else None
    return {
        "mark_stop_truth": (
            "confirmed_mark_stop"
            if cross_index is not None
            else "confirmed_no_earlier_mark_stop"
        ),
        "first_mark_stop_cross_time_ms": (
            None if cross_index is None else int(times[cross_index])
        ),
        "first_mark_stop_cross_received_ts_ns": (
            None if cross_index is None else int(receipt_times[cross_index])
        ),
        "minimum_mark_price": float(marks.min()),
        "maximum_mark_price": float(marks.max()),
        "mark_rows": len(window),
        "maximum_mark_gap_ms": maximum_gap,
    }


def _stop_execution(
    lifecycle: Record,
    mark: Record,
    books: Sequence[Record] | None,
    execution: Record,
) -> dict[str, object]:
    proxy_time = _integer(lifecycle.get("exit_book_time_ms"), "proxy exit time")
    base = {
        "exit_book_time_ms": proxy_time,
        "exit_reason": _text(lifecycle.get("exit_reason"), "exit reason"),
        "net_pnl_usd_before_funding": lifecycle.get("net_pnl_usd_before_funding"),
    }
    if books is None or mark.get("mark_stop_truth") != "confirmed_mark_stop":
        return base
    trigger_ns = _integer(
        mark.get("first_mark_stop_cross_received_ts_ns"), "mark trigger receipt"
    )
    book = _first_causal_stop_book(books, trigger_ns, execution)
    fill = visible_depth_fill(
        _book_event(book),
        position_side=_side(lifecycle.get("side")),
        notional=0.0,
        quantity=_positive(lifecycle.get("entry_quantity"), "entry quantity"),
    )
    if fill.get("complete") is not True:
        raise ValueError("HYPE stop exit exceeds retained public L2 depth")
    return _stop_economics(lifecycle, book, fill, execution, proxy_time, trigger_ns)


def _first_causal_stop_book(
    books: Sequence[Record], trigger_ns: int, execution: Record
) -> Record:
    ordered = sorted(
        books, key=lambda row: _integer(row.get("received_ts_ns"), "L2 receipt")
    )
    selected = next(
        (
            row
            for row in ordered
            if _integer(row.get("received_ts_ns"), "L2 receipt") >= trigger_ns
        ),
        None,
    )
    if selected is None:
        raise ValueError("HYPE mark trigger has no causal retained L2 book")
    delay = _integer(selected.get("received_ts_ns"), "L2 receipt") - trigger_ns
    maximum = _positive_integer(execution.get("maximum_exit_delay_ms"), "exit delay")
    if delay > maximum * 1_000_000:
        raise ValueError("HYPE causal stop book exceeds maximum exit delay")
    return selected


def _stop_economics(
    lifecycle: Record,
    book: Record,
    fill: Record,
    execution: Record,
    proxy_time: int,
    trigger_ns: int,
) -> dict[str, object]:
    quantity = _positive(lifecycle.get("entry_quantity"), "entry quantity")
    entry_price = _positive(lifecycle.get("entry_price"), "entry price")
    exit_price = _positive(fill.get("price"), "stop exit price")
    gross = quantity * (exit_price - entry_price)
    turnover = quantity * (entry_price + exit_price)
    fee = turnover * _number(execution.get("fee_bps_per_side"), "fee bps") / 10_000
    slip = (
        turnover
        * _number(execution.get("residual_slippage_bps_per_side"), "slippage bps")
        / 10_000
    )
    received_ns = _integer(book.get("received_ts_ns"), "L2 receipt")
    return {
        "proxy_exit_book_time_ms": proxy_time,
        "exit_book_time_ms": received_ns // 1_000_000,
        "exit_reason": "protective_stop_mark_trigger",
        "exit_price": exit_price,
        "exit_levels_consumed": fill.get("levels_consumed"),
        "mark_trigger_to_book_delay_ms": (received_ns - trigger_ns) / 1_000_000,
        "gross_pnl_usd": gross,
        "fee_usd": fee,
        "residual_slippage_usd": slip,
        "net_pnl_usd_before_funding": gross - fee - slip,
    }


def _book_event(book: Record) -> dict[str, object]:
    if book.get("symbol") != "HYPE" or book.get("source") != "hyperliquid_ws_l2Book":
        raise ValueError("HYPE stop book identity differs")
    received_ns = _integer(book.get("received_ts_ns"), "L2 receipt")
    return {
        "event_type": "book_observation",
        "run_id": "hype_native_exact_stop_resolution",
        "payload": {
            "symbol": "HYPE",
            "exchange_ts_ms": _integer(book.get("exchange_ts_ms"), "exchange time"),
            "recv_ts_ms": received_ns // 1_000_000,
            "bids": book.get("bids"),
            "asks": book.get("asks"),
        },
    }


def _require_exit_mark_consistency(lifecycle: Record, mark: Record) -> None:
    reason = _text(lifecycle.get("exit_reason"), "exit reason")
    crossed = mark.get("mark_stop_truth") == "confirmed_mark_stop"
    if crossed and reason != "protective_stop_bbo_proxy":
        raise ValueError("HYPE mark stop predates reported exit")
    if not crossed and reason == "protective_stop_bbo_proxy":
        raise HypeProxyExitUnconfirmedError(mark)


def _closed_lifecycles(report: Record) -> list[Record]:
    rows = _records(report.get("lifecycles"), "HYPE lifecycles")
    closed = [row for row in rows if row.get("exit_book_time_ms") is not None]
    if not closed:
        raise ValueError("HYPE prospective report has no closed lifecycle")
    if any(row.get("technical_path_resolved") is not True for row in closed):
        raise ValueError("HYPE closed lifecycle has unresolved technical evidence")
    return closed


def _require_report(report: Record) -> None:
    if report.get("schema_version") != 1 or report.get("mode") != _MODE:
        raise ValueError("HYPE prospective report contract is invalid")
    contract = _mapping(report.get("contract"), "HYPE contract")
    if (
        contract.get("report_only") is not True
        or contract.get("execution_authority") != "none"
    ):
        raise ValueError("HYPE prospective resolution requires report-only evidence")
    identity = _mapping(report.get("identity"), "HYPE identity")
    expected = {
        "profile_id": _PROFILE,
        "profile_fingerprint": _PROFILE_FINGERPRINT,
        "strategy_id": _STRATEGY,
        "symbol": "HYPE",
    }
    if any(identity.get(field) != value for field, value in expected.items()):
        raise ValueError("HYPE prospective resolution identity is invalid")


def _execution(report: Record) -> Record:
    contract = _mapping(report.get("contract"), "HYPE contract")
    execution = _mapping(contract.get("execution"), "HYPE execution contract")
    expected = {
        "maximum_exit_delay_ms": 60_000,
        "fee_bps_per_side": 4.32,
        "residual_slippage_bps_per_side": 2.0,
    }
    if any(execution.get(field) != value for field, value in expected.items()):
        raise ValueError("HYPE prospective execution contract is invalid")
    return execution


def _prices(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"ts_ms", "mark_price", "oracle_price"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"HYPE prices are missing columns: {sorted(missing)}")
    result = frame.loc[:, sorted(required)].copy()
    result["ts_ms"] = pd.to_numeric(result["ts_ms"], errors="raise")
    for field in ("mark_price", "oracle_price"):
        result[field] = pd.to_numeric(result[field], errors="coerce")
        values = result[field].dropna()
        if not np.isfinite(values).all() or values.le(0.0).any():
            raise ValueError(f"HYPE {field} must be positive and finite")
    timestamps = result["ts_ms"].to_numpy(dtype=float)
    if not np.isfinite(timestamps).all() or (timestamps != np.floor(timestamps)).any():
        raise ValueError("HYPE price timestamps must be finite integers")
    result["ts_ms"] = result["ts_ms"].astype("int64")
    if (
        result["ts_ms"].duplicated().any()
        or not result["ts_ms"].is_monotonic_increasing
    ):
        raise ValueError("HYPE price timestamps must be ordered and unique")
    return result


def _marks(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"ts_ms", "mark_price"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"HYPE marks are missing columns: {sorted(missing)}")
    has_receipts = "received_ts_ns" in frame.columns
    columns = ["ts_ms", "mark_price"]
    if has_receipts:
        columns.insert(1, "received_ts_ns")
    result = frame.loc[:, columns].copy()
    result["ts_ms"] = pd.to_numeric(result["ts_ms"], errors="raise")
    result["mark_price"] = pd.to_numeric(result["mark_price"], errors="raise")
    timestamps = result["ts_ms"].to_numpy(dtype=float)
    marks = result["mark_price"].to_numpy(dtype=float)
    if not np.isfinite(timestamps).all() or (timestamps != np.floor(timestamps)).any():
        raise ValueError("HYPE mark timestamps must be finite integers")
    if not np.isfinite(marks).all() or (marks <= 0.0).any():
        raise ValueError("HYPE mark prices must be positive and finite")
    result["ts_ms"] = result["ts_ms"].astype("int64")
    if "received_ts_ns" not in result.columns:
        result["received_ts_ns"] = result["ts_ms"] * 1_000_000
    result["received_ts_ns"] = pd.to_numeric(
        result["received_ts_ns"], errors="raise"
    ).astype("int64")
    if (result["received_ts_ns"] < result["ts_ms"] * 1_000_000).any():
        raise ValueError("HYPE mark receipt cannot precede its millisecond bucket")
    order = result["received_ts_ns"] if has_receipts else result["ts_ms"]
    if order.duplicated().any() or not order.is_monotonic_increasing:
        raise ValueError("HYPE mark observations must be ordered and unique")
    return result


def _records(value: object, label: str) -> list[Record]:
    if not isinstance(value, list) or any(
        not isinstance(row, Mapping) for row in value
    ):
        raise ValueError(f"{label} must be an object array")
    return list(value)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _side(value: object) -> str:
    if value not in {"long", "short"}:
        raise ValueError("HYPE lifecycle side must be long or short")
    return str(value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be non-empty text")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _positive_integer(value: object, label: str) -> int:
    result = _integer(value, label)
    if result <= 0:
        raise ValueError(f"{label} must be positive")
    return result


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _positive(value: object, label: str) -> float:
    result = _number(value, label)
    if result <= 0.0:
        raise ValueError(f"{label} must be positive")
    return result
