"""Report-only protective-stop recovery sensitivity."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_live_audit_values import mapping, number, text

Record = Mapping[str, object]


def build_stop_recovery_sensitivity(
    trades: Sequence[Record], *, stop_widths_bps: Sequence[float]
) -> dict[str, object]:
    """Build a non-executable protective-stop recovery sensitivity report."""
    widths = _validated_widths(stop_widths_bps)
    observations = [
        _trade_observation(trade, widths)
        for trade in trades
        if trade.get("exit_reason") == "protective_stop"
    ]
    return {
        "schema_version": 1,
        "mode": "cohort_protective_stop_recovery_sensitivity_v1",
        "contract": _contract(),
        "stop_widths_bps": list(widths),
        "summary": {"protective_stop_trades": len(observations)},
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


def _trade_observation(trade: Record, widths: tuple[float, ...]) -> dict[str, object]:
    entry = mapping(trade.get("entry"), "stop sensitivity entry")
    stop = mapping(trade.get("protective_stop"), "stop sensitivity stop")
    entry_price = _positive(entry.get("price"), "entry price")
    stop_price = _positive(stop.get("trigger_price"), "stop price")
    side = text(trade.get("side"), "stop sensitivity side")
    paths = mapping(trade.get("entry_followthrough_path"), "followthrough paths")
    return {
        "lifecycle_id": text(trade.get("lifecycle_id"), "lifecycle identity"),
        "source_run_id": text(trade.get("source_run_id"), "source run identity"),
        "source_profile_fingerprint": text(
            trade.get("source_profile_fingerprint"), "source profile fingerprint"
        ),
        "strategy_id": text(trade.get("strategy_id"), "strategy identity"),
        "symbol": text(trade.get("symbol"), "trade symbol"),
        "side": side,
        "actual_stop_width_bps": _stop_width(side, entry_price, stop_price),
        "horizons": _horizons(paths, widths),
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
        output[str(key)] = {
            "status": status,
            "adverse_excursion_bps": adverse,
            "candidates": _candidates(widths, adverse, directional),
        }
    return output


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
        "candidate results omit counterfactual fees, funding, slippage, and resized risk",
        "the report cannot change, route, size, or submit an order",
    ]
