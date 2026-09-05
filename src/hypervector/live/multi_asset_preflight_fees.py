"""Point-in-time effective fee evidence for multi-asset preflight reports."""

from __future__ import annotations

from math import isfinite

from hypervector.live.hyperliquid_protocol import (
    Hip3MarketFeeMetadata,
    HyperliquidFeeSchedule,
)
from hypervector.research.hip3_fee_model import Hip3FeeInputs, effective_hip3_fees


def preflight_fee_payload(
    *,
    symbol: str,
    fees: HyperliquidFeeSchedule,
    hip3_metadata: Hip3MarketFeeMetadata | None,
) -> dict[str, object]:
    """Resolve account-base or HIP-3 effective rates without execution authority."""
    _validate_base_fees(fees)
    common = {
        "account_base_maker_fee_rate": fees.maker_rate,
        "account_base_taker_fee_rate": fees.taker_rate,
        "active_referral_discount": fees.active_referral_discount,
    }
    if ":" not in symbol:
        if hip3_metadata is not None:
            raise ValueError(f"{symbol} core market cannot carry HIP-3 fee metadata")
        referral_scale = 1.0 - fees.active_referral_discount
        maker_rate = fees.maker_rate * referral_scale
        taker_rate = fees.taker_rate * referral_scale
        return {
            **common,
            "effective_fee_status": "resolved_core_after_referral",
            "effective_maker_fee_rate": maker_rate,
            "effective_taker_fee_rate": taker_rate,
            "one_way_maker_fee_bps": maker_rate * 10_000.0,
            "one_way_taker_fee_bps": taker_rate * 10_000.0,
            "fee_formula_source": "official_user_fees_account_rate_x_referral_scale",
        }
    if hip3_metadata is None:
        raise ValueError(f"{symbol} HIP-3 market requires exact fee metadata")
    hip3_common = {
        **common,
        "deployer_fee_scale": hip3_metadata.deployer_fee_scale,
        "growth_mode": hip3_metadata.growth_mode,
        "collateral_token_index": hip3_metadata.collateral_token_index,
        "aligned_quote": False,
        "aligned_quote_status": "unresolved_conservative_false",
    }
    if hip3_metadata.deployer_fee_scale is None:
        return {
            **hip3_common,
            "effective_fee_status": "unresolved_deployer_fee_scale",
            "effective_maker_fee_rate": None,
            "effective_taker_fee_rate": None,
            "one_way_maker_fee_bps": None,
            "one_way_taker_fee_bps": None,
            "fee_formula_source": None,
        }
    if hip3_metadata.growth_mode is None:
        return {
            **hip3_common,
            "effective_fee_status": "unresolved_growth_mode",
            "effective_maker_fee_rate": None,
            "effective_taker_fee_rate": None,
            "one_way_maker_fee_bps": None,
            "one_way_taker_fee_bps": None,
            "fee_formula_source": None,
        }
    effective = effective_hip3_fees(
        Hip3FeeInputs(
            account_maker_rate=fees.maker_rate,
            account_taker_rate=fees.taker_rate,
            active_referral_discount=fees.active_referral_discount,
            deployer_fee_scale=hip3_metadata.deployer_fee_scale,
            growth_mode=hip3_metadata.growth_mode,
            aligned_quote=False,
            aligned_quote_status="unresolved_conservative_false",
            evidence_label="multi_asset_read_only_preflight",
        )
    )
    return {
        **hip3_common,
        "effective_fee_status": "resolved_hip3",
        "effective_maker_fee_rate": effective.effective_maker_rate,
        "effective_taker_fee_rate": effective.effective_taker_rate,
        "one_way_maker_fee_bps": effective.one_way_maker_fee_bps,
        "one_way_taker_fee_bps": effective.one_way_taker_fee_bps,
        "fee_formula_source": effective.formula_source,
    }


def _validate_base_fees(fees: HyperliquidFeeSchedule) -> None:
    if not isfinite(fees.maker_rate) or not -0.01 < fees.maker_rate < 0.01:
        raise ValueError("account maker fee rate must be finite and within one percent")
    if not isfinite(fees.taker_rate) or not 0.0 <= fees.taker_rate < 0.01:
        raise ValueError("account taker fee rate must be finite and below one percent")
    if (
        not isfinite(fees.active_referral_discount)
        or not 0.0 <= fees.active_referral_discount < 1.0
    ):
        raise ValueError("active referral discount must be finite and in [0, 1)")
