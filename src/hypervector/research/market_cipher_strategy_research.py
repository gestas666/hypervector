"""Immutable-input Hulk Smash research run construction and reporting."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd

from hypervector.research.backtest_lab_cipher_adapter import (
    compute_market_cipher_signal_components,
    inspect_backtest_lab_sources,
)
from hypervector.research.cipher_suite_candles import (
    load_cipher_ohlcv_from_candle_bundle,
)
from hypervector.research.cipher_suite_duckdb import (
    CIPHER_RESEARCH_SYMBOLS,
    load_cipher_ohlcv,
)
from hypervector.research.cipher_suite_timeframes import resample_cipher_bars
from hypervector.research.hulk_smash_candidates import (
    select_hulk_expansion_moderate_adx,
)
from hypervector.research.hulk_smash_quality import build_hulk_quality_frame
from hypervector.research.hulk_smash_rebuilt_signals import (
    RebuiltHulkConfig,
    evaluate_rebuilt_hulk_signals,
)
from hypervector.research.market_cipher_data import (
    attach_hourly_funding,
    load_verified_hourly_funding,
)
from hypervector.research.market_cipher_replay import evaluate_market_cipher_replay
from hypervector.research.market_cipher_replay_models import (
    MarketCipherReplayConfig,
    MarketCipherReplayReport,
    MarketCipherReplayTrade,
)
from hypervector.research.market_cipher_source_contract import (
    audit_market_cipher_sources,
)


@dataclass(frozen=True)
class HulkResearchProfile:
    """One immutable deterministic Hulk signal profile."""

    name: str
    side: str | None
    supertrend_period: int
    supertrend_multiplier: float
    adx_period: int
    squeeze_period: int
    minimum_score: int
    pivot_bars: int
    adx_usable: float
    adx_trending: float
    status: str


@dataclass(frozen=True)
class MarketCipherStrategyResearchRun:
    """Report plus machine-readable sidecars for one immutable run."""

    report: dict[str, object]
    signals: pd.DataFrame
    trades: pd.DataFrame


_PROFILES = {
    "hulk_expansion_control_v1": HulkResearchProfile(
        "hulk_expansion_control_v1",
        None,
        10,
        3.0,
        14,
        20,
        8,
        5,
        18.0,
        25.0,
        "failed_control",
    ),
    "hulk_expansion_bidirectional_tuned_v2": HulkResearchProfile(
        "hulk_expansion_bidirectional_tuned_v2",
        None,
        7,
        3.0,
        20,
        20,
        8,
        8,
        18.0,
        25.0,
        "failed_forward_diagnostic",
    ),
    "hulk_expansion_short_tuned_v2": HulkResearchProfile(
        "hulk_expansion_short_tuned_v2",
        "short",
        7,
        3.0,
        20,
        20,
        8,
        8,
        18.0,
        25.0,
        "research_challenger_not_promoted",
    ),
    "hulk_expansion_short_robust_v3": HulkResearchProfile(
        "hulk_expansion_short_robust_v3",
        "short",
        7,
        3.0,
        20,
        20,
        7,
        6,
        16.0,
        23.0,
        "forward_robustness_survivor_not_promoted",
    ),
}

_ROBUSTNESS_NAMES = (
    "nominal",
    "cost_stress",
    "entry_delay_2_bars",
    "stop_cap_60_bps",
    "stop_cap_90_bps",
    "funding_2x",
)


def resolve_hulk_research_profile(name: str) -> HulkResearchProfile:
    """Return one frozen profile or reject an unjournaled identity."""
    if name not in _PROFILES:
        raise ValueError(f"unknown Hulk research profile: {name}")
    return _PROFILES[name]


def hulk_research_profile_names() -> tuple[str, ...]:
    """Return stable CLI choices for the immutable strategy screen."""
    return tuple(_PROFILES)


def market_cipher_robustness_names() -> tuple[str, ...]:
    """Return the frozen, predeclared execution perturbation identities."""
    return _ROBUSTNESS_NAMES


def resolve_market_cipher_replay_config(
    name: str,
    *,
    bar_minutes: int = 30,
) -> MarketCipherReplayConfig:
    """Resolve one frozen replay configuration or reject unknown variants."""
    nominal = _nominal_replay_config(bar_minutes)
    if name == "nominal":
        return nominal
    if name == "cost_stress":
        return replace(
            nominal,
            entry_fee_rate=0.00055,
            target_fee_rate=0.00025,
            market_exit_fee_rate=0.00055,
            entry_slippage_bps=3.0,
            market_exit_slippage_bps=3.0,
        )
    if name == "entry_delay_2_bars":
        return replace(nominal, entry_delay_bars=2)
    if name == "stop_cap_60_bps":
        return replace(nominal, maximum_stop_bps=60.0)
    if name == "stop_cap_90_bps":
        return replace(nominal, maximum_stop_bps=90.0)
    if name == "funding_2x":
        return replace(nominal, funding_rate_multiplier=2.0)
    raise ValueError(f"unknown Market Cipher robustness identity: {name}")


def frame_sha256(frame: pd.DataFrame) -> str:
    """Hash ordered frame labels, dtypes, index, and values."""
    digest = sha256()
    digest.update(json.dumps([str(value) for value in frame.columns]).encode())
    digest.update(json.dumps([str(value) for value in frame.dtypes]).encode())
    digest.update(pd.util.hash_pandas_object(frame, index=True).to_numpy().tobytes())
    return digest.hexdigest()


def run_market_cipher_strategy_research(
    *,
    database_path: Path,
    backtest_lab_root: Path,
    mc_scalper_root: Path,
    market_cipher_cli_root: Path,
    funding_by_symbol: dict[str, tuple[Path, ...]],
    symbols: tuple[str, ...],
    start_utc: pd.Timestamp,
    end_utc: pd.Timestamp,
    segment: str,
    profile_name: str,
    robustness_name: str = "nominal",
    bar_minutes: int = 30,
    candle_bundles_by_symbol: dict[str, Path] | None = None,
) -> MarketCipherStrategyResearchRun:
    """Run one causal friction-aware profile without execution authority."""
    start, end = _window(start_utc, end_utc)
    signal_minutes = _validated_bar_minutes(bar_minutes)
    profile = resolve_hulk_research_profile(profile_name)
    replay_config = resolve_market_cipher_replay_config(
        robustness_name,
        bar_minutes=signal_minutes,
    )
    bars_by_symbol: dict[str, pd.DataFrame] = {}
    evidence: dict[str, object] = {}
    signal_parts: list[pd.DataFrame] = []
    normalized_symbols = _symbols(symbols, funding_by_symbol)
    candle_bundles = _candle_bundles(candle_bundles_by_symbol or {}, normalized_symbols)
    for symbol in normalized_symbols:
        bars, signals, symbol_evidence = _symbol_inputs(
            database_path,
            backtest_lab_root,
            funding_by_symbol[symbol],
            symbol,
            start,
            end,
            profile,
            signal_minutes,
            candle_bundles.get(symbol),
        )
        bars_by_symbol[symbol] = bars
        signal_parts.append(signals)
        evidence[symbol] = symbol_evidence
    signals = _combined_signals(signal_parts)
    replay = evaluate_market_cipher_replay(bars_by_symbol, signals, replay_config)
    source_identity = audit_market_cipher_sources(
        mc_scalper_root, market_cipher_cli_root
    )
    source_identity["backtest_lab"] = inspect_backtest_lab_sources(backtest_lab_root)
    report = _report(
        start,
        end,
        segment,
        profile,
        robustness_name,
        replay_config,
        source_identity,
        evidence,
        signals,
        replay,
        signal_minutes,
    )
    return MarketCipherStrategyResearchRun(report, signals, _trade_frame(replay))


def _symbol_inputs(
    database_path: Path,
    source_root: Path,
    funding_paths: tuple[Path, ...],
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    profile: HulkResearchProfile,
    bar_minutes: int,
    candle_bundle: Path | None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    source_evidence: dict[str, object] = {"source": "canonical_trade_5m_bars"}
    if candle_bundle is None:
        inputs = load_cipher_ohlcv(
            database_path,
            symbol,
            start.to_pydatetime(),
            end.to_pydatetime(),
            history_bars=1_440,
            horizon_bars=288,
        )
    else:
        inputs, source_evidence = load_cipher_ohlcv_from_candle_bundle(
            candle_bundle,
            symbol,
            start.to_pydatetime(),
            end.to_pydatetime(),
            history_bars=1_440,
            horizon_bars=288,
        )
    strategy = resample_cipher_bars(inputs.bars, bar_minutes=bar_minutes)
    indexed = strategy.set_index("bar_open_at")
    components = compute_market_cipher_signal_components(
        strategy, source_root, bar_minutes=bar_minutes
    )
    quality = build_hulk_quality_frame(
        indexed,
        supertrend_period=profile.supertrend_period,
        supertrend_multiplier=profile.supertrend_multiplier,
        adx_period=profile.adx_period,
        squeeze_period=profile.squeeze_period,
    )
    signals = _profile_signals(indexed, components, quality, profile, symbol)
    signals = signals.loc[
        signals["signal_time_utc"].ge(start) & signals["signal_time_utc"].lt(end)
    ].copy()
    funding = load_verified_hourly_funding(
        list(funding_paths),
        indexed.index.min(),
        indexed.index.max() + pd.Timedelta(minutes=bar_minutes),
    )
    replay_bars = attach_hourly_funding(indexed, funding)
    replay_bars["wave_cross"] = components["wave_cross"]
    data_evidence = _data_evidence(
        inputs.bars,
        replay_bars,
        funding_paths,
        bar_minutes,
    )
    data_evidence["ohlcv_source"] = source_evidence
    return replay_bars, signals, data_evidence


def _profile_signals(
    bars: pd.DataFrame,
    components: pd.DataFrame,
    quality: pd.DataFrame,
    profile: HulkResearchProfile,
    symbol: str,
) -> pd.DataFrame:
    config = RebuiltHulkConfig(
        minimum_score=profile.minimum_score,
        pivot_bars=profile.pivot_bars,
        adx_usable=profile.adx_usable,
        adx_trending=profile.adx_trending,
    )
    signals = select_hulk_expansion_moderate_adx(
        evaluate_rebuilt_hulk_signals(bars, components, quality, config)
    )
    if profile.side is not None:
        signals = signals.loc[signals["side"].eq(profile.side)].copy()
    signals["candidate"] = profile.name
    signals["symbol"] = symbol
    return signals


def _combined_signals(parts: list[pd.DataFrame]) -> pd.DataFrame:
    if not parts:
        raise ValueError("Hulk research requires at least one symbol")
    return (
        pd.concat(parts, ignore_index=True)
        .sort_values(["signal_time_utc", "symbol", "candidate"])
        .reset_index(drop=True)
    )


def _nominal_replay_config(bar_minutes: int) -> MarketCipherReplayConfig:
    signal_minutes = _validated_bar_minutes(bar_minutes)
    return MarketCipherReplayConfig(
        initial_equity=15_000.0,
        risk_fraction=0.0025,
        maximum_portfolio_risk_fraction=0.02,
        maximum_concurrent_positions=3,
        leverage=5.0,
        exit_variant="all_at_2r_control",
        minimum_stop_bps=20.0,
        maximum_stop_bps=75.0,
        target_r_multiple=3.0,
        maximum_hold_bars=(24 * 60) // signal_minutes,
        entry_fee_rate=0.00045,
        target_fee_rate=0.00015,
        market_exit_fee_rate=0.00045,
        liquidation_penalty_rate=0.01,
        entry_slippage_bps=2.0,
        market_exit_slippage_bps=2.0,
    )


def _report(
    start: pd.Timestamp,
    end: pd.Timestamp,
    segment: str,
    profile: HulkResearchProfile,
    robustness_name: str,
    config: MarketCipherReplayConfig,
    source_identity: dict[str, object],
    evidence: dict[str, object],
    signals: pd.DataFrame,
    replay: MarketCipherReplayReport,
    bar_minutes: int,
) -> dict[str, object]:
    return {
        "schema_version": "market_cipher_strategy_screen_v3",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "report_only": True,
        "execution_authority": "none",
        "place_attempted": False,
        "segment": segment,
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "profile": asdict(profile),
        "robustness": robustness_name,
        "bar_minutes": bar_minutes,
        "replay_parameters": asdict(config),
        "source_identity": source_identity,
        "data_evidence": evidence,
        "signal_count": len(signals),
        "performance": _performance(replay),
        "monthly_net_usd": _monthly(replay.trades),
        "direction_attribution": _attribution(replay.trades, "direction"),
        "symbol_attribution": _attribution(replay.trades, "symbol"),
        "replay": replay.to_dict(),
    }


def _performance(replay: MarketCipherReplayReport) -> dict[str, object]:
    return {
        "completed_trades": replay.completed_trades,
        "wins": replay.wins,
        "losses": replay.losses,
        "net_pnl_usd": replay.net_pnl_usd,
        "profit_factor": replay.profit_factor,
        "maximum_drawdown_pct": replay.maximum_drawdown_pct,
        "total_fees_usd": replay.total_fees_usd,
        "funding_cashflow_usd": replay.funding_cashflow_usd,
        "liquidations": replay.liquidations,
        "rejections": len(replay.rejections),
    }


def _attribution(
    trades: tuple[MarketCipherReplayTrade, ...], field: str
) -> dict[str, object]:
    labels = sorted({str(getattr(trade, field)) for trade in trades})
    return {
        label: _trade_summary(
            [trade for trade in trades if str(getattr(trade, field)) == label]
        )
        for label in labels
    }


def _trade_summary(trades: list[MarketCipherReplayTrade]) -> dict[str, object]:
    profits = sum(max(trade.net_pnl_usd, 0.0) for trade in trades)
    losses = -sum(min(trade.net_pnl_usd, 0.0) for trade in trades)
    return {
        "trades": len(trades),
        "net_pnl_usd": sum(trade.net_pnl_usd for trade in trades),
        "profit_factor": profits / losses if losses > 0.0 else None,
    }


def _monthly(trades: tuple[MarketCipherReplayTrade, ...]) -> dict[str, float]:
    values: dict[str, float] = {}
    for trade in trades:
        month = pd.Timestamp(trade.exit_time_utc).strftime("%Y-%m")
        values[month] = values.get(month, 0.0) + trade.net_pnl_usd
    return values


def _trade_frame(replay: MarketCipherReplayReport) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for trade in replay.trades:
        row = asdict(trade)
        row["exit_legs_json"] = json.dumps(row.pop("exit_legs"), sort_keys=True)
        rows.append(row)
    return pd.DataFrame(rows)


def _data_evidence(
    source_bars: pd.DataFrame,
    replay_bars: pd.DataFrame,
    funding_paths: tuple[Path, ...],
    bar_minutes: int,
) -> dict[str, object]:
    gaps = (
        replay_bars.index.to_series()
        .diff()
        .iloc[1:]
        .ne(pd.Timedelta(minutes=bar_minutes))
    )
    return {
        "source_5m_rows": len(source_bars),
        "strategy_bar_minutes": bar_minutes,
        "strategy_rows": len(replay_bars),
        "first_bar_utc": replay_bars.index.min().isoformat(),
        "last_bar_utc": replay_bars.index.max().isoformat(),
        "internal_gap_count": int(gaps.sum()),
        "missing_values": int(replay_bars.isna().sum().sum()),
        "replay_frame_sha256": frame_sha256(replay_bars),
        "funding_files": [
            {"path": str(path.resolve()), "sha256": _file_sha256(path)}
            for path in funding_paths
        ],
    }


def _validated_bar_minutes(value: int) -> int:
    if isinstance(value, bool) or value not in {15, 30}:
        raise ValueError("Market Cipher bar_minutes must be 15 or 30")
    return value


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _window(
    start: pd.Timestamp, end: pd.Timestamp
) -> tuple[pd.Timestamp, pd.Timestamp]:
    first, last = pd.Timestamp(start), pd.Timestamp(end)
    if first.tz is None or last.tz is None or first >= last:
        raise ValueError("Hulk research requires an ordered timezone-aware window")
    return first.tz_convert("UTC"), last.tz_convert("UTC")


def _symbols(
    symbols: tuple[str, ...],
    funding: dict[str, tuple[Path, ...]],
) -> tuple[str, ...]:
    normalized = tuple(symbol.strip().upper() for symbol in symbols)
    if not normalized or len(set(normalized)) != len(normalized):
        raise ValueError("Hulk research symbols must be non-empty and unique")
    if set(normalized) != set(funding):
        raise ValueError("Hulk research requires explicit funding for every symbol")
    if any(symbol not in CIPHER_RESEARCH_SYMBOLS for symbol in normalized):
        raise ValueError("Hulk research symbol is unsupported")
    return normalized


def _candle_bundles(
    bundles: dict[str, Path], symbols: tuple[str, ...]
) -> dict[str, Path]:
    normalized = {
        symbol.strip().upper(): Path(path) for symbol, path in bundles.items()
    }
    if len(normalized) != len(bundles) or not set(normalized).issubset(symbols):
        raise ValueError("Hulk candle bundles must map unique requested symbols")
    return normalized
