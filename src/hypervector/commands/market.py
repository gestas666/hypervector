"""Market command handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from hypervector.commands.common import (
    CommandRefused,
    _ensure_root,
    _load_bars,
    bars_window,
    cache_age_options,
    history_failure,
    json_safe,
    print_error,
)


def cmd_book_record(args: argparse.Namespace) -> int:
    """Poll HL public L2 and append snapshots under data/cache/book/."""
    from hypervector.data.book_record import append_snapshot, run_book_recorder

    max_errors = int(getattr(args, "max_consecutive_errors", 10))
    if max_errors < 1:
        raise CommandRefused("--max-consecutive-errors must be at least 1")
    paths = _ensure_root(args)
    symbol = str(getattr(args, "symbol", "BTC"))
    once = bool(getattr(args, "once", False))
    if once:
        try:
            row = append_snapshot(paths.root, symbol)
        except Exception as exc:  # noqa: BLE001
            return print_error(args, exc)
        print(json.dumps({"ok": True, "mode": "once", **row}, indent=2, default=str))
        return 0

    interval = float(args.interval_seconds)
    max_n = getattr(args, "max_snapshots", None)
    stop = getattr(args, "stop_file", None)
    try:
        result = run_book_recorder(
            paths.root,
            symbol=symbol,
            interval_secs=interval,
            max_snapshots=int(max_n) if max_n is not None else None,
            stop_file=stop,
            max_consecutive_errors=max_errors,
        )
    except Exception as exc:  # noqa: BLE001
        return print_error(args, exc)
    print(json.dumps(result, indent=2, default=str))
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    """Load (cache-first) research history and report its provenance and window.

    A failed load (network, failed backfill, cache miss offline) prints one
    error document with the loader's notes and exits 1.
    """
    from hypervector.data.pipeline import cache_key

    cache_age_options(args)
    try:
        df, prov = _load_bars(args)
    except (RuntimeError, OSError) as exc:
        return history_failure(args, exc)
    served = prov.get("cache_path") if isinstance(prov, dict) else None
    if served:
        # The entry the loader actually read or wrote (a strict load may be
        # served by the _hlonly key or by an all-HL default entry).
        cache_path = Path(str(served))
    else:
        key = cache_key(
            args.symbol,
            args.timeframe,
            args.lookback,
            strict_hl_only=bool(getattr(args, "strict_hl_only", False)),
        )
        cache_path = Path(args.data_root) / "cache" / f"{key}.parquet"
    start, end = _bar_window(df)
    dataset = {
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "start": start,
        "end": end,
        "rows": len(df),
        "sources": prov.get("sources") if isinstance(prov, dict) else None,
        "cache_path": str(cache_path.resolve()),
    }
    print(
        json.dumps(
            json_safe(
                {
                    "ok": True,
                    "bars": len(df),
                    "symbol": args.symbol,
                    "timeframe": args.timeframe,
                    "lookback_days": args.lookback,
                    "data_window": bars_window(df),
                    "provenance": prov,
                    "artifacts": {"dataset": dataset},
                }
            ),
            indent=2,
            default=str,
        )
    )
    return 0


def _bar_window(df: object) -> tuple[str | None, str | None]:
    """First and last bar open times as ISO strings (None when empty)."""
    import pandas as pd

    frame = df if isinstance(df, pd.DataFrame) else pd.DataFrame()
    if frame.empty:
        return None, None
    if "timestamp" in frame.columns:
        stamps = pd.to_datetime(frame["timestamp"], utc=True)
    elif isinstance(frame.index, pd.DatetimeIndex):
        stamps = pd.Series(frame.index)
    else:
        return None, None
    return stamps.min().isoformat(), stamps.max().isoformat()


def cmd_book_align(args: argparse.Namespace) -> int:
    """Align L2 orderbook snapshot data with OHLCV bars and export parquet.

    The JSON reports how many bars carry a real snapshot (``matched_bars``,
    ``book_coverage``); unmatched bars hold missing values, printed as null.
    ``--min-coverage`` (opt-in) turns low coverage into ok:false and exit 1.
    """
    from hypervector.data.book_align import (
        align_orderbook_to_ohlcv,
        book_coverage_summary,
        load_l2_jsonl,
    )

    minimum = getattr(args, "min_coverage", None)
    if minimum is not None and not 0.0 <= float(minimum) <= 1.0:
        raise CommandRefused("--min-coverage must be within 0..1")
    book_path = Path(args.book_path)
    if not book_path.is_file():
        raise CommandRefused(f"book path not found: {book_path}")
    cache_age_options(args)
    root = Path(args.data_root)
    try:
        df_bars, provenance = _load_bars(args)
    except (RuntimeError, OSError) as exc:
        return history_failure(args, exc)

    df_book = load_l2_jsonl(book_path)

    aligned = align_orderbook_to_ohlcv(df_bars, df_book)
    coverage = book_coverage_summary(aligned)
    out_dir = root / "cache" / "aligned"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{args.symbol}_{args.timeframe}_aligned_book.parquet"
    aligned.to_parquet(out_file)

    columns = [
        column
        for column in ("close", "spread_bps", "obi_5", "book_depth_ratio")
        if column in aligned.columns
    ]
    below = minimum is not None and coverage["book_coverage"] < float(minimum)
    out = {
        "ok": not below,
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "bars_count": len(aligned),
        "book_records": len(df_book),
        "aligned_path": str(out_file),
        "matched_bars": coverage["matched_bars"],
        "book_coverage": coverage["book_coverage"],
        "book_first_ts_utc": coverage["book_first_ts_utc"],
        "book_last_ts_utc": coverage["book_last_ts_utc"],
        "max_tolerance_ms": coverage["max_tolerance_ms"],
        "min_coverage": minimum,
        "warnings": coverage["warnings"],
        "data_window": bars_window(df_bars),
        "data_provenance": provenance,
        "sample": aligned[columns].tail(3).to_dict(orient="records"),
    }
    rendered = json.dumps(json_safe(out), indent=2, default=str, allow_nan=False)
    if below:
        print(rendered, file=sys.stderr)
        return 1
    print(rendered)
    return 0
