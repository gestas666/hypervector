"""Reviewed local Backtest Lab adapter with Pine-fidelity Cipher corrections."""

from __future__ import annotations

from hashlib import sha256
import importlib
from pathlib import Path
import sys
from typing import Callable

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from hypervector.research.cipher_suite_signals import (
    cipher_b_cross_events_from_waves,
    cipher_b_events_from_waves,
    cipher_b_states_from_waves,
    pine_aroon_bullish,
    pine_mfi_source,
    state_from_events,
)
from hypervector.research.market_cipher_components import (
    build_market_cipher_components,
)


_PINE_FILES: dict[str, str] = {
    "cipher_a_pine_sha256": "cipher_a.pine",
    "cipher_b_pine_sha256": "cipher_b.pine",
    "cipher_dbsi_pine_sha256": "cipher_dbsi.pine",
    "krown_rsi_ema_pine_sha256": "krown_rsi_ema.pine",
}


def inspect_backtest_lab_sources(root: Path) -> dict[str, str]:
    """Hash the exact local Pine files and reviewed Python primitive tree."""
    resolved = root.resolve()
    _validate_root(resolved)
    identity = {
        key: _file_sha256(resolved / "indicators" / filename)
        for key, filename in _PINE_FILES.items()
    }
    identity["python_primitives_tree_sha256"] = _tree_sha256(
        resolved / "src" / "backtest_lab" / "market_decryptor"
    )
    identity["root"] = str(resolved)
    return identity


def compute_cipher_component_states(
    bars: pd.DataFrame,
    backtest_lab_root: Path,
    *,
    bar_minutes: int,
) -> pd.DataFrame:
    """Compute corrected, causal Cipher A/B/DBSI states for completed bars."""
    frame = _validated_bars(bars)
    root = backtest_lab_root.resolve()
    _validate_root(root)
    _activate_package(root)
    if bar_minutes < 1:
        raise ValueError("Cipher bar duration must be positive")
    return _compute_blockwise(
        frame,
        bar_minutes=bar_minutes,
        columns=("cipher_a", "cipher_b", "cipher_dbsi"),
        compute=_compute_contiguous_states,
    )


def compute_cipher_bundle_components(
    bars: pd.DataFrame,
    backtest_lab_root: Path,
    *,
    bar_minutes: int,
) -> pd.DataFrame:
    """Compute documented A-trend/B-trigger components and optional DBSI state."""
    frame = _validated_bars(bars)
    root = backtest_lab_root.resolve()
    _validate_root(root)
    _activate_package(root)
    if bar_minutes < 1:
        raise ValueError("Cipher bar duration must be positive")
    return _compute_blockwise(
        frame,
        bar_minutes=bar_minutes,
        columns=(
            "cipher_a_trend",
            "cipher_b_trigger",
            "cipher_b_cross_trigger",
            "cipher_b_money_flow",
            "cipher_dbsi",
        ),
        compute=_compute_contiguous_bundle,
    )


def compute_market_cipher_signal_components(
    bars: pd.DataFrame,
    backtest_lab_root: Path,
    *,
    bar_minutes: int,
) -> pd.DataFrame:
    """Compute causal raw components used by recovered MC strategies."""
    frame = _validated_bars(bars)
    root = backtest_lab_root.resolve()
    _validate_root(root)
    _activate_package(root)
    if bar_minutes < 1:
        raise ValueError("Market Cipher bar duration must be positive")
    gaps = frame.index.to_series().diff().ne(pd.Timedelta(minutes=bar_minutes))
    blocks = [
        _compute_market_cipher_block(block, bar_minutes)
        for _, block in frame.groupby(gaps.cumsum().to_numpy(), sort=True)
    ]
    return pd.concat(blocks).sort_index()


def _compute_blockwise(
    frame: pd.DataFrame,
    *,
    bar_minutes: int,
    columns: tuple[str, ...],
    compute: Callable[[pd.DataFrame], pd.DataFrame],
) -> pd.DataFrame:
    """Compute one indicator frame per gap-free block with fresh warmup."""
    output = pd.DataFrame(0, index=frame.index, columns=list(columns), dtype=np.int8)
    gaps = frame.index.to_series().diff().ne(pd.Timedelta(minutes=bar_minutes))
    for _, block in frame.groupby(gaps.cumsum().to_numpy(), sort=True):
        if len(block) < 240:
            continue
        computed = compute(block)
        computed.iloc[:239, :] = 0
        output.loc[block.index, :] = computed
    return output


def _compute_contiguous_states(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute component states for one gap-free block."""
    opening, high, low, close, volume = (
        frame[column].to_numpy(dtype=np.float64)
        for column in ("open", "high", "low", "close", "volume")
    )
    cipher_a_state = _cipher_a_state(opening, high, low, close)
    cipher_b_state = _cipher_b_state(high, low, close)
    dbsi_state = _dbsi_state(frame.index, opening, high, low, close, volume)
    return pd.DataFrame(
        {
            "cipher_a": cipher_a_state,
            "cipher_b": cipher_b_state,
            "cipher_dbsi": dbsi_state,
        },
        index=frame.index,
    )


def _compute_contiguous_bundle(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute the documented A environment and B timing contract."""
    opening, high, low, close, volume = (
        frame[column].to_numpy(dtype=np.float64)
        for column in ("open", "high", "low", "close", "volume")
    )
    extreme_trigger, cross_trigger = _cipher_b_triggers(high, low, close)
    return pd.DataFrame(
        {
            "cipher_a_trend": _cipher_a_ribbon_trend(close),
            "cipher_b_trigger": extreme_trigger,
            "cipher_b_cross_trigger": cross_trigger,
            "cipher_b_money_flow": _cipher_b_money_flow(opening, high, low, close),
            "cipher_dbsi": _dbsi_state(frame.index, opening, high, low, close, volume),
        },
        index=frame.index,
    )


def _compute_market_cipher_block(frame: pd.DataFrame, bar_minutes: int) -> pd.DataFrame:
    """Compute one gap-free block without sharing future state."""
    high, low, close = (
        frame[column].to_numpy(dtype=np.float64) for column in ("high", "low", "close")
    )
    moving = importlib.import_module("backtest_lab.market_decryptor.ta.moving_averages")
    oscillators = importlib.import_module(
        "backtest_lab.market_decryptor.ta.oscillators"
    )
    krown = importlib.import_module(
        "backtest_lab.market_decryptor.indicators.krown_rsi_ema"
    )
    wt1, wt2 = _cipher_b_waves(high, low, close)
    stoch_k, stoch_d = oscillators.stoch_rsi(close, 14, 14, 3, 3, True)
    krown_result = krown.compute(close)
    return build_market_cipher_components(
        frame,
        wt1=wt1,
        wt2=wt2,
        ema_11=moving.ema(close, 11),
        ema_15=moving.ema(close, 15),
        ema_34=moving.ema(close, 34),
        rsi_14=oscillators.rsi(close, 14),
        stoch_k=stoch_k,
        stoch_d=stoch_d,
        krown_rsi=krown_result.rsi,
        krown_rsi_ema=krown_result.rsi_ema,
        krown_direction=np.where(
            krown_result.is_bullish,
            1,
            np.where(krown_result.is_bearish, -1, 0),
        ).astype(np.int8),
        bar_minutes=bar_minutes,
    )


def _cipher_a_ribbon_trend(close: NDArray[np.float64]) -> NDArray[np.int8]:
    """Return Pine Cipher A's persistent EMA 11/34 ribbon direction."""
    moving = importlib.import_module("backtest_lab.market_decryptor.ta.moving_averages")
    ema_2 = moving.ema(close, 11)
    ema_8 = moving.ema(close, 34)
    valid = np.isfinite(ema_2) & np.isfinite(ema_8)
    return np.where(
        valid & (ema_2 > ema_8),
        1,
        np.where(valid & (ema_2 < ema_8), -1, 0),
    ).astype(np.int8)


def _cipher_a_state(
    opening: NDArray[np.float64],
    high: NDArray[np.float64],
    low: NDArray[np.float64],
    close: NDArray[np.float64],
) -> NDArray[np.int8]:
    config_module = importlib.import_module("backtest_lab.market_decryptor.config")
    cipher_a = importlib.import_module(
        "backtest_lab.market_decryptor.indicators.cipher_a"
    )
    result = cipher_a.compute(opening, high, low, close, config_module.CipherAConfig())
    long_events = np.asarray(result.blue_triangle) | np.asarray(result.bull_candle)
    short_events = np.asarray(result.red_diamond) | np.asarray(result.blood_diamond)
    return state_from_events(long_events, short_events)


def _cipher_b_state(
    high: NDArray[np.float64],
    low: NDArray[np.float64],
    close: NDArray[np.float64],
) -> NDArray[np.int8]:
    wt1, wt2 = _cipher_b_waves(high, low, close)
    return cipher_b_states_from_waves(wt1, wt2)


def _cipher_b_triggers(
    high: NDArray[np.float64],
    low: NDArray[np.float64],
    close: NDArray[np.float64],
) -> tuple[NDArray[np.int8], NDArray[np.int8]]:
    """Return Cipher B extreme and ordinary WaveTrend crossing pulses."""
    wt1, wt2 = _cipher_b_waves(high, low, close)
    return (
        cipher_b_events_from_waves(wt1, wt2),
        cipher_b_cross_events_from_waves(wt1, wt2),
    )


def _cipher_b_money_flow(
    opening: NDArray[np.float64],
    high: NDArray[np.float64],
    low: NDArray[np.float64],
    close: NDArray[np.float64],
) -> NDArray[np.int8]:
    """Return the Pine Cipher B RSI+MFI area direction around zero."""
    spread = high - low
    raw = np.full(len(close), np.nan, dtype=np.float64)
    valid = np.isfinite(spread) & (spread != 0.0)
    raw[valid] = (close[valid] - opening[valid]) / spread[valid] * 150.0
    flow = pd.Series(raw).rolling(60).mean().to_numpy() - 2.5
    return np.where(
        np.isfinite(flow) & (flow > 0.0),
        1,
        np.where(np.isfinite(flow) & (flow < 0.0), -1, 0),
    ).astype(np.int8)


def _cipher_b_waves(
    high: NDArray[np.float64],
    low: NDArray[np.float64],
    close: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Compute exact-source Cipher B WaveTrend 9/12/3 waves."""
    wavetrend_module = importlib.import_module(
        "backtest_lab.market_decryptor.ta.wavetrend"
    )
    source = (high + low + close) / 3.0
    wt1, wt2 = wavetrend_module.wavetrend(source, 9, 12, 3)
    return wt1, wt2


def _dbsi_state(
    index: pd.DatetimeIndex,
    opening: NDArray[np.float64],
    high: NDArray[np.float64],
    low: NDArray[np.float64],
    close: NDArray[np.float64],
    volume: NDArray[np.float64],
) -> NDArray[np.int8]:
    dbsi = importlib.import_module("backtest_lab.market_decryptor.indicators.dbsi")
    oscillators = importlib.import_module(
        "backtest_lab.market_decryptor.ta.oscillators"
    )
    moving = importlib.import_module("backtest_lab.market_decryptor.ta.moving_averages")
    timestamps = (index.view("int64") // 1_000_000).astype(np.int64)
    conditions = dbsi._compute_all_conditions(
        opening, high, low, close, volume, timestamps, len(close)
    )
    conditions[1] = _finite_gt(oscillators.cci(close, 20), 0.0)
    conditions[16] = pine_aroon_bullish(high, low, period=14)
    conditions[24] = _finite_gt(pine_mfi_source(close, volume, period=14), 50.0)
    conditions[31] = _finite_gt_pair(close, moving.ema(close, 20))
    bull = np.sum(np.stack(conditions), axis=0, dtype=np.int16)
    bear = 33 - bull
    return np.where(bull > bear, 1, np.where(bear > bull, -1, 0)).astype(np.int8)


def _finite_gt(values: NDArray[np.float64], threshold: float) -> NDArray[np.bool_]:
    return np.isfinite(values) & (values > threshold)


def _finite_gt_pair(
    left: NDArray[np.float64],
    right: NDArray[np.float64],
) -> NDArray[np.bool_]:
    return np.isfinite(left) & np.isfinite(right) & (left > right)


def _validated_bars(bars: pd.DataFrame) -> pd.DataFrame:
    required = {"bar_open_at", "open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(bars.columns))
    if missing:
        raise ValueError(f"Cipher adapter bars missing columns: {missing}")
    frame = bars.loc[
        :, ["bar_open_at", "open", "high", "low", "close", "volume"]
    ].copy()
    index = pd.DatetimeIndex(frame.pop("bar_open_at"))
    if index.tz is None or not index.is_monotonic_increasing or index.has_duplicates:
        raise ValueError("Cipher adapter timestamps must be ordered, unique, and aware")
    if frame.empty:
        raise ValueError("Cipher adapter bars must be non-empty")
    values = frame.to_numpy(dtype=np.float64)
    if not np.isfinite(values).all() or (values[:, :4] <= 0.0).any():
        raise ValueError(
            "Cipher adapter OHLCV values must be finite with positive prices"
        )
    if (values[:, 4] < 0.0).any():
        raise ValueError("Cipher adapter volume must be non-negative")
    frame.index = index
    return frame


def _validate_root(root: Path) -> None:
    expected = [root / "indicators" / filename for filename in _PINE_FILES.values()]
    expected.append(root / "src" / "backtest_lab" / "market_decryptor")
    missing = [str(path) for path in expected if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Backtest Lab Cipher sources missing: {missing}")


def _activate_package(root: Path) -> None:
    source = str(root / "src")
    if source not in sys.path:
        sys.path.insert(0, source)
    module = importlib.import_module("backtest_lab.market_decryptor")
    module_path = Path(str(module.__file__)).resolve()
    if not module_path.is_relative_to(root):
        raise RuntimeError(f"Loaded backtest_lab from unexpected path: {module_path}")


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_sha256(root: Path) -> str:
    digest = sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()
