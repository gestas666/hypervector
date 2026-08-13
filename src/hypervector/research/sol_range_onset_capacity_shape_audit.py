"""Paired evidence audit for the SOL 60-versus-80-bps stop comparison."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math
from pathlib import Path
from typing import Mapping, Sequence, cast

from hypervector.data.oxa_storage import file_evidence

_SEGMENTS = ("development", "validation", "pseudo_holdout", "continuous")
_DIRECTIONS = ("long", "short")
_INITIAL_EQUITY_USD = 15_000.0


@dataclass(frozen=True)
class _Trade:
    direction: str
    entry_time_ms: int
    exit_time_ms: int
    exit_reason: str
    net_pnl_usd: float


@dataclass(frozen=True)
class _Replay:
    initial_equity_usd: float
    final_equity_usd: float
    fees_usd: float
    funding_usd: float
    liquidations: int
    realized_drawdown_pct: float
    trades: tuple[_Trade, ...]


@dataclass(frozen=True)
class _Block:
    source_path: Path
    shape_path: Path
    start: datetime
    end: datetime
    sixty: _Replay
    eighty: _Replay


def audit_capacity_shape_pairs(
    pairs: Sequence[tuple[Path, Path]],
    *,
    expected_trades: int,
) -> dict[str, object]:
    """Bind exact 60-bps controls and aggregate paired 60/80-bps blocks."""
    _validate_request(pairs, expected_trades)
    blocks = tuple(sorted((_load_pair(*pair) for pair in pairs), key=lambda x: x.start))
    _validate_blocks(blocks, expected_trades)
    return {
        "schema_version": 1,
        "mode": "sol_range_onset_capacity_shape_paired_audit",
        "execution_authority": "none",
        "model_authority": "none",
        "runtime_strategy_changed": False,
        "control_match": True,
        "entry_population_match": True,
        "artifact_pair_count": len(blocks),
        "paired_changed_exits": _changed_exits(blocks),
        "stops": {
            "60": _aggregate(blocks, stop_bps=60.0),
            "80": _aggregate(blocks, stop_bps=80.0),
        },
        "blocks": [_block_summary(block) for block in blocks],
        "source_evidence": [_pair_evidence(block) for block in blocks],
        "limitations": [
            "the SOL range-onset rule was discovered after inspecting later data",
            "paired blocks are disjoint but do not constitute a randomized sample",
            "public-trade stop crossings can differ from venue mark-price triggers",
            "visible L2 depth can disappear before a live IOC reaches the venue",
        ],
    }


def _validate_request(
    pairs: Sequence[tuple[Path, Path]],
    expected_trades: int,
) -> None:
    if not pairs or len(set(pairs)) != len(pairs):
        raise ValueError("capacity-shape pairs must be non-empty and unique")
    paths = [path for pair in pairs for path in pair]
    if len(set(paths)) != len(paths):
        raise ValueError("capacity-shape artifact paths must be unique")
    if isinstance(expected_trades, bool) or expected_trades <= 0:
        raise ValueError("expected_trades must be a positive integer")


def _load_pair(source_path: Path, shape_path: Path) -> _Block:
    source = _read_mapping(source_path)
    shape = _read_mapping(shape_path)
    _validate_header(source, source_path, "capacity")
    _validate_header(shape, shape_path, "capacity-shape")
    continuous: tuple[Mapping[str, object], Mapping[str, object]] | None = None
    for name in _SEGMENTS:
        selected = _validate_segment(source, shape, source_path, shape_path, name)
        if name == "continuous":
            continuous = selected
    if continuous is None:
        raise ValueError("capacity-shape continuous segment is missing")
    source_segment = _mapping(source.get("continuous"), "continuous")
    start = _timestamp(source_segment.get("start_utc"), "continuous start")
    end = _timestamp(source_segment.get("end_utc"), "continuous end")
    sixty = _parse_replay(continuous[0], source_path)
    eighty = _parse_replay(continuous[1], shape_path)
    _validate_entry_population(sixty, eighty, shape_path)
    return _Block(source_path, shape_path, start, end, sixty, eighty)


def _validate_header(
    payload: Mapping[str, object],
    path: Path,
    expected_surface: str,
) -> None:
    expected = {
        "symbol": "SOL",
        "execution_authority": "none",
        "model_authority": "none",
        "trial_surface": expected_surface,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError(f"capacity-shape artifact header differs: {path}")


def _validate_segment(
    source: Mapping[str, object],
    shape: Mapping[str, object],
    source_path: Path,
    shape_path: Path,
    name: str,
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    source_segment = _mapping(source.get(name), f"source {name}")
    shape_segment = _mapping(shape.get(name), f"shape {name}")
    for key in ("start_utc", "end_utc", "signal_events", "funding_events"):
        if source_segment.get(key) != shape_segment.get(key):
            raise ValueError(f"capacity-shape {name} boundary differs: {shape_path}")
    source_sixty = _select_replay(source_segment, 60.0, source_path)
    shape_sixty = _select_replay(shape_segment, 60.0, shape_path)
    if source_sixty != shape_sixty:
        raise ValueError(f"60-bps control differs in {name}: {shape_path}")
    return shape_sixty, _select_replay(shape_segment, 80.0, shape_path)


def _select_replay(
    segment: Mapping[str, object],
    stop_bps: float,
    path: Path,
) -> Mapping[str, object]:
    trial_id = f"stop={stop_bps:g}__exposure=0.15"
    trials = [
        _mapping(value, "trial") for value in _sequence(segment.get("trials"), "trials")
    ]
    matching = [trial for trial in trials if trial.get("trial_id") == trial_id]
    if len(matching) != 1:
        raise ValueError(f"capacity-shape requires one {trial_id} trial: {path}")
    trial = matching[0]
    config = _mapping(trial.get("trial"), "trial config")
    expected = {"stop_bps": stop_bps, "margin_fraction": 0.03, "leverage": 5.0}
    if any(
        not math.isclose(_number(config, key), value) for key, value in expected.items()
    ):
        raise ValueError(f"capacity-shape trial identity differs: {path}")
    if not math.isclose(_number(trial, "effective_exposure"), 0.15):
        raise ValueError(f"capacity-shape exposure differs: {path}")
    return _mapping(trial.get("event_replay"), "event replay")


def _parse_replay(values: Mapping[str, object], path: Path) -> _Replay:
    if values.get("status") != "complete" or values.get("failure") is not None:
        raise ValueError(f"capacity-shape replay is incomplete: {path}")
    rows = _sequence(values.get("trades"), "trades")
    declared = _integer(values, "completed_trades")
    if declared != len(rows):
        raise ValueError(f"capacity-shape trade count differs: {path}")
    trades = tuple(_parse_trade(_mapping(row, "trade"), path) for row in rows)
    wins = sum(trade.net_pnl_usd > 0.0 for trade in trades)
    losses = sum(trade.net_pnl_usd < 0.0 for trade in trades)
    if _integer(values, "wins") != wins or _integer(values, "losses") != losses:
        raise ValueError(f"capacity-shape win/loss count differs: {path}")
    drawdown = _nullable_number(values, "realized_maximum_drawdown_pct")
    return _Replay(
        _positive_number(values, "initial_equity"),
        _positive_number(values, "final_equity"),
        _finite_number(values, "total_fees_usd"),
        _finite_number(values, "funding_cashflow_usd"),
        _integer(values, "liquidations"),
        0.0 if drawdown is None else drawdown,
        trades,
    )


def _parse_trade(values: Mapping[str, object], path: Path) -> _Trade:
    direction = values.get("direction")
    reason = values.get("exit_reason")
    if direction not in _DIRECTIONS or not isinstance(reason, str) or not reason:
        raise ValueError(f"capacity-shape trade identity is invalid: {path}")
    if reason == "end_of_data":
        raise ValueError(f"capacity-shape replay contains end_of_data trade: {path}")
    return _Trade(
        str(direction),
        _integer(values, "entry_decision_time_ms"),
        _integer(values, "exit_event_time_ms"),
        reason,
        _finite_number(values, "net_pnl_usd"),
    )


def _validate_entry_population(sixty: _Replay, eighty: _Replay, path: Path) -> None:
    sixty_entries = [(trade.entry_time_ms, trade.direction) for trade in sixty.trades]
    eighty_entries = [(trade.entry_time_ms, trade.direction) for trade in eighty.trades]
    if sixty_entries != eighty_entries:
        raise ValueError(f"capacity-shape entry population differs: {path}")


def _validate_blocks(blocks: tuple[_Block, ...], expected_trades: int) -> None:
    if sum(len(block.sixty.trades) for block in blocks) != expected_trades:
        found = sum(len(block.sixty.trades) for block in blocks)
        raise ValueError(f"expected {expected_trades} trades, found {found}")
    for block in blocks:
        if block.end <= block.start:
            raise ValueError("capacity-shape block end must follow start")
        for replay in (block.sixty, block.eighty):
            if not math.isclose(replay.initial_equity_usd, _INITIAL_EQUITY_USD):
                raise ValueError("capacity-shape blocks require equal reset equity")
    for previous, current in zip(blocks, blocks[1:], strict=False):
        if current.start < previous.end:
            raise ValueError("capacity-shape artifact windows overlap")


def _aggregate(blocks: tuple[_Block, ...], *, stop_bps: float) -> dict[str, object]:
    replays = [_replay_for_stop(block, stop_bps) for block in blocks]
    trades = [trade for replay in replays for trade in replay.trades]
    profits = [trade.net_pnl_usd for trade in trades if trade.net_pnl_usd > 0.0]
    losses = [-trade.net_pnl_usd for trade in trades if trade.net_pnl_usd < 0.0]
    gross_profit, gross_loss = sum(profits), sum(losses)
    largest_winner = max(profits, default=0.0)
    product = _product_equity(replays)
    leave_one_out = [
        _product_equity(replays[:index] + replays[index + 1 :])
        for index in range(len(replays))
    ]
    return {
        "stop_bps": stop_bps,
        "trades": len(trades),
        "wins": len(profits),
        "losses": len(losses),
        "reset_block_net_pnl_usd": sum(
            replay.final_equity_usd - replay.initial_equity_usd for replay in replays
        ),
        "gross_profit_usd": gross_profit,
        "gross_loss_usd": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "largest_winner_usd": largest_winner,
        "largest_winner_gross_profit_share": (
            largest_winner / gross_profit if gross_profit else None
        ),
        "net_pnl_without_largest_winner_usd": gross_profit
        - gross_loss
        - largest_winner,
        "product_equity_usd": product,
        "product_return_pct": (product / _INITIAL_EQUITY_USD - 1.0) * 100.0,
        "positive_blocks": sum(
            replay.final_equity_usd > replay.initial_equity_usd for replay in replays
        ),
        "total_fees_usd": sum(replay.fees_usd for replay in replays),
        "funding_cashflow_usd": sum(replay.funding_usd for replay in replays),
        "liquidations": sum(replay.liquidations for replay in replays),
        "worst_block_realized_drawdown_pct": min(
            replay.realized_drawdown_pct for replay in replays
        ),
        "leave_one_block_out_min_net_pnl_usd": min(
            value - _INITIAL_EQUITY_USD for value in leave_one_out
        ),
        "directions": {
            direction: _direction_metrics(trades, direction)
            for direction in _DIRECTIONS
        },
    }


def _replay_for_stop(block: _Block, stop_bps: float) -> _Replay:
    return block.sixty if math.isclose(stop_bps, 60.0) else block.eighty


def _product_equity(replays: Sequence[_Replay]) -> float:
    return _INITIAL_EQUITY_USD * math.prod(
        replay.final_equity_usd / replay.initial_equity_usd for replay in replays
    )


def _direction_metrics(trades: Sequence[_Trade], direction: str) -> dict[str, object]:
    selected = [trade for trade in trades if trade.direction == direction]
    profits = [trade.net_pnl_usd for trade in selected if trade.net_pnl_usd > 0.0]
    losses = [-trade.net_pnl_usd for trade in selected if trade.net_pnl_usd < 0.0]
    return {
        "trades": len(selected),
        "wins": len(profits),
        "losses": len(losses),
        "net_pnl_usd": sum(trade.net_pnl_usd for trade in selected),
        "profit_factor": sum(profits) / sum(losses) if losses else None,
    }


def _changed_exits(blocks: tuple[_Block, ...]) -> int:
    return sum(
        (left.exit_time_ms, left.exit_reason) != (right.exit_time_ms, right.exit_reason)
        for block in blocks
        for left, right in zip(block.sixty.trades, block.eighty.trades, strict=True)
    )


def _block_summary(block: _Block) -> dict[str, object]:
    return {
        "start_utc": block.start.isoformat(),
        "end_utc": block.end.isoformat(),
        "trades": len(block.sixty.trades),
        "stop_60_final_equity_usd": block.sixty.final_equity_usd,
        "stop_80_final_equity_usd": block.eighty.final_equity_usd,
    }


def _pair_evidence(block: _Block) -> dict[str, object]:
    return {
        "source": {"path": str(block.source_path), **file_evidence(block.source_path)},
        "shape": {"path": str(block.shape_path), **file_evidence(block.shape_path)},
    }


def _read_mapping(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid capacity-shape artifact: {path}") from exc
    return _mapping(value, "artifact")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"capacity-shape {label} must be an object")
    return cast(dict[str, object], value)


def _sequence(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"capacity-shape {label} must be a list")
    return value


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"capacity-shape {label} must be an ISO timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"capacity-shape {label} must be timezone-aware")
    return parsed.astimezone(UTC)


def _integer(values: Mapping[str, object], key: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"capacity-shape {key} must be a non-negative integer")
    return value


def _number(values: Mapping[str, object], key: str) -> float:
    return _finite_number(values, key)


def _positive_number(values: Mapping[str, object], key: str) -> float:
    number = _finite_number(values, key)
    if number <= 0.0:
        raise ValueError(f"capacity-shape {key} must be positive")
    return number


def _nullable_number(values: Mapping[str, object], key: str) -> float | None:
    return None if values.get(key) is None else _finite_number(values, key)


def _finite_number(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"capacity-shape {key} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"capacity-shape {key} must be finite")
    return number
