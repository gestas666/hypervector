"""Development-only replay for HIP-3 oil shock continuation."""

from __future__ import annotations

import pandas as pd

from hypervector.research.hip3_oil_shock_continuation_signals import (
    build_hip3_oil_shock_continuation_signals,
)
from hypervector.research.hip3_oil_shock_reversion_candidate import (
    Hip3OilDevelopmentResult,
    evaluate_hip3_oil_shock_development,
)
from hypervector.research.hip3_oil_shock_reversion_signals import (
    Hip3OilShockReversionConfig,
)
from hypervector.research.mu_hip3_archive_candidate import MuArchiveExecution
from hypervector.research.mu_hip3_candidate import MuChronologicalWindows


def evaluate_hip3_oil_shock_continuation_development(
    bars: pd.DataFrame,
    execution: MuArchiveExecution,
    *,
    windows: MuChronologicalWindows,
    signal: Hip3OilShockReversionConfig = Hip3OilShockReversionConfig(),
) -> Hip3OilDevelopmentResult:
    """Replay the frozen continuation family without reading OOS economics."""
    return evaluate_hip3_oil_shock_development(
        bars,
        execution,
        windows=windows,
        signal=signal,
        signal_builder=build_hip3_oil_shock_continuation_signals,
        family="continuation",
    )
