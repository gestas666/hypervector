"""Canonical causal regime labels shared by backend consumers."""

from __future__ import annotations

from enum import Enum


class PrimaryRegime(str, Enum):
    """Primary market structure emitted by the backend classifier."""

    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    BREAKOUT = "BREAKOUT"
    RANGE = "RANGE"
    TRANSITION = "TRANSITION"
    UNKNOWN = "UNKNOWN"


class BreakoutDirection(str, Enum):
    """Direction attached to a confirmed breakout."""

    UPWARD = "BK_UPWARD"
    DOWNWARD = "BK_DOWNWARD"

