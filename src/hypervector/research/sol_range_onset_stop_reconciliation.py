"""Cross-era reconciliation for paired SOL stop-distance evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import product
import json
import math
from pathlib import Path
from typing import Mapping, Sequence, cast

from hypervector.data.oxa_storage import file_evidence

_INITIAL_EQUITY_USD = 15_000.0
_STOP_KEYS = ("60", "80")
_BACKWARD_MODE = "sol_range_onset_backward_exact_audit"
_LATER_MODE = "sol_range_onset_capacity_shape_paired_audit"


@dataclass(frozen=True)
class _Stop:
    trades: int
    wins: int
    losses: int
    gross_profit_usd: float
    gross_loss_usd: float
    fees_usd: float
    funding_usd: float
    liquidations: int
    worst_drawdown_pct: float


@dataclass(frozen=True)
class _Block:
    start: datetime
    end: datetime
    trades: int
    final_60_usd: float
    final_80_usd: float


@dataclass(frozen=True)
class _Audit:
    path: Path
    mode: str
    mark_status: str
    stops: Mapping[str, _Stop]
    blocks: tuple[_Block, ...]


def reconcile_stop_audits(backward_path: Path, later_path: Path) -> dict[str, object]:
    """Combine two disjoint paired stop audits without granting authority."""
    backward = _load_audit(backward_path, expected_mode=_BACKWARD_MODE)
    later = _load_audit(later_path, expected_mode=_LATER_MODE)
    blocks = tuple(
        sorted(backward.blocks + later.blocks, key=lambda block: block.start)
    )
    _validate_chronology(blocks)
    stops = {key: _aggregate((backward, later), blocks, key) for key in _STOP_KEYS}
    comparison = _paired_comparison(blocks)
    leader = _leader(stops)
    mark_status = _combined_mark_status((backward, later))
    return {
        "schema_version": 1,
        "mode": "sol_range_onset_cross_era_stop_reconciliation",
        "execution_authority": "none",
        "model_authority": "none",
        "runtime_strategy_changed": False,
        "entry_population_match": True,
        "trade_count": sum(block.trades for block in blocks),
        "block_count": len(blocks),
        "aggregate_leader_bps": leader,
        "mark_trigger_evidence": mark_status,
        "stops": stops,
        "paired_block_comparison": comparison,
        "recommendation": _recommendation(leader, mark_status, comparison),
        "eras": [_audit_summary(audit) for audit in (backward, later)],
        "limitations": _limitations(mark_status),
    }


def _load_audit(path: Path, *, expected_mode: str) -> _Audit:
    values = _read_mapping(path)
    _validate_header(values, path, expected_mode)
    stops = _mapping(values.get("stops"), "stops")
    if tuple(sorted(stops)) != _STOP_KEYS:
        raise ValueError(f"stop audit must contain exactly 60 and 80 bps: {path}")
    parsed_stops = {
        key: _parse_stop(_mapping(stops[key], key), path) for key in _STOP_KEYS
    }
    blocks = tuple(
        _parse_block(value, path) for value in _sequence(values.get("blocks"), "blocks")
    )
    _validate_report_totals(parsed_stops, blocks, path)
    return _Audit(
        path, expected_mode, _mark_status(values, expected_mode), parsed_stops, blocks
    )


def _validate_header(values: Mapping[str, object], path: Path, mode: str) -> None:
    expected = {
        "mode": mode,
        "execution_authority": "none",
        "model_authority": "none",
        "runtime_strategy_changed": False,
    }
    if any(values.get(key) != value for key, value in expected.items()):
        raise ValueError(f"stop audit header differs: {path}")
    if mode == _LATER_MODE:
        if (
            values.get("control_match") is not True
            or values.get("entry_population_match") is not True
        ):
            raise ValueError(f"later stop audit is not a paired control: {path}")
    else:
        surfaces = _mapping(values.get("surfaces"), "backward surfaces")
        public = _mapping(surfaces.get("public_trade"), "public-trade surface")
        if public.get("status") != "complete":
            raise ValueError(f"backward public-trade stop audit is incomplete: {path}")


def _parse_stop(values: Mapping[str, object], path: Path) -> _Stop:
    stop = _Stop(
        trades=_integer(values, "trades"),
        wins=_integer(values, "wins"),
        losses=_integer(values, "losses"),
        gross_profit_usd=_nonnegative(values, "gross_profit_usd"),
        gross_loss_usd=_nonnegative(values, "gross_loss_usd"),
        fees_usd=_nonnegative(values, "total_fees_usd"),
        funding_usd=_finite(values, "funding_cashflow_usd"),
        liquidations=_integer(values, "liquidations"),
        worst_drawdown_pct=_finite(values, "worst_block_realized_drawdown_pct"),
    )
    if stop.trades != stop.wins + stop.losses:
        raise ValueError(f"stop audit win/loss total differs: {path}")
    return stop


def _parse_block(value: object, path: Path) -> _Block:
    values = _mapping(value, "block")
    block = _Block(
        start=_timestamp(values.get("start_utc"), "block start"),
        end=_timestamp(values.get("end_utc"), "block end"),
        trades=_integer(values, "trades"),
        final_60_usd=_positive(values, "stop_60_final_equity_usd"),
        final_80_usd=_positive(values, "stop_80_final_equity_usd"),
    )
    if block.end <= block.start:
        raise ValueError(f"stop audit block end must follow start: {path}")
    return block


def _validate_report_totals(
    stops: Mapping[str, _Stop],
    blocks: Sequence[_Block],
    path: Path,
) -> None:
    if not blocks:
        raise ValueError(f"stop audit blocks must be non-empty: {path}")
    trade_count = sum(block.trades for block in blocks)
    if any(stop.trades != trade_count for stop in stops.values()):
        raise ValueError(f"stop audit trade count differs from blocks: {path}")


def _validate_chronology(blocks: Sequence[_Block]) -> None:
    for previous, current in zip(blocks, blocks[1:], strict=False):
        if current.start < previous.end:
            raise ValueError("cross-era stop audit windows overlap")


def _aggregate(
    audits: Sequence[_Audit],
    blocks: Sequence[_Block],
    stop_key: str,
) -> dict[str, object]:
    stop_values = [audit.stops[stop_key] for audit in audits]
    finals = [_block_final(block, stop_key) for block in blocks]
    gross_profit = sum(stop.gross_profit_usd for stop in stop_values)
    gross_loss = sum(stop.gross_loss_usd for stop in stop_values)
    product_equity = _INITIAL_EQUITY_USD * math.prod(
        final / _INITIAL_EQUITY_USD for final in finals
    )
    leave_one_out = [_product_without(finals, index) for index in range(len(finals))]
    return {
        "stop_bps": float(stop_key),
        "trades": sum(stop.trades for stop in stop_values),
        "wins": sum(stop.wins for stop in stop_values),
        "losses": sum(stop.losses for stop in stop_values),
        "reset_block_net_pnl_usd": sum(final - _INITIAL_EQUITY_USD for final in finals),
        "gross_profit_usd": gross_profit,
        "gross_loss_usd": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "product_equity_usd": product_equity,
        "product_return_pct": (product_equity / _INITIAL_EQUITY_USD - 1.0) * 100.0,
        "positive_blocks": sum(final > _INITIAL_EQUITY_USD for final in finals),
        "total_fees_usd": sum(stop.fees_usd for stop in stop_values),
        "funding_cashflow_usd": sum(stop.funding_usd for stop in stop_values),
        "public_trade_liquidations": sum(stop.liquidations for stop in stop_values),
        "worst_block_realized_drawdown_pct": min(
            stop.worst_drawdown_pct for stop in stop_values
        ),
        "leave_one_block_out_min_product_pnl_usd": min(
            value - _INITIAL_EQUITY_USD for value in leave_one_out
        ),
    }


def _product_without(finals: Sequence[float], omitted: int) -> float:
    included = (final for index, final in enumerate(finals) if index != omitted)
    return _INITIAL_EQUITY_USD * math.prod(
        final / _INITIAL_EQUITY_USD for final in included
    )


def _block_final(block: _Block, stop_key: str) -> float:
    return block.final_60_usd if stop_key == "60" else block.final_80_usd


def _paired_comparison(blocks: Sequence[_Block]) -> dict[str, object]:
    deltas = [
        (block.final_80_usd - block.final_60_usd) / _INITIAL_EQUITY_USD * 100.0
        for block in blocks
    ]
    nonzero = [delta for delta in deltas if not math.isclose(delta, 0.0, abs_tol=1e-15)]
    return {
        "metric": "stop_80_minus_stop_60_reset_block_return_percentage_points",
        "mean_delta_percentage_points": sum(deltas) / len(deltas),
        "blocks_favoring_60": sum(delta < 0.0 for delta in deltas),
        "blocks_favoring_80": sum(delta > 0.0 for delta in deltas),
        "ties": len(deltas) - len(nonzero),
        "exact_sign_flip_p_value_two_sided": _sign_flip_p_value(nonzero),
    }


def _sign_flip_p_value(deltas: Sequence[float]) -> float | None:
    if not deltas:
        return None
    if len(deltas) > 20:
        raise ValueError("exact sign-flip audit supports at most 20 nonzero blocks")
    observed = abs(sum(deltas))
    tolerance = 1e-15
    extreme = sum(
        abs(sum(sign * delta for sign, delta in zip(signs, deltas, strict=True)))
        + tolerance
        >= observed
        for signs in product((-1.0, 1.0), repeat=len(deltas))
    )
    return extreme / (2 ** len(deltas))


def _leader(stops: Mapping[str, Mapping[str, object]]) -> float | None:
    sixty = _finite(stops["60"], "product_equity_usd")
    eighty = _finite(stops["80"], "product_equity_usd")
    if math.isclose(sixty, eighty):
        return None
    return 60.0 if sixty > eighty else 80.0


def _recommendation(
    leader: float | None,
    mark_status: str,
    comparison: Mapping[str, object],
) -> dict[str, object]:
    p_value = comparison.get("exact_sign_flip_p_value_two_sided")
    confidence = (
        "medium"
        if mark_status == "complete" and isinstance(p_value, float) and p_value <= 0.1
        else "low"
    )
    return {
        "forward_stop_bps": leader,
        "action": "retain aggregate leader for forward observation"
        if leader is not None
        else "keep both as challengers",
        "confidence": confidence,
        "falsifying_evidence": [
            "fresh venue-mark stops or liquidations materially exceed replay",
            "the non-leading stop has higher net performance after comparable forward trades",
            "entry timing or fill impact breaks the paired replay identity",
        ],
    }


def _mark_status(values: Mapping[str, object], mode: str) -> str:
    if mode != _BACKWARD_MODE:
        return "unverified"
    surfaces = _mapping(values.get("surfaces"), "backward surfaces")
    mark = _mapping(surfaces.get("sampled_mark"), "sampled-mark surface")
    status = mark.get("status")
    return status if isinstance(status, str) else "unverified"


def _combined_mark_status(audits: Sequence[_Audit]) -> str:
    statuses = {audit.mark_status for audit in audits}
    if "censored" in statuses:
        return "censored"
    return "complete" if statuses == {"complete"} else "unverified"


def _audit_summary(audit: _Audit) -> dict[str, object]:
    return {
        "mode": audit.mode,
        "mark_status": audit.mark_status,
        "block_count": len(audit.blocks),
        "trade_count": sum(block.trades for block in audit.blocks),
        "evidence": {"path": str(audit.path), **file_evidence(audit.path)},
    }


def _limitations(mark_status: str) -> list[str]:
    return [
        "the SOL range-onset rule was discovered after inspecting the later era",
        "paired chronological blocks are not a randomized sample",
        f"venue mark-price stop evidence is {mark_status}",
        "public-trade stop crossings and visible L2 fills can differ from live execution",
        "a stop-distance comparison does not independently validate the entry edge",
    ]


def _read_mapping(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid stop audit artifact: {path}") from exc
    return _mapping(value, "artifact")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"stop reconciliation {label} must be an object")
    return cast(dict[str, object], value)


def _sequence(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"stop reconciliation {label} must be a list")
    return value


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"stop reconciliation {label} must be an ISO timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"stop reconciliation {label} must include a timezone")
    return parsed.astimezone(UTC)


def _integer(values: Mapping[str, object], key: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"stop reconciliation {key} must be a non-negative integer")
    return value


def _positive(values: Mapping[str, object], key: str) -> float:
    value = _finite(values, key)
    if value <= 0.0:
        raise ValueError(f"stop reconciliation {key} must be positive")
    return value


def _nonnegative(values: Mapping[str, object], key: str) -> float:
    value = _finite(values, key)
    if value < 0.0:
        raise ValueError(f"stop reconciliation {key} must be non-negative")
    return value


def _finite(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"stop reconciliation {key} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"stop reconciliation {key} must be finite")
    return number
