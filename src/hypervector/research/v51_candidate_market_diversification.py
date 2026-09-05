"""Source-native market-diversification evidence for v51 candidates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json

import numpy as np
import pandas as pd

_INTERVAL = pd.Timedelta(hours=1)
_REQUIRED_COLUMNS = frozenset({"timestamp", "close", "source"})


@dataclass(frozen=True)
class CandidateMarketDiversificationConfig:
    """Bound one report to an explicit roster, window, and sample contract."""

    baseline_symbols: tuple[str, ...]
    candidate_symbols: tuple[str, ...]
    start_utc: pd.Timestamp
    end_utc: pd.Timestamp
    minimum_shared_returns: int
    chronological_folds: int

    def __post_init__(self) -> None:
        """Reject ambiguous roster and window contracts."""
        symbols = self.baseline_symbols + self.candidate_symbols
        if not self.baseline_symbols or not self.candidate_symbols:
            raise ValueError("baseline and candidate symbols must be nonempty")
        if len(set(symbols)) != len(symbols):
            raise ValueError("market-diversification symbols must be unique")
        if self.start_utc.tzinfo is None or self.end_utc.tzinfo is None:
            raise ValueError("market-diversification bounds must be timezone-aware")
        if self.start_utc >= self.end_utc:
            raise ValueError("market-diversification window must be positive")
        if self.minimum_shared_returns < 2:
            raise ValueError("minimum shared returns must be at least two")
        if self.chronological_folds < 2:
            raise ValueError("chronological folds must be at least two")


def build_candidate_market_diversification_report(
    frames: Mapping[str, pd.DataFrame],
    config: CandidateMarketDiversificationConfig,
) -> dict[str, object]:
    """Build a report-only synchronized market-return diagnostic."""
    symbols = config.baseline_symbols + config.candidate_symbols
    if set(frames) != set(symbols):
        raise ValueError("market-diversification inputs must match the exact roster")
    prepared = {
        symbol: _prepare_symbol(symbol, frames[symbol], config) for symbol in symbols
    }
    returns = pd.concat(
        {symbol: item[0] for symbol, item in prepared.items()}, axis=1, join="inner"
    ).dropna()
    if len(returns) < config.minimum_shared_returns:
        raise ValueError("insufficient synchronized contiguous market returns")
    correlation = _finite_correlation(returns)
    folds = _fold_reports(returns, config)
    return {
        "schema_version": "v51_candidate_market_diversification_v1",
        "mode": "report_only_market_return_diagnostic",
        "contract": _contract(),
        "method": _method(config),
        "coverage": _coverage(returns, prepared),
        "correlation_matrix": _matrix_record(correlation),
        "candidate_diagnostics": _candidate_diagnostics(returns, correlation, config),
        "candidate_pair_correlation": _candidate_pair(correlation, config),
        "portfolio_sensitivity": _portfolio_sensitivity(returns, correlation, config),
        "chronological_folds": folds,
        "source_evidence": {symbol: item[1] for symbol, item in prepared.items()},
        "conclusion": _conclusion(),
        "limitations": _limitations(),
    }


def _prepare_symbol(
    symbol: str,
    frame: pd.DataFrame,
    config: CandidateMarketDiversificationConfig,
) -> tuple[pd.Series, dict[str, object], int]:
    missing = sorted(_REQUIRED_COLUMNS.difference(frame.columns))
    if missing:
        raise ValueError(f"{symbol} candles missing columns: {missing}")
    source_values = set(frame["source"].dropna().astype(str))
    if source_values != {"hl"}:
        raise ValueError(f"{symbol} candles must use exact public HL source")
    timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    if timestamps.duplicated().any():
        raise ValueError(f"{symbol} has duplicate candle timestamps")
    closes = pd.to_numeric(frame["close"], errors="raise").astype(float)
    if (closes <= 0.0).any() or not np.isfinite(closes).all():
        raise ValueError(f"{symbol} close prices must be finite and positive")
    bounded = pd.Series(closes.to_numpy(), index=timestamps, name=symbol).sort_index()
    bounded = bounded.loc[
        (bounded.index >= config.start_utc)
        & (bounded.index + _INTERVAL <= config.end_utc)
    ]
    if len(bounded) < 2:
        raise ValueError(f"{symbol} has insufficient bounded candles")
    deltas = bounded.index.to_series().diff()
    returns = bounded.pct_change(fill_method=None).where(deltas.eq(_INTERVAL)).dropna()
    evidence = _source_record(bounded)
    excluded = int((deltas.iloc[1:] != _INTERVAL).sum())
    return returns, evidence, excluded


def _source_record(closes: pd.Series) -> dict[str, object]:
    rows = [
        {"timestamp_ms": int(timestamp.timestamp() * 1000), "close": float(value)}
        for timestamp, value in closes.items()
    ]
    encoded = json.dumps(rows, separators=(",", ":"), sort_keys=True).encode()
    return {
        "source": "hyperliquid_public_candleSnapshot_1h",
        "rows": len(rows),
        "first_timestamp_utc": closes.index[0].isoformat(),
        "last_timestamp_utc": closes.index[-1].isoformat(),
        "close_rows_sha256": sha256(encoded).hexdigest(),
        "close_rows": rows,
    }


def _finite_correlation(returns: pd.DataFrame) -> pd.DataFrame:
    if (returns.std(ddof=1) <= 0.0).any():
        raise ValueError("market return variance must be positive for every symbol")
    correlation = returns.corr(method="pearson")
    if not np.isfinite(correlation.to_numpy()).all():
        raise ValueError("market return correlations must be finite")
    return correlation


def _candidate_diagnostics(
    returns: pd.DataFrame,
    correlation: pd.DataFrame,
    config: CandidateMarketDiversificationConfig,
) -> dict[str, object]:
    crypto = tuple(symbol for symbol in config.baseline_symbols if ":" not in symbol)
    noncrypto = tuple(symbol for symbol in config.baseline_symbols if ":" in symbol)
    return {
        symbol: _candidate_record(returns, correlation, symbol, crypto, noncrypto)
        for symbol in config.candidate_symbols
    }


def _candidate_record(
    returns: pd.DataFrame,
    correlation: pd.DataFrame,
    symbol: str,
    crypto: tuple[str, ...],
    noncrypto: tuple[str, ...],
) -> dict[str, object]:
    baseline = crypto + noncrypto
    abs_values = correlation.loc[symbol, list(baseline)].abs()
    baseline_return = returns.loc[:, list(baseline)].mean(axis=1)
    candidate_negative = returns[symbol] < 0.0
    joint_negative = candidate_negative & (baseline_return < 0.0)
    return {
        "mean_correlation_to_baseline": float(
            correlation.loc[symbol, list(baseline)].mean()
        ),
        "mean_absolute_correlation_to_baseline": float(abs_values.mean()),
        "mean_absolute_correlation_to_crypto": _group_mean(correlation, symbol, crypto),
        "mean_absolute_correlation_to_live_noncrypto": _group_mean(
            correlation, symbol, noncrypto
        ),
        "maximum_absolute_baseline_correlation": float(abs_values.max()),
        "maximum_absolute_baseline_symbol": str(abs_values.idxmax()),
        "joint_negative_hour_fraction": float(joint_negative.mean()),
        "baseline_negative_given_candidate_negative": _conditional_rate(
            joint_negative, candidate_negative
        ),
    }


def _group_mean(
    correlation: pd.DataFrame, symbol: str, group: tuple[str, ...]
) -> float | None:
    if not group:
        return None
    return float(correlation.loc[symbol, list(group)].abs().mean())


def _conditional_rate(numerator: pd.Series, denominator: pd.Series) -> float | None:
    count = int(denominator.sum())
    return float(numerator.sum() / count) if count else None


def _portfolio_sensitivity(
    returns: pd.DataFrame,
    correlation: pd.DataFrame,
    config: CandidateMarketDiversificationConfig,
) -> dict[str, object]:
    baseline = config.baseline_symbols
    all_symbols = baseline + config.candidate_symbols
    individual = {
        symbol: _hourly_volatility(returns.loc[:, list(baseline) + [symbol]])
        for symbol in config.candidate_symbols
    }
    return {
        "illustrative_equal_weight_only": True,
        "baseline_hourly_volatility": _hourly_volatility(
            returns.loc[:, list(baseline)]
        ),
        "baseline_plus_candidate_hourly_volatility": individual,
        "all_assets_hourly_volatility": _hourly_volatility(
            returns.loc[:, list(all_symbols)]
        ),
        "baseline_mean_absolute_pairwise_correlation": _pairwise_mean(
            correlation, baseline
        ),
        "all_assets_mean_absolute_pairwise_correlation": _pairwise_mean(
            correlation, all_symbols
        ),
    }


def _hourly_volatility(frame: pd.DataFrame) -> float:
    return float(frame.mean(axis=1).std(ddof=1))


def _pairwise_mean(correlation: pd.DataFrame, symbols: tuple[str, ...]) -> float:
    matrix = correlation.loc[list(symbols), list(symbols)].to_numpy()
    values = np.abs(matrix[np.triu_indices(len(symbols), k=1)])
    return float(values.mean())


def _candidate_pair(
    correlation: pd.DataFrame, config: CandidateMarketDiversificationConfig
) -> float | None:
    if len(config.candidate_symbols) != 2:
        return None
    left, right = config.candidate_symbols
    return float(correlation.loc[left, right])


def _fold_reports(
    returns: pd.DataFrame, config: CandidateMarketDiversificationConfig
) -> list[dict[str, object]]:
    indexes = np.array_split(np.arange(len(returns)), config.chronological_folds)
    reports: list[dict[str, object]] = []
    for number, positions in enumerate(indexes, start=1):
        if len(positions) < 2:
            raise ValueError("chronological fold has insufficient shared returns")
        fold = returns.iloc[positions]
        correlation = _finite_correlation(fold)
        reports.append(_fold_record(number, fold, correlation, config))
    return reports


def _fold_record(
    number: int,
    returns: pd.DataFrame,
    correlation: pd.DataFrame,
    config: CandidateMarketDiversificationConfig,
) -> dict[str, object]:
    diagnostics = _candidate_diagnostics(returns, correlation, config)
    return {
        "fold": number,
        "rows": len(returns),
        "start_utc": returns.index[0].isoformat(),
        "end_utc": returns.index[-1].isoformat(),
        "candidate_pair_correlation": _candidate_pair(correlation, config),
        "candidate_diagnostics": diagnostics,
    }


def _coverage(
    returns: pd.DataFrame,
    prepared: Mapping[str, tuple[pd.Series, dict[str, object], int]],
) -> dict[str, object]:
    return {
        "shared_return_rows": len(returns),
        "shared_start_utc": returns.index[0].isoformat(),
        "shared_end_utc": returns.index[-1].isoformat(),
        "return_rows_by_symbol": {
            symbol: len(item[0]) for symbol, item in prepared.items()
        },
        "excluded_noncontiguous_returns": {
            symbol: item[2] for symbol, item in prepared.items()
        },
    }


def _matrix_record(correlation: pd.DataFrame) -> dict[str, dict[str, float]]:
    return {
        row: {
            column: float(correlation.loc[row, column])
            for column in correlation.columns
        }
        for row in correlation.index
    }


def _method(config: CandidateMarketDiversificationConfig) -> dict[str, object]:
    return {
        "source": "hyperliquid_public_candleSnapshot",
        "return_interval": "1h",
        "return_type": "simple_close_to_close",
        "gap_policy": "exclude_noncontiguous_returns_then_inner_join_all_assets",
        "correlation": "pearson_on_exact_shared_rows",
        "chronological_folds": config.chronological_folds,
        "baseline_symbols": list(config.baseline_symbols),
        "candidate_symbols": list(config.candidate_symbols),
        "window_start_utc": config.start_utc.isoformat(),
        "window_end_utc": config.end_utc.isoformat(),
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "covariance_weights_generated": False,
    }


def _conclusion() -> dict[str, object]:
    return {
        "market_return_diversification_evidence_available": True,
        "strategy_edge_established": False,
        "live_addition_authorized": False,
        "interpretation": (
            "Shared market returns measure dependence, not strategy signals, fills, "
            "costs, co-triggers, or portfolio PnL."
        ),
    }


def _limitations() -> list[str]:
    return [
        "Market-return correlation does not establish strategy-return diversification.",
        "Equal-weight volatility is illustrative and is not the active v51 allocation.",
        "Pearson correlation can miss nonlinear and tail dependence.",
        "The public candle snapshot is a point-in-time source and can differ from trade OHLC.",
        "No route, asset, parameter, leverage, sizing, risk, or deployment setting changed.",
    ]
