"""Historical funding-reference integration tests."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd
import pytest

from hypervector.research.oracle_price_series import CausalOraclePriceSeries

_SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "multi_asset_range_onset_event_replay.py"
)


def _module() -> ModuleType:
    spec = spec_from_file_location("range_onset_historical_funding", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.path.insert(0, str(_SCRIPT.parent))
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(_SCRIPT.parent))
    return module


def test_funding_conversion_binds_causal_oracle_evidence() -> None:
    """Historical funding must use the last known venue oracle sample."""
    module = _module()
    index = pd.date_range("2026-01-01", periods=2, freq="1h", tz="UTC")
    bars = pd.DataFrame(
        {"open": [80.0, 81.0], "funding_rate": [0.0, 0.001]},
        index=index,
    )
    settlement_ms = int(index[1].timestamp() * 1_000)
    prices = CausalOraclePriceSeries(
        pd.DataFrame(
            {
                "ts_ms": [settlement_ms - 2_000, settlement_ms + 1_000],
                "oracle_price": [100.0, 101.0],
            }
        ),
        maximum_staleness_ms=120_000,
    )

    funding = module.to_event_funding(bars, prices)

    assert len(funding) == 1
    assert funding[0].reference_price == pytest.approx(100.0)
    assert funding[0].reference_observed_time_ms == settlement_ms - 2_000
    assert funding[0].reference_source == "oxa_oracle_last_at_or_before"


def test_funding_conversion_rejects_bar_open_fallback() -> None:
    """Missing oracle evidence must be an explicit failure, not a price fallback."""
    module = _module()
    index = pd.date_range("2026-01-01", periods=2, freq="1h", tz="UTC")
    bars = pd.DataFrame(
        {"open": [80.0, 81.0], "funding_rate": [0.0, 0.001]},
        index=index,
    )

    with pytest.raises(ValueError, match="oracle price evidence is required"):
        module.to_event_funding(bars, None)


def test_funding_conversion_excludes_pre_execution_warmup() -> None:
    """Signal warmup settlements must not require irrelevant funding evidence."""
    module = _module()
    index = pd.date_range("2026-01-01", periods=2, freq="1h", tz="UTC")
    bars = pd.DataFrame(
        {"funding_rate": [0.001, 0.002]},
        index=index,
    )
    execution_ms = int(index[1].timestamp() * 1_000)
    prices = CausalOraclePriceSeries(
        pd.DataFrame({"ts_ms": [execution_ms], "oracle_price": [100.0]}),
        maximum_staleness_ms=120_000,
    )

    funding = module.to_event_funding(
        bars,
        prices,
        minimum_timestamp_ms=execution_ms,
    )

    assert [event.timestamp_ms for event in funding] == [execution_ms]


def test_funding_conversion_skips_stale_rows_outside_position_windows() -> None:
    """Oracle gaps cannot censor settlements that no trial position could use."""
    module = _module()
    index = pd.date_range("2026-01-01", periods=3, freq="1h", tz="UTC")
    bars = pd.DataFrame(
        {"funding_rate": [0.0, 0.001, 0.002]},
        index=index,
    )
    relevant_ms = int(index[2].timestamp() * 1_000)
    prices = CausalOraclePriceSeries(
        pd.DataFrame(
            {
                "ts_ms": [int(index[0].timestamp() * 1_000), relevant_ms],
                "oracle_price": [99.0, 100.0],
            }
        ),
        maximum_staleness_ms=120_000,
    )

    funding = module.to_event_funding(
        bars,
        prices,
        potential_position_windows=((relevant_ms, relevant_ms + 60_000),),
    )

    assert [event.timestamp_ms for event in funding] == [relevant_ms]
    assert funding[0].reference_price == pytest.approx(100.0)
