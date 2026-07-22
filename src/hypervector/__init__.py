"""Hypervector: multi-stage quantitative research and execution pipeline."""

__version__ = "0.1.0"

from hypervector.config import (
    DEFAULT_LOOKBACK,
    FLOOR_LOOKBACK,
    PROMO_LOOKBACK,
    ResearchConfig,
    validate_lookback,
)
from hypervector.infra import ensure_data_layout, paths_for

__all__ = [
    "__version__",
    "DEFAULT_LOOKBACK",
    "FLOOR_LOOKBACK",
    "PROMO_LOOKBACK",
    "ResearchConfig",
    "ensure_data_layout",
    "paths_for",
    "validate_lookback",
]
