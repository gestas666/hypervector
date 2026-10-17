"""Reproduce the live runner's own runtime validation for a profile, offline.

Report-only. execution_authority: none. No credentials, no venue client.

The configuration loader, the read-only preflight and the observe-mode runner all
accept shapes that ``MultiAssetLiveRunner`` refuses at construction through
``validate_runtime`` — for example a ``sizing_overrides`` table on a provider
whose ``execution_symbols`` is empty. On 2026-09-22 that gap cost a 13-minute
armed startup (prestart backup plus full ledger replay) that ended in
``provider entry sizing exceeds executable provider-symbol scope``.

This tool builds exactly the arguments ``scripts/multi_asset_bidirectional_live.py``
hands to the runner — using the same ``build_router`` and the same config-derived
mappings — and calls ``validate_runtime`` with placeholder engines, which the
validator inspects only by key. Run it before every armed start.

In live mode it also refuses two shapes the loader and the runner both accept
but the armed start cannot survive. The kill switch and the cohort ledger must
be the paths the supervisor watches (``SupervisorPaths``), with ``stop_file`` as
STOP beside the ledger; otherwise an operator stop or a stale heartbeat goes
unseen. And every provider must resolve the default collector the armed
entrypoint builds, so a mistyped ``strategy_id`` is refused here rather than
after the pre-arm checks pass. Collector construction reads no venue data.

Live mode also refuses a route whose stop could sit beyond its liquidation
price. The armed start tolerates any venue maximum leverage at or above a
market's requested leverage (``ceil(leverage)``); a lower maximum raises the
maintenance margin and pulls liquidation toward the entry. Every executable
route's widest stop plus its cost buffer must stay inside the isolated
liquidation distance at that lowest tolerated maximum, so no venue change the
start accepts can leave a stop that never fires.

With ``--equity`` it also runs the book-level config check of the V94 size
ladder (docs/plans/2026-09-24-v94-size-ladder.md): across executable routes at
that equity, the summed maximum at-stop loss must stay within 3% of equity and
the summed posted margin within 25%. It is a configuration validation, not a
trade gate: the live runner never consults it.

Exit codes: 0 accepted, 1 runner objection, 2 loader, live-path, collector or
stop-beyond-liquidation refusal, 3 book-level limit exceeded.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import sys
import tomllib

from hypervector_supervision.cohort_supervisor_models import (
    REPOSITORY_ROOT,
    SupervisorPaths,
)

from hypervector.live.cohort_execution_plan_validation import CohortExecutionPlanError
from hypervector.live.cohort_runtime_preflight import validate_runtime_configuration
from hypervector.live.multi_asset_default_collectors import build_default_collector
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_live_runner_support import (
    MultiAssetLiveRunnerError,
)
from hypervector.live.multi_asset_market_bars import MultiAssetIntentPollerError

BOOK_AT_STOP_RISK_LIMIT = 0.03
BOOK_MARGIN_LIMIT = 0.25
# The declared stop-risk cost allowance every V93 provider uses; applied only to
# a route whose provider declares no stop_risk_budget of its own.
DEFAULT_COST_BUFFER_BPS = 20.0
BPS_PER_UNIT = 10_000.0
# The armed entrypoint's default, "../backtest-lab/backtest_lab" relative to the
# repository root the supervisor runs it from; anchored there, not to this cwd.
DEFAULT_BACKTEST_LAB = REPOSITORY_ROOT.parent / "backtest-lab" / "backtest_lab"
# Hyperliquid's maintenance margin is half the initial margin at the venue's
# maximum leverage.
MAINTENANCE_MARGIN_SHARE = 0.5


def check(
    config_path: Path,
    *,
    mode: str,
    backtest_lab_root: Path = DEFAULT_BACKTEST_LAB,
) -> list[str]:
    """Return the runtime validator's objections for one profile, if any.

    In live mode a profile whose paths the supervisor does not watch, whose
    provider has no default collector, or whose stop could sit beyond its
    liquidation price raises instead: those are refusals.
    """
    armed = mode == "live"
    config = load_multi_asset_live_config(
        config_path, mode=mode, enabled=armed, accepts_live_risk=armed
    )
    if armed:
        require_supervised_paths(config)
        require_default_collectors(config, backtest_lab_root.resolve())
        require_stops_inside_liquidation(config_path)
    problems: list[str] = []
    try:
        validate_runtime_configuration(config)
    except MultiAssetLiveRunnerError as exc:
        problems.append(str(exc))
    return problems


def require_supervised_paths(
    config: MultiAssetLiveConfig, paths: SupervisorPaths | None = None
) -> None:
    """Refuse a live profile whose kill switch or ledger the supervisor does not watch.

    The backend runs from the repository root, so relative profile paths are
    compared as the supervisor's absolute ones there.
    """
    supervised = paths if paths is not None else SupervisorPaths()
    stop_file = _repository_path(config.stop_file)
    ledger = _repository_path(config.cohort_ledger)
    problems: list[str] = []
    if stop_file != ledger.parent / "STOP":
        problems.append(
            f"stop_file {config.stop_file} is not STOP beside cohort_ledger "
            f"{config.cohort_ledger}"
        )
    if stop_file != supervised.stop_file:
        problems.append(
            f"stop_file {stop_file} is not the supervisor's {supervised.stop_file}"
        )
    if ledger != supervised.ledger:
        problems.append(
            f"cohort_ledger {ledger} is not the supervisor's {supervised.ledger}"
        )
    if problems:
        raise MultiAssetLiveConfigError("; ".join(problems))


def require_default_collectors(
    config: MultiAssetLiveConfig, backtest_lab_root: Path
) -> None:
    """Build every provider's collector exactly as the armed entrypoint does.

    The armed start builds one for every provider, executable or not, and a
    strategy_id without one is refused there. Construction fetches nothing.
    """
    for provider in config.providers:
        build_default_collector(provider, config, backtest_lab_root)


def _repository_path(path: Path) -> Path:
    return path if path.is_absolute() else REPOSITORY_ROOT / path


def isolated_liquidation_distance_bps(
    leverage: float, venue_max_leverage: int
) -> float:
    """Return the nearer (short-side) isolated liquidation distance from entry.

    Hyperliquid liquidates an isolated position once its margin, 1/leverage of
    the entry notional, falls to the maintenance margin at the venue maximum.
    The distance grows with the venue maximum.
    """
    maintenance = MAINTENANCE_MARGIN_SHARE / venue_max_leverage
    return (1.0 / leverage - maintenance) / (1.0 + maintenance) * BPS_PER_UNIT


def liquidation_problems(config_path: Path) -> list[str]:
    """Name each executable route whose stop could sit beyond its liquidation.

    Each route is checked at the lowest venue maximum the armed start tolerates,
    ``ceil(leverage)``. Funding accrued while a position is open is not modeled.
    """
    with config_path.open("rb") as handle:
        profile = tomllib.load(handle)
    assets = {
        str(row["symbol"]): row for row in _tables(profile.get("assets"), "assets")
    }
    problems: list[str] = []
    for provider in _tables(profile.get("providers"), "providers"):
        execution = provider.get("execution")
        execution = execution if isinstance(execution, Mapping) else {}
        for symbol in provider.get("execution_symbols") or ():
            if symbol not in assets:
                raise ValueError(f"executable route {symbol} has no asset table")
            asset = assets[symbol]
            leverage = _positive(asset.get("leverage"), f"{symbol} leverage")
            venue_floor = math.ceil(leverage)
            distance = isolated_liquidation_distance_bps(leverage, venue_floor)
            stop = _maximum_stop_bps(execution, provider, str(symbol), asset)
            buffer = _cost_buffer_bps(execution)
            if stop + buffer >= distance:
                problems.append(
                    f"{provider.get('strategy_id')} {symbol} stop {stop:g} bps plus "
                    f"cost buffer {buffer:g} bps reaches its {distance:.0f} bps "
                    f"liquidation distance at {leverage:g}x once the venue maximum "
                    f"is {venue_floor}x"
                )
    return problems


def require_stops_inside_liquidation(config_path: Path) -> None:
    """Refuse a live profile with any route whose stop could never fire."""
    problems = liquidation_problems(config_path)
    if problems:
        raise MultiAssetLiveConfigError("; ".join(problems))


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
    buffer = _cost_buffer_bps(execution)
    if not isinstance(raw, Mapping):
        return None, buffer, "none"
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


def _cost_buffer_bps(execution: Mapping[str, object]) -> float:
    raw = execution.get("stop_risk_budget")
    if not isinstance(raw, Mapping):
        return DEFAULT_COST_BUFFER_BPS
    buffer = raw.get("cost_buffer_bps", DEFAULT_COST_BUFFER_BPS)
    return _nonnegative(buffer, "stop_risk_budget cost_buffer_bps")


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


def build_parser() -> argparse.ArgumentParser:
    """Build the offline runtime-validation command line."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--mode", choices=("observe", "live"), default="live")
    parser.add_argument(
        "--equity",
        type=float,
        help="account equity in USD for the book-level at-stop risk and margin check",
    )
    parser.add_argument(
        "--backtest-lab-root",
        type=Path,
        default=None,
        help=(
            "backtest-lab dependency root, as passed to the armed entrypoint "
            "(default: the supervised entrypoint's, beside the repository root)"
        ),
    )
    return parser


def book_report(result: BookCheck) -> dict[str, object]:
    """The book-level check as JSON (amounts in USD, fractions of equity)."""
    equity = result.equity_usd
    return {
        "equity_usd": equity,
        "maximum_positions": result.maximum_positions,
        "at_stop_loss_usd": result.at_stop_loss_usd,
        "at_stop_loss_fraction": result.at_stop_loss_usd / equity,
        "at_stop_risk_limit_fraction": BOOK_AT_STOP_RISK_LIMIT,
        "margin_usd": result.margin_usd,
        "margin_fraction": result.margin_usd / equity,
        "margin_limit_fraction": BOOK_MARGIN_LIMIT,
        "routes": [asdict(route) for route in result.routes],
        "problems": list(result.problems),
    }


def _emit(report: dict[str, object]) -> int:
    """Print the single JSON document on stdout and return its exit code."""
    print(json.dumps(report, indent=2, default=str))
    return int(report["exit_code"])  # type: ignore[call-overload]


def main(argv: Sequence[str] | None = None) -> int:
    """Exit 0 only when the runner would accept the profile.

    stdout carries exactly one JSON document (``verdict``, ``exit_code``,
    ``problems`` and, with ``--equity``, the ``book`` check); the operator
    lines stay on stderr.
    """
    args = build_parser().parse_args(argv)
    backtest_lab_root = (
        DEFAULT_BACKTEST_LAB
        if args.backtest_lab_root is None
        else args.backtest_lab_root
    )
    report: dict[str, object] = {
        "ok": False,
        "config": str(args.config),
        "mode": args.mode,
        "equity_usd": args.equity,
        "execution_authority": "none",
        "problems": [],
        "book": None,
    }
    try:
        problems = check(
            args.config, mode=args.mode, backtest_lab_root=backtest_lab_root
        )
        book = (
            book_check(args.config, equity_usd=args.equity)
            if args.equity is not None and not problems
            else None
        )
    except (
        MultiAssetLiveConfigError,
        MultiAssetIntentPollerError,
        CohortExecutionPlanError,
        FileNotFoundError,
        ValueError,
    ) as exc:
        # Exit 1 is reserved for collected runner objections. Every loader refusal
        # reports 2, exactly as the armed entrypoint does, so an operator can tell
        # "this profile is unloadable" from "the runner would refuse it".
        print(f"loader refused: {exc}", file=sys.stderr)
        report.update(
            verdict="loader_refused",
            exit_code=2,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return _emit(report)
    if problems:
        for problem in problems:
            print(f"runtime validator would refuse: {problem}", file=sys.stderr)
        report.update(verdict="runner_refused", exit_code=1, problems=problems)
        return _emit(report)
    message = f"runtime validator accepts {args.config} in {args.mode} mode"
    print(message, file=sys.stderr)
    report.update(ok=True, verdict="accepted", exit_code=0, message=message)
    if book is None:
        return _emit(report)
    print(format_book_table(book), file=sys.stderr)
    for problem in book.problems:
        print(f"book-level check would refuse: {problem}", file=sys.stderr)
    report["book"] = book_report(book)
    if book.problems:
        # Report-only advisory: the runner never reads the book-level check.
        report.update(verdict="book_level_advisory", exit_code=3)
    return _emit(report)


if __name__ == "__main__":
    raise SystemExit(main())
