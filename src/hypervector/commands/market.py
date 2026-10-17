"""Market command handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from hypervector.commands.common import _ensure_root, _load_bars


def cmd_book_record(args: argparse.Namespace) -> int:
    """Poll HL public L2 and append snapshots under data/cache/book/."""
    from hypervector.data.book_record import append_snapshot, run_book_recorder

    paths = _ensure_root(args)
    symbol = str(getattr(args, "symbol", "BTC"))
    once = bool(getattr(args, "once", False))
    if once:
        try:
            row = append_snapshot(paths.root, symbol)
        except Exception as exc:  # noqa: BLE001
            print(
                json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr
            )
            return 1
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
        )
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    df, prov = _load_bars(args)
    print(
        json.dumps(
            {
                "bars": len(df),
                "symbol": args.symbol,
                "timeframe": args.timeframe,
                "lookback_days": args.lookback,
                "provenance": prov,
            },
            indent=2,
            default=str,
        )
    )
    return 0


def cmd_book_align(args: argparse.Namespace) -> int:
    """Align L2 orderbook snapshot data with OHLCV bars and export parquet."""
    from hypervector.data.book_align import (
        align_orderbook_to_ohlcv,
        load_l2_jsonl,
        load_l2_sqlite_feature_samples,
    )

    root = Path(args.data_root)
    df_bars, _ = _load_bars(args)

    book_path = Path(args.book_path)
    if str(book_path).endswith(".jsonl"):
        df_book = load_l2_jsonl(book_path)
    else:
        df_book = load_l2_sqlite_feature_samples(book_path, coin=args.symbol)

    aligned = align_orderbook_to_ohlcv(df_bars, df_book)
    out_dir = root / "cache" / "aligned"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{args.symbol}_{args.timeframe}_aligned_book.parquet"
    aligned.to_parquet(out_file)

    out = {
        "ok": True,
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "bars_count": len(aligned),
        "book_records": len(df_book),
        "aligned_path": str(out_file),
        "sample": aligned[["close", "spread_bps", "obi_5", "book_depth_ratio"]]
        .tail(3)
        .to_dict(orient="records"),
    }
    print(json.dumps(out, indent=2, default=str))
    return 0
