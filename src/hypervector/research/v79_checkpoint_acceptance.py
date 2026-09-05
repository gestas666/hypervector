"""Backward-compatible V79 acceptance attachment entry point."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from hypervector.research.seven_asset_checkpoint_acceptance import (
    attach_seven_asset_poststart_acceptance,
)


def attach_v79_poststart_acceptance(
    checkpoint: dict[str, object],
    config_path: Path,
    *,
    observed_at: datetime,
) -> bool:
    """Delegate exact V79 attachment to the shared seven-asset contract."""
    return attach_seven_asset_poststart_acceptance(
        checkpoint,
        config_path,
        observed_at=observed_at,
    )
