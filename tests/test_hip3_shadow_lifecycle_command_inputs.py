"""Distinct warmup and prospective bounds for HIP-3 lifecycle inputs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from hypervector.live.hip3_breakout_shadow_specs import SP500_SHADOW_SPEC
from hypervector.research.hip3_shadow_lifecycle_command_inputs import (
    load_shadow_market_inputs,
)
from hypervector.research.hip3_shadow_lifecycle_models import (
    Hip3ShadowLifecycleConfig,
)


class _Marks:
    def __init__(self) -> None:
        self.start_ms: int | None = None

    def load(
        self, *, data_root: Path, symbol: str, start_ms: int, end_ms: int
    ) -> tuple[tuple[dict[str, object], ...], dict[str, object]]:
        del data_root, symbol, end_ms
        self.start_ms = start_ms
        return (), {"rows": 0}

    def require_unchanged(self, evidence: dict[str, object]) -> None:
        assert evidence == {"rows": 0}


def test_signal_warmup_precedes_the_prospective_mark_window(tmp_path: Path) -> None:
    """Frozen historical candles must not widen lifecycle mark acquisition."""
    marks = _Marks()
    starts: list[int] = []

    def candles(
        _symbol: str, _timeframe: str, lookback: float, *, end_ms: int
    ) -> pd.DataFrame:
        starts.append(end_ms - int((lookback - 0.25) * 86_400_000))
        return _candles()

    market = load_shadow_market_inputs(
        candle_fetcher=candles,
        funding_fetcher=lambda *_args, **_kwargs: pd.DataFrame(),
        mark_source=marks,
        data_root=tmp_path,
        spec=SP500_SHADOW_SPEC,
        config=_config(),
        start_ms=1_800_000,
        signal_start_ms=900_000,
        observed_at_ms=3_600_000,
    )

    assert starts == [900_000]
    assert marks.start_ms == 1_800_000
    assert len(market.candles) == 2


def _config() -> Hip3ShadowLifecycleConfig:
    return Hip3ShadowLifecycleConfig(
        SP500_SHADOW_SPEC.symbol,
        SP500_SHADOW_SPEC.provider_id,
        SP500_SHADOW_SPEC.profile_id,
        SP500_SHADOW_SPEC.ledger_profile_id,
        SP500_SHADOW_SPEC.config,
        1.0,
        0.0,
        2.0,
        5_000.0,
        15_000,
        5_000,
        1_440,
        "test",
    )


def _candles() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime([900_000, 1_800_000], unit="ms", utc=True),
            "open": [100.0, 100.0],
            "high": [101.0, 101.0],
            "low": [99.0, 99.0],
            "close": [100.0, 100.0],
            "source": ["hl", "hl"],
        }
    )
