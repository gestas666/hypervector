"""Common command handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from hypervector.config import DEFAULT_LOOKBACK
from typing import TYPE_CHECKING
from hypervector.infra import DataPaths, ensure_data_layout

if TYPE_CHECKING:
    import pandas as pd

    from hypervector.sweep.exits import ExitConfig

SECRET_ENV_WALLET = "HYPERVECTOR_HL_WALLET_ADDRESS"
SECRET_ENV_API_KEY = "HYPERVECTOR_HL_API_PRIVATE_KEY"


class CommandRefused(Exception):
    """A refusal before any side effect; the CLI maps it to exit code 2."""


def exit_config_from_args(args: argparse.Namespace) -> ExitConfig:
    """Build the shared exit model from the canonical exits fragment."""
    from hypervector.sweep.exits import ExitConfig

    return ExitConfig(
        mode=args.exit_mode,
        sl_pct=float(args.sl_pct),
        rr=float(args.rr),
        atr_length=int(args.atr_length),
        sl_atr_mult=float(args.sl_atr_mult),
        trail_atr_mult=float(args.trail_atr_mult),
    )


def _secrets_present() -> bool:
    """True when both live secret env vars are set (values never logged)."""
    return bool(os.environ.get(SECRET_ENV_WALLET)) and bool(
        os.environ.get(SECRET_ENV_API_KEY)
    )


def _default_data_root() -> Path:
    return Path("data")


def _ensure_root(args: argparse.Namespace) -> DataPaths:
    """Create I2 layout under --data-root before any IO."""
    return ensure_data_layout(Path(args.data_root))


def cache_age_options(args: argparse.Namespace) -> dict[str, object]:
    """``max_cache_age`` for the history loader, only when the operator chose one.

    ``--pin-cache`` serves whatever is cached (``max_cache_age=None``);
    ``--max-cache-age-hours H`` refreshes only windows older than H hours.
    Neither flag keeps the loader's own default. Both together are refused.
    """
    hours = getattr(args, "max_cache_age_hours", None)
    pinned = getattr(args, "pin_cache", False) is True
    if pinned and hours is not None:
        raise CommandRefused("--pin-cache and --max-cache-age-hours are exclusive")
    if pinned:
        if getattr(args, "force", False):
            raise CommandRefused("--pin-cache and --refresh are exclusive")
        return {"max_cache_age": None}
    if hours is None:
        return {}
    import pandas as pd

    return {"max_cache_age": pd.Timedelta(hours=float(hours))}


def _load_bars(args: argparse.Namespace) -> tuple[pd.DataFrame, dict[str, object]]:
    """Load OHLCV from cache or live HL→Binance→Bybit pipeline."""
    from hypervector.data.pipeline import load_research_history

    options = cache_age_options(args)
    _ensure_root(args)
    return load_research_history(
        args.data_root,
        symbol=getattr(args, "symbol", "BTC"),
        timeframe=getattr(args, "timeframe", "1m"),
        lookback_days=getattr(args, "lookback", DEFAULT_LOOKBACK),
        strict_hl_only=getattr(args, "strict_hl_only", False),
        force_refresh=getattr(args, "force", False),
        **options,
    )


BOOK_SQLITE_SUFFIXES = frozenset({".sqlite", ".sqlite3", ".db", ".zst"})


def book_path_or_refuse(args: argparse.Namespace) -> Path | None:
    """The explicit ``--book-path`` as a file, or a refusal before any data load."""
    value = getattr(args, "book_path", None)
    if not value:
        return None
    path = Path(value)
    if not path.is_file():
        raise CommandRefused(f"book path not found: {path}")
    return path


def align_book(bars: pd.DataFrame, path: Path, symbol: str) -> pd.DataFrame:
    """Align a JSONL snapshot file or SQLite feature samples onto the bars."""
    from hypervector.data import book_align

    if path.suffix.lower() in BOOK_SQLITE_SUFFIXES:
        book = book_align.load_l2_sqlite_feature_samples(path, coin=symbol)
    else:
        book = book_align.load_l2_jsonl(path)
    return book_align.align_orderbook_to_ohlcv(bars, book)


def bars_window(frame: object) -> dict[str, object]:
    """First/last bar time and bar count of a loaded frame (the board format)."""
    import pandas as pd

    from hypervector.sweep.autotune_provenance import bars_window as window

    if not isinstance(frame, pd.DataFrame):
        return {"first_bar_utc": None, "last_bar_utc": None, "bar_count": 0}
    return window(frame)


def json_safe(value: object) -> object:
    """Replace NaN and infinities with None (strict JSON has no NaN token)."""
    import math

    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if type(value).__module__ == "numpy" and hasattr(value, "item"):
        try:
            return json_safe(value.item())  # numpy scalar
        except (TypeError, ValueError):
            return value
    return value


def history_failure(args: argparse.Namespace, exc: BaseException) -> int:
    """Report a failed history load as one error document on stderr (exit 1).

    The loader's notes (for example the HL-only cache key it kept after a
    failed backfill) are carried over, with a hint for the next step.
    """
    import json
    import sys

    notes = [str(note) for note in getattr(exc, "__notes__", ()) or ()]
    if any("--strict-hl-only" in note for note in notes):
        hint = "rerun with --strict-hl-only to use the HL bars already fetched"
    elif isinstance(exc, FileNotFoundError):
        hint = "no cached window for this request; allow network access to fetch it"
    else:
        hint = (
            "check network access and retry, or pass --pin-cache to serve an "
            "existing cached window as is"
        )
    report = {
        "ok": False,
        "command": getattr(args, "command", None),
        "error_type": type(exc).__name__,
        "error": str(exc),
        "notes": notes,
        "hint": hint,
    }
    print(json.dumps(report), file=sys.stderr)
    return 1
