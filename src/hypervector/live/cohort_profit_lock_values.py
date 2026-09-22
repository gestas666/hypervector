"""Strict scalar validation for durable profit-lock decisions."""

import math
from hypervector.live.multi_asset_live_runner_support import MultiAssetLiveRunnerError


def _positive_price(value: object, label: str, symbol: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MultiAssetLiveRunnerError(f"{symbol} profit lock lacks a {label}")
    price = float(value)
    if not math.isfinite(price) or price <= 0.0:
        raise MultiAssetLiveRunnerError(f"{symbol} profit lock has invalid {label}")
    return price


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MultiAssetLiveRunnerError(
            f"persisted profit-lock {label} must be an integer"
        )
    return value



def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MultiAssetLiveRunnerError(
            f"persisted profit-lock {label} must be non-empty text"
        )
    return value.strip()
