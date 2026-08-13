"""Pooled diagnostics for the post-hoc SOL fixed-target exit surface."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math
from pathlib import Path
from typing import Mapping, Sequence, cast

from hypervector.data.oxa_storage import file_evidence

_TARGETS = (None, 25.0, 40.0, 60.0, 80.0, 120.0)
_DIRECTIONS = ("long", "short")
_SURFACE = "v49-target-exit-posthoc"


@dataclass(frozen=True)
class TargetExitTrade:
    """One immutable completed target-surface lifecycle."""

    direction: str
    entry_time_ms: int
    exit_time_ms: int
    exit_reason: str
    net_pnl_usd: float


@dataclass(frozen=True)
class TargetExitReplay:
    """One target's complete replay inside one independent block."""

    target_bps: float | None
    initial_equity_usd: float
    final_equity_usd: float
    fees_usd: float
    funding_usd: float
    drawdown_pct: float
    liquidations: int
    trades: tuple[TargetExitTrade, ...]


@dataclass(frozen=True)
class TargetExitBlock:
    """One non-overlapping source artifact and its target trials."""

    path: Path
    start: datetime
    end: datetime
    replays: tuple[TargetExitReplay, ...]


def audit_target_exit_blocks(
    paths: Sequence[Path],
    *,
    expected_trades: int,
) -> dict[str, object]:
    """Validate and pool paired target trials without granting authority."""
    _validate_request(paths, expected_trades)
    blocks = tuple(sorted((_load_block(path) for path in paths), key=lambda x: x.start))
    _validate_blocks(blocks, expected_trades)
    return {
        "schema_version": 1,
        "mode": "sol_range_onset_v49_target_exit_audit",
        "execution_authority": "none",
        "model_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_promotion": False,
        "posthoc_surface": True,
        "paired_entry_population": True,
        "targets": {
            _target_key(target): _aggregate(blocks, target) for target in _TARGETS
        },
        "blocks": [_block_summary(block) for block in blocks],
        "source_evidence": [
            {"path": str(block.path), **file_evidence(block.path)} for block in blocks
        ],
        "interpretation": _interpretation(),
        "limitations": _limitations(),
    }


def _validate_request(paths: Sequence[Path], expected_trades: int) -> None:
    if not paths or len(set(paths)) != len(paths):
        raise ValueError("target-exit artifact paths must be non-empty and unique")
    if isinstance(expected_trades, bool) or expected_trades <= 0:
        raise ValueError("expected_trades must be a positive integer")


def _load_block(path: Path) -> TargetExitBlock:
    payload = _read_mapping(path)
    expected = {
        "symbol": "SOL",
        "execution_authority": "none",
        "model_authority": "none",
        "trial_surface": _SURFACE,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError(f"target-exit artifact identity differs: {path}")
    continuous = _mapping(payload.get("continuous"), "continuous")
    replays = tuple(
        _parse_trial(_mapping(row, "trial"), path)
        for row in _sequence(continuous.get("trials"), "trials")
    )
    _validate_trial_set(replays, path)
    _validate_paired_entries(replays, path)
    return TargetExitBlock(
        path,
        _timestamp(continuous.get("start_utc"), "start"),
        _timestamp(continuous.get("end_utc"), "end"),
        replays,
    )


def _parse_trial(row: Mapping[str, object], path: Path) -> TargetExitReplay:
    config = _mapping(row.get("trial"), "trial config")
    target = _optional_number(config.get("target_bps"), "target_bps")
    _validate_config(config, target, path)
    replay = _mapping(row.get("event_replay"), "event replay")
    if replay.get("status") != "complete" or replay.get("failure") is not None:
        raise ValueError(f"target-exit replay is incomplete: {path}")
    trades = tuple(
        _parse_trade(_mapping(value, "trade"), path)
        for value in _sequence(replay.get("trades"), "trades")
    )
    _validate_counts(replay, trades, path)
    drawdown = _optional_number(replay.get("realized_maximum_drawdown_pct"), "drawdown")
    return TargetExitReplay(
        target,
        _positive_number(replay.get("initial_equity"), "initial equity"),
        _positive_number(replay.get("final_equity"), "final equity"),
        _number(replay.get("total_fees_usd"), "fees"),
        _number(replay.get("funding_cashflow_usd"), "funding"),
        0.0 if drawdown is None else drawdown,
        _integer(replay.get("liquidations"), "liquidations"),
        trades,
    )


def _validate_config(
    config: Mapping[str, object], target: float | None, path: Path
) -> None:
    expected = {
        "stop_bps": 80.0,
        "margin_fraction": 0.15,
        "leverage": 5.0,
        "initial_equity": 5_000.0,
        "taker_fee_rate": 0.000432,
    }
    if any(
        not math.isclose(_number(config.get(key), key), value)
        for key, value in expected.items()
    ):
        raise ValueError(f"target-exit replay config differs: {path}")
    if target not in _TARGETS:
        raise ValueError(f"target-exit trial target differs: {path}")


def _parse_trade(row: Mapping[str, object], path: Path) -> TargetExitTrade:
    direction = row.get("direction")
    reason = row.get("exit_reason")
    if direction not in _DIRECTIONS or not isinstance(reason, str) or not reason:
        raise ValueError(f"target-exit trade identity is invalid: {path}")
    if reason == "end_of_data":
        raise ValueError(f"target-exit replay contains end_of_data trade: {path}")
    return TargetExitTrade(
        str(direction),
        _integer(row.get("entry_decision_time_ms"), "entry time"),
        _integer(row.get("exit_event_time_ms"), "exit time"),
        reason,
        _number(row.get("net_pnl_usd"), "net PnL"),
    )


def _validate_counts(
    replay: Mapping[str, object],
    trades: tuple[TargetExitTrade, ...],
    path: Path,
) -> None:
    wins = sum(trade.net_pnl_usd > 0.0 for trade in trades)
    losses = sum(trade.net_pnl_usd < 0.0 for trade in trades)
    declared = (
        _integer(replay.get("completed_trades"), "completed trades"),
        _integer(replay.get("wins"), "wins"),
        _integer(replay.get("losses"), "losses"),
    )
    if declared != (len(trades), wins, losses):
        raise ValueError(f"target-exit replay counts differ: {path}")


def _validate_trial_set(replays: tuple[TargetExitReplay, ...], path: Path) -> None:
    targets = tuple(replay.target_bps for replay in replays)
    if len(replays) != len(_TARGETS) or set(targets) != set(_TARGETS):
        raise ValueError(f"target-exit trial set differs: {path}")


def _validate_paired_entries(replays: tuple[TargetExitReplay, ...], path: Path) -> None:
    populations = {
        tuple((trade.entry_time_ms, trade.direction) for trade in replay.trades)
        for replay in replays
    }
    if len(populations) != 1:
        raise ValueError(f"target-exit entry population differs: {path}")


def _validate_blocks(blocks: tuple[TargetExitBlock, ...], expected_trades: int) -> None:
    control_trades = sum(len(_select(block, None).trades) for block in blocks)
    if control_trades != expected_trades:
        raise ValueError(f"expected {expected_trades} trades, found {control_trades}")
    for block in blocks:
        if block.end <= block.start:
            raise ValueError("target-exit block end must follow start")
    for previous, current in zip(blocks, blocks[1:], strict=False):
        if current.start < previous.end:
            raise ValueError("target-exit artifact windows overlap")


def _aggregate(
    blocks: tuple[TargetExitBlock, ...], target: float | None
) -> dict[str, object]:
    replays = tuple(_select(block, target) for block in blocks)
    trades = tuple(trade for replay in replays for trade in replay.trades)
    profits = tuple(trade.net_pnl_usd for trade in trades if trade.net_pnl_usd > 0.0)
    losses = tuple(-trade.net_pnl_usd for trade in trades if trade.net_pnl_usd < 0.0)
    largest = max(profits, default=0.0)
    return {
        "target_bps": target,
        "trades": len(trades),
        "wins": len(profits),
        "losses": len(losses),
        "positive_blocks": sum(
            replay.final_equity_usd > replay.initial_equity_usd for replay in replays
        ),
        "pooled_reset_net_usd": sum(
            replay.final_equity_usd - replay.initial_equity_usd for replay in replays
        ),
        "gross_profit_usd": sum(profits),
        "gross_loss_usd": sum(losses),
        "profit_factor": sum(profits) / sum(losses) if losses else None,
        "largest_winner_usd": largest,
        "net_excluding_largest_winner_usd": sum(profits) - sum(losses) - largest,
        "worst_block_drawdown_pct": min(replay.drawdown_pct for replay in replays),
        "fees_usd": sum(replay.fees_usd for replay in replays),
        "funding_usd": sum(replay.funding_usd for replay in replays),
        "liquidations": sum(replay.liquidations for replay in replays),
        "directions": {
            direction: _direction_metrics(trades, direction)
            for direction in _DIRECTIONS
        },
        "exit_reasons": _exit_reason_counts(trades),
    }


def _direction_metrics(
    trades: Sequence[TargetExitTrade], direction: str
) -> dict[str, object]:
    selected = tuple(trade for trade in trades if trade.direction == direction)
    profits = tuple(trade.net_pnl_usd for trade in selected if trade.net_pnl_usd > 0.0)
    losses = tuple(-trade.net_pnl_usd for trade in selected if trade.net_pnl_usd < 0.0)
    largest = max(profits, default=0.0)
    return {
        "trades": len(selected),
        "wins": len(profits),
        "losses": len(losses),
        "net_pnl_usd": sum(profits) - sum(losses),
        "profit_factor": sum(profits) / sum(losses) if losses else None,
        "net_excluding_largest_winner_usd": sum(profits) - sum(losses) - largest,
    }


def _exit_reason_counts(trades: Sequence[TargetExitTrade]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for trade in trades:
        counts[trade.exit_reason] = counts.get(trade.exit_reason, 0) + 1
    return dict(sorted(counts.items()))


def _select(block: TargetExitBlock, target: float | None) -> TargetExitReplay:
    selected = [replay for replay in block.replays if replay.target_bps == target]
    if len(selected) != 1:
        raise ValueError(f"target-exit block has invalid target {target}")
    return selected[0]


def _target_key(target: float | None) -> str:
    return "native" if target is None else f"{target:g}"


def _block_summary(block: TargetExitBlock) -> dict[str, object]:
    return {
        "path": str(block.path),
        "start_utc": block.start.isoformat(),
        "end_utc": block.end.isoformat(),
        "targets": {
            _target_key(replay.target_bps): replay.final_equity_usd
            - replay.initial_equity_usd
            for replay in block.replays
        },
    }


def _interpretation() -> dict[str, object]:
    return {
        "selection_authority": "none",
        "runtime_recommendation": "retain_native_pending_forward_exit_challenger",
        "diagnostic_lead_target_bps": 60.0,
        "reason": (
            "60 bps is the only fixed target with positive pooled and "
            "largest-winner-removed PnL; side and block breadth remain unresolved"
        ),
    }


def _limitations() -> list[str]:
    return [
        "the target surface was declared after inspecting live giveback",
        "four disjoint blocks are not an untouched randomized holdout",
        "the same SOL signal population remains serial within each reset block",
        "public trades approximate executable target crossings",
        "visible L2 depth can disappear before a live IOC reaches the venue",
        "diagnostic results do not authorize or automatically change live execution",
    ]


def _read_mapping(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid target-exit artifact: {path}") from exc
    return _mapping(value, "artifact")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"target-exit {label} must be an object")
    return cast(dict[str, object], value)


def _sequence(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"target-exit {label} must be a list")
    return value


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"target-exit {label} must be an ISO timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"target-exit {label} must be timezone-aware")
    return parsed.astimezone(UTC)


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"target-exit {label} must be a non-negative integer")
    return value


def _optional_number(value: object, label: str) -> float | None:
    return None if value is None else _number(value, label)


def _positive_number(value: object, label: str) -> float:
    number = _number(value, label)
    if number <= 0.0:
        raise ValueError(f"target-exit {label} must be positive")
    return number


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"target-exit {label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"target-exit {label} must be finite")
    return number
