from __future__ import annotations

import pytest

from hypervector.research.cohort_friction_parity import build_friction_parity


_SOURCE = "hypervelocity_source_follow_bidirectional_5m_v1"
_HYPE = "hype_breakout_onset_bidirectional_v1"
_HYPE_COMPRESSION = "hype_breakout_compression_pullback_bidirectional_v1"
_HULK = "hulk_expansion_bidirectional_tuned_v2"
_RANGE = "range_onset_bidirectional_v1"
_ETH = "eth_breakout_precompression_pullback_bidirectional_v1"
_HIP3_SWING_INDEX = "hip3_swing_ha_sp500_spcx_bidirectional_v2"
_HIP3_BREAKOUT_INDEX = "hip3_breakout_pressure_sp500_spcx_bidirectional_v1"
_HIP3_BREAKOUT_COMMODITY = "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1"


def test_source_follow_uses_frozen_deployed_shape_without_claiming_edge() -> None:
    """Source-follow parity cites its exact deployed-shape venue replay."""
    identity = {
        "assets": [{"symbol": "BTC", "stop_bps": 80.0, "maximum_hold_seconds": 28_800}],
        "providers": [
            _provider(
                _SOURCE,
                "BTC",
                stop_policy="fixed_bps",
                target_policy="fixed_bps",
                maximum_hold_seconds=86_400,
                stop_bps=80.0,
                target_bps=26.6666666667,
                safety_stop_overlay=True,
            )
        ],
    }
    report = build_friction_parity(
        identity,
        [_fill(_SOURCE, "BTC", fee_usd=0.010599, slippage_bps=1.589)],
    )

    row = report["by_provider_symbol"][f"{_SOURCE}|BTC"]
    assert row["parity_state"] == "runtime_shape_aligned"
    assert row["mismatches"] == []
    assert row["modeled_contract"]["entry_liquidity"] == "taker"
    assert row["runtime_contract"]["entry_liquidity"] == "taker"
    assert row["runtime_contract"]["provider_recipe_exit_policy"] == "ignore"
    assert row["modeled_contract"]["entry_fee_bps"] == 4.5
    assert row["modeled_contract"]["entry_slippage_bps"] == 2.0
    assert row["modeled_contract"]["evidence_source"] == (
        "data/logs/research/source_follow_deployed_shape_btc_1y_20260804.json"
    )
    assert row["strategy_edge_identifiable"] is False
    assert row["observed_entry"]["fee_rate_bps"]["mean"] == pytest.approx(
        0.010599 / (62_915.0 * 0.00039) * 10_000.0
    )
    assert row["observed_entry"]["slippage_bps"]["mean"] == 1.589
    assert row["observed_entry"]["acknowledgement_latency_ms"]["mean"] == 1_223
    assert row["observed_entry"]["fee_mean_minus_modeled_bps"] == pytest.approx(
        0.010599 / (62_915.0 * 0.00039) * 10_000.0 - 4.5
    )
    assert row["observed_entry"]["slippage_mean_minus_modeled_bps"] == pytest.approx(
        -0.411
    )


def test_hype_contract_matches_runtime_shape_without_claiming_edge() -> None:
    """Matching mechanics remain descriptive and separate from profitability."""
    identity = {
        "assets": [
            {"symbol": "HYPE", "stop_bps": 80.0, "maximum_hold_seconds": 28_800}
        ],
        "providers": [
            _provider(
                _HYPE,
                "HYPE",
                stop_policy="fixed_bps",
                target_policy="none",
                maximum_hold_seconds=28_800,
                stop_bps=80.0,
                maximum_hold_policy="extend_while_regime_supported",
                hard_maximum_hold_seconds=86_400,
                provider_recipe_exit_policy="honor",
            )
        ],
    }
    report = build_friction_parity(
        identity,
        [_fill(_HYPE, "HYPE", fee_usd=0.01078, slippage_bps=1.924)],
    )

    row = report["by_provider_symbol"][f"{_HYPE}|HYPE"]
    assert row["parity_state"] == "runtime_shape_aligned"
    assert row["mismatches"] == []
    assert row["observed_entry"]["fills"] == 1
    assert row["runtime_contract"]["provider_recipe_exit_policy"] == "honor"
    assert row["strategy_edge_identifiable"] is False
    assert report["contract"] == {
        "report_only": True,
        "performance_gate": False,
        "automatic_pause": False,
        "automatic_retuning": False,
        "execution_authority": "none",
    }


def test_hype_compression_reuses_the_frozen_hype_execution_shape() -> None:
    """The v39 HYPE filter changes signals, not its execution mechanics."""
    identity = {
        "assets": [{"symbol": "HYPE"}],
        "providers": [
            _provider(
                _HYPE_COMPRESSION,
                "HYPE",
                stop_policy="fixed_bps",
                target_policy="none",
                maximum_hold_seconds=28_800,
                stop_bps=80.0,
                maximum_hold_policy="extend_while_regime_supported",
                hard_maximum_hold_seconds=86_400,
            )
        ],
    }

    row = build_friction_parity(identity, [])["by_provider_symbol"][
        f"{_HYPE_COMPRESSION}|HYPE"
    ]

    assert row["parity_state"] == "runtime_shape_aligned"
    assert row["mismatches"] == []
    assert row["modeled_contract"]["evidence_source"].endswith(
        "hype_breakout_live_extension_parity_20260804.json"
    )


def test_eth_pullback_contract_cites_shared_canary_falsification() -> None:
    """ETH live friction remains comparable to its exact shared replay shape."""
    identity = {
        "assets": [{"symbol": "ETH", "stop_bps": 60.0, "maximum_hold_seconds": 43_200}],
        "providers": [
            _provider(
                _ETH,
                "ETH",
                stop_policy="fixed_bps",
                target_policy="none",
                maximum_hold_seconds=43_200,
                stop_bps=60.0,
            )
        ],
    }

    report = build_friction_parity(identity, [])

    row = report["by_provider_symbol"][f"{_ETH}|ETH"]
    assert row["parity_state"] == "runtime_shape_aligned"
    assert row["mismatches"] == []
    assert row["modeled_contract"]["entry_fee_bps"] == 4.5
    assert row["modeled_contract"]["entry_slippage_bps"] == 2.0
    assert row["modeled_contract"]["evidence_source"] == (
        "data/logs/research/eth_sol_shared_canary_falsification_20260807_v1.json"
    )


def test_observed_entry_retains_signed_price_improvement() -> None:
    """A favorable fill remains negative slippage rather than breaking the report."""
    report = build_friction_parity(
        _identity(_SOURCE, "BTC", stop_bps=80.0, maximum_hold_seconds=28_800),
        [_fill(_SOURCE, "BTC", fee_usd=0.010599, slippage_bps=-2.666)],
    )

    observed = report["by_provider_symbol"][f"{_SOURCE}|BTC"]["observed_entry"]
    assert observed["slippage_bps"] == {
        "count": 1,
        "minimum": -2.666,
        "median": -2.666,
        "maximum": -2.666,
        "mean": -2.666,
    }
    assert observed["slippage_mean_minus_modeled_bps"] == pytest.approx(-4.666)


def test_all_active_provider_contracts_are_explicit_even_without_fills() -> None:
    """A no-fill mapping still discloses whether its live mechanics match research."""
    identity = {
        "assets": [
            {"symbol": "BTC", "stop_bps": 80.0, "maximum_hold_seconds": 28_800},
            {"symbol": "SOL", "stop_bps": 80.0, "maximum_hold_seconds": 28_800},
            {"symbol": "HYPE", "stop_bps": 80.0, "maximum_hold_seconds": 28_800},
        ],
        "providers": [
            {
                "strategy_id": "hulk_expansion_bidirectional_tuned_v2",
                "symbols": ["BTC"],
            },
            {"strategy_id": "range_onset_bidirectional_v1", "symbols": ["SOL"]},
            {"strategy_id": _SOURCE, "symbols": ["BTC"]},
            {"strategy_id": _HYPE, "symbols": ["HYPE"]},
        ],
    }

    report = build_friction_parity(identity, [])

    assert report["summary"] == {
        "provider_symbols": 4,
        "runtime_shape_aligned": 0,
        "contract_mismatch": 4,
        "unsupported_contract": 0,
        "runtime_contract_missing": 0,
        "provider_symbols_with_entry_fills": 0,
    }
    assert all(
        row["observed_entry"]["status"] == "not_observed"
        for row in report["by_provider_symbol"].values()
    )


def test_provider_execution_contracts_override_generic_asset_defaults() -> None:
    """Parity must compare research with each provider's configured mechanics."""
    identity = {
        "assets": [
            {"symbol": "BTC", "stop_bps": 80.0, "maximum_hold_seconds": 28_800},
            {"symbol": "SOL", "stop_bps": 80.0, "maximum_hold_seconds": 28_800},
            {"symbol": "HYPE", "stop_bps": 80.0, "maximum_hold_seconds": 28_800},
        ],
        "providers": [
            _provider(
                _HULK,
                "BTC",
                stop_policy="structural_clamped_bps",
                target_policy="reward_risk",
                maximum_hold_seconds=86_400,
                minimum_stop_bps=20.0,
                maximum_stop_bps=75.0,
                target_r_multiple=3.0,
            ),
            _provider(
                _RANGE,
                "SOL",
                stop_policy="fixed_bps",
                target_policy="none",
                maximum_hold_seconds=172_800,
                stop_bps=60.0,
            ),
            _provider(
                _SOURCE,
                "BTC",
                stop_policy="fixed_bps",
                target_policy="fixed_bps",
                maximum_hold_seconds=86_400,
                stop_bps=80.0,
                target_bps=26.6666666667,
                safety_stop_overlay=True,
            ),
            _provider(
                _HYPE,
                "HYPE",
                stop_policy="fixed_bps",
                target_policy="none",
                maximum_hold_seconds=28_800,
                stop_bps=80.0,
                maximum_hold_policy="extend_while_regime_supported",
                hard_maximum_hold_seconds=86_400,
            ),
        ],
    }

    report = build_friction_parity(identity, [])
    rows = report["by_provider_symbol"]

    assert rows[f"{_HULK}|BTC"]["parity_state"] == "runtime_shape_aligned"
    assert rows[f"{_RANGE}|SOL"]["parity_state"] == "runtime_shape_aligned"
    source = rows[f"{_SOURCE}|BTC"]
    assert source["mismatches"] == []
    assert source["runtime_contract_source"] == "provider_execution"
    assert source["runtime_contract"]["target_policy"] == "fixed_bps"
    assert source["runtime_contract"]["target_bps"] == pytest.approx(26.6666666667)
    hype = rows[f"{_HYPE}|HYPE"]
    assert hype["mismatches"] == []
    assert report["summary"]["runtime_shape_aligned"] == 4
    assert report["summary"]["contract_mismatch"] == 0


def test_hip3_cost_contract_is_exact_to_provider_and_symbol() -> None:
    """SP500 and SPCX cannot share one liquidity assumption."""
    identity = {
        "assets": [
            {"symbol": "xyz:SP500"},
            {"symbol": "xyz:SPCX"},
        ],
        "providers": [
            _provider(
                _HIP3_BREAKOUT_INDEX,
                "xyz:SP500",
                stop_policy="fixed_bps",
                target_policy="none",
                maximum_hold_seconds=86_400,
                stop_bps=80.0,
            ),
            _provider(
                _HIP3_BREAKOUT_INDEX,
                "xyz:SPCX",
                stop_policy="fixed_bps",
                target_policy="none",
                maximum_hold_seconds=86_400,
                stop_bps=80.0,
            ),
        ],
    }

    report = build_friction_parity(identity, [])
    sp500 = report["by_provider_symbol"][f"{_HIP3_BREAKOUT_INDEX}|xyz:SP500"]
    spcx = report["by_provider_symbol"][f"{_HIP3_BREAKOUT_INDEX}|xyz:SPCX"]

    assert sp500["parity_state"] == "runtime_shape_aligned"
    assert sp500["mismatches"] == []
    assert sp500["modeled_contract"]["entry_fee_bps"] == 0.864
    assert sp500["modeled_contract"]["entry_slippage_bps"] == pytest.approx(
        1.4030892763
    )
    assert spcx["modeled_contract"]["entry_slippage_bps"] == pytest.approx(2.7515676541)
    assert spcx["modeled_contract"]["evidence_source"].endswith(
        "hip3_v25_lifecycle_bar_diagnostic_20260807.json"
    )


def test_hip3_gold_contract_preserves_measured_higher_fee_world() -> None:
    """The deployed diagnostic must retain GOLD's measured higher fee."""
    identity = {
        "assets": [{"symbol": "xyz:GOLD"}],
        "providers": [
            _provider(
                _HIP3_BREAKOUT_COMMODITY,
                "xyz:GOLD",
                stop_policy="fixed_bps",
                target_policy="none",
                maximum_hold_seconds=86_400,
                stop_bps=80.0,
            )
        ],
    }

    report = build_friction_parity(identity, [])
    row = report["by_provider_symbol"][f"{_HIP3_BREAKOUT_COMMODITY}|xyz:GOLD"]

    assert row["modeled_contract"]["entry_fee_bps"] == pytest.approx(8.64)
    assert row["modeled_contract"]["entry_slippage_bps"] == pytest.approx(1.1245748882)
    assert row["modeled_contract"]["evidence_source"].endswith(
        "hip3_v25_lifecycle_bar_diagnostic_20260807.json"
    )


def test_hip3_swing_contract_matches_deployed_fixed_stop_and_hold() -> None:
    """Friction parity must cite the deployment-shaped lifecycle diagnostic."""
    identity = {
        "assets": [{"symbol": "xyz:SPCX"}],
        "providers": [
            _provider(
                _HIP3_SWING_INDEX,
                "xyz:SPCX",
                stop_policy="fixed_bps",
                target_policy="none",
                maximum_hold_seconds=86_400,
                stop_bps=80.0,
            )
        ],
    }

    report = build_friction_parity(identity, [])
    row = report["by_provider_symbol"][f"{_HIP3_SWING_INDEX}|xyz:SPCX"]

    assert row["parity_state"] == "runtime_shape_aligned"
    assert row["modeled_contract"]["stop_policy"] == "fixed_bps"
    assert row["modeled_contract"]["stop_bps"] == 80.0
    assert row["modeled_contract"]["maximum_hold_policy"] == "fixed"
    assert row["modeled_contract"]["maximum_hold_seconds"] == 86_400
    assert row["mismatches"] == []


def _identity(
    strategy_id: str,
    symbol: str,
    *,
    stop_bps: float,
    maximum_hold_seconds: int,
) -> dict[str, object]:
    return {
        "assets": [
            {
                "symbol": symbol,
                "stop_bps": stop_bps,
                "maximum_hold_seconds": maximum_hold_seconds,
            }
        ],
        "providers": [{"strategy_id": strategy_id, "symbols": [symbol]}],
    }


def _fill(
    strategy_id: str,
    symbol: str,
    *,
    fee_usd: float,
    slippage_bps: float,
) -> dict[str, object]:
    return {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "operation": "entry",
        "fee_usd": fee_usd,
        "price": 62_915.0 if symbol == "BTC" else 51.988,
        "size": 0.00039 if symbol == "BTC" else 0.48,
        "slippage_bps": slippage_bps,
        "acknowledgement_latency_ms": 1_223,
    }


def _provider(
    strategy_id: str,
    symbol: str,
    *,
    stop_policy: str,
    target_policy: str,
    maximum_hold_seconds: int,
    stop_bps: float | None = None,
    minimum_stop_bps: float | None = None,
    maximum_stop_bps: float | None = None,
    target_bps: float | None = None,
    target_r_multiple: float | None = None,
    safety_stop_overlay: bool = False,
    maximum_hold_policy: str = "fixed",
    hard_maximum_hold_seconds: int | None = None,
    provider_recipe_exit_policy: str = "ignore",
) -> dict[str, object]:
    return {
        "strategy_id": strategy_id,
        "symbols": [symbol],
        "execution": {
            "entry_liquidity": "taker_ioc",
            "stop_policy": stop_policy,
            "target_policy": target_policy,
            "maximum_hold_seconds": maximum_hold_seconds,
            "stop_bps": stop_bps,
            "minimum_stop_bps": minimum_stop_bps,
            "maximum_stop_bps": maximum_stop_bps,
            "target_bps": target_bps,
            "target_r_multiple": target_r_multiple,
            "safety_stop_overlay": safety_stop_overlay,
            "maximum_hold_policy": maximum_hold_policy,
            "hard_maximum_hold_seconds": hard_maximum_hold_seconds,
            "provider_recipe_exit_policy": provider_recipe_exit_policy,
        },
    }
