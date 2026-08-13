"""Three-arm evidence comparison for the HIP-3 early-adverse exit policy."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from hypervector.research.hip3_deployed_lifecycle import (
    Hip3DeployedLifecycleCell,
    Hip3DeployedLifecycleSpec,
)
from hypervector.research.shared_portfolio_models import SharedPortfolioTrade

_POLICIES = ("ignore", "honor", "early_adverse")
_PHASES = ("development", "validation")
_FRICTIONS = ("nominal", "stress")


@dataclass(frozen=True)
class Hip3ExitPolicyArm:
    """One frozen lifecycle specification and its complete result cells."""

    spec: Hip3DeployedLifecycleSpec
    cells: tuple[Hip3DeployedLifecycleCell, ...]


def build_exit_policy_comparison(
    arms: Mapping[str, Hip3ExitPolicyArm],
) -> dict[str, object]:
    """Compare fixed ignore, honor-all, and early-adverse lifecycle arms."""
    _validate_arms(arms)
    results = {
        phase: {
            friction: {
                policy: _cell_group_summary(
                    _select_cells(arms[policy].cells, phase, friction)
                )
                for policy in _POLICIES
            }
            for friction in _FRICTIONS
        }
        for phase in _PHASES
    }
    return {
        "policies": list(_POLICIES),
        "policy_contracts": {
            policy: _policy_contract(arms[policy].spec) for policy in _POLICIES
        },
        "results": results,
        "deltas_vs_ignore": _deltas(results),
        "execution_authority": "none",
        "automatic_promotion": False,
    }


def _validate_arms(arms: Mapping[str, Hip3ExitPolicyArm]) -> None:
    if set(arms) != set(_POLICIES):
        raise ValueError("HIP-3 comparison requires exactly three exit policies")
    coverage: set[tuple[str, str, str]] | None = None
    for policy in _POLICIES:
        arm = arms[policy]
        if arm.spec.signal_exit_policy != policy:
            raise ValueError(f"HIP-3 {policy} policy identity does not match its spec")
        keys = {(cell.phase, cell.friction, cell.symbol) for cell in arm.cells}
        if len(keys) != len(arm.cells):
            raise ValueError(f"HIP-3 {policy} contains duplicate result cells")
        _validate_coverage_shape(keys)
        if coverage is not None and keys != coverage:
            raise ValueError("HIP-3 exit arms require identical cell coverage")
        coverage = keys


def _validate_coverage_shape(keys: set[tuple[str, str, str]]) -> None:
    symbols = {symbol for _, _, symbol in keys}
    if not symbols:
        raise ValueError("HIP-3 exit arms require at least one symbol")
    expected = {
        (phase, friction, symbol)
        for phase in _PHASES
        for friction in _FRICTIONS
        for symbol in symbols
    }
    if keys != expected:
        raise ValueError("HIP-3 exit arms require identical cell coverage")


def _select_cells(
    cells: Sequence[Hip3DeployedLifecycleCell],
    phase: str,
    friction: str,
) -> tuple[Hip3DeployedLifecycleCell, ...]:
    return tuple(
        cell for cell in cells if cell.phase == phase and cell.friction == friction
    )


def _cell_group_summary(
    cells: Sequence[Hip3DeployedLifecycleCell],
) -> dict[str, object]:
    trades = tuple(trade for cell in cells for trade in cell.report.trades)
    aggregate = _trade_summary(trades)
    aggregate.update(
        {
            "worst_independent_asset_drawdown_pct": min(
                cell.report.maximum_drawdown_pct for cell in cells
            ),
            "liquidations": sum(cell.report.liquidations for cell in cells),
            "forced_end_exits": sum(cell.report.forced_end_exits for cell in cells),
        }
    )
    return {
        "aggregate": aggregate,
        "by_symbol": {
            cell.symbol: {
                **_trade_summary(cell.report.trades),
                "maximum_drawdown_pct": cell.report.maximum_drawdown_pct,
            }
            for cell in sorted(cells, key=lambda item: item.symbol)
        },
        "by_direction": {
            direction: _trade_summary(
                tuple(trade for trade in trades if trade.direction == direction)
            )
            for direction in ("long", "short")
        },
    }


def _trade_summary(trades: Sequence[SharedPortfolioTrade]) -> dict[str, object]:
    pnl = [trade.net_pnl_usd for trade in trades]
    gross_profit = sum(max(value, 0.0) for value in pnl)
    gross_loss = -sum(min(value, 0.0) for value in pnl)
    exits = Counter(trade.exit_reason for trade in trades)
    largest = max((value for value in pnl if value > 0.0), default=0.0)
    return {
        "completed_trades": len(trades),
        "wins": sum(value > 0.0 for value in pnl),
        "losses": sum(value < 0.0 for value in pnl),
        "net_pnl_usd": sum(pnl),
        "gross_profit_usd": gross_profit,
        "gross_loss_usd": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "net_pnl_ex_largest_winner_usd": sum(pnl) - largest,
        "fees_usd": sum(trade.fees_usd for trade in trades),
        "funding_cashflow_usd": sum(trade.funding_cashflow_usd for trade in trades),
        "signal_exits": exits["signal"],
        "stop_exits": exits["stop"],
        "maximum_hold_exits": exits["max_hold"],
        "opposite_signal_exits": exits["opposite_signal"],
        "exit_reasons": dict(sorted(exits.items())),
    }


def _policy_contract(spec: Hip3DeployedLifecycleSpec) -> dict[str, object]:
    conditional = spec.signal_exit_policy == "early_adverse"
    return {
        "policy": spec.signal_exit_policy,
        "max_age_bars": spec.early_exit_max_bars if conditional else None,
        "max_mfe_bps": spec.early_exit_max_mfe_bps if conditional else None,
        "min_adverse_bps": spec.early_exit_min_adverse_bps if conditional else None,
        "stop_bps": spec.stop_bps,
        "maximum_hold_seconds": spec.maximum_hold_seconds,
    }


def _deltas(results: Mapping[str, object]) -> dict[str, object]:
    return {
        phase: {
            friction: _cell_deltas(
                _result_cell(results, phase, friction, "ignore"),
                {
                    policy: _result_cell(results, phase, friction, policy)
                    for policy in ("honor", "early_adverse")
                },
            )
            for friction in _FRICTIONS
        }
        for phase in _PHASES
    }


def _result_cell(
    results: Mapping[str, object],
    phase: str,
    friction: str,
    policy: str,
) -> Mapping[str, object]:
    phase_rows = results[phase]
    if not isinstance(phase_rows, Mapping):
        raise TypeError("HIP-3 comparison phase result must be a mapping")
    friction_rows = phase_rows[friction]
    if not isinstance(friction_rows, Mapping):
        raise TypeError("HIP-3 comparison friction result must be a mapping")
    row = friction_rows[policy]
    if not isinstance(row, Mapping):
        raise TypeError("HIP-3 comparison policy result must be a mapping")
    aggregate = row["aggregate"]
    if not isinstance(aggregate, Mapping):
        raise TypeError("HIP-3 comparison aggregate must be a mapping")
    return aggregate


def _cell_deltas(
    baseline: Mapping[str, object],
    candidates: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    fields = (
        "completed_trades",
        "net_pnl_usd",
        "net_pnl_ex_largest_winner_usd",
        "fees_usd",
        "funding_cashflow_usd",
        "signal_exits",
        "worst_independent_asset_drawdown_pct",
    )
    return {
        policy: {
            field: _number(candidate[field]) - _number(baseline[field])
            for field in fields
        }
        for policy, candidate in candidates.items()
    }


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("HIP-3 delta input must be numeric")
    return float(value)
