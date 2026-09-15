"""Report startup input capture without turning archival into a trading gate."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

import pandas as pd

from hypervector.live.cohort_startup_candles import StartupCandleContext, write_startup_candles
from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig

StartupCandleObserver: TypeAlias = Callable[[Mapping[str, pd.DataFrame], int, int], None]


@dataclass(frozen=True)
class CohortStartupCandleRecorder:
    """Capture one poller input and emit either its receipt or explicit failure."""

    config: MultiAssetLiveConfig
    ledger_directory: Path
    run_id: str
    emit: Callable[[str, Mapping[str, object]], None]

    def __call__(
        self, frames: Mapping[str, pd.DataFrame], activation_ms: int, observed_ms: int,
    ) -> None:
        """Keep capture failure visible while preserving existing trading decisions."""
        context = StartupCandleContext(
            self.config.profile_id, self.config.profile_fingerprint,
            self.config.run_fingerprint, self.run_id, self.config.symbols,
            activation_ms, observed_ms, float(self.config.lookback_days),
        )
        payload: dict[str, object] = {
            "context": context.as_payload(), "execution_authority": "none",
        }
        try:
            receipt = write_startup_candles(
                self.ledger_directory / "startup_inputs", context, frames,
            )
        except (OSError, ValueError, ImportError) as exc:
            payload.update(status="unavailable", error_type=type(exc).__name__, reason=str(exc))
        else:
            payload.update(status="captured", **receipt.as_payload())
        self.emit("startup_candle_inputs", payload)
