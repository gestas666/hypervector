#!/usr/bin/env python3
"""Monte Carlo power table for the Donchian size-ladder rules (review AGG-1).

Report-only. execution_authority: none. This tool imports nothing from
``hypervector``: it reads closed-trade R multiples that other tools already
wrote (a live closed-trade table, ``cohort_ladder_evidence.py`` reports and,
optionally, a research R pool), resamples each pool with replacement after
shifting its mean to a chosen edge, and applies three ladder rules to every
simulated sequence of closes:

- CURRENT (``docs/plans/2026-09-24-v94-size-ladder.md`` section 4): advance
  after the first 30 closes if mean R > 0 and ex-top-3 net USD >= 0, never
  re-tested; step down on any sliding 50-close mean R < 0, or -12% from the
  rung high.
- PROPOSED (review AGG-1): advance at looks 30/60/90 on cumulative mean R > 0
  and ex-top-3 R >= 0; step down when the cumulative t <= -1 at 50/100/150
  closes since the rung start, or -12% from the rung high.
- CONSERVATIVE: advance at looks 30/60/90 on cumulative t >= 1.6; step down as
  PROPOSED.

The table gives P(advance) by 30, 60 and 90 closes and P(step-down within 150
closes) at each edge. Each pool keeps its own shape (spread, skew, tail); only
its mean moves. Dollars per R for the USD gate use rung-0 sizing and the equity
path for the -12% rule uses rung-1 sizing, both per symbol from the ladder doc.
Closes are treated as sequential, so overlapping positions are not modeled. The
seed fixes every draw: the same inputs give the same table, and each pool and
edge draws from a stream named by the pool's name and the edge's value, so a
row does not change when other pools or edges are added to the run.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import sys
import zlib

import numpy as np
from numpy.typing import NDArray
import pandas as pd

DONCHIAN_PREFIX = "hourly_donchian_20_10_"
LIVE_SYMBOLS = ("SOL", "xyz:SNDK", "xyz:BRENTOIL", "xyz:TSLA")
DEFAULT_EDGES = (-0.10, 0.0, 0.10, 0.20, 0.34)
DEFAULT_SEED = 20_260_926
DEFAULT_SIMULATIONS = 40_000
CHUNK_SIMULATIONS = 10_000

CURRENT_ADVANCE_CLOSES = 30
ADVANCE_LOOKS = (30, 60, 90)
STEP_DOWN_HORIZON = 150
CURRENT_STEP_DOWN_WINDOW = 50
PROPOSED_STEP_DOWN_LOOKS = (50, 100, 150)
PROPOSED_STEP_DOWN_T = -1.0
CONSERVATIVE_ADVANCE_T = 1.6
STEP_DOWN_DRAWDOWN = -0.12
EXCLUDED_TOP = 3
WEAK_SHORT_ATR = 1.0

# Ladder doc sections 2 and 3 at the $4,831 reference equity: notional at each
# rung and the observed structural stop distance d per route.
REFERENCE_EQUITY_USD = 4_831.0
OBSERVED_STOP_BPS = {
    "SOL": 210.0,
    "xyz:SNDK": 185.0,
    "xyz:BRENTOIL": 151.0,
    "xyz:TSLA": 81.0,
}
RUNG0_NOTIONAL_USD = {
    "SOL": 502.42,
    "xyz:SNDK": 1_288.27,
    "xyz:BRENTOIL": 579.72,
    "xyz:TSLA": 502.42,
}
RUNG1_NOTIONAL_USD = {
    "SOL": 1_159.44,
    "xyz:SNDK": 1_288.27,
    "xyz:BRENTOIL": 1_449.30,
    "xyz:TSLA": 1_449.30,
}
# Dollars one R is worth at rung 0 (CURRENT rule's USD ex-top-3 gate) and the
# equity fraction one R moves at rung 1 (the -12% step-down path).
RUNG0_USD_PER_R = {
    symbol: RUNG0_NOTIONAL_USD[symbol] * OBSERVED_STOP_BPS[symbol] / 10_000
    for symbol in LIVE_SYMBOLS
}
RUNG1_EQUITY_PER_R = {
    symbol: RUNG1_NOTIONAL_USD[symbol]
    * OBSERVED_STOP_BPS[symbol]
    / 10_000
    / REFERENCE_EQUITY_USD
    for symbol in LIVE_SYMBOLS
}

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]
Record = dict[str, object]


# ---------------------------------------------------------------- pools


@dataclass(frozen=True)
class Trade:
    """One closed trade's R multiple and the route it came from."""

    symbol: str
    r: float
    key: str


@dataclass(frozen=True)
class Pool:
    """An empirical R distribution to resample."""

    name: str
    trades: tuple[Trade, ...]
    source: str

    @property
    def r(self) -> FloatArray:
        """R multiples as an array."""
        return np.array([trade.r for trade in self.trades], dtype=np.float64)

    def weights(self, table: Mapping[str, float]) -> FloatArray:
        """Per-trade weights; a symbol off the table takes the table mean."""
        fallback = float(np.mean(list(table.values())))
        return np.array(
            [table.get(trade.symbol, fallback) for trade in self.trades],
            dtype=np.float64,
        )


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"unsupported table format: {path}")


def _finite(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _trade_key(symbol: str, oid: object) -> str:
    """``symbol:entry_oid``; empty when the oid is unknown (never de-duplicated)."""
    number = _finite(oid)
    return f"{symbol}:{int(number)}" if number is not None else ""


def load_live_trades(path: Path, prefix: str = DONCHIAN_PREFIX) -> list[Trade]:
    """Closed Donchian trades from a live closed-trade table (parquet or CSV).

    The table needs ``strategy_id`` and ``R`` (net R on the lifecycle's own
    initial stop); ``coin`` or ``symbol`` names the route and ``entry_oid``, when
    present, identifies the trade for de-duplication.
    """
    frame = _read_table(path)
    symbol_column = "coin" if "coin" in frame.columns else "symbol"
    missing = {"strategy_id", "R", symbol_column}.difference(frame.columns)
    if missing:
        raise ValueError(f"{path} lacks columns: {sorted(missing)}")
    trades: list[Trade] = []
    for row in frame.to_dict("records"):
        strategy = row.get("strategy_id")
        r = _finite(row.get("R"))
        if not isinstance(strategy, str) or not strategy.startswith(prefix):
            continue
        if r is None:
            continue
        symbol = str(row[symbol_column])
        trades.append(Trade(symbol, r, _trade_key(symbol, row.get("entry_oid"))))
    return trades


def load_ladder_reports(
    paths: Sequence[Path], prefix: str = DONCHIAN_PREFIX
) -> list[Trade]:
    """Closed, reconciled Donchian lifecycles from ladder evidence JSON reports."""
    trades: list[Trade] = []
    for path in paths:
        report = json.loads(path.read_text())
        rows = report.get("lifecycles") if isinstance(report, Mapping) else None
        if not isinstance(rows, list):
            raise ValueError(f"{path} is not a cohort ladder evidence report")
        for row in rows:
            if not isinstance(row, Mapping) or row.get("status") != "closed":
                continue
            strategy = row.get("strategy_id")
            r = _finite(row.get("r_multiple"))
            if not isinstance(strategy, str) or not strategy.startswith(prefix):
                continue
            if r is None:
                continue
            symbol = str(row.get("symbol"))
            trades.append(Trade(symbol, r, _trade_key(symbol, row.get("entry_oid"))))
    return trades


def load_research_pool(
    path: Path,
    *,
    screen: str | None = "recent",
    variant: str | None = "plain",
    cost: str | None = "measured",
    symbols: Sequence[str] | None = LIVE_SYMBOLS,
    drop_weak_shorts: bool = True,
) -> list[Trade]:
    """Research-screen trades from a CSV with ``symbol`` and ``R`` columns.

    Optional ``screen``, ``variant`` and ``cost`` columns are filtered when a
    value is given. With ``drop_weak_shorts`` a short whose breakout extension
    (``ext_atr``) is below 1.0 ATR is removed, matching the V94 strong-short
    identity; a short without an extension is kept.
    """
    frame = _read_table(path)
    missing = {"symbol", "R"}.difference(frame.columns)
    if missing:
        raise ValueError(f"{path} lacks columns: {sorted(missing)}")
    for column, value in (("screen", screen), ("variant", variant), ("cost", cost)):
        if value is not None and column in frame.columns:
            frame = frame[frame[column] == value]
    if symbols is not None:
        frame = frame[frame["symbol"].isin(list(symbols))]
    if drop_weak_shorts and {"side", "ext_atr"}.issubset(frame.columns):
        weak = (frame["side"] == "short") & (frame["ext_atr"] < WEAK_SHORT_ATR)
        frame = frame[~weak]
    trades = []
    for index, row in enumerate(frame.to_dict("records")):
        r = _finite(row.get("R"))
        if r is not None:
            trades.append(Trade(str(row["symbol"]), r, f"research:{index}"))
    return trades


def merge_live(table: Sequence[Trade], reports: Sequence[Trade]) -> list[Trade]:
    """Table trades first; a report lifecycle already merged is skipped.

    Reports are checked against each other too, so overlapping reports (or one
    report passed twice) add each lifecycle once. A trade without an entry oid
    has no key and is always kept.
    """
    seen = {trade.key for trade in table if trade.key}
    merged = list(table)
    for trade in reports:
        if trade.key:
            if trade.key in seen:
                continue
            seen.add(trade.key)
        merged.append(trade)
    return merged


# ---------------------------------------------------------------- rules


def _ex_top(values: FloatArray, count: int = EXCLUDED_TOP) -> FloatArray:
    """Row sums without the ``count`` largest values."""
    return np.sort(values, axis=1)[:, :-count].sum(axis=1)


def _t_stat(values: FloatArray) -> FloatArray:
    """Row one-sample t; zero spread gives +/-inf (or nan at a zero mean)."""
    count = values.shape[1]
    with np.errstate(divide="ignore", invalid="ignore"):
        return values.mean(axis=1) / (values.std(axis=1, ddof=1) / math.sqrt(count))


def evaluate_rules(
    r: FloatArray, usd: FloatArray, equity_per_r: FloatArray
) -> dict[str, BoolArray]:
    """Apply every rule to simulated paths of at least 150 closes (one per row).

    ``usd`` is each close in rung-0 dollars and ``equity_per_r`` the equity
    fraction one R moves at rung 1. Advance flags are cumulative: advanced by
    that look. Step-down flags cover the first 150 closes from the rung start.
    """
    if r.shape[1] < max(STEP_DOWN_HORIZON, *ADVANCE_LOOKS):
        raise ValueError("paths are shorter than the evaluated horizon")
    rows = r.shape[0]
    flags: dict[str, BoolArray] = {}
    first = r[:, :CURRENT_ADVANCE_CLOSES]
    current = (first.mean(axis=1) > 0) & (_ex_top(usd[:, :CURRENT_ADVANCE_CLOSES]) >= 0)
    proposed = np.zeros(rows, dtype=np.bool_)
    conservative = np.zeros(rows, dtype=np.bool_)
    for look in ADVANCE_LOOKS:
        block = r[:, :look]
        proposed |= (block.mean(axis=1) > 0) & (_ex_top(block) >= 0)
        conservative |= _t_stat(block) >= CONSERVATIVE_ADVANCE_T
        # The rule in force samples the first 30 closes once and never re-tests.
        flags[f"current_advance_{look}"] = current.copy()
        flags[f"proposed_advance_{look}"] = proposed.copy()
        flags[f"conservative_advance_{look}"] = conservative.copy()
    horizon = r[:, :STEP_DOWN_HORIZON]
    cumulative = np.cumsum(np.pad(horizon, ((0, 0), (1, 0))), axis=1)
    window = CURRENT_STEP_DOWN_WINDOW
    means = (cumulative[:, window:] - cumulative[:, :-window]) / window
    window_down = (means < 0).any(axis=1)
    t_down = np.zeros(rows, dtype=np.bool_)
    for look in PROPOSED_STEP_DOWN_LOOKS:
        t_down |= _t_stat(horizon[:, :look]) <= PROPOSED_STEP_DOWN_T
    equity = np.cumprod(1 + equity_per_r[:, :STEP_DOWN_HORIZON] * horizon, axis=1)
    high = np.maximum(np.maximum.accumulate(equity, axis=1), 1.0)
    drawdown = (equity / high - 1 <= STEP_DOWN_DRAWDOWN + 1e-12).any(axis=1)
    flags["step_down_window"] = window_down
    flags["step_down_t"] = t_down
    flags["step_down_drawdown"] = drawdown
    flags["current_step_down"] = window_down | drawdown
    flags["proposed_step_down"] = t_down | drawdown
    return flags


def simulate(
    pool: Pool,
    edge: float,
    *,
    simulations: int,
    seed: int,
    stream: Sequence[int],
) -> dict[str, float]:
    """Probability of every rule flag with the pool's mean moved to ``edge`` R.

    ``stream`` names this draw inside the seed; ``build_table`` derives it from
    the pool name and the edge value (``draw_stream``).
    """
    if simulations < 1:
        raise ValueError("simulations must be positive")
    base = pool.r
    if base.size == 0:
        raise ValueError(f"pool {pool.name} is empty")
    centered = base - base.mean()
    usd_per_r = pool.weights(RUNG0_USD_PER_R)
    equity_per_r = pool.weights(RUNG1_EQUITY_PER_R)
    rng = np.random.default_rng([seed, *stream])
    columns = max(STEP_DOWN_HORIZON, *ADVANCE_LOOKS)
    totals: dict[str, int] = {}
    for start in range(0, simulations, CHUNK_SIMULATIONS):
        size = min(CHUNK_SIMULATIONS, simulations - start)
        index = rng.integers(0, base.size, (size, columns))
        r = centered[index] + edge
        flags = evaluate_rules(r, r * usd_per_r[index], equity_per_r[index])
        for name, values in flags.items():
            totals[name] = totals.get(name, 0) + int(values.sum())
    return {name: count / simulations for name, count in totals.items()}


def draw_stream(pool_name: str, edge: float) -> tuple[int, int]:
    """Name one pool-and-edge draw by identity, never by its position in a run."""
    canonical = f"{round(edge, 6) + 0.0:.6f}"  # + 0.0 folds -0.0 into 0.0
    return zlib.crc32(pool_name.encode()), zlib.crc32(canonical.encode())


def _row(edge: float, probabilities: Mapping[str, float]) -> Record:
    def by_look(rule: str) -> dict[str, float]:
        return {
            str(look): probabilities[f"{rule}_advance_{look}"] for look in ADVANCE_LOOKS
        }

    return {
        "edge_r": edge,
        "current": {
            "p_advance": by_look("current"),
            "p_step_down_150": probabilities["current_step_down"],
            "p_step_down_window_only": probabilities["step_down_window"],
        },
        "proposed": {
            "p_advance": by_look("proposed"),
            "p_step_down_150": probabilities["proposed_step_down"],
            "p_step_down_t_only": probabilities["step_down_t"],
        },
        "conservative": {
            "p_advance": by_look("conservative"),
            "p_step_down_150": probabilities["proposed_step_down"],
        },
        "p_drawdown_12pct_150": probabilities["step_down_drawdown"],
    }


def pool_stats(pool: Pool) -> Record:
    """Shape of the pool before any shift."""
    values = pool.r
    spread = float(values.std(ddof=1)) if values.size > 1 else None
    symbols: dict[str, int] = {}
    for trade in pool.trades:
        symbols[trade.symbol] = symbols.get(trade.symbol, 0) + 1
    return {
        "source": pool.source,
        "n": int(values.size),
        "mean_r": float(values.mean()),
        "sd_r": spread,
        "median_r": float(np.median(values)),
        "t_stat": float(values.mean() / (spread / math.sqrt(values.size)))
        if spread
        else None,
        "se_mean_at_30": spread / math.sqrt(CURRENT_ADVANCE_CLOSES) if spread else None,
        "top_r": [float(value) for value in np.sort(values)[::-1][:5]],
        "symbols": dict(sorted(symbols.items())),
    }


def build_table(
    pools: Sequence[Pool],
    *,
    edges: Sequence[float] = DEFAULT_EDGES,
    simulations: int = DEFAULT_SIMULATIONS,
    seed: int = DEFAULT_SEED,
) -> Record:
    """Simulate every pool at every edge; deterministic for a given seed."""
    output: dict[str, Record] = {}
    for pool in pools:
        rows = [
            _row(
                edge,
                simulate(
                    pool,
                    edge,
                    simulations=simulations,
                    seed=seed,
                    stream=draw_stream(pool.name, edge),
                ),
            )
            for edge in edges
        ]
        output[pool.name] = {"stats": pool_stats(pool), "table": rows}
    return {
        "execution_authority": "none",
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "seed": seed,
        "simulations": simulations,
        "edges_r": list(edges),
        "rules": {
            "current": "advance: first 30 closes, mean R > 0 and ex-top-3 net USD "
            ">= 0 (rung-0 $/R), never re-tested; step-down: any sliding 50-close "
            "mean R < 0, or -12% from the rung high (rung-1 equity per R)",
            "proposed": "advance: at 30/60/90 closes, cumulative mean R > 0 and "
            "ex-top-3 R >= 0; step-down: cumulative t <= -1 at 50/100/150 closes "
            "since rung start, or -12% from the rung high",
            "conservative": "advance: at 30/60/90 closes, cumulative t >= 1.6; "
            "step-down as proposed",
        },
        "model": {
            "resampling": "iid with replacement from each pool after shifting its "
            "mean to the edge (shape kept)",
            "draw_stream": "seed, crc32(pool name), crc32(edge to 6 dp): a row is "
            "independent of the other pools and edges in the run",
            "rung0_usd_per_r": RUNG0_USD_PER_R,
            "rung1_equity_per_r": RUNG1_EQUITY_PER_R,
            "unlisted_symbol_weight": "mean of the table",
            "omitted": "overlapping positions, serial correlation and regime "
            "clustering are not modeled; every close is sequential",
        },
        "pools": output,
    }


# ---------------------------------------------------------------- output


def _pct(value: object) -> str:
    return f"{float(value) * 100:.0f}%" if isinstance(value, (int, float)) else "n/a"


def _looks(values: object) -> str:
    assert isinstance(values, Mapping)
    return " / ".join(_pct(values[str(look)]) for look in ADVANCE_LOOKS)


def markdown(table: Mapping[str, object]) -> str:
    """Render the power table as Markdown for the ladder doc and reviews."""
    pools = table["pools"]
    assert isinstance(pools, Mapping)
    lines = [
        f"Seed {table['seed']}, {table['simulations']:,} paths per cell. "
        "P(advance) is cumulative by 30 / 60 / 90 closes; P(step-down) is within "
        "150 closes of the rung start.",
    ]
    for name, entry in pools.items():
        assert isinstance(entry, Mapping)
        stats, rows = entry["stats"], entry["table"]
        assert isinstance(stats, Mapping) and isinstance(rows, list)
        sd = stats["sd_r"]
        lines += [
            "",
            f"**Pool `{name}`** ({stats['source']}): n = {stats['n']}, mean "
            f"{float(stats['mean_r']):+.3f}R, sd "
            f"{f'{float(sd):.2f}R' if isinstance(sd, float) else 'n/a'}, median "
            f"{float(stats['median_r']):+.2f}R.",
            "",
            "| Edge | CURRENT advance | PROPOSED advance | CONSERVATIVE advance "
            "| CURRENT step-down | PROPOSED step-down | 50-window / t <= -1 / -12% |",
            "|---|---|---|---|---|---|---|",
        ]
        for row in rows:
            assert isinstance(row, Mapping)
            current, proposed = row["current"], row["proposed"]
            conservative = row["conservative"]
            assert isinstance(current, Mapping) and isinstance(proposed, Mapping)
            assert isinstance(conservative, Mapping)
            lines.append(
                f"| {float(row['edge_r']):+.2f}R | {_looks(current['p_advance'])} "
                f"| {_looks(proposed['p_advance'])} "
                f"| {_looks(conservative['p_advance'])} "
                f"| {_pct(current['p_step_down_150'])} "
                f"| {_pct(proposed['p_step_down_150'])} "
                f"| {_pct(current['p_step_down_window_only'])} / "
                f"{_pct(proposed['p_step_down_t_only'])} / "
                f"{_pct(row['p_drawdown_12pct_150'])} |"
            )
    return "\n".join(lines)


def _edges(text: str) -> tuple[float, ...]:
    values = tuple(float(part) for part in text.split(",") if part.strip())
    if not values or not all(math.isfinite(value) for value in values):
        raise argparse.ArgumentTypeError("edges must be finite numbers")
    return values


def build_parser() -> argparse.ArgumentParser:
    """Build the read-only command line."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--live-trades",
        type=Path,
        help="closed-trade table (parquet or CSV) with strategy_id, coin, R",
    )
    parser.add_argument(
        "--ladder-report",
        type=Path,
        action="append",
        default=[],
        help="cohort_ladder_evidence JSON; adds closes missing from the table",
    )
    parser.add_argument(
        "--research-pool", type=Path, help="research CSV with symbol and R columns"
    )
    parser.add_argument("--research-screen", default="recent")
    parser.add_argument("--research-variant", default="plain")
    parser.add_argument("--research-cost", default="measured")
    parser.add_argument("--research-symbols", default=",".join(LIVE_SYMBOLS))
    parser.add_argument(
        "--keep-weak-shorts",
        action="store_true",
        help="keep research shorts below 1.0 ATR of breakout extension",
    )
    parser.add_argument("--prefix", default=DONCHIAN_PREFIX)
    parser.add_argument("--edges", type=_edges, default=DEFAULT_EDGES)
    parser.add_argument("--simulations", type=int, default=DEFAULT_SIMULATIONS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", type=Path, help="write the JSON table here")
    return parser


def build_pools(args: argparse.Namespace) -> list[Pool]:
    """Assemble the live, research and combined pools that have data."""
    live: list[Trade] = []
    if args.live_trades is not None:
        live = load_live_trades(args.live_trades, args.prefix)
    live = merge_live(live, load_ladder_reports(args.ladder_report, args.prefix))
    research: list[Trade] = []
    if args.research_pool is not None:
        symbols = [part.strip() for part in args.research_symbols.split(",")]
        research = load_research_pool(
            args.research_pool,
            screen=args.research_screen or None,
            variant=args.research_variant or None,
            cost=args.research_cost or None,
            symbols=[symbol for symbol in symbols if symbol] or None,
            drop_weak_shorts=not args.keep_weak_shorts,
        )
    pools = []
    if live:
        pools.append(
            Pool(
                "live",
                tuple(live),
                "live Donchian 20/10 closes, realized net R; holds past the "
                "maximum hold (outages) are not capped",
            )
        )
    if research:
        source = (
            f"research {args.research_screen}/{args.research_variant}/"
            f"{args.research_cost}"
            + ("" if args.keep_weak_shorts else ", weak shorts removed")
        )
        pools.append(Pool("research", tuple(research), source))
    if live and research:
        pools.append(
            Pool("combined", tuple(live + research), "live and research pooled")
        )
    return pools


def main(argv: Sequence[str] | None = None) -> int:
    """Write the JSON table (when --out is given) and print it as Markdown."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.simulations < 1:
        parser.error("--simulations must be positive")
    pools = build_pools(args)
    if not pools:
        parser.error(
            "no closes: give --live-trades, --ladder-report or --research-pool"
        )
    table = build_table(
        pools, edges=args.edges, simulations=args.simulations, seed=args.seed
    )
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(table, indent=2, allow_nan=False) + "\n")
    print(markdown(table))
    return 0


if __name__ == "__main__":
    sys.exit(main())
