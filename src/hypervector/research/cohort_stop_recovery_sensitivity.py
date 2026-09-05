"""Report-only protective-stop recovery sensitivity."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_live_audit_values import mapping, number, text

Record = Mapping[str, object]


def build_stop_recovery_sensitivity(
    trades: Sequence[Record],
    *,
    stop_widths_bps: Sequence[float],
    assessment_horizon_minutes: int | None = None,
) -> dict[str, object]:
    """Build a non-executable protective-stop recovery sensitivity report."""
    widths = _validated_widths(stop_widths_bps)
    horizon = _validated_horizon(assessment_horizon_minutes)
    observations = [
        _trade_observation(trade, widths)
        for trade in trades
        if trade.get("exit_reason") == "protective_stop"
    ]
    return {
        "schema_version": 2,
        "mode": "cohort_protective_stop_recovery_sensitivity_v2",
        "contract": _contract(),
        "stop_widths_bps": list(widths),
        "summary": _summary(observations, widths, horizon),
        "trades": observations,
        "limitations": _limitations(),
    }


def _validated_widths(values: Sequence[float]) -> tuple[float, ...]:
    widths = tuple(float(value) for value in values)
    if not widths or any(value <= 0.0 for value in widths):
        raise ValueError("stop widths must be positive")
    if any(right <= left for left, right in zip(widths, widths[1:])):
        raise ValueError("stop widths must be strictly increasing")
    return widths


def _validated_horizon(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("assessment horizon must be a positive integer")
    return value


def _trade_observation(trade: Record, widths: tuple[float, ...]) -> dict[str, object]:
    entry = mapping(trade.get("entry"), "stop sensitivity entry")
    stop = mapping(trade.get("protective_stop"), "stop sensitivity stop")
    entry_price = _positive(entry.get("price"), "entry price")
    exit_price = _optional_positive(
        _optional_mapping(trade.get("exit"), "stop sensitivity exit").get("price"),
        "exit price",
    )
    stop_price = _positive(stop.get("trigger_price"), "stop price")
    side = text(trade.get("side"), "stop sensitivity side")
    paths = mapping(trade.get("entry_followthrough_path"), "followthrough paths")
    entry_notional = entry_price * _positive(entry.get("size"), "entry size")
    stop_width = _stop_width(side, entry_price, stop_price)
    leverage = _optional_positive(trade.get("leverage"), "trade leverage")
    volatility = _entry_volatility(trade)
    return {
        "lifecycle_id": text(trade.get("lifecycle_id"), "lifecycle identity"),
        "source_run_id": text(trade.get("source_run_id"), "source run identity"),
        "source_profile_fingerprint": text(
            trade.get("source_profile_fingerprint"), "source profile fingerprint"
        ),
        "strategy_id": text(trade.get("strategy_id"), "strategy identity"),
        "symbol": text(trade.get("symbol"), "trade symbol"),
        "side": side,
        "entry_notional_usd": entry_notional,
        "actual_stop_width_bps": stop_width,
        "price_stop_distance_is_leverage_independent": True,
        "leverage": leverage,
        "control_barrier_loss_on_margin_pct": (
            None if leverage is None else stop_width * leverage / 100.0
        ),
        "stop_distance_recent_bar_range_units": _distance_units(
            stop_width, volatility["recent_bar_range_bps"]
        ),
        "stop_distance_atr_units": _distance_units(stop_width, volatility["atr_bps"]),
        "volatility_evidence": volatility,
        "control_barrier_risk_usd": entry_notional * stop_width / 10_000.0,
        "horizons": _horizons(paths, widths),
        "post_stop_horizons": _post_stop_horizons(
            trade.get("post_exit_path"), side, entry_price, exit_price
        ),
    }


def _horizons(paths: Record, widths: tuple[float, ...]) -> dict[str, object]:
    output: dict[str, object] = {}
    for key, value in sorted(paths.items(), key=lambda item: int(item[0])):
        path = mapping(value, f"followthrough path {key}")
        status = text(path.get("status"), f"followthrough path {key} status")
        if status != "resolved":
            output[str(key)] = {"status": status, "candidates": {}}
            continue
        adverse = number(path.get("adverse_excursion_bps"), "adverse excursion")
        directional = number(
            path.get("directional_close_return_bps"), "directional close return"
        )
        favorable = path.get("favorable_excursion_bps")
        output[str(key)] = {
            "status": status,
            "adverse_excursion_bps": adverse,
            "directional_close_return_bps": directional,
            "favorable_excursion_bps": None
            if favorable is None
            else number(favorable, "favorable excursion"),
            "candidates": _candidates(widths, adverse, directional),
        }
    return output


def _summary(
    trades: Sequence[Mapping[str, object]],
    widths: tuple[float, ...],
    horizon: int | None,
) -> dict[str, object]:
    summary: dict[str, object] = {"protective_stop_trades": len(trades)}
    if horizon is None:
        return summary
    resolved = _resolved_horizon_rows(trades, horizon)
    recovered, post_stop_resolved = _post_stop_recovery_counts(trades, horizon)
    summary["assessment"] = {
        "horizon_minutes": horizon,
        "resolved_trades": len(resolved),
        "censored_trades": len(trades) - len(resolved),
        "post_stop_resolved_trades": post_stop_resolved,
        "entry_recovered_after_stop": recovered,
        "possible_control_whipsaws": recovered,
        "counterfactual_net_pnl_available": False,
        "candidates": {
            _width_key(width): _candidate_summary(resolved, width) for width in widths
        },
    }
    return summary


def _resolved_horizon_rows(
    trades: Sequence[Mapping[str, object]], horizon: int
) -> list[tuple[Mapping[str, object], Mapping[str, object]]]:
    output: list[tuple[Mapping[str, object], Mapping[str, object]]] = []
    for trade in trades:
        horizons = mapping(trade.get("horizons"), "trade horizons")
        value = horizons.get(str(horizon))
        if value is None:
            continue
        path = mapping(value, "assessment horizon")
        if path.get("status") == "resolved":
            output.append((trade, path))
    return output


def _post_stop_recovery_counts(
    trades: Sequence[Mapping[str, object]], horizon: int
) -> tuple[int, int]:
    recovered = 0
    resolved = 0
    for trade in trades:
        paths = mapping(trade.get("post_stop_horizons"), "post-stop horizons")
        value = paths.get(str(horizon))
        if value is None:
            continue
        path = mapping(value, "post-stop assessment horizon")
        if path.get("status") != "resolved":
            continue
        resolved += 1
        recovered += path.get("entry_recovered") is True
    return recovered, resolved


def _candidate_summary(
    rows: Sequence[tuple[Mapping[str, object], Mapping[str, object]]], width: float
) -> dict[str, object]:
    if not rows:
        return {
            "status": "insufficient_path_evidence",
            "resolved_trades": 0,
            "barrier_crossed": 0,
            "survived": 0,
            "equal_risk_notional_usd": None,
            "equal_risk_gross_pnl_usd": None,
        }
    crossed = 0
    gross = 0.0
    notional = 0.0
    for trade, path in rows:
        risk = float(trade["control_barrier_risk_usd"])
        candidate_notional = risk * 10_000.0 / width
        adverse = float(path["adverse_excursion_bps"])
        candidate_crossed = adverse >= width
        crossed += candidate_crossed
        notional += candidate_notional
        gross += (
            -risk
            if candidate_crossed
            else (
                candidate_notional
                * float(path["directional_close_return_bps"])
                / 10_000.0
            )
        )
    return {
        "status": "resolved_path_sensitivity",
        "resolved_trades": len(rows),
        "barrier_crossed": crossed,
        "survived": len(rows) - crossed,
        "equal_risk_notional_usd": notional,
        "equal_risk_gross_pnl_usd": gross,
    }


def _candidates(
    widths: tuple[float, ...], adverse: float, directional: float
) -> dict[str, object]:
    return {
        _width_key(width): (
            {
                "status": "barrier_crossed",
                "counterfactual_execution_pnl_available": False,
            }
            if adverse >= width
            else {
                "status": "survived_observed_path",
                "directional_close_return_bps": directional,
                "counterfactual_execution_pnl_available": False,
            }
        )
        for width in widths
    }


def _stop_width(side: str, entry: float, stop: float) -> float:
    if side == "long" and stop < entry:
        return (entry - stop) / entry * 10_000.0
    if side == "short" and stop > entry:
        return (stop - entry) / entry * 10_000.0
    raise ValueError("protective stop must be adverse to the trade side")


def _post_stop_horizons(
    value: object, side: str, entry: float, exit_price: float | None
) -> dict[str, object]:
    if value is None or exit_price is None:
        return {}
    paths = mapping(value, "post-exit paths")
    required = _entry_recovery_bps(side, entry, exit_price)
    output: dict[str, object] = {}
    for key, raw in sorted(paths.items(), key=lambda item: int(item[0])):
        path = mapping(raw, f"post-exit path {key}")
        status = text(path.get("status"), f"post-exit path {key} status")
        favorable = _optional_number(
            path.get("favorable_excursion_bps"), "post-exit favorable excursion"
        )
        output[str(key)] = {
            "status": status,
            "entry_recovery_required_bps": required,
            "favorable_excursion_bps": favorable,
            "entry_recovered": status == "resolved"
            and favorable is not None
            and favorable >= required,
        }
    return output


def _entry_recovery_bps(side: str, entry: float, exit_price: float) -> float:
    if side == "long" and exit_price < entry:
        return (entry / exit_price - 1.0) * 10_000.0
    if side == "short" and exit_price > entry:
        return (1.0 - entry / exit_price) * 10_000.0
    raise ValueError("protective-stop exit must be adverse to the trade side")


def _entry_volatility(trade: Record) -> dict[str, float | None]:
    context = _optional_mapping(trade.get("entry_context"), "entry context")
    provider = _optional_mapping(context.get("signal_provider"), "signal provider")
    readiness = _optional_mapping(provider.get("readiness"), "entry readiness")
    metrics = _optional_mapping(readiness.get("metrics"), "entry metrics")
    atr = next(
        (
            _optional_positive(metrics.get(key), f"{key} volatility")
            for key in ("atr_bps", "atr_14_bps", "atr14_bps")
            if metrics.get(key) is not None
        ),
        None,
    )
    return {
        "recent_bar_range_bps": _optional_positive(
            metrics.get("bar_range_bps"), "entry bar range"
        ),
        "atr_bps": atr,
    }


def _optional_mapping(value: object, label: str) -> Record:
    return {} if value is None else mapping(value, label)


def _distance_units(distance: float, volatility: float | None) -> float | None:
    return None if volatility is None else distance / volatility


def _optional_number(value: object, label: str) -> float | None:
    return None if value is None else number(value, label)


def _optional_positive(value: object, label: str) -> float | None:
    return None if value is None else _positive(value, label)


def _width_key(width: float) -> str:
    return f"{width:g}bps"


def _positive(value: object, label: str) -> float:
    parsed = number(value, label)
    if parsed <= 0.0:
        raise ValueError(f"{label} must be positive")
    return parsed


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_strategy_changes": False,
        "runtime_strategy_changed": False,
        "performance_gate": False,
    }


def _limitations() -> list[str]:
    return [
        "completed candles cannot identify an executable intrabar stop fill",
        "survival means only that observed adverse excursion stayed inside the barrier",
        "leverage changes margin return and liquidation headroom, not the configured price-bps stop distance",
        "ATR units remain unavailable when the recorded entry lacks causal ATR telemetry",
        "a post-stop entry recovery is a possible whipsaw, not proof that a wider stop improves net execution",
        "equal-risk gross candidates resize notional but omit counterfactual fees, funding, and slippage",
        "the report cannot change, route, size, or submit an order",
    ]
