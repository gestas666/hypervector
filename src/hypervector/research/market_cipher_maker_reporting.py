"""Auditable reporting for the paired BTC maker-entry counterfactual."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd

from hypervector.research.market_cipher_maker_entry import MakerEntryConfig
from hypervector.research.market_cipher_replay_models import (
    MarketCipherReplayConfig,
    MarketCipherReplayReport,
    MarketCipherReplayTrade,
)
from hypervector.research.market_cipher_strategy_research import frame_sha256


def build_maker_report(
    *,
    baseline_path: Path,
    baseline_report: dict[str, object],
    signal_count: int,
    paired_trade_count: int,
    entries: pd.DataFrame,
    bars: pd.DataFrame,
    replay: MarketCipherReplayReport,
    replay_config: MarketCipherReplayConfig,
    entry_config: MakerEntryConfig,
    start: pd.Timestamp,
    end: pd.Timestamp,
    segment: str,
) -> dict[str, object]:
    """Build one provenance-rich report with explicit experiment limits."""
    return {
        "schema_version": "market_cipher_maker_screen_v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "report_only": True,
        "execution_authority": "none",
        "place_attempted": False,
        "segment": segment,
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "candidate": "hulk_expansion_bidirectional_tuned_v2_maker_bbo_v1",
        "paired_counterfactual": True,
        "baseline_signal_count": signal_count,
        "paired_baseline_trade_count": paired_trade_count,
        "baseline_omitted_signal_count": signal_count - paired_trade_count,
        "entry_parameters": asdict(entry_config),
        "replay_parameters": asdict(replay_config),
        "baseline_evidence": _baseline_evidence(baseline_path, baseline_report),
        "maker_entry_evidence": _entry_evidence(entries),
        "one_minute_evidence": _bar_evidence(bars),
        "performance": _performance(replay),
        "direction_attribution": _direction_attribution(replay.trades),
        "development_criterion_met": _criterion_met(entries, replay),
        "replay": replay.to_dict(),
        "limitations": _limitations(),
    }


def replay_trade_frame(replay: MarketCipherReplayReport) -> pd.DataFrame:
    """Serialize completed replay trades without opaque nested structures."""
    rows: list[dict[str, object]] = []
    for trade in replay.trades:
        row = asdict(trade)
        row["exit_legs_json"] = json.dumps(row.pop("exit_legs"), sort_keys=True)
        rows.append(row)
    return pd.DataFrame(rows)


def _baseline_evidence(path: Path, report: dict[str, object]) -> dict[str, object]:
    files = (
        path,
        path.with_suffix(".signals.parquet"),
        path.with_suffix(".trades.parquet"),
    )
    return {
        "schema_version": report.get("schema_version"),
        "profile": report.get("profile"),
        "files": [
            {"path": str(file.resolve()), "sha256": _file_sha256(file)}
            for file in files
        ],
    }


def _entry_evidence(entries: pd.DataFrame) -> dict[str, object]:
    counts = entries["status"].value_counts().to_dict() if not entries.empty else {}
    filled = entries.loc[entries["status"].eq("filled")]
    total = len(entries)
    return {
        "total": total,
        "filled": int(counts.get("filled", 0)),
        "unfilled": int(counts.get("unfilled", 0)),
        "missing_book": int(counts.get("missing_book", 0)),
        "fill_rate": len(filled) / total if total else None,
        "mean_wait_seconds": _mean(filled, "wait_seconds"),
        "maximum_wait_seconds": _maximum(filled, "wait_seconds"),
        "mean_entry_improvement_bps": _mean(filled, "entry_improvement_bps"),
        "mean_lifecycle_gap_seconds": _mean(filled, "lifecycle_gap_seconds"),
        "maximum_lifecycle_gap_seconds": _maximum(filled, "lifecycle_gap_seconds"),
    }


def _bar_evidence(bars: pd.DataFrame) -> dict[str, object]:
    gaps = bars.index.to_series().diff().iloc[1:].ne(pd.Timedelta(minutes=1))
    return {
        "rows": len(bars),
        "first_bar_utc": bars.index.min().isoformat(),
        "last_bar_utc": bars.index.max().isoformat(),
        "internal_gap_count": int(gaps.sum()),
        "maximum_gap_seconds": _maximum_gap_seconds(bars.index),
        "missing_values": int(bars.isna().sum().sum()),
        "frame_sha256": frame_sha256(bars),
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


def _direction_attribution(
    trades: tuple[MarketCipherReplayTrade, ...],
) -> dict[str, object]:
    return {
        direction: _trade_summary(
            [trade for trade in trades if trade.direction == direction]
        )
        for direction in ("long", "short")
    }


def _trade_summary(trades: list[MarketCipherReplayTrade]) -> dict[str, object]:
    profits = sum(max(trade.net_pnl_usd, 0.0) for trade in trades)
    losses = -sum(min(trade.net_pnl_usd, 0.0) for trade in trades)
    return {
        "trades": len(trades),
        "net_pnl_usd": sum(trade.net_pnl_usd for trade in trades),
        "profit_factor": profits / losses if losses > 0.0 else None,
    }


def _criterion_met(entries: pd.DataFrame, replay: MarketCipherReplayReport) -> bool:
    directions = {trade.direction for trade in replay.trades}
    complete = not entries.empty and entries["status"].ne("missing_book").all()
    return bool(
        complete
        and replay.net_pnl_usd > 0.0
        and replay.profit_factor is not None
        and replay.profit_factor > 1.0
        and directions == {"long", "short"}
        and replay.liquidations == 0
    )


def _limitations() -> list[str]:
    return [
        "This is a paired counterfactual over market-entry-accepted baseline trades, not a standalone signal replay.",
        "Public L2 cannot identify private queue rank or cancellations ahead of the order.",
        "The fill-to-next-complete-minute interval is excluded and reported explicitly.",
        "One-minute OHLC uses pessimistic liquidation-before-stop-before-target ordering.",
        "Internal one-minute source gaps are reported and can hide intragap barriers.",
    ]


def _mean(frame: pd.DataFrame, column: str) -> float | None:
    return float(frame[column].mean()) if not frame.empty else None


def _maximum(frame: pd.DataFrame, column: str) -> float | None:
    return float(frame[column].max()) if not frame.empty else None


def _maximum_gap_seconds(index: pd.DatetimeIndex) -> float:
    if len(index) < 2:
        return 0.0
    return float(index.to_series().diff().dt.total_seconds().max())


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest()
