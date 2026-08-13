"""Report-only entry-alignment outcomes across completed live lifecycles."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from statistics import median

Record = Mapping[str, object]
_COMPONENT_ALIGNED = "aligned_with_position"
_COMPONENT_OPPOSED = "opposing_position"
_COMPONENT_VALUES = frozenset(
    {_COMPONENT_ALIGNED, _COMPONENT_OPPOSED, "unavailable", "mixed_or_transition"}
)
_BREAKOUT_VALUES = frozenset({"aligned", "opposed", "unavailable"})
_POSITION_SIDES = frozenset({"long", "short"})
_HIP3_SWING_STRATEGIES = frozenset(
    {
        "hip3_swing_ha_sp500_spcx_bidirectional_v2",
        "hip3_swing_ha_sndk_gold_brent_bidirectional_v1",
    }
)
_HIP3_ENTRY_MODES = frozenset({"onset", "state"})
_HIP3_EXIT_MODES = frozenset({"ha_flip", "alignment_loss"})


def build_live_entry_alignment_mechanism(
    reflected_trades: Sequence[Record],
    *,
    open_trades: Sequence[Record] = (),
) -> dict[str, object]:
    """Normalize closed outcomes and separately expose provisional open paths."""
    grouped: defaultdict[tuple[str, str], list[Record]] = defaultdict(list)
    grouped_by_side: defaultdict[tuple[str, str, str], list[Record]] = defaultdict(list)
    for trade in reflected_trades:
        strategy = _text(trade.get("strategy_id"), "strategy id")
        symbol = _text(trade.get("symbol"), "symbol")
        side = _position_side(trade)
        _number(trade.get("net_pnl_usd"), "net pnl")
        _number(trade.get("net_return_on_margin_pct"), "return on margin")
        grouped[(strategy, symbol)].append(trade)
        grouped_by_side[(strategy, symbol, side)].append(trade)
    reports = {
        f"{strategy}|{symbol}": _pair_report(trades)
        for (strategy, symbol), trades in sorted(grouped.items())
    }
    side_reports = {
        f"{strategy}|{symbol}|{side}": _side_report(side, trades)
        for (strategy, symbol, side), trades in sorted(grouped_by_side.items())
    }
    return {
        "schema_version": 3,
        "mode": "cohort_live_entry_alignment_mechanism_v3",
        "scope": "all_live_history_mixed_profiles",
        "contract": _contract(),
        "closed_trades": sum(len(rows) for rows in grouped.values()),
        "provider_symbols": len(grouped),
        "pooled": _pair_report(reflected_trades),
        "by_provider_symbol": reports,
        "provider_symbol_sides": len(grouped_by_side),
        "by_provider_symbol_side": side_reports,
        "provisional_open": _provisional_open_report(open_trades),
        "limitations": _limitations(),
    }


def _provisional_open_report(trades: Sequence[Record]) -> dict[str, object]:
    """Group marked open paths without pooling them with resolved economics."""
    grouped: defaultdict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(
        list
    )
    for trade in trades:
        strategy = _text(trade.get("strategy_id"), "strategy id")
        symbol = _text(trade.get("symbol"), "symbol")
        side = _position_side(trade)
        grouped[(strategy, symbol, side)].append(_provisional_row(trade))
    reports = {
        f"{strategy}|{symbol}|{side}": _provisional_pair_report(side, rows)
        for (strategy, symbol, side), rows in sorted(grouped.items())
    }
    return {
        "positions": sum(len(rows) for rows in grouped.values()),
        "provider_symbol_sides": len(grouped),
        "pooled_with_closed_performance": False,
        "by_provider_symbol_side": reports,
    }


def _provisional_row(trade: Record) -> dict[str, object]:
    """Extract one explicit marked path and its decision-time mechanism identity."""
    marked = _optional_mapping(trade.get("marked_economics"), "marked economics")
    net = _optional_number(marked.get("active_lifecycle_marked_net_pnl_usd"))
    margin = _optional_number(marked.get("margin_used_usd"))
    if margin is not None and margin <= 0.0:
        raise ValueError("open marked margin must be positive")
    marked_return = net / margin * 100.0 if net is not None and margin else None
    path = _open_path_metrics(trade.get("path_since_entry"))
    stop = _optional_mapping(trade.get("protective_stop"), "protective stop")
    return {
        "lifecycle_id": _text(trade.get("lifecycle_id"), "lifecycle id"),
        "component_stance": _component_category(trade),
        "breakout_side_relation": _breakout_category(trade),
        "provider_native_mechanism": _provider_native_identity(trade),
        "marked_net_pnl_usd": net,
        "marked_return_on_margin_pct": marked_return,
        "mfe_bps": None if path is None else path[0],
        "mae_bps": None if path is None else path[1],
        "peak_giveback_bps": None if path is None else path[2],
        "protected": stop.get("oid") is not None,
    }


def _open_path_metrics(value: object) -> tuple[float, float, float] | None:
    """Return a complete observed MFE/MAE/giveback triple when available."""
    path = _optional_mapping(value, "path since entry")
    if not path or path.get("status") != "observed":
        return None
    return (
        _number(path.get("maximum_favorable_excursion_bps"), "open MFE"),
        _number(path.get("maximum_adverse_excursion_bps"), "open MAE"),
        _number(path.get("peak_giveback_bps"), "open peak giveback"),
    )


def _provisional_pair_report(
    side: str, rows: Sequence[dict[str, object]]
) -> dict[str, object]:
    """Summarize one strategy-symbol-side open cohort as provisional telemetry."""
    marked = [row for row in rows if row["marked_net_pnl_usd"] is not None]
    paths = [row for row in rows if row["mfe_bps"] is not None]
    returns = [
        _required_row_number(row, "marked_return_on_margin_pct") for row in marked
    ]
    return {
        "side": side,
        "positions": len(rows),
        "protected_positions": sum(bool(row["protected"]) for row in rows),
        "component_stance_counts": _category_counts(rows, "component_stance"),
        "breakout_side_relation_counts": _category_counts(
            rows, "breakout_side_relation"
        ),
        "provider_native_mechanism_counts": _category_counts(
            rows, "provider_native_mechanism"
        ),
        "marked_economics_coverage": _coverage(marked, rows),
        "marked_net_pnl_usd": sum(
            _required_row_number(row, "marked_net_pnl_usd") for row in marked
        ),
        "mean_marked_return_on_margin_pct": _mean(returns),
        "path_coverage": _coverage(paths, rows),
        "mean_mfe_bps": _mean(_row_numbers(paths, "mfe_bps")),
        "mean_mae_bps": _mean(_row_numbers(paths, "mae_bps")),
        "mean_peak_giveback_bps": _mean(_row_numbers(paths, "peak_giveback_bps")),
        "lifecycles": list(rows),
    }


def _category_counts(rows: Sequence[dict[str, object]], field: str) -> dict[str, int]:
    """Return sorted categorical counts for one provisional cohort."""
    values = (_text(row.get(field), field.replace("_", " ")) for row in rows)
    return dict(sorted(Counter(values).items()))


def _coverage(
    available: Sequence[dict[str, object]], all_rows: Sequence[dict[str, object]]
) -> dict[str, int]:
    """Expose available and unavailable provisional observations."""
    return {"available": len(available), "unavailable": len(all_rows) - len(available)}


def _row_numbers(rows: Sequence[dict[str, object]], field: str) -> list[float]:
    """Return finite values from rows whose field is required to be present."""
    return [_required_row_number(row, field) for row in rows]


def _required_row_number(row: Mapping[str, object], field: str) -> float:
    """Return one required finite numeric row value."""
    return _number(row.get(field), field.replace("_", " "))


def _mean(values: Sequence[float]) -> float | None:
    """Return the arithmetic mean or unavailable for an empty cohort."""
    return sum(values) / len(values) if values else None


def _pair_report(trades: Sequence[Record]) -> dict[str, object]:
    component = _attribution_report(
        trades,
        _component_category,
        _COMPONENT_ALIGNED,
        _COMPONENT_OPPOSED,
    )
    relation = _attribution_report(trades, _breakout_category, "aligned", "opposed")
    return {
        "closed_trades": len(trades),
        "component_stance": component,
        "breakout_side_relation": relation,
        "provider_native_mechanism": _native_attribution_report(trades),
    }


def _native_attribution_report(trades: Sequence[Record]) -> dict[str, object]:
    """Separate outcomes by exact provider-native mechanism identity."""
    grouped: defaultdict[str, list[Record]] = defaultdict(list)
    unavailable = 0
    for trade in trades:
        identity = _provider_native_identity(trade)
        if identity == "unavailable":
            unavailable += 1
        else:
            grouped[identity].append(trade)
    attributable = sum(len(rows) for rows in grouped.values())
    return {
        "coverage": {"attributable": attributable, "unavailable": unavailable},
        "by_identity": {
            identity: _outcome_summary(rows)
            for identity, rows in sorted(grouped.items())
        },
    }


def _side_report(side: str, trades: Sequence[Record]) -> dict[str, object]:
    return {"side": side, "outcome": _outcome_summary(trades), **_pair_report(trades)}


def _attribution_report(
    trades: Sequence[Record],
    category_reader: Callable[[Record], str],
    aligned_value: str,
    opposed_value: str,
) -> dict[str, object]:
    aligned: list[Record] = []
    opposed: list[Record] = []
    for trade in trades:
        category = category_reader(trade)
        if category == aligned_value:
            aligned.append(trade)
        elif category == opposed_value:
            opposed.append(trade)
    attributable = len(aligned) + len(opposed)
    aligned_summary = _outcome_summary(aligned)
    opposed_summary = _outcome_summary(opposed)
    return {
        "coverage": {
            "attributable": attributable,
            "unavailable": len(trades) - attributable,
        },
        "aligned": aligned_summary,
        "opposed": opposed_summary,
        "opposed_minus_aligned_mean_pct": _mean_difference(
            aligned_summary, opposed_summary
        ),
    }


def _outcome_summary(trades: Sequence[Record]) -> dict[str, object]:
    returns = [
        _number(row.get("net_return_on_margin_pct"), "return on margin")
        for row in trades
    ]
    pnl = [_number(row.get("net_pnl_usd"), "net pnl") for row in trades]
    gains = sum(value for value in returns if value > 0.0)
    losses = -sum(value for value in returns if value < 0.0)
    usd_gains = sum(value for value in pnl if value > 0.0)
    usd_losses = -sum(value for value in pnl if value < 0.0)
    return {
        "trades": len(trades),
        "wins": sum(value > 0.0 for value in returns),
        "losses": sum(value < 0.0 for value in returns),
        "breakeven": sum(value == 0.0 for value in returns),
        "net_pnl_usd": sum(pnl),
        "mean_net_return_on_margin_pct": (
            sum(returns) / len(returns) if returns else None
        ),
        "median_net_return_on_margin_pct": median(returns) if returns else None,
        "usd_profit_factor": usd_gains / usd_losses if usd_losses > 0.0 else None,
        "normalized_profit_factor": gains / losses if losses > 0.0 else None,
    }


def _component_category(trade: Record) -> str:
    assessment = _optional_mapping(
        trade.get("entry_regime_assessment"), "entry regime assessment"
    )
    value = assessment.get("component_stance")
    if value is None:
        return "unavailable"
    category = _text(value, "component stance")
    if category not in _COMPONENT_VALUES:
        raise ValueError(f"unsupported component stance: {category}")
    return category


def _breakout_category(trade: Record) -> str:
    provider = _signal_provider(trade)
    readiness = _optional_mapping(provider.get("readiness"), "provider readiness")
    metrics = _optional_mapping(readiness.get("metrics"), "provider metrics")
    value = metrics.get("breakout_side_relation")
    if value is None:
        return "unavailable"
    category = _text(value, "breakout-side relation")
    if category not in _BREAKOUT_VALUES:
        raise ValueError(f"unsupported breakout-side relation: {category}")
    return category


def _provider_native_identity(trade: Record) -> str:
    """Return an exact HIP-3 Swing recipe identity or explicit unavailability."""
    strategy = _text(trade.get("strategy_id"), "strategy id")
    if strategy not in _HIP3_SWING_STRATEGIES:
        return "unavailable"
    provider = _signal_provider(trade)
    readiness = _optional_mapping(provider.get("readiness"), "provider readiness")
    metrics = _optional_mapping(readiness.get("metrics"), "provider metrics")
    required = ("entry_mode", "exit_mode", "ema_fast", "ema_slow")
    if not metrics or all(metrics.get(field) is None for field in required):
        return "unavailable"
    if any(metrics.get(field) is None for field in required):
        raise ValueError("HIP-3 native mechanism metrics are incomplete")
    side = _position_side(trade)
    entry_mode = _choice(metrics.get("entry_mode"), _HIP3_ENTRY_MODES, "entry mode")
    exit_mode = _choice(metrics.get("exit_mode"), _HIP3_EXIT_MODES, "exit mode")
    ema = _numeric_relation(metrics, "ema_fast", "ema_slow", side)
    ha = _optional_signed_relation(metrics.get("ha_color"), side, "HA color")
    order_block = _optional_signed_relation(
        metrics.get("active_order_block_direction"), side, "order block"
    )
    if provider.get("eligible") is not True:
        raise ValueError("HIP-3 executed lifecycle requires an eligible entry decision")
    return (
        f"hip3_swing:entry={entry_mode}:exit={exit_mode}:ema={ema}:ha={ha}:"
        f"order_block={order_block}:pivot=confirmed_by_eligible_decision"
    )


def _signal_provider(trade: Record) -> Record:
    """Return one trade's causal signal-provider record."""
    entry = _optional_mapping(trade.get("entry_context"), "entry context")
    return _optional_mapping(entry.get("signal_provider"), "signal provider")


def _numeric_relation(
    metrics: Record, fast_field: str, slow_field: str, side: str
) -> str:
    """Classify a two-value relation against the position direction."""
    fast = _number(metrics.get(fast_field), fast_field.replace("_", " "))
    slow = _number(metrics.get(slow_field), slow_field.replace("_", " "))
    if fast == slow:
        return "flat"
    direction = 1.0 if fast > slow else -1.0
    return _direction_relation(direction, side)


def _optional_signed_relation(value: object, side: str, label: str) -> str:
    """Classify an optional signed provider feature without inventing a value."""
    if value is None:
        return "unavailable"
    return _signed_relation(value, side, label)


def _signed_relation(value: object, side: str, label: str) -> str:
    """Classify a signed provider feature against the position direction."""
    number = _number(value, label)
    if number == 0.0:
        return "neutral"
    return _direction_relation(number, side)


def _direction_relation(value: float, side: str) -> str:
    """Return aligned or opposed for a nonzero signed direction."""
    expected = 1.0 if side == "long" else -1.0
    return "aligned" if value * expected > 0.0 else "opposed"


def _choice(value: object, allowed: frozenset[str], label: str) -> str:
    """Return one validated categorical provider value."""
    selected = _text(value, label)
    if selected not in allowed:
        raise ValueError(f"unsupported HIP-3 {label}: {selected}")
    return selected


def _position_side(trade: Record) -> str:
    side = _text(trade.get("side"), "position side").lower()
    if side not in _POSITION_SIDES:
        raise ValueError(f"unsupported position side: {side}")
    return side


def _mean_difference(
    aligned: Mapping[str, object], opposed: Mapping[str, object]
) -> float | None:
    aligned_mean = aligned.get("mean_net_return_on_margin_pct")
    opposed_mean = opposed.get("mean_net_return_on_margin_pct")
    if aligned_mean is None or opposed_mean is None:
        return None
    return _number(opposed_mean, "opposed mean") - _number(aligned_mean, "aligned mean")


def _optional_mapping(value: object, label: str) -> Record:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _optional_number(value: object) -> float | None:
    """Return an optional finite number without fabricating absent telemetry."""
    if value is None:
        return None
    return _number(value, "optional numeric telemetry")


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_strategy_changes": False,
        "runtime_strategy_changed": False,
        "execution_gate": False,
        "portfolio_pnl_claimed": False,
    }


def _limitations() -> list[str]:
    return [
        "component stance uses fixed descriptive weights rather than fitted returns",
        "legacy lifecycles without point-in-time telemetry remain unavailable",
        "mixed profile sizes make net USD descriptive rather than portfolio additive",
        "side-separated categories have fewer effective samples than pooled categories",
        "small categories cannot establish a durable entry-direction edge",
    ]
