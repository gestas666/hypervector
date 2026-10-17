"""Convert research OHLCV DataFrames to Nautilus ``Bar`` lists (offline).

Uses ``BarDataWrangler`` (same path as Nautilus custom-CSV examples). Does not
claim CEX/research bars equal Hyperliquid book; this is a sim feed adapter only.

Research frames label each bar by its open time. :func:`dataframe_to_bars`
stamps Nautilus bars at the bar close by default (Nautilus convention for
EXTERNAL bars), so the engine never sees a close price before the bar has
closed; :func:`bar_open_label_ns` recovers the research label.
"""

from __future__ import annotations

import io
import re
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import pandas as pd
from nautilus_trader.model.currencies import BTC, USDT
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import CryptoPerpetual
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.persistence.wranglers import BarDataWrangler

from hypervector.nautilus.venue_spec import research_symbol_to_instrument

if TYPE_CHECKING:
    from hypervector.nautilus.load_export import StrategyLoadout

_OHLCV = ("open", "high", "low", "close", "volume")

# Research timeframe tokens → Nautilus bar aggregation token
_TF_MAP = {
    "1m": "1-MINUTE",
    "3m": "3-MINUTE",
    "5m": "5-MINUTE",
    "15m": "15-MINUTE",
    "30m": "30-MINUTE",
    "1h": "1-HOUR",
    "4h": "4-HOUR",
    "1d": "1-DAY",
}


def synthetic_btc_perp_instrument(
    venue: str = "HYPERLIQUID",
    symbol: str = "BTC-PERP",
    *,
    maker_fee: Decimal = Decimal("0.00015"),
    taker_fee: Decimal = Decimal("0.00045"),
    margin_init: Decimal = Decimal("0.025"),
    margin_maint: Decimal = Decimal("0.0125"),
) -> CryptoPerpetual:
    """Minimal BTC perpetual for offline backtests (no network).

    Defaults to venue ``HYPERLIQUID``; pass ``SIM`` for pure sim identity.
    Price/size increments are coarse stubs sufficient for bar wrangling — not
    a live HL instrument definition. Fee and margin rates default to the
    historical stub values; the Phase 2 runner passes the export cost model
    and leverage-derived margins explicitly.
    """
    return CryptoPerpetual(
        instrument_id=InstrumentId(symbol=Symbol(symbol), venue=Venue(venue)),
        raw_symbol=Symbol(symbol),
        base_currency=BTC,
        quote_currency=USDT,
        settlement_currency=USDT,
        is_inverse=False,
        price_precision=1,
        size_precision=3,
        price_increment=Price.from_str("0.1"),
        size_increment=Quantity.from_str("0.001"),
        max_quantity=Quantity.from_str("1000.000"),
        min_quantity=Quantity.from_str("0.001"),
        max_notional=None,
        min_notional=Money(10.00, USDT),
        max_price=Price.from_str("1000000.0"),
        min_price=Price.from_str("0.1"),
        margin_init=Decimal(margin_init),
        margin_maint=Decimal(margin_maint),
        maker_fee=Decimal(maker_fee),
        taker_fee=Decimal(taker_fee),
        ts_event=0,
        ts_init=0,
    )


def bar_type_from_loadout(
    loadout: StrategyLoadout | Any,
    *,
    venue: str = "HYPERLIQUID",
    price_type: str = "LAST",
    aggregation_source: str = "EXTERNAL",
) -> str:
    """Build a Nautilus bar-type string from a :class:`StrategyLoadout`.

    Example: ``BTC-PERP.HYPERLIQUID-1-MINUTE-LAST-EXTERNAL``

    Uses loadout ``symbol`` / ``timeframe`` (defaults BTC / 1m). Research symbol
    ``BTC`` is mapped to instrument id ``BTC-PERP``.
    """
    symbol = str(getattr(loadout, "symbol", None) or "BTC")
    timeframe = str(getattr(loadout, "timeframe", None) or "1m")
    instrument_symbol = _research_symbol_to_instrument(symbol)
    agg = _timeframe_to_aggregation(timeframe)
    return f"{instrument_symbol}.{venue}-{agg}-{price_type}-{aggregation_source}"


def dataframe_to_bars(
    df: pd.DataFrame,
    bar_type: str | BarType,
    instrument: CryptoPerpetual | Any,
    *,
    timestamp_at: Literal["close", "open"] = "close",
) -> list[Bar]:
    """Convert a research OHLCV frame into a list of Nautilus ``Bar`` objects.

    Parameters
    ----------
    df:
        Research OHLCV (UTC ``timestamp`` column or index; open/high/low/close/volume).
        Extra columns (e.g. ``source``) are dropped. Research timestamps are
        bar-open labels.
    bar_type:
        Nautilus bar type string (e.g. from :func:`bar_type_from_loadout`) or
        a :class:`BarType` instance.
    instrument:
        Instrument definition for ``BarDataWrangler`` (price/size precision).
        Required — the wrangler needs it even when ``bar_type`` is a string.
        Use :func:`synthetic_btc_perp_instrument` for offline tests.
    timestamp_at:
        ``"close"`` (default, Nautilus convention for EXTERNAL bars) stamps
        ``ts_event``/``ts_init`` at the bar close (open label + bar interval),
        so the engine clock, fills and positions never see a bar's close
        price before the bar has closed. ``"open"`` keeps the research label.

    Returns
    -------
    list[Bar]
        One bar per input row, ordered by timestamp.

    Notes
    -----
    Offline conversion only — does not start a backtest engine. Use
    :func:`bar_open_label_ns` to recover the research label from a bar.
    """
    work = _to_wrangler_ohlcv(df)
    bt = BarType.from_str(bar_type) if isinstance(bar_type, str) else bar_type
    if timestamp_at == "close":
        work.index = work.index + bar_interval(bt)
    elif timestamp_at != "open":
        raise ValueError(
            f"timestamp_at must be 'close' or 'open', got {timestamp_at!r}"
        )
    wrangler = BarDataWrangler(bt, instrument)
    # pandas>=3 CoW: homogeneous float frames expose read-only .values; Cython
    # ``double[:]`` in BarDataWrangler rejects them. Materialize via CSV like
    # the official custom-CSV example so the block is writeable.
    work = _writeable_ohlcv_frame(work)
    return wrangler.process(work)


def _research_symbol_to_instrument(symbol: str) -> str:
    """``BTC`` → ``BTC-PERP`` (single mapping shared with :mod:`venue_spec`)."""
    return research_symbol_to_instrument(symbol)


def bar_interval(bar_type: str | BarType) -> pd.Timedelta:
    """Wall-clock length of one bar for a time-aggregated bar type."""
    bt = BarType.from_str(bar_type) if isinstance(bar_type, str) else bar_type
    return pd.Timedelta(bt.spec.timedelta)


def bar_interval_ns(bar_type: str | BarType) -> int:
    return int(bar_interval(bar_type).value)


def bar_open_label_ns(bar: Bar, *, timestamp_at: str = "close") -> int:
    """Research bar-open label (ns) for a bar built by :func:`dataframe_to_bars`."""
    ts = int(bar.ts_event)
    if timestamp_at == "close":
        return ts - bar_interval_ns(bar.bar_type)
    return ts


def _timeframe_to_aggregation(timeframe: str) -> str:
    tf = timeframe.strip().lower()
    if tf in _TF_MAP:
        return _TF_MAP[tf]
    # bare forms already in Nautilus style
    if re.fullmatch(r"\d+-(MINUTE|HOUR|DAY|SECOND|WEEK|MONTH)", timeframe.upper()):
        return timeframe.upper()
    # e.g. "15min", "1hour"
    m = re.fullmatch(r"(\d+)\s*(m|min|minute|minutes|h|hr|hour|hours|d|day|days)", tf)
    if m:
        n, unit = m.group(1), m.group(2)
        if unit.startswith("m"):
            return f"{n}-MINUTE"
        if unit.startswith("h"):
            return f"{n}-HOUR"
        if unit.startswith("d"):
            return f"{n}-DAY"
    raise ValueError(f"unsupported timeframe for Nautilus bar type: {timeframe!r}")


def _to_wrangler_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """UTC timestamp index + open/high/low/close/volume float columns."""
    if df is None or len(df) == 0:
        raise ValueError("dataframe_to_bars requires a non-empty OHLCV frame")

    work = df.copy()
    if "timestamp" in work.columns:
        ts = pd.to_datetime(work["timestamp"], utc=True)
        work = work.drop(columns=["timestamp"])
        work.index = pd.DatetimeIndex(ts, name="timestamp")
    elif not isinstance(work.index, pd.DatetimeIndex):
        raise ValueError("OHLCV frame needs a timestamp column or DatetimeIndex")
    else:
        work.index = pd.DatetimeIndex(
            pd.to_datetime(work.index, utc=True), name="timestamp"
        )

    missing = [c for c in _OHLCV if c not in work.columns]
    if missing:
        raise ValueError(f"OHLCV missing columns: {missing}")

    out = work.loc[:, list(_OHLCV)].sort_index()
    for col in _OHLCV:
        out[col] = out[col].astype(np.float64)
    # OHLC sanity for Bar validation (high >= max(o,c), low <= min(o,c))
    # Research fixtures already satisfy this; leave values as-is.
    return out


def _writeable_ohlcv_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Return an OHLCV frame whose ``.values`` is writeable for BarDataWrangler."""
    # Fast path: mixed float/int dtypes force a writeable values copy under CoW.
    vol = df["volume"].to_numpy(dtype=np.float64, copy=True)
    if np.all(np.isfinite(vol)) and np.all(vol == np.round(vol)):
        out = df.copy()
        out["volume"] = vol.astype(np.int64)
        if out.to_numpy().flags.writeable or out.values.flags.writeable:
            return out

    # General path: CSV materialization (matches Nautilus example_01 CSV load).
    serial = df.copy()
    if getattr(serial.index, "tz", None) is not None:
        serial.index = serial.index.tz_convert("UTC").tz_localize(None)
    buf = io.StringIO()
    serial.to_csv(buf)
    buf.seek(0)
    loaded = pd.read_csv(buf, index_col=0, parse_dates=True)
    loaded.index.name = "timestamp"
    return loaded.astype({c: np.float64 for c in _OHLCV})
