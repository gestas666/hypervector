"""Reproduce the live runner's own runtime validation for a profile, offline.

Report-only. execution_authority: none. No credentials, no venue client.

The configuration loader, the read-only preflight and the observe-mode runner all
accept shapes that ``MultiAssetLiveRunner`` refuses at construction through
``validate_runtime`` — for example a ``sizing_overrides`` table on a provider
whose ``execution_symbols`` is empty. On 2026-09-22 that gap cost a 13-minute
armed startup (prestart backup plus full ledger replay) that ended in
``provider entry sizing exceeds executable provider-symbol scope``.

This script builds exactly the arguments ``scripts/multi_asset_bidirectional_live.py``
hands to the runner — using the same ``build_router`` and the same config-derived
mappings — and calls ``validate_runtime`` with placeholder engines, which the
validator inspects only by key. Run it before every armed start.

With ``--equity`` it also runs the book-level config check of the V94 size
ladder (docs/plans/2026-09-24-v94-size-ladder.md): across executable routes at
that equity, the summed maximum at-stop loss must stay within 3% of equity and
the summed posted margin within 25%. It is a configuration validation, not a
trade gate: the live runner never consults it.

Exit codes: 0 accepted, 1 runner objection, 2 loader refusal, 3 book-level
limit exceeded.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
import math
from pathlib import Path
import sys
import tomllib

from hypervector.live.cohort_execution_plan_validation import CohortExecutionPlanError
from hypervector.live.cohort_runtime_preflight import validate_runtime_configuration
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_live_runner_support import (
    MultiAssetLiveRunnerError,
)

BOOK_AT_STOP_RISK_LIMIT = 0.03
BOOK_MARGIN_LIMIT = 0.25
# The declared stop-risk cost allowance every V93 provider uses; applied only to
# a route whose provider declares no stop_risk_budget of its own.
DEFAULT_COST_BUFFER_BPS = 20.0
BPS_PER_UNIT = 10_000.0


def check(config_path: Path, *, mode: str) -> list[str]:
    """Return the runtime validator's objections for one profile, if any."""
    armed = mode == "live"
    config = load_multi_asset_live_config(
        config_path, mode=mode, enabled=armed, accepts_live_risk=armed
    )
    problems: list[str] = []
    try:
        validate_runtime_configuration(config)
    except MultiAssetLiveRunnerError as exc:
        problems.append(str(exc))
    return problems


@dataclass(frozen=True)
class RouteExposure:
    """One executable provider-symbol route's worst case at the stated equity."""

    strategy_id: str
    symbol: str
    leverage: float
    planned_notional_usd: float
    margin_usd: float
    stop_bps: float
    cost_buffer_bps: float
    stop_budget_usd: float | None
    budget_source: str
    at_stop_loss_usd: float


@dataclass(frozen=True)
class BookCheck:
    """Summed worst-case routes, one position per symbol, up to maximum_positions."""

    equity_usd: float
    maximum_positions: int
    routes: tuple[RouteExposure, ...]
    at_stop_loss_usd: float
    margin_usd: float
    problems: tuple[str, ...]


def book_check(config_path: Path, *, equity_usd: float) -> BookCheck:
    """Bound total at-stop risk and margin across the profile's executable routes.

    Reads the TOML directly (tolerant of budget forms the typed loader may not
    know yet) and mirrors the runtime sizing: side-specific, then provider-symbol,
    then asset margin and cap; notional = min(equity x margin_fraction x leverage,
    max_notional_usd). A route's maximum at-stop loss is
    min(effective stop budget, notional x (maximum stop bps incl. clamp + cost
    buffer bps)); its margin is notional / leverage.
    """
    if (
        isinstance(equity_usd, bool)
        or not math.isfinite(equity_usd)
        or equity_usd <= 0.0
    ):
        raise ValueError("book check equity must be finite and positive")
    with config_path.open("rb") as handle:
        profile = tomllib.load(handle)
    assets = {
        str(row["symbol"]): row for row in _tables(profile.get("assets"), "assets")
    }
    routes: list[RouteExposure] = []
    for provider in _tables(profile.get("providers"), "providers"):
        for symbol in provider.get("execution_symbols") or ():
            if symbol not in assets:
                raise ValueError(f"executable route {symbol} has no asset table")
            routes.append(_route(provider, str(symbol), assets[symbol], equity_usd))
    worst_loss: dict[str, float] = {}
    worst_margin: dict[str, float] = {}
    for route in routes:
        # Isolated one-way margin: at most one position per symbol at a time.
        worst_loss[route.symbol] = max(
            worst_loss.get(route.symbol, 0.0), route.at_stop_loss_usd
        )
        worst_margin[route.symbol] = max(
            worst_margin.get(route.symbol, 0.0), route.margin_usd
        )
    maximum_positions = int(profile.get("maximum_positions", len(worst_loss)))
    loss = sum(sorted(worst_loss.values(), reverse=True)[:maximum_positions])
    margin = sum(sorted(worst_margin.values(), reverse=True)[:maximum_positions])
    problems: list[str] = []
    if loss > BOOK_AT_STOP_RISK_LIMIT * equity_usd:
        problems.append(
            f"book at-stop risk ${loss:,.2f} ({loss / equity_usd:.2%} of "
            f"${equity_usd:,.2f}) exceeds {BOOK_AT_STOP_RISK_LIMIT:.2%} of equity"
        )
    if margin > BOOK_MARGIN_LIMIT * equity_usd:
        problems.append(
            f"book margin ${margin:,.2f} ({margin / equity_usd:.2%} of "
            f"${equity_usd:,.2f}) exceeds {BOOK_MARGIN_LIMIT:.2%} of equity"
        )
    return BookCheck(
        equity_usd,
        maximum_positions,
        tuple(routes),
        loss,
        margin,
        tuple(problems),
    )


def _tables(value: object, label: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list) or not all(
        isinstance(row, Mapping) for row in value
    ):
        raise ValueError(f"profile {label} must be an array of tables")
    return value


def _route(
    provider: Mapping[str, object],
    symbol: str,
    asset: Mapping[str, object],
    equity_usd: float,
) -> RouteExposure:
    execution = provider.get("execution")
    execution = execution if isinstance(execution, Mapping) else {}
    leverage = _positive(asset.get("leverage"), f"{symbol} leverage")
    notional = max(
        _planned_notional(provider, symbol, side, asset, equity_usd, leverage)
        for side in _sides(provider, symbol)
    )
    stop_bps = _maximum_stop_bps(execution, provider, symbol, asset)
    budget, buffer, source = _stop_budget(execution, equity_usd)
    modeled = notional * (stop_bps + buffer) / BPS_PER_UNIT
    return RouteExposure(
        strategy_id=str(provider.get("strategy_id")),
        symbol=symbol,
        leverage=leverage,
        planned_notional_usd=notional,
        margin_usd=notional / leverage,
        stop_bps=stop_bps,
        cost_buffer_bps=buffer,
        stop_budget_usd=budget,
        budget_source=source,
        at_stop_loss_usd=modeled if budget is None else min(budget, modeled),
    )


def _sides(provider: Mapping[str, object], symbol: str) -> tuple[str, ...]:
    overrides = provider.get("execution_side_overrides")
    sides = (
        overrides.get(symbol)
        if isinstance(overrides, Mapping) and symbol in overrides
        else provider.get("sides")
    )
    if not isinstance(sides, list) or not sides:
        return ("long", "short")
    return tuple(str(side) for side in sides)


def _planned_notional(
    provider: Mapping[str, object],
    symbol: str,
    side: str,
    asset: Mapping[str, object],
    equity_usd: float,
    leverage: float,
) -> float:
    directional = provider.get("directional_sizing_overrides")
    by_symbol = directional.get(symbol) if isinstance(directional, Mapping) else None
    sided = by_symbol.get(side) if isinstance(by_symbol, Mapping) else None
    symbol_sizing = provider.get("sizing_overrides")
    override = symbol_sizing.get(symbol) if isinstance(symbol_sizing, Mapping) else None
    # Same precedence as StrategyProviderConfig.entry_sizing, then the asset.
    policy: Mapping[str, object] = (
        sided
        if isinstance(sided, Mapping)
        else override
        if isinstance(override, Mapping)
        else asset
    )
    fraction = _positive(policy.get("margin_fraction"), f"{symbol} margin_fraction")
    cap = _positive(policy.get("max_notional_usd"), f"{symbol} max_notional_usd")
    return min(equity_usd * fraction * leverage, cap)


def _maximum_stop_bps(
    execution: Mapping[str, object],
    provider: Mapping[str, object],
    symbol: str,
    asset: Mapping[str, object],
) -> float:
    policy = execution.get("stop_policy")
    if policy == "structural_clamped_bps":
        return _positive(
            execution.get("maximum_stop_bps"), f"{symbol} maximum_stop_bps"
        )
    overrides = provider.get("stop_bps_overrides")
    if isinstance(overrides, Mapping) and symbol in overrides:
        return _positive(overrides[symbol], f"{symbol} stop_bps override")
    if policy == "fixed_bps":
        return _positive(execution.get("stop_bps"), f"{symbol} provider stop_bps")
    return _positive(asset.get("stop_bps"), f"{symbol} asset stop_bps")


def _stop_budget(
    execution: Mapping[str, object], equity_usd: float
) -> tuple[float | None, float, str]:
    """Return (effective budget, cost buffer, source) as the runtime prices it.

    ``maximum_loss_fraction_of_equity`` (V94) is read tolerantly beside the
    legacy ``maximum_loss_usd``; when both are declared the smaller applies,
    matching ``StopRiskBudget.effective_maximum_loss_usd``.
    """
    raw = execution.get("stop_risk_budget")
    if not isinstance(raw, Mapping):
        return None, DEFAULT_COST_BUFFER_BPS, "none"
    buffer = raw.get("cost_buffer_bps", DEFAULT_COST_BUFFER_BPS)
    buffer = _nonnegative(buffer, "stop_risk_budget cost_buffer_bps")
    candidates: list[tuple[float, str]] = []
    if raw.get("maximum_loss_usd") is not None:
        candidates.append(
            (_positive(raw["maximum_loss_usd"], "maximum_loss_usd"), "maximum_loss_usd")
        )
    if raw.get("maximum_loss_fraction_of_equity") is not None:
        fraction = _positive(
            raw["maximum_loss_fraction_of_equity"], "maximum_loss_fraction_of_equity"
        )
        candidates.append((fraction * equity_usd, "maximum_loss_fraction_of_equity"))
    if not candidates:
        return None, buffer, "none"
    budget, source = min(candidates)
    return budget, buffer, source


def _positive(value: object, label: str) -> float:
    number = _nonnegative(value, label)
    if number <= 0.0:
        raise ValueError(f"{label} must be positive")
    return number


def _nonnegative(value: object, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(f"{label} must be a finite nonnegative number")
    return float(value)


def format_book_table(result: BookCheck) -> str:
    """Render the per-route table and book totals for the operator."""
    equity = result.equity_usd
    lines = [
        f"book-level check at equity ${equity:,.2f} "
        f"(limits: at-stop risk {BOOK_AT_STOP_RISK_LIMIT:.0%}, "
        f"margin {BOOK_MARGIN_LIMIT:.0%}; maximum_positions "
        f"{result.maximum_positions})",
        f"{'route':<52} {'symbol':<13} {'lev':>4} {'notional':>9} {'margin':>8} "
        f"{'stop+buf':>9} {'budget':>8} {'at-stop':>8} {'%eq':>6}",
    ]
    for route in result.routes:
        budget = (
            "-" if route.stop_budget_usd is None else f"{route.stop_budget_usd:.2f}"
        )
        lines.append(
            f"{route.strategy_id:<52} {route.symbol:<13} {route.leverage:>4.0f} "
            f"{route.planned_notional_usd:>9.2f} {route.margin_usd:>8.2f} "
            f"{route.stop_bps + route.cost_buffer_bps:>7.0f}bp {budget:>8} "
            f"{route.at_stop_loss_usd:>8.2f} {route.at_stop_loss_usd / equity:>6.2%}"
        )
    lines.append(
        f"book at-stop risk ${result.at_stop_loss_usd:,.2f} "
        f"({result.at_stop_loss_usd / equity:.2%}); book margin "
        f"${result.margin_usd:,.2f} ({result.margin_usd / equity:.2%})"
    )
    return "\n".join(lines)


def main() -> int:
    """Exit 0 only when the runner would accept the profile."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--mode", choices=("observe", "live"), default="live")
    parser.add_argument(
        "--equity",
        type=float,
        help="account equity in USD for the book-level at-stop risk and margin check",
    )
    args = parser.parse_args()
    try:
        problems = check(args.config, mode=args.mode)
        book = (
            book_check(args.config, equity_usd=args.equity)
            if args.equity is not None and not problems
            else None
        )
    except (
        MultiAssetLiveConfigError,
        CohortExecutionPlanError,
        FileNotFoundError,
        ValueError,
    ) as exc:
        # Exit 1 is reserved for collected runner objections. Every loader refusal
        # reports 2, exactly as the armed entrypoint does, so an operator can tell
        # "this profile is unloadable" from "the runner would refuse it".
        print(f"loader refused: {exc}", file=sys.stderr)
        return 2
    if problems:
        for problem in problems:
            print(f"runtime validator would refuse: {problem}", file=sys.stderr)
        return 1
    print(f"runtime validator accepts {args.config} in {args.mode} mode")
    if book is None:
        return 0
    print(format_book_table(book))
    for problem in book.problems:
        print(f"book-level check would refuse: {problem}", file=sys.stderr)
    return 3 if book.problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
