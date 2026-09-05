"""Stable JSON and hash rendering for HIP-3 lifecycle input frames."""

from __future__ import annotations

import hashlib
from typing import cast

import pandas as pd


def frame_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    """Return JSON-safe records without changing the caller's frame."""
    rendered = frame.copy()
    for column in rendered.columns:
        if pd.api.types.is_datetime64_any_dtype(rendered[column]):
            rendered[column] = pd.to_datetime(rendered[column], utc=True).map(
                lambda value: value.isoformat()
            )
    return cast(list[dict[str, object]], rendered.to_dict(orient="records"))


def frame_evidence(frame: pd.DataFrame) -> dict[str, object]:
    """Return a deterministic content identity for one tabular input."""
    content = frame.to_csv(index=False, lineterminator="\n").encode()
    return {
        "rows": len(frame),
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }
