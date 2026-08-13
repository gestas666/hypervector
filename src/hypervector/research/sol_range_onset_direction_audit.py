"""Direction and block-stability audit for resolved SOL range-onset replays."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math
from pathlib import Path
from typing import Mapping, Sequence, cast

from hypervector.data.oxa_storage import file_evidence

_EXPOSURE = 0.15
_LEVERAGE = 5.0
_MARGIN_FRACTION = 0.03
_STOP_BPS = 60.0
_DIRECTIONS = ("long", "short")


@dataclass(frozen=True)
class _Trade:
    direction: str
    net_pnl_usd: float


@dataclass(frozen=True)
class _Block:
    path: Path
    start: datetime
    end: datetime
    initial_equity_usd: float
    final_equity_usd: float
    trades: tuple[_Trade, ...]


def audit_sol_range_onset_directions(
    paths: Sequence[Path],
    *,
    expected_trades: int,
) -> dict[str, object]:
    """Audit exact 0.15x/60-bps resolved blocks without changing strategy."""
    if not paths or len(set(paths)) != len(paths):
        raise ValueError("direction audit paths must be non-empty and unique")
    if isinstance(expected_trades, bool) or expected_trades <= 0:
        raise ValueError("expected_trades must be a positive integer")
    blocks = tuple(sorted((_load_block(path) for path in paths), key=lambda x: x.start))
    _validate_block_sequence(blocks)
    trades = tuple(trade for block in blocks for trade in block.trades)
    if len(trades) != expected_trades:
        raise ValueError(f"expected {expected_trades} trades, found {len(trades)}")
    initial = blocks[0].initial_equity_usd
    return {
        "schema_version": 1,
        "mode": "sol_range_onset_direction_stability_audit",
        "execution_authority": "none",
        "model_authority": "none",
        "runtime_strategy_changed": False,
        "trial_identity": _trial_identity(),
        "artifact_count": len(blocks),
        "trade_count": len(trades),
        "reset_block_net_pnl_usd": sum(trade.net_pnl_usd for trade in trades),
        "product_equity_usd": _product_equity(blocks, initial),
        "directions": {
            direction: _direction_metrics(direction, blocks)
            for direction in _DIRECTIONS
        },
        "blocks": [_block_summary(block) for block in blocks],
        "source_evidence": [
            {"path": str(block.path), **file_evidence(block.path)} for block in blocks
        ],
    }


def _load_block(path: Path) -> _Block:
    payload = _read_mapping(path)
    if payload.get("execution_authority") != "none":
        raise ValueError(f"SOL direction artifact has execution authority: {path}")
    if payload.get("model_authority") != "none":
        raise ValueError(f"SOL direction artifact has model authority: {path}")
    continuous = _mapping(payload.get("continuous"), "continuous")
    start = _timestamp(continuous.get("start_utc"), "start_utc")
    end = _timestamp(continuous.get("end_utc"), "end_utc")
    if end <= start:
        raise ValueError(f"SOL direction artifact end must follow start: {path}")
    trial = _select_trial(continuous, path)
    replay = _mapping(trial.get("event_replay"), "event_replay")
    trades = _validated_trades(replay, path)
    initial = _positive_number(replay, "initial_equity")
    final = _positive_number(replay, "final_equity")
    return _Block(path, start, end, initial, final, trades)


def _select_trial(continuous: Mapping[str, object], path: Path) -> Mapping[str, object]:
    trials = _sequence(continuous.get("trials"), "continuous trials")
    matching = [
        _mapping(value, "trial")
        for value in trials
        if math.isclose(
            _number(_mapping(value, "trial"), "effective_exposure"),
            _EXPOSURE,
        )
    ]
    if len(matching) != 1:
        raise ValueError(f"SOL direction artifact requires one 0.15x trial: {path}")
    trial = matching[0]
    config = _mapping(trial.get("trial"), "trial config")
    expected = {
        "leverage": _LEVERAGE,
        "margin_fraction": _MARGIN_FRACTION,
        "stop_bps": _STOP_BPS,
    }
    if any(
        not math.isclose(_number(config, key), value) for key, value in expected.items()
    ):
        raise ValueError(f"SOL direction artifact trial identity changed: {path}")
    return trial


def _validated_trades(
    replay: Mapping[str, object],
    path: Path,
) -> tuple[_Trade, ...]:
    if replay.get("status") != "complete" or replay.get("failure") is not None:
        raise ValueError(f"SOL direction artifact replay is not complete: {path}")
    values = _sequence(replay.get("trades"), "event replay trades")
    declared = replay.get("completed_trades")
    if (
        isinstance(declared, bool)
        or not isinstance(declared, int)
        or declared != len(values)
    ):
        raise ValueError(f"SOL direction artifact trade count differs: {path}")
    trades: list[_Trade] = []
    for value in values:
        row = _mapping(value, "trade")
        direction = row.get("direction")
        if direction not in _DIRECTIONS:
            raise ValueError(f"SOL direction artifact has invalid trade side: {path}")
        if row.get("exit_reason") == "end_of_data":
            raise ValueError(
                f"SOL direction artifact contains end_of_data trade: {path}"
            )
        trades.append(_Trade(str(direction), _finite_number(row, "net_pnl_usd")))
    return tuple(trades)


def _validate_block_sequence(blocks: tuple[_Block, ...]) -> None:
    initial = blocks[0].initial_equity_usd
    for block in blocks:
        if not math.isclose(block.initial_equity_usd, initial):
            raise ValueError("SOL direction blocks require equal reset equity")
    for previous, current in zip(blocks, blocks[1:], strict=False):
        if current.start < previous.end:
            raise ValueError("SOL direction artifact windows overlap")


def _direction_metrics(direction: str, blocks: tuple[_Block, ...]) -> dict[str, object]:
    trades = [
        trade
        for block in blocks
        for trade in block.trades
        if trade.direction == direction
    ]
    profits = sorted(
        (trade.net_pnl_usd for trade in trades if trade.net_pnl_usd > 0.0), reverse=True
    )
    losses = [-trade.net_pnl_usd for trade in trades if trade.net_pnl_usd < 0.0]
    block_pnl = [_side_block_pnl(block, direction) for block in blocks]
    active_pnl = [pnl for pnl, count in block_pnl if count > 0]
    leave_one_out = [_side_pnl_without(block, blocks, direction) for block in blocks]
    gross_profit = sum(profits)
    gross_loss = sum(losses)
    return {
        "trades": len(trades),
        "wins": len(profits),
        "losses": len(losses),
        "net_pnl_usd": sum(trade.net_pnl_usd for trade in trades),
        "gross_profit_usd": gross_profit,
        "gross_loss_usd": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "blocks_with_trades": len(active_pnl),
        "positive_blocks": sum(pnl > 0.0 for pnl in active_pnl),
        "negative_blocks": sum(pnl < 0.0 for pnl in active_pnl),
        "leave_one_block_out_min_net_pnl_usd": min(leave_one_out),
        "leave_one_block_out_all_positive": all(pnl > 0.0 for pnl in leave_one_out),
        "top_1_winner_gross_profit_share": _winner_share(profits, 1),
        "top_3_winner_gross_profit_share": _winner_share(profits, 3),
    }


def _side_block_pnl(block: _Block, direction: str) -> tuple[float, int]:
    trades = [trade for trade in block.trades if trade.direction == direction]
    return sum(trade.net_pnl_usd for trade in trades), len(trades)


def _side_pnl_without(
    removed: _Block, blocks: tuple[_Block, ...], direction: str
) -> float:
    return sum(
        trade.net_pnl_usd
        for block in blocks
        if block is not removed
        for trade in block.trades
        if trade.direction == direction
    )


def _winner_share(profits: list[float], count: int) -> float | None:
    total = sum(profits)
    return sum(profits[:count]) / total if total else None


def _product_equity(blocks: tuple[_Block, ...], initial: float) -> float:
    multiplier = math.prod(block.final_equity_usd / initial for block in blocks)
    return initial * multiplier


def _block_summary(block: _Block) -> dict[str, object]:
    return {
        "path": str(block.path),
        "start_utc": block.start.isoformat(),
        "end_utc": block.end.isoformat(),
        "trades": len(block.trades),
        "long_net_pnl_usd": _side_block_pnl(block, "long")[0],
        "short_net_pnl_usd": _side_block_pnl(block, "short")[0],
        "final_equity_usd": block.final_equity_usd,
    }


def _trial_identity() -> dict[str, float]:
    return {
        "effective_exposure": _EXPOSURE,
        "leverage": _LEVERAGE,
        "margin_fraction": _MARGIN_FRACTION,
        "stop_bps": _STOP_BPS,
    }


def _read_mapping(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid SOL direction artifact: {path}") from exc
    return _mapping(value, "artifact")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"SOL direction {label} must be an object")
    return cast(dict[str, object], value)


def _sequence(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"SOL direction {label} must be a list")
    return value


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"SOL direction {label} must be an ISO timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"SOL direction {label} must be timezone-aware")
    return parsed.astimezone(UTC)


def _number(values: Mapping[str, object], key: str) -> float:
    return _finite_number(values, key)


def _positive_number(values: Mapping[str, object], key: str) -> float:
    number = _finite_number(values, key)
    if number <= 0.0:
        raise ValueError(f"SOL direction {key} must be positive")
    return number


def _finite_number(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"SOL direction {key} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"SOL direction {key} must be finite")
    return number
