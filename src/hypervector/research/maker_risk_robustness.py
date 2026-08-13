"""Cross-block robustness diagnostics for maker-risk replay candidates."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import prod, sqrt

_WILSON_95_Z = 1.959963984540054
_MAX_ADDITIONAL_TRADES = 100_000


@dataclass(frozen=True)
class _BlockEvidence:
    initial_equity: float
    contract: tuple[float, float, float]
    factors: list[float]
    block_pnls: list[float]
    trade_pnls: list[float]
    status_counts: dict[str, int]
    drawdowns: list[float]


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    return float(value)


def _candidate(block: Mapping[str, object], name: str) -> Mapping[str, object]:
    fresh_value = block.get("fresh")
    if fresh_value is None:
        fresh_value = block.get("fresh_20260727")
    fresh = _mapping(fresh_value, "block fresh result")
    candidates = _mapping(fresh.get("candidates"), "block candidates")
    if name not in candidates:
        raise ValueError(f"block is missing candidate: {name}")
    return _mapping(candidates[name], f"candidate {name}")


def _candidate_contract(candidate: Mapping[str, object]) -> tuple[float, float, float]:
    return (
        _number(candidate.get("margin_fraction"), "candidate margin fraction"),
        _number(candidate.get("leverage"), "candidate leverage"),
        _number(candidate.get("target_margin_pct"), "candidate target margin"),
    )


def _trades(replay: Mapping[str, object]) -> list[Mapping[str, object]]:
    value = replay.get("trades")
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("candidate replay trades must be an array")
    return [_mapping(row, "candidate trade") for row in value]


def _wilson_interval(events: int, total: int) -> tuple[float, float]:
    if total <= 0 or events < 0 or events > total:
        raise ValueError("Wilson interval requires 0 <= events <= total")
    proportion = events / total
    z_squared = _WILSON_95_Z**2
    denominator = 1.0 + z_squared / total
    center = proportion + z_squared / (2.0 * total)
    spread = _WILSON_95_Z * sqrt(
        proportion * (1.0 - proportion) / total + z_squared / (4.0 * total**2)
    )
    return (center - spread) / denominator, (center + spread) / denominator


def _additional_zero_loss_trades(
    losses: int,
    total: int,
    break_even_loss_rate: float,
) -> int:
    if break_even_loss_rate <= 0.0:
        raise ValueError("break-even loss rate must be positive")
    if _wilson_interval(losses, total)[1] < break_even_loss_rate:
        return 0
    for additional in range(1, _MAX_ADDITIONAL_TRADES + 1):
        if _wilson_interval(losses, total + additional)[1] < break_even_loss_rate:
            return additional
    raise RuntimeError("loss-rate uncertainty did not converge within the bound")


def _append_trades(
    trades: Sequence[Mapping[str, object]],
    trade_pnls: list[float],
    statuses: Counter[str],
) -> None:
    for trade in trades:
        trade_pnls.append(_number(trade.get("net_pnl"), "trade net PnL"))
        status = trade.get("status")
        if not isinstance(status, str) or not status:
            raise ValueError("candidate trade status must be a non-empty string")
        statuses[status] += 1


def _collect_block_evidence(
    blocks: Sequence[Mapping[str, object]],
    candidate_name: str,
) -> _BlockEvidence:
    factors: list[float] = []
    block_pnls: list[float] = []
    trade_pnls: list[float] = []
    statuses: Counter[str] = Counter()
    drawdowns: list[float] = []
    initial_equity: float | None = None
    contract: tuple[float, float, float] | None = None
    for block in blocks:
        candidate = _candidate(block, candidate_name)
        candidate_contract = _candidate_contract(candidate)
        if contract is None:
            contract = candidate_contract
        elif candidate_contract != contract:
            raise ValueError("candidate contract mismatch across robustness blocks")
        replay = _mapping(candidate.get("replay"), "candidate replay")
        initial = _number(replay.get("initial_equity"), "initial equity")
        final = _number(replay.get("final_equity"), "final equity")
        if initial <= 0.0:
            raise ValueError("initial equity must be positive")
        if initial_equity is None:
            initial_equity = initial
        elif initial != initial_equity:
            raise ValueError("all robustness blocks must use the same initial equity")
        factors.append(final / initial)
        block_pnls.append(final - initial)
        _append_trades(_trades(replay), trade_pnls, statuses)
        drawdowns.append(
            _number(replay.get("maximum_drawdown_pct"), "maximum drawdown")
        )
    if initial_equity is None or contract is None:
        raise RuntimeError("maker risk robustness block evidence is unavailable")
    if not trade_pnls:
        raise ValueError("robustness audit requires completed trade economics")
    return _BlockEvidence(
        initial_equity,
        contract,
        factors,
        block_pnls,
        trade_pnls,
        dict(sorted(statuses.items())),
        drawdowns,
    )


def _trade_statistics(
    trade_pnls: Sequence[float],
    status_counts: Mapping[str, int],
) -> dict[str, object]:
    profits = [pnl for pnl in trade_pnls if pnl > 0.0]
    losses = [-pnl for pnl in trade_pnls if pnl < 0.0]
    gross_profit = sum(profits)
    gross_loss = sum(losses)
    average_win = gross_profit / len(profits) if profits else 0.0
    average_loss = gross_loss / len(losses) if losses else 0.0
    break_even = average_win / (average_win + average_loss)
    loss_interval = _wilson_interval(len(losses), len(trade_pnls))
    return {
        "completed_trade_count": len(trade_pnls),
        "profitable_trade_count": len(profits),
        "losing_trade_count": len(losses),
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "status_counts": dict(status_counts),
        "profit_factor": gross_profit / gross_loss if gross_loss > 0.0 else None,
        "largest_profitable_trade_share": max(profits) / gross_profit,
        "observed_loss_rate": len(losses) / len(trade_pnls),
        "empirical_break_even_loss_rate": break_even,
        "loss_rate_wilson_95_lower": loss_interval[0],
        "loss_rate_wilson_95_upper": loss_interval[1],
        "wilson_interval_assumption": (
            "approximately_independent_stationary_binary_outcomes"
        ),
        "loss_rate_upper_below_break_even": loss_interval[1] < break_even,
        "additional_zero_loss_trades_for_upper_below_break_even": (
            _additional_zero_loss_trades(len(losses), len(trade_pnls), break_even)
        ),
    }


def _leave_one_out_products(evidence: _BlockEvidence) -> list[float]:
    return [
        evidence.initial_equity
        * prod(
            factor for other, factor in enumerate(evidence.factors) if other != index
        )
        for index in range(len(evidence.factors))
    ]


def summarize_candidate_blocks(
    blocks: Sequence[Mapping[str, object]],
    candidate_name: str,
) -> dict[str, object]:
    """Summarize concentration and loss tolerance without stitching data gaps."""
    if not blocks:
        raise ValueError("maker risk robustness requires at least one block")
    evidence = _collect_block_evidence(blocks, candidate_name)
    leave_one_out = _leave_one_out_products(evidence)
    positive_block_pnl = [pnl for pnl in evidence.block_pnls if pnl > 0.0]
    return {
        "candidate": candidate_name,
        "candidate_contract": {
            "margin_fraction": evidence.contract[0],
            "leverage": evidence.contract[1],
            "target_margin_pct": evidence.contract[2],
        },
        "block_count": len(blocks),
        "positive_blocks": sum(pnl > 0.0 for pnl in evidence.block_pnls),
        "aggregate_reset_block_pnl": sum(evidence.block_pnls),
        "largest_profitable_block_share": (
            max(positive_block_pnl) / sum(positive_block_pnl)
            if positive_block_pnl
            else None
        ),
        "worst_block_drawdown_pct": min(evidence.drawdowns),
        "product_ending_equity": evidence.initial_equity * prod(evidence.factors),
        **_trade_statistics(evidence.trade_pnls, evidence.status_counts),
        "leave_one_block_out_product_min": min(leave_one_out),
        "leave_one_block_out_product_max": max(leave_one_out),
        "portfolio_paths_stitched_across_gaps": False,
    }
