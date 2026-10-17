"""Nautilus command handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from hypervector.commands.common import CommandRefused
from hypervector.commands.exports import resolve_export
from hypervector.export.schema import ExportSchemaError

CATALOG_BATCH_SIZE = 1000


def cmd_check(args: argparse.Namespace) -> int:
    """Load a strategy bundle as a Nautilus loadout and probe the engine (read-only)."""
    from hypervector.nautilus.config_stub import phase2_check_report

    path = resolve_export(args.export, args.data_root)
    try:
        report = phase2_check_report(
            path,
            data_root=args.data_root,
            strict=not args.loose,
            probe_nautilus=not args.no_nautilus_probe,
        )
    except ExportSchemaError as exc:
        _schema_error(args, path, exc)
        return 1
    report["export_dir"] = str(path)
    print(json.dumps(report, indent=2, default=str))
    print(
        "note: 'nautilus run' replays the bundle on recorded bars; "
        "paper/shadow on live bars → 'paper run' (default shadow, no venue orders); "
        "live execution → 'live start' (--enabled + --i-accept-live-risk)",
        file=sys.stderr,
    )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Backtest a strict strategy bundle event by event with NautilusTrader.

    The lookback defaults to the bundle's own window. Technical failures (a
    cache miss with --no-network, an engine error) print error JSON and exit 1.
    """
    path = resolve_export(args.export, args.data_root)
    lookback, lookback_source = _run_lookback(args, path)
    try:
        from hypervector.nautilus.runner import run_phase2_backtest

        result = run_phase2_backtest(
            export_dir=path,
            data_root=Path(args.data_root),
            conviction=float(args.conviction),
            lookback_days=lookback,
            allow_network=not args.no_network,
        )
    except ExportSchemaError as exc:
        _schema_error(args, path, exc)
        return 1
    except Exception as exc:  # noqa: BLE001 - engine failures are technical (exit 1)
        if os.environ.get("HYPERVECTOR_DEBUG") == "1":
            raise
        _technical_error(args, path, exc, lookback=lookback)
        return 1

    payload = json.loads(result.report_path.read_text(encoding="utf-8"))
    out = {
        "ok": True,
        "execution_mode": payload.get("execution_mode", "phase2_historical"),
        "orders_count": result.orders_count,
        "pnl": result.pnl,
        "report_path": str(result.report_path),
        "export_dir": str(result.export_dir),
        "candidate_id": Path(result.export_dir).name,
        "run_id": payload.get("run_id"),
        "bars": payload.get("bars"),
        "lookback_days": lookback,
        "lookback_source": lookback_source,
        "network": not args.no_network,
        "conviction": payload.get("conviction", float(args.conviction)),
        "loadout": result.loadout_summary,
        "artifacts": {
            "export": str(result.export_dir),
            "validation": str(result.report_path),
        },
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


def cmd_catalog(args: argparse.Namespace) -> int:
    """Write recorded public Hyperliquid events into a Nautilus ParquetDataCatalog."""
    symbol = str(args.symbol)
    if not symbol or "/" in symbol or symbol in (".", ".."):
        raise CommandRefused(f"invalid symbol for a catalog path: {symbol!r}")
    for flag, value in (
        ("--price-precision", args.price_precision),
        ("--size-precision", args.size_precision),
    ):
        if int(value) < 0:
            raise CommandRefused(f"{flag} must be a non-negative digit count")
    root = Path(args.data_root)
    events = root / "cache" / "events" / "hyperliquid" / symbol
    if not events.is_dir():
        raise FileNotFoundError(
            f"no recorded public events for {symbol} under {events}"
        )
    out_dir = (
        Path(args.out_dir)
        if args.out_dir is not None
        else root / "nautilus" / "catalog" / symbol
    )
    instrument_id = args.instrument_id or f"{symbol}-PERP.HYPERLIQUID"

    from hypervector.data.event_archive import EventArchive
    from hypervector.nautilus.hl_catalog import write_hyperliquid_catalog

    result = write_hyperliquid_catalog(
        archive=EventArchive(
            data_root=root, symbol=symbol, batch_size=CATALOG_BATCH_SIZE
        ),
        catalog_path=out_dir,
        instrument_id=instrument_id,
        price_precision=int(args.price_precision),
        size_precision=int(args.size_precision),
    )
    out = {
        "ok": True,
        "symbol": symbol,
        "instrument_id": instrument_id,
        "events_dir": str(events.resolve()),
        "catalog_path": str(out_dir.resolve()),
        "book_delta_count": result.book_delta_count,
        "quote_count": result.quote_count,
        "trade_count": result.trade_count,
        "gap_count": result.gap_count,
        "gap_provenance_path": str(result.gap_provenance_path),
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


def _run_lookback(args: argparse.Namespace, path: Path) -> tuple[int | None, str]:
    """The explicit lookback, else the bundle's recorded window, else the runner default."""
    if args.lookback is not None:
        return int(args.lookback), "flag"
    try:
        meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
        days = meta.get("lookback_days") if isinstance(meta, dict) else None
        if days is not None:
            return int(days), "export"
    except (OSError, ValueError, TypeError):
        pass  # the runner reports an unreadable bundle as a schema error
    return None, "default"


def _schema_error(args: argparse.Namespace, path: Path, exc: ExportSchemaError) -> None:
    print(
        json.dumps(
            {
                "ok": False,
                "command": args.command,
                "error_type": "ExportSchemaError",
                "export_dir": str(path),
                "path": str(path),
                "errors": exc.errors,
            },
            indent=2,
        ),
        file=sys.stderr,
    )


def _technical_error(
    args: argparse.Namespace, path: Path, exc: BaseException, **context: Any
) -> None:
    print(
        json.dumps(
            {
                "ok": False,
                "command": args.command,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "export_dir": str(path),
                **context,
            },
            default=str,
        ),
        file=sys.stderr,
    )
