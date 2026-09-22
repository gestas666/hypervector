"""Reproduce the exit policy v2 evidence: matched-entry composite overlays on the frozen
V92 Donchian screens plus the recorded live executable-quote paths.

Report-only. No execution clients. Arms are declared below before any result is read and
every cell is written. Usage (from the repository root):

    uv run python scripts/v93_exit_v2_matrix.py --output <new directory>
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path("data/logs/research/bidirectional_cohort")
SCREENS = {
    "recent": (
        BASE / "v92_strategy_repair_20260922/screen_v2",
        (
            BASE / "v90_expansion_screen_20260920_v1/inputs_15m_stitched",
            BASE / "v90_expansion_screen_20260920_v1/inputs_15m",
        ),
    ),
    "year": (
        BASE / "v92_strategy_repair_20260922/screen_365d_v1",
        (BASE / "v92_strategy_repair_20260922/inputs_365d",),
    ),
}
PROBE = BASE / "v93_exit_design_probe_20260922"
ARMS = {
    "C1 floor(2R,0.5R)+gated(0.5R,0.5R)": dict(floor=(2.0, 0.5), gated=(0.5, 0.5)),
    "C4 floor(2R,0.5R) only": dict(floor=(2.0, 0.5), gated=None),
    "C5 gated(0.5R,0.5R) only": dict(floor=None, gated=(0.5, 0.5)),
    "breakeven native after 2R": dict(floor=(2.0, 0.0), gated=None),
}
UNCONDITIONAL = {
    f"ratchet a{a} g{g}": (a, g) for a, g in itertools.product((0.5, 1.0), (0.5, 1.0))
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bars(roots: tuple[Path, ...], symbol: str) -> tuple[pd.DataFrame, Path]:
    for root in roots:
        candidate = root / symbol / "bars.parquet"
        if candidate.exists():
            return pd.read_parquet(candidate), candidate
    raise FileNotFoundError(symbol)


def _composite(
    trade: dict, aux: dict, cfg: dict, arm: dict, variant: str
) -> tuple[float, bool]:
    sgn = 1 if trade["direction"] == "long" else -1
    ep, qty, notional = trade["entry_price"], trade["quantity"], trade["notional_usd"]
    risk = abs(ep - trade["stop_price"]) / ep * 1e4 if trade.get("stop_price") else None
    if not risk or risk <= 0:
        return trade["net_pnl_usd"], False
    e, x = trade["entry_position"], trade["exit_position"]
    highs, lows, opens, closes = aux["high"], aux["low"], aux["open"], aux["close"]
    fav = highs if sgn == 1 else lows
    slip, fee = cfg["market_exit_slippage_bps"] / 1e4, cfg["market_exit_fee_rate"]
    actual_bars = max(1, x - e)

    def net_at(px: float, bar: int) -> float:
        held = max(1, bar - e)
        gross = sgn * (px - ep) * qty
        return (
            gross
            - notional * cfg["entry_fee_rate"]
            - abs(px * qty) * fee
            + trade["funding_cashflow_usd"] * min(1.0, held / actual_bars)
        )

    peak = 0.0
    for i in range(e, x):
        if variant == "native":
            floors = []
            if arm["floor"] and peak >= arm["floor"][0] * risk:
                floors.append(arm["floor"][1] * risk)
            if (
                arm["gated"]
                and peak >= arm["gated"][0] * risk
                and i > e
                and (aux["opp_long"][i - 1] if sgn == 1 else aux["opp_short"][i - 1])
            ):
                floors.append(peak - arm["gated"][1] * risk)
            if floors:
                fp = ep * (1 + sgn * max(floors) / 1e4)
                if lows[i] <= fp if sgn == 1 else highs[i] >= fp:
                    fill = (min(fp, opens[i]) if sgn == 1 else max(fp, opens[i])) * (
                        1 - sgn * slip
                    )
                    return net_at(fill, i), True
        peak = max(peak, sgn * (fav[i] - ep) / ep * 1e4)
        nxt = i + 1
        if nxt > x:
            break
        if variant == "software":
            close_bps = sgn * (closes[i] - ep) / ep * 1e4
            fill = opens[nxt] * (1 - sgn * slip)
            if (
                arm["floor"]
                and peak >= arm["floor"][0] * risk
                and close_bps <= arm["floor"][1] * risk
            ):
                return net_at(fill, nxt), True
            opp = aux["opp_long"][i] if sgn == 1 else aux["opp_short"][i]
            if (
                arm["gated"]
                and peak >= arm["gated"][0] * risk
                and opp
                and close_bps <= peak - arm["gated"][1] * risk
            ):
                return net_at(fill, nxt), True
    return trade["net_pnl_usd"], False


def _unconditional(
    trade: dict, aux: dict, cfg: dict, a: float, g: float
) -> tuple[float, bool]:
    sgn = 1 if trade["direction"] == "long" else -1
    ep, qty, notional = trade["entry_price"], trade["quantity"], trade["notional_usd"]
    risk = abs(ep - trade["stop_price"]) / ep * 1e4 if trade.get("stop_price") else None
    if not risk:
        return trade["net_pnl_usd"], False
    e, x = trade["entry_position"], trade["exit_position"]
    fav = aux["high"] if sgn == 1 else aux["low"]
    slip, fee = cfg["market_exit_slippage_bps"] / 1e4, cfg["market_exit_fee_rate"]
    peak = 0.0
    for i in range(e, x):
        peak = max(peak, sgn * (fav[i] - ep) / ep * 1e4)
        if i + 1 > x:
            break
        close_bps = sgn * (aux["close"][i] - ep) / ep * 1e4
        if peak >= a * risk and close_bps <= peak - g * risk:
            px = aux["open"][i + 1] * (1 - sgn * slip)
            gross = sgn * (px - ep) * qty
            held = max(1, i + 1 - e)
            return gross - notional * cfg["entry_fee_rate"] - abs(
                px * qty
            ) * fee + trade["funding_cashflow_usd"] * min(
                1.0, held / max(1, x - e)
            ), True
    return trade["net_pnl_usd"], False


def screen_cells() -> tuple[list[dict], dict]:
    cells, inputs = [], {}
    for screen, (tdir, roots) in SCREENS.items():
        for f in sorted(tdir.glob("*_donchian_*.json")):
            if "bounded" in f.stem:
                continue
            symbol, cost = f.stem.replace("_donchian_", "|").split("|")
            d = json.loads(f.read_text())
            cfg, trades = d["config"], d["trades"]
            bars, path = _bars(roots, symbol)
            inputs[f"{screen}/{symbol}"] = {
                "bars": str(path),
                "bars_sha256": _sha(path),
                "trades": str(f),
                "trades_sha256": _sha(f),
            }
            for t in trades[:50]:
                assert str(bars.index[t["entry_position"]])[:16] == t["entry_time_utc"][
                    :16
                ].replace("T", " ")
            c = bars["close"]
            e21 = c.ewm(span=21, adjust=False).mean()
            e55 = c.ewm(span=55, adjust=False).mean()
            aux = dict(
                high=bars["high"].values,
                low=bars["low"].values,
                open=bars["open"].values,
                close=c.values,
                opp_long=((e21 < e55) & (c < e21)).values,
                opp_short=((e21 > e55) & (c > e21)).values,
            )
            base = np.array([t["net_pnl_usd"] for t in trades])
            edges = pd.date_range(
                bars.index[0], bars.index[-1] + pd.Timedelta(minutes=15), periods=4
            )
            et = pd.to_datetime([t["entry_time_utc"] for t in trades])
            runs = [
                (
                    name,
                    variant,
                    lambda t, arm=arm, variant=variant: _composite(
                        t, aux, cfg, arm, variant
                    ),
                )
                for name, arm in ARMS.items()
                for variant in ("software", "native")
            ]
            runs += [
                (
                    name,
                    "software",
                    lambda t, a=a, g=g: _unconditional(t, aux, cfg, a, g),
                )
                for name, (a, g) in UNCONDITIONAL.items()
            ]
            for name, variant, fn in runs:
                nets, cut, trig = [], 0, 0
                for t in trades:
                    n, altered = fn(t)
                    nets.append(n)
                    trig += altered
                    if altered and t["net_pnl_usd"] > 20 and n < t["net_pnl_usd"]:
                        cut += 1
                nets = np.array(nets)
                cells.append(
                    dict(
                        screen=screen,
                        symbol=symbol,
                        cost=cost,
                        arm=name,
                        variant=variant,
                        trades=len(trades),
                        baseline_net_usd=float(base.sum()),
                        net_usd=float(nets.sum()),
                        delta_usd=float(nets.sum() - base.sum()),
                        ex_top3_delta_usd=float(
                            np.sort(nets)[:-3].sum() - np.sort(base)[:-3].sum()
                        ),
                        triggers=trig,
                        winners_over_20_cut=cut,
                        block_deltas_usd=[
                            float(
                                nets[(et >= edges[k]) & (et < edges[k + 1])].sum()
                                - base[(et >= edges[k]) & (et < edges[k + 1])].sum()
                            )
                            for k in range(3)
                        ],
                    )
                )
    return cells, inputs


def live_cells() -> tuple[list[dict], dict]:
    paths = PROBE / "excursion_paths.jsonl"
    canon = PROBE / "canonical_rows.csv"
    trades = [json.loads(line) for line in paths.open()]
    rows = pd.read_csv(canon)
    weights = {"state_1m": 1.0, "state_5m": 3.0, "context_15m": 2.0}

    def value(state: object, sd: object) -> float | None:
        return (
            {"TREND_UP": 1.0, "TREND_DOWN": -1.0, "RANGE": 0.0, "TRANSITION": 0.0}.get(
                state
            )
            if state != "BREAKOUT"
            else {"long": 1.0, "short": -1.0}.get(sd, 0.0)
        )

    align: dict[str, tuple[list[int], list[float | None]]] = {}
    for sym, g in rows.groupby("symbol"):
        g = g.sort_values("decision_time_ms")
        ts, vals = g.decision_time_ms.tolist(), []
        for _, r in g.iterrows():
            num = den = 0.0
            for col, w in weights.items():
                v = value(r[col], r["structural_direction"])
                if v is None:
                    continue
                num += w * v
                den += w
            vals.append(num / den if den else None)
        align[str(sym).upper()] = (ts, vals)

    def alignment(sym: str, ms: int, side: str) -> float | None:
        if sym not in align:
            return None
        ts, vals = align[sym]
        i = bisect.bisect_right(ts, ms) - 1
        if i < 0 or ms - ts[i] > 1_800_000 or vals[i] is None:
            return None
        return vals[i] if side == "long" else -vals[i]

    def fee_bps(sym: str) -> float:
        return 0.864 if sym.startswith("XYZ:") else 4.32

    def run(t: dict, arm: dict | None) -> tuple[float, bool]:
        if arm is None:
            return t["net_usd"], False
        ep = t["entry_price"]
        sgn = 1 if t["side"] == "long" else -1
        risk = abs(ep - t["stop_trigger"]) / ep * 1e4 if t.get("stop_trigger") else None
        if not risk:
            return t["net_usd"], False
        notional = ep * t["entry_size"]
        hold = max(1, t["path"][-1][0] - t["entry_ms"])
        peak = 0.0
        for pt in t["path"]:
            ms, bid, ask = pt[0], pt[1], pt[2]
            pnl = sgn * ((bid if sgn == 1 else ask) - ep) / ep * 1e4
            peak = max(peak, pnl)
            fire = (
                arm["floor"]
                and peak >= arm["floor"][0] * risk
                and pnl <= arm["floor"][1] * risk
            )
            if (
                not fire
                and arm["gated"]
                and peak >= arm["gated"][0] * risk
                and pnl <= peak - arm["gated"][1] * risk
            ):
                a = alignment(t["symbol"], ms, t["side"])
                fire = a is not None and a <= -0.5
            if fire:
                frac = min(1.0, (ms - t["entry_ms"]) / hold)
                return (pnl - 2.0) / 1e4 * notional - 2 * notional * fee_bps(
                    t["symbol"]
                ) / 1e4 + t["funding_usd"] * frac, True
        return t["net_usd"], False

    cells = []
    for name, arm in [("actual", None), *ARMS.items()]:
        for era in ("v89+", "pre"):
            sub = [
                t
                for t in trades
                if (t["entry_time"] >= "2026-09-07") == (era == "v89+")
            ]
            nets = np.array([run(t, arm)[0] for t in sub])
            base = np.array([t["net_usd"] for t in sub])
            trig = sum(run(t, arm)[1] for t in sub)
            cells.append(
                dict(
                    era=era,
                    arm=name,
                    trades=len(sub),
                    baseline_net_usd=float(base.sum()),
                    net_usd=float(nets.sum()),
                    delta_usd=float(nets.sum() - base.sum()),
                    triggers=int(trig),
                    win_rate=float((nets > 0).mean()),
                )
            )
    return cells, {
        "paths": str(paths),
        "paths_sha256": _sha(paths),
        "canonical": str(canon),
        "canonical_sha256": _sha(canon),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"output directory already exists: {args.output}")
    args.output.mkdir(parents=True)
    screen, inputs = screen_cells()
    live, live_inputs = live_cells()
    df = pd.DataFrame(screen)
    aggregate = df.groupby(["screen", "cost", "arm", "variant"], as_index=False).agg(
        trades=("trades", "sum"),
        baseline_net_usd=("baseline_net_usd", "sum"),
        net_usd=("net_usd", "sum"),
        delta_usd=("delta_usd", "sum"),
        ex_top3_delta_usd=("ex_top3_delta_usd", "sum"),
        triggers=("triggers", "sum"),
        winners_over_20_cut=("winners_over_20_cut", "sum"),
    )
    report = {
        "execution_authority": "none",
        "automatic_promotion": False,
        "arms": {k: v for k, v in ARMS.items()},
        "unconditional_arms": UNCONDITIONAL,
        "inputs": inputs,
        "live_inputs": live_inputs,
        "aggregate": aggregate.to_dict(orient="records"),
        "cells": screen,
        "live": live,
        "limitations": [
            "Fixed-entry overlays omit new entries made possible by freed capital.",
            "15m bars cannot establish intrabar ordering; native floors fill at min(floor, open) with slippage.",
            "The 15m trend gate is an EMA21/55 proxy for the live canonical regime, which is unavailable historically.",
            "Live paths are 139 recorded trades; regime alignment exists only for the 29 trades since 2026-09-07.",
            "Data were examined before these arms were declared; no cell is a sealed holdout.",
        ],
    }
    (args.output / "report.json").write_text(
        json.dumps(report, indent=2, default=float)
    )
    aggregate.to_csv(args.output / "aggregate.csv", index=False)
    pd.DataFrame(live).to_csv(args.output / "live.csv", index=False)
    print(
        aggregate[
            aggregate.arm.str.startswith(("C1", "breakeven", "ratchet a0.5 g0.5"))
        ]
        .round(2)
        .to_string(index=False)
    )
    print(pd.DataFrame(live).round(2).to_string(index=False))


if __name__ == "__main__":
    main()
