"""Frozen-entry minute-candle exit counterfactual; no invented regime or book data."""

from __future__ import annotations

import argparse
from bisect import bisect_left
import hashlib
import json
from pathlib import Path

from hypervector.cohort_profit_lock_policy import ProfitLockPolicy
from hypervector.live.cohort_adaptive_exit_inputs import adaptive_atr_bps
from hypervector.live.cohort_adaptive_exit_policy import AdaptiveExitObservation, AdaptiveExitState, advance_adaptive_exit
from hypervector.research.cohort_profit_lock_delayed import build_delayed_profit_lock_result
from hypervector.research.cohort_profit_lock_results import ProfitLockEconomics, estimate_counterfactual_net
from hypervector.research.cohort_trade_reflection_index import Candle


def adaptive_result(
    bars: tuple[Candle, ...], side: str, economics: ProfitLockEconomics,
    funding: dict[int, float], stress_bps: float,
) -> dict[str, object]:
    """Evaluate the production state machine with explicitly unavailable L2/regime."""
    first = economics.entry_timestamp_ms // 60_000 * 60_000 + 60_000
    last = (economics.exit_timestamp_ms - 60_000) // 60_000 * 60_000
    stamps = [bar.timestamp_ms for bar in bars]
    lo, hi = bisect_left(stamps, first), bisect_left(stamps, last + 1)
    scoped = bars[lo:hi]
    if tuple(bar.timestamp_ms for bar in scoped) != tuple(range(first, last + 1, 60_000)):
        return {"status": "missing_lifecycle_candles", "net_usd": None}
    if adaptive_atr_bps(bars[max(0, lo - 20):lo + 1], economics.entry_price) is None:
        return {"status": "missing_initial_volatility_history", "net_usd": None}
    state = AdaptiveExitState()
    sign = 1 if side == "long" else -1
    for index in range(lo, hi):
        bar = bars[index]
        atr = adaptive_atr_bps(bars[index - 20:index + 1], economics.entry_price)
        if atr is None:
            raise ValueError("validated lifecycle unexpectedly lost ATR history")
        state = advance_adaptive_exit(state, AdaptiveExitObservation(
            bar.timestamp_ms + 60_000, sign * (bar.close / economics.entry_price - 1) * 10_000,
            atr, 20.0, None))
        if state.exit_reason:
            price = bar.close * (1 - sign * stress_bps / 10_000)
            net = estimate_counterfactual_net(side, state.observed_ms, price, economics, funding)
            return {"status": "triggered", "net_usd": net, "decision_ms": state.observed_ms,
                    "floor_bps": state.floor_bps, "peak_bps": state.peak_bps,
                    "retained_gross_bps_before_stress": sign * (bar.close / economics.entry_price - 1) * 10_000}
    return {"status": "unchanged", "net_usd": economics.actual_net_pnl_usd}


def main() -> int:
    """Report all eligible trades, withheld paths, and fixed-rule comparisons."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    encoded = args.inputs.read_bytes()
    inputs = json.loads(encoded)
    candles = {symbol: tuple(Candle(**bar) for bar in rows) for symbol, rows in inputs["candles"].items()}
    rows = []
    for trade in inputs["trades"]:
        economics = ProfitLockEconomics(**trade["economics"])
        bars = candles[trade["symbol"]]
        funding = {int(key): value for key, value in inputs["funding"].get(trade["symbol"], {}).items()}
        for stress in (5.0, 15.0):
            adaptive = adaptive_result(bars, trade["side"], economics, funding, stress)
            fixed = build_delayed_profit_lock_result(ProfitLockPolicy("prior_100_25_50", 100, 25, 50),
                                                    trade["side"], bars, economics, funding, adverse_bps=stress)
            rows.append({"lifecycle_id": trade["lifecycle_id"], "symbol": trade["symbol"],
                         "stress_bps": stress, "actual_net_usd": economics.actual_net_pnl_usd,
                         "adaptive": adaptive, "fixed": fixed})
    summaries = [_summary(rows, stress) for stress in (5.0, 15.0)]
    result = {"execution_authority": "none", "input_sha256": hashlib.sha256(encoded).hexdigest(),
              "limitations": ["frozen original entries; no replacement entries or portfolio capacity effects",
                              "minute-close execution proxy with adverse stress, not actual quotes",
                              "regime and L2 unavailable in frozen input: tested production unknown-context path",
                              "historical exploratory sample, not untouched strategy holdout"],
              "summaries": summaries, "trades": rows}
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(summaries, indent=2))
    return 0


def _summary(rows: list[dict[str, object]], stress: float) -> dict[str, object]:
    eligible = [row for row in rows if row["stress_bps"] == stress and row["adaptive"]["net_usd"] is not None]
    return {"stress_bps": stress, "eligible": len(eligible), "withheld": len(rows) // 2 - len(eligible),
            "actual_net_usd": sum(row["actual_net_usd"] for row in eligible),
            "adaptive_net_usd": sum(row["adaptive"]["net_usd"] for row in eligible),
            "fixed_net_usd": sum(row["fixed"]["estimated_net_pnl_usd"] for row in eligible),
            "triggers": sum(row["adaptive"]["status"] == "triggered" for row in eligible),
            "improved": sum(row["adaptive"]["net_usd"] > row["actual_net_usd"] for row in eligible),
            "worsened": sum(row["adaptive"]["net_usd"] < row["actual_net_usd"] for row in eligible)}


if __name__ == "__main__":
    raise SystemExit(main())
