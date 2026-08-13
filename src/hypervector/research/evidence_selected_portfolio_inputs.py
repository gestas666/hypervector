"""Immutable-source adapters for evidence-selected portfolio diagnostics."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import math

import pandas as pd

from hypervector.research.current_cohort_shared_portfolio import (
    CohortOutcome,
    CohortTradeSpec,
)
from hypervector.research.shared_trade_portfolio import SharedTradeOutcome


def adapt_range_context_payload(
    payload: Mapping[str, object],
    spec: CohortTradeSpec,
    *,
    candidate_id: str,
) -> tuple[CohortOutcome, ...]:
    """Normalize one exact range-context candidate to a fixed live cap."""
    if payload.get("execution_authority") != "none":
        raise ValueError("range context source must have no execution authority")
    if payload.get("model_authority") != "none":
        raise ValueError("range context source must have no model authority")
    if _text(payload, "symbol").upper() != spec.symbol.upper():
        raise ValueError("range context source symbol does not match live route")
    continuous = _mapping(payload.get("continuous"), "range context continuous")
    candidates = _mapping_rows(continuous.get("candidates"), "context candidates")
    matches = [row for row in candidates if row.get("candidate_id") == candidate_id]
    if len(matches) != 1:
        raise ValueError(
            "range context source must contain one exact context candidate"
        )
    trades = _mapping_rows(matches[0].get("trades"), "context candidate trades")
    if not trades:
        raise ValueError("range context candidate contains no completed trades")
    return tuple(
        _adapt_normalized_trade(
            trade,
            spec,
            f"context:{candidate_id}",
            index,
            entry_fee_usd=spec.notional_usd * spec.entry_fee_bps / 10_000.0,
        )
        for index, trade in enumerate(trades)
    )


def adapt_hip3_sidecar(
    frame: pd.DataFrame,
    specs: Mapping[tuple[str, str], CohortTradeSpec],
    *,
    friction: str,
) -> tuple[CohortOutcome, ...]:
    """Normalize selected opened HIP-3 phases for one friction scenario."""
    _validate_hip3_frame(frame, friction)
    output: list[CohortOutcome] = []
    for (strategy_id, symbol), spec in specs.items():
        if (strategy_id, symbol) != (spec.strategy_id, spec.symbol):
            raise ValueError("HIP-3 sidecar spec identity is inconsistent")
        mask = (
            frame["strategy_id"].eq(strategy_id)
            & frame["symbol"].eq(symbol)
            & frame["friction"].eq(friction)
        )
        selected = frame.loc[mask]
        if selected.empty:
            raise ValueError(
                f"HIP-3 sidecar contains no selected route: {strategy_id}|{symbol}"
            )
        output.extend(_adapt_hip3_rows(selected, spec, friction))
    return tuple(output)


def _validate_hip3_frame(frame: pd.DataFrame, friction: str) -> None:
    required = {
        "strategy_id",
        "symbol",
        "phase",
        "friction",
        "direction",
        "entry_time_utc",
        "exit_time_utc",
        "notional_usd",
        "fees_usd",
        "net_pnl_usd",
        "exit_reason",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"HIP-3 sidecar columns are missing: {missing}")
    phases = set(frame["phase"].astype(str))
    if not phases or not phases.issubset({"development", "validation"}):
        raise ValueError(
            f"HIP-3 phases must be opened development/validation: {sorted(phases)}"
        )
    observed_friction = set(frame["friction"].astype(str))
    if not observed_friction.issubset({"nominal", "stress"}):
        raise ValueError("HIP-3 friction must be nominal or stress")
    if friction not in {"nominal", "stress"}:
        raise ValueError("requested HIP-3 friction must be nominal or stress")


def _adapt_hip3_rows(
    rows: pd.DataFrame,
    spec: CohortTradeSpec,
    friction: str,
) -> list[CohortOutcome]:
    output: list[CohortOutcome] = []
    for index, (_, row) in enumerate(rows.iterrows()):
        source_notional = _positive_number(row["notional_usd"], "HIP-3 notional")
        source_fees = _nonnegative_number(row["fees_usd"], "HIP-3 fees")
        scale = spec.notional_usd / source_notional
        trade = {
            "direction": row["direction"],
            "entry_time_utc": row["entry_time_utc"],
            "exit_time_utc": row["exit_time_utc"],
            "source_notional_usd": source_notional,
            "net_pnl_usd": row["net_pnl_usd"],
            "exit_reason": row["exit_reason"],
        }
        phase = str(row["phase"])
        output.append(
            _adapt_normalized_trade(
                trade,
                spec,
                f"hip3:{phase}|{friction}",
                index,
                entry_fee_usd=source_fees * 0.5 * scale,
            )
        )
    return output


def _adapt_normalized_trade(
    trade: Mapping[str, object],
    spec: CohortTradeSpec,
    source: str,
    index: int,
    *,
    entry_fee_usd: float,
) -> CohortOutcome:
    side = _text(trade, "direction").lower()
    if side not in {"long", "short"}:
        raise ValueError("source trade direction must be long or short")
    entry_ms = _timestamp_ms(_text(trade, "entry_time_utc"))
    exit_ms = _timestamp_ms(_text(trade, "exit_time_utc"))
    if exit_ms < entry_ms:
        raise ValueError("source trade exit precedes its entry")
    if exit_ms == entry_ms:
        exit_ms += 1
    source_notional = _source_notional(trade)
    net_pnl = _number(trade.get("net_pnl_usd"), "source net_pnl_usd")
    identity = f"{spec.strategy_id}|{spec.symbol}|{source}|{entry_ms}|{index:05d}"
    outcome = SharedTradeOutcome(
        identity,
        spec.symbol,
        entry_ms,
        exit_ms,
        spec.reference_equity_usd,
        spec.margin_fraction,
        entry_fee_usd,
        net_pnl / source_notional * spec.notional_usd,
        _text(trade, "exit_reason"),
    )
    return CohortOutcome(spec.strategy_id, side, outcome)


def _source_notional(trade: Mapping[str, object]) -> float:
    explicit = trade.get("source_notional_usd")
    if explicit is not None:
        return _positive_number(explicit, "source notional")
    price = _positive_number(trade.get("entry_price"), "source entry price")
    quantity = abs(_number(trade.get("quantity"), "source quantity"))
    return _positive_number(price * quantity, "source entry notional")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object with text keys")
    return value


def _mapping_rows(value: object, label: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return [_mapping(row, f"{label} row") for row in value]


def _text(row: Mapping[str, object], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()


def _timestamp_ms(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("source timestamps must include a UTC offset")
    return int(parsed.timestamp() * 1_000)


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _positive_number(value: object, label: str) -> float:
    result = _number(value, label)
    if result <= 0.0:
        raise ValueError(f"{label} must be positive")
    return result


def _nonnegative_number(value: object, label: str) -> float:
    result = _number(value, label)
    if result < 0.0:
        raise ValueError(f"{label} must be non-negative")
    return result
