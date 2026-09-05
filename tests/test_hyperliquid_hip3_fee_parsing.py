"""Strict parsing tests for live HIP-3 fee metadata."""

from __future__ import annotations

import pytest

from hypervector.live.hyperliquid_hip3_fee_parsing import (
    parse_hip3_market_fee_metadata,
)
from hypervector.live.hyperliquid_sol_parsing import HyperliquidAdapterError


def _metadata(growth_mode: str = "enabled") -> dict[str, object]:
    return {
        "collateralToken": 0,
        "universe": [
            {
                "name": "xyz:SP500",
                "szDecimals": 3,
                "maxLeverage": 50,
                "growthMode": growth_mode,
            }
        ],
    }


def test_preserves_missing_growth_mode_as_unresolved() -> None:
    """An omitted venue modifier must remain unknown rather than defaulting."""
    metadata = _metadata()
    del metadata["universe"][0]["growthMode"]

    result = parse_hip3_market_fee_metadata(
        metadata=metadata,
        dexes=[None, {"name": "xyz", "deployerFeeScale": "1.0"}],
        symbol="xyz:SP500",
        perp_dex="xyz",
    )

    assert result.growth_mode is None


def test_parses_exact_dex_and_market_fee_metadata() -> None:
    """Fee inputs must retain their exact namespace and market identity."""
    result = parse_hip3_market_fee_metadata(
        metadata=_metadata(),
        dexes=[None, {"name": "xyz", "deployerFeeScale": "1.0"}],
        symbol="xyz:SP500",
        perp_dex="xyz",
    )

    assert result.deployer_fee_scale == 1.0
    assert result.growth_mode is True
    assert result.collateral_token_index == 0


def test_prefers_market_specific_deployer_fee_scale() -> None:
    """A market-level fee scale must resolve when the dex-wide field is absent."""
    metadata = _metadata()
    metadata["universe"][0]["deployerFeeScale"] = "1.0"

    result = parse_hip3_market_fee_metadata(
        metadata=metadata,
        dexes=[None, {"name": "xyz"}],
        symbol="xyz:SP500",
        perp_dex="xyz",
    )

    assert result.deployer_fee_scale == 1.0


def test_preserves_missing_deployer_fee_scale_as_unresolved() -> None:
    """Current API omission must not invent a fee scale or block reconciliation."""
    result = parse_hip3_market_fee_metadata(
        metadata=_metadata(),
        dexes=[None, {"name": "xyz"}],
        symbol="xyz:SP500",
        perp_dex="xyz",
    )

    assert result.deployer_fee_scale is None
    assert result.growth_mode is True


@pytest.mark.parametrize("growth_mode", ("", "unknown"))
def test_rejects_unsupported_growth_mode(growth_mode: str) -> None:
    """Unknown fee modes must fail rather than inherit a plausible default."""
    with pytest.raises(HyperliquidAdapterError, match="growthMode"):
        parse_hip3_market_fee_metadata(
            metadata=_metadata(growth_mode),
            dexes=[{"name": "xyz", "deployerFeeScale": "1.0"}],
            symbol="xyz:SP500",
            perp_dex="xyz",
        )


def test_rejects_missing_exact_dex_fee_scale() -> None:
    """A native or different HIP-3 dex must not supply fee-scale evidence."""
    with pytest.raises(HyperliquidAdapterError, match="deployer fee metadata"):
        parse_hip3_market_fee_metadata(
            metadata=_metadata(),
            dexes=[{"name": "cash", "deployerFeeScale": "0.5"}],
            symbol="xyz:SP500",
            perp_dex="xyz",
        )
