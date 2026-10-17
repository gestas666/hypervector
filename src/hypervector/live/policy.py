"""Live execution policy: secrets, arm flag, size caps (fail-closed).

Pure checks — no network, no order placement. Used by live-check / live-run
before any venue client is constructed.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any

# Same env names as paper surface (values never logged).
SECRET_ENV_WALLET = "HYPERVECTOR_HL_WALLET_ADDRESS"
SECRET_ENV_API_KEY = "HYPERVECTOR_HL_API_PRIVATE_KEY"

DEFAULT_MAX_NOTIONAL_USD = 50.0


class LivePolicyError(ValueError):
    """Live policy refused to arm or size an order."""


def notional_cap_error(value: object) -> str | None:
    """Return why ``value`` is not a usable hard notional cap, or None if it is.

    ``float("nan")`` compares false against every bound, so a NaN or infinite cap
    would silently disable both the engine scaling and the client cap check.
    """
    try:
        cap = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return f"max_notional_usd must be a finite positive number, got {value!r}"
    if not math.isfinite(cap) or cap <= 0.0:
        return f"max_notional_usd must be a finite positive number, got {value!r}"
    return None


def require_notional_cap(value: object) -> float:
    """Return a validated hard notional cap or raise :class:`LivePolicyError`."""
    error = notional_cap_error(value)
    if error is not None:
        raise LivePolicyError(error)
    return float(value)  # type: ignore[arg-type]


@dataclass(frozen=True)
class LivePolicy:
    """Fail-closed gates for Phase 4b-live.

    Parameters
    ----------
    enabled:
        Config ``[live] enabled`` — must be True for live-run.
    armed:
        Explicit operator arm (CLI ``--i-accept-live-risk``).
    max_notional_usd:
        Hard notional cap (qty * mark_px) before place.
    secrets_present:
        Both wallet + API key env vars non-empty.
    """

    enabled: bool = False
    armed: bool = False
    max_notional_usd: float = DEFAULT_MAX_NOTIONAL_USD
    secrets_present: bool = False

    def require_start(self) -> None:
        """Raise if live daemon must not start."""
        if not self.enabled:
            raise LivePolicyError(
                "live.enabled is false — set [live] enabled=true to allow live-run"
            )
        if not self.armed:
            raise LivePolicyError(
                "live not armed — pass --i-accept-live-risk to accept mainnet risk"
            )
        if not self.secrets_present:
            raise LivePolicyError(
                "live secrets missing — set "
                f"{SECRET_ENV_WALLET} and {SECRET_ENV_API_KEY}"
            )
        require_notional_cap(self.max_notional_usd)

    def require_notional(self, *, qty: float, mark_px: float) -> float:
        """Return notional if within cap; else raise."""
        q = float(qty)
        px = float(mark_px)
        if q <= 0:
            raise LivePolicyError(f"qty must be positive, got {qty!r}")
        if px <= 0:
            raise LivePolicyError(f"mark_px must be positive, got {mark_px!r}")
        notional = abs(q) * px
        cap = require_notional_cap(self.max_notional_usd)
        if notional > cap + 1e-12:
            raise LivePolicyError(
                f"notional {notional:.6f} exceeds max_notional_usd {cap:.6f}"
            )
        return notional

    def readiness(self) -> dict[str, Any]:
        """JSON-safe readiness (never secret values)."""
        # Capability metadata does not import execution clients.
        from hypervector.live.capabilities import is_submit_wired

        wired = bool(is_submit_wired())
        cap_error = notional_cap_error(self.max_notional_usd)
        return {
            "enabled": self.enabled,
            "armed": self.armed,
            "secrets_present": self.secrets_present,
            "max_notional_usd": float(self.max_notional_usd),
            "secret_env_names": [SECRET_ENV_WALLET, SECRET_ENV_API_KEY],
            "network": "mainnet",
            "submit_wired": wired,
            "max_notional_valid": cap_error is None,
            "can_start": bool(
                self.enabled
                and self.armed
                and self.secrets_present
                and cap_error is None
            ),
            "note": (
                "Live exec client present (F2). "
                "live-run / venue place only when enabled+armed+secrets (F3)."
                if wired
                else (
                    "Foundation only: live ledger + policy. "
                    "Venue submit is a later 4b-live task."
                )
            ),
        }


def secrets_present_from_env(
    *,
    environ: dict[str, str] | None = None,
) -> bool:
    env = environ if environ is not None else os.environ
    wallet = (env.get(SECRET_ENV_WALLET) or "").strip()
    key = (env.get(SECRET_ENV_API_KEY) or "").strip()
    return bool(wallet) and bool(key)


def live_policy_from_env(
    *,
    enabled: bool = False,
    armed: bool = False,
    max_notional_usd: float = DEFAULT_MAX_NOTIONAL_USD,
    environ: dict[str, str] | None = None,
) -> LivePolicy:
    """Build policy from flags + process env (or injected environ for tests)."""
    return LivePolicy(
        enabled=bool(enabled),
        armed=bool(armed),
        max_notional_usd=float(max_notional_usd),
        secrets_present=secrets_present_from_env(environ=environ),
    )
