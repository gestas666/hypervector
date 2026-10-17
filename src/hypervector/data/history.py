"""HL-first history merge with Binance/Bybit backfill (SRS_HV1_DATA_*)."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from hypervector.data.provenance import normalize_ohlcv


def merge_history(
    hl_df: pd.DataFrame | None,
    backfills: Sequence[tuple[str, pd.DataFrame]] = (),
) -> pd.DataFrame:
    """Merge HL-max with backfill frames. HL wins on timestamp overlap.

    Backfill order in ``backfills`` is priority (first listed fills first;
    later sources only fill remaining gaps). Default design: Binance then Bybit.
    """
    pieces: list[pd.DataFrame] = []
    if hl_df is not None and len(hl_df):
        pieces.append(
            normalize_ohlcv(hl_df, source=None if "source" in hl_df.columns else "hl")
        )

    claimed: set[pd.Timestamp] = set()
    if pieces:
        claimed = set(pd.to_datetime(pieces[0]["timestamp"], utc=True))

    for name, frame in backfills:
        if frame is None or len(frame) == 0:
            continue
        bf = normalize_ohlcv(
            frame, source=name if "source" not in frame.columns else None
        )
        if "source" not in frame.columns:
            bf["source"] = name
        else:
            bf = normalize_ohlcv(bf)
            # keep existing source labels but default empty to name
            bf.loc[bf["source"].isna() | (bf["source"] == ""), "source"] = name
        ts = pd.to_datetime(bf["timestamp"], utc=True)
        mask = ~ts.isin(claimed)
        if mask.any():
            kept = bf.loc[mask].copy()
            pieces.append(kept)
            claimed |= set(pd.to_datetime(kept["timestamp"], utc=True))

    if not pieces:
        return normalize_ohlcv(
            pd.DataFrame(
                columns=[
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "source",
                ]
            ),
            source="hl",
        )

    out = pd.concat(pieces, ignore_index=True)
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    out = out.sort_values("timestamp").drop_duplicates(
        subset=["timestamp"], keep="first"
    )
    return out.reset_index(drop=True)
