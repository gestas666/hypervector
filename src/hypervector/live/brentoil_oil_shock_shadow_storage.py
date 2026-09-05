"""Durable JSONL storage for the BRENTOIL oil-shock shadow."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from hypervector.live.brentoil_oil_shock_shadow import (
    BRENTOIL_OIL_SHOCK_SYMBOL,
    BRENTOIL_SIGNAL_SOURCE,
)
from hypervector.live.hip3_shadow_candle_storage import (
    ShadowCandleAppendResult,
    ShadowCandleContract,
    append_candles_once as append_shadow_candles_once,
    append_jsonl as append_jsonl,
    candle_summary as shadow_candle_summary,
    jsonl_rows as jsonl_rows,
    source_revision_status as shadow_source_revision_status,
    validate_candle_row as validate_shadow_candle_row,
)

_INTERVAL_MS = 300_000
_CANDLE_CONTRACT = ShadowCandleContract(
    symbol=BRENTOIL_OIL_SHOCK_SYMBOL,
    source=BRENTOIL_SIGNAL_SOURCE,
    event_type="brentoil_oil_shock_candle_observation",
    interval_ms=_INTERVAL_MS,
    maximum_observation_delay_ms=15_000,
    revision_tolerant_fields=("volume",),
)


def append_candles_once(
    path: Path,
    frame: pd.DataFrame,
    *,
    observed_at_ms: int,
    prior_boundary_ms: int,
) -> ShadowCandleAppendResult:
    """Append each frozen source candle once with prospective provenance."""
    return append_shadow_candles_once(
        path,
        frame,
        contract=_CANDLE_CONTRACT,
        observed_at_ms=observed_at_ms,
        prior_boundary_ms=prior_boundary_ms,
    )


def candle_summary(path: Path) -> dict[str, object]:
    """Return cumulative historical/prospective candle counts."""
    return shadow_candle_summary(path)


def validate_candle_row(row: dict[str, object]) -> None:
    """Validate one BRENTOIL candle against the frozen observer contract."""
    validate_shadow_candle_row(row, _CANDLE_CONTRACT)


def source_revision_status(
    path: Path,
    *,
    current_bars: tuple[int, ...],
    current_fields: tuple[str, ...],
) -> dict[str, object]:
    """Carry forward immutable disclosure of every detected source revision."""
    return shadow_source_revision_status(
        path,
        current_bars=current_bars,
        current_fields=current_fields,
        allowed_fields=("volume",),
    )
