"""Compare SNDK onset persistence with frozen risk on explicitly approximate bars."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioConfig,
    SharedPortfolioReport,
)
from hypervector.research.sndk_onset_sensitivity import (
    build_sndk_onset_sensitivity_signals,
)

_SYMBOL = "xyz:SNDK"
_BPS_PER_UNIT = 10_000.0
_SLIPPAGE_CASES_BPS = (2.5, 5.5)
_ENTRY_CAP_FRACTION = 0.002
_MAXIMUM_ENTRY_DELAY_SECONDS = 30


def main() -> int:
    """Publish a controlled mechanism sensitivity, without live or exact-fill claims."""
    args = _parser().parse_args()
    if args.out.exists():
        raise FileExistsError(f"sensitivity output exists: {args.out}")
    bars = pd.read_parquet(args.bars).set_index("timestamp")
    funding = pd.read_parquet(args.funding)
    funding = funding.loc[funding.symbol.eq(_SYMBOL)].set_index("timestamp")
    start, end = funding.index.min(), funding.index.max() + pd.Timedelta(hours=1)
    expected = pd.date_range(start, end, freq="h", inclusive="left")
    if not funding.index.equals(expected) or funding.funding_rate.isna().any():
        raise ValueError("SNDK funding must contain every ordered native hourly event")
    signals = build_sndk_onset_sensitivity_signals(bars)
    mask = (bars.index >= start) & (bars.index < end)
    bars = bars.loc[mask].copy()
    bars["funding_rate"] = funding.funding_rate.reindex(bars.index, fill_value=0.0)
    cases = []
    for slip in _SLIPPAGE_CASES_BPS:
        config = _execution_config(args, slip)
        for name, values in signals.items():
            selected = values.loc[mask].copy()
            candidates = int(selected.short_entry.sum())
            _censor_expired_entries(bars, selected, slip)
            result = evaluate_shared_bar_portfolio(bars, selected, config)
            cases.append(_case(name, config, candidates, selected, result))
            print(name, slip, result.completed_trades, result.net_pnl_usd)
    write_immutable_json(args.out, _report(args, bars, funding, cases))
    return 0


def _case(
    name: str,
    config: SharedPortfolioConfig,
    candidates: int,
    selected: pd.DataFrame,
    result: SharedPortfolioReport,
) -> dict[str, object]:
    censored = {"data_gap", "end_of_data"}
    return {
        "mechanism": name,
        "execution": asdict(config),
        "candidate_entries": candidates,
        "entries_after_quote_constraints": int(selected.short_entry.sum()),
        "conditional_path_output": result.to_dict(),
        "uncertain_gap_or_terminal_exits": sum(
            t.exit_reason in censored for t in result.trades
        ),
        "net_excluding_gap_or_terminal_exits_usd": sum(
            t.net_pnl_usd for t in result.trades if t.exit_reason not in censored
        ),
        "net_excluding_largest_trade_usd": result.net_pnl_usd
        - max((t.net_pnl_usd for t in result.trades), default=0.0),
        "ambiguous_intrabar_exits": sum(t.same_bar_ambiguous for t in result.trades),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("bars", "funding", "config", "out"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--initial-equity", type=float, required=True)
    parser.add_argument("--taker-fee-bps", type=float, required=True)
    return parser


def _execution_config(args: argparse.Namespace, slip: float) -> SharedPortfolioConfig:
    config = load_multi_asset_live_config(args.config, mode="observe")
    provider = next(
        row for row in config.providers if row.execution_symbols == (_SYMBOL,)
    )
    asset = next(row for row in config.assets if row.symbol == _SYMBOL)
    if (
        asset.effective_entry_slippage_cap_fraction != _ENTRY_CAP_FRACTION
        or provider.maximum_entry_delay_seconds != _MAXIMUM_ENTRY_DELAY_SECONDS
    ):
        raise ValueError(
            "sensitivity entry quote constraints differ from configuration"
        )
    sizing = provider.entry_sizing(_SYMBOL, "short")
    execution = provider.execution_for(_SYMBOL, "short")
    if sizing is None or provider.executable_sides(_SYMBOL) != frozenset({"short"}):
        raise ValueError("sensitivity requires explicit SNDK short-only sizing")
    if (
        execution.stop_policy,
        execution.target_policy,
        execution.maximum_hold_policy,
        execution.provider_recipe_exit_policy,
        execution.profit_lock_policy,
    ) != ("fixed_bps", "none", "fixed", "ignore", "none") or execution.stop_bps is None:
        raise ValueError("sensitivity does not implement this SNDK exit contract")
    fee = args.taker_fee_bps / _BPS_PER_UNIT
    return SharedPortfolioConfig(
        symbol=_SYMBOL,
        initial_equity=args.initial_equity,
        margin_fraction=sizing.margin_fraction,
        leverage=asset.leverage,
        venue_max_leverage=asset.leverage,
        maximum_notional_usd=sizing.max_notional_usd,
        stop_margin_pct=execution.stop_bps * asset.leverage / 100.0,
        max_hold_seconds=execution.maximum_hold_seconds,
        entry_fee_rate=fee,
        target_fee_rate=fee,
        market_exit_fee_rate=fee,
        liquidation_fee_rate=fee,
        entry_slippage_bps=slip,
        market_exit_slippage_bps=slip,
        reentry_cooldown_bars=0,
        close_on_opposite_signal=False,
        open_bid_column="entry_bid",
        open_ask_column="entry_ask",
        close_bid_column="decision_bid",
        close_ask_column="decision_ask",
    )


def _censor_expired_entries(
    bars: pd.DataFrame, signals: pd.DataFrame, slip: float
) -> None:
    next_bid = bars.entry_bid.shift(-1) * (1.0 - slip / _BPS_PER_UNIT)
    quote_within_ioc = next_bid.ge(bars.close * (1.0 - _ENTRY_CAP_FRACTION))
    timely = bars.first_boundary_delay_ms.shift(-1).le(
        _MAXIMUM_ENTRY_DELAY_SECONDS * 1000
    )
    adjacent = (
        bars.index.to_series().shift(-1).sub(bars.index).eq(pd.Timedelta(minutes=15))
    )
    signals["short_entry"] &= quote_within_ioc & timely & adjacent


def _report(
    args: argparse.Namespace,
    bars: pd.DataFrame,
    funding: pd.DataFrame,
    cases: list[dict[str, object]],
) -> dict[str, object]:
    paths = [args.bars, args.funding, args.config, Path(__file__)]
    paths.extend(sorted(Path("src/hypervector/research").glob("shared_*portfolio*.py")))
    paths.append(Path("src/hypervector/research/sndk_onset_sensitivity.py"))
    return {
        "schema_version": 1,
        "execution_authority": "none",
        "exact_current_or_corrected_live_replay": False,
        "experiment": "same-input state-entry versus durable onset mechanism sensitivity",
        "scoring_first_bar_utc": str(bars.index[0]),
        "scoring_last_bar_utc": str(bars.index[-1]),
        "observed_bars": len(bars),
        "native_hourly_funding_events": len(funding),
        "funding_events_without_observed_bar": len(
            funding.index.difference(bars.index)
        ),
        "cases": cases,
        "evidence": {str(path.resolve()): file_evidence(path) for path in paths},
        "limitations": [
            "Opened historical data; not pristine out-of-sample or a parameter search.",
            "OHLC are L2 midpoint proxies, not exact venue candleSnapshot signals or mark risk.",
            "Both mechanisms use the same exchange-age filter; V3 receipt age is not reconstructed.",
            "V4 publication delays, durable candle revisions and restart paths are not reconstructed.",
            "Next-bar bid/ask plus adverse slippage are assumed fills; depth and partial fills are unverified.",
            "Funding uses native hourly rates and observed opening midpoint as a mark proxy.",
            "Missing-bar funding and in-gap stops are unresolved; data-gap exits use first observed quote.",
            "Final forced exits and gap exits are censored lifecycle sensitivities, not measured returns.",
            "One-position-per-asset isolation; shared-account interactions remain unmeasured.",
        ],
    }


if __name__ == "__main__":
    raise SystemExit(main())
