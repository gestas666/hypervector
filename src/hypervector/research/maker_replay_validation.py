"""Evidence validation for causal maker replay."""

from __future__ import annotations

import pandas as pd


def validate_book(book: pd.DataFrame) -> pd.DataFrame:
    """Return chronological, unique, positive, uncrossed top-of-book evidence."""
    required = {"ts_ms", "best_bid", "best_ask"}
    missing = required.difference(book.columns)
    if missing:
        raise ValueError(f"maker replay book missing columns: {sorted(missing)}")
    frame = book.loc[:, ["ts_ms", "best_bid", "best_ask"]].copy()
    _reject_conflicting_book_timestamps(frame)
    frame = frame.sort_values("ts_ms").drop_duplicates("ts_ms", keep="last")
    if frame.empty:
        raise ValueError("maker replay requires at least one book snapshot")
    if (frame[["best_bid", "best_ask"]].astype(float) <= 0.0).any().any():
        raise ValueError("maker replay book prices must be positive")
    if (frame["best_bid"].astype(float) >= frame["best_ask"].astype(float)).any():
        raise ValueError("maker replay book must have best_bid < best_ask")
    return frame.reset_index(drop=True)


def _reject_conflicting_book_timestamps(frame: pd.DataFrame) -> None:
    duplicates = frame.loc[frame["ts_ms"].duplicated(keep=False)]
    for timestamp, group in duplicates.groupby("ts_ms", sort=False):
        if len(group.drop_duplicates()) != 1:
            raise ValueError(f"conflicting duplicate book timestamp: {timestamp}")


def validate_trades(trades: pd.DataFrame | None) -> pd.DataFrame:
    """Return unique public prints, accepting exact adjacent-window repeats."""
    if trades is None:
        raise ValueError("trade-through replay requires public trade prints")
    required = {"ts_ms", "trade_id", "aggressor_side", "price", "size"}
    missing = required.difference(trades.columns)
    if missing:
        raise ValueError(f"maker replay trades missing columns: {sorted(missing)}")
    frame = trades.loc[:, sorted(required)].copy()
    if frame.empty:
        raise ValueError("trade-through replay requires public trade prints")
    if not frame["aggressor_side"].isin(("buy", "sell")).all():
        raise ValueError("maker replay aggressor_side must be buy|sell")
    if (frame[["price", "size"]].astype(float) <= 0.0).any().any():
        raise ValueError("maker replay trade price and size must be positive")
    _reject_conflicting_trade_ids(frame)
    return (
        frame.drop_duplicates("trade_id", keep="last")
        .sort_values(["ts_ms", "trade_id"])
        .reset_index(drop=True)
    )


def _reject_conflicting_trade_ids(frame: pd.DataFrame) -> None:
    duplicates = frame.loc[frame["trade_id"].duplicated(keep=False)]
    for trade_id, group in duplicates.groupby("trade_id", sort=False):
        if len(group.drop_duplicates()) != 1:
            raise ValueError(f"conflicting duplicate trade_id: {trade_id}")
