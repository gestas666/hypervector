from __future__ import annotations

import pytest

from hypervector.research import cohort_friction_contracts
from hypervector.research.cohort_friction_contract_models import (
    ModeledExecutionContract,
)
from hypervector.research.cohort_friction_parity import build_friction_parity


_SOURCE = "test_mirror_1m"
_HYPE = "test_fade_1m"
_TREND = "test_trend_5m"
_BREAKOUT = "test_breakout_1m"
_HIP3_BREAKOUT_INDEX = "test_session_a_15m"
_ANCHOR_TARGET = "test_anchor_target_15m"


def test_mirror_provider_uses_frozen_deployed_shape_without_claiming_edge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mirror-provider parity cites its registered deployed-shape contract."""
    _register(monkeypatch, _SOURCE, None, _source_contract())
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
    assert row["modeled_contract"]["evidence_source"] == "evidence/source.json"
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


def test_hype_contract_matches_runtime_shape_without_claiming_edge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Matching mechanics remain descriptive and separate from profitability."""
    _register(monkeypatch, _HYPE, None, _hype_contract())
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


def test_unmodeled_route_is_unsupported_rather_than_aligned() -> None:
    """A route without reviewed research mechanics cannot claim parity."""
    identity = {
        "assets": [{"symbol": "HYPE"}],
        "providers": [
            _provider(
                _HYPE,
                "HYPE",
                stop_policy="fixed_bps",
                target_policy="none",
                maximum_hold_seconds=28_800,
                stop_bps=80.0,
            )
        ],
    }

    report = build_friction_parity(
        identity,
        [_fill(_HYPE, "HYPE", fee_usd=0.01078, slippage_bps=1.924)],
    )

    row = report["by_provider_symbol"][f"{_HYPE}|HYPE"]
    assert row["parity_state"] == "unsupported_contract"
    assert row["mismatches"] == ["modeled_contract_missing"]
    assert row["modeled_contract"] is None
    assert row["runtime_contract"]["stop_bps"] == 80.0
    assert row["observed_entry"]["fills"] == 1
    assert row["observed_entry"]["fee_mean_minus_modeled_bps"] is None
    assert row["observed_entry"]["slippage_mean_minus_modeled_bps"] is None
    assert row["strategy_edge_identifiable"] is False
    assert report["summary"]["unsupported_contract"] == 1
    assert report["summary"]["runtime_shape_aligned"] == 0


def test_observed_entry_retains_signed_price_improvement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A favorable fill remains negative slippage rather than breaking the report."""
    _register(monkeypatch, _SOURCE, None, _source_contract())
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


def test_all_active_provider_contracts_are_explicit_even_without_fills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A no-fill mapping still discloses whether its live mechanics match research."""
    for strategy in (_TREND, _BREAKOUT, _SOURCE, _HYPE):
        _register(monkeypatch, strategy, None, _hype_contract())
    identity = {
        "assets": [
            {"symbol": "BTC", "stop_bps": 80.0, "maximum_hold_seconds": 28_800},
            {"symbol": "SOL", "stop_bps": 80.0, "maximum_hold_seconds": 28_800},
            {"symbol": "HYPE", "stop_bps": 80.0, "maximum_hold_seconds": 28_800},
        ],
        "providers": [
            {"strategy_id": _TREND, "symbols": ["BTC"]},
            {"strategy_id": _BREAKOUT, "symbols": ["SOL"]},
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
        row["runtime_contract_source"] == "asset_fallback"
        and row["observed_entry"]["status"] == "not_observed"
        for row in report["by_provider_symbol"].values()
    )


def test_provider_execution_contracts_override_generic_asset_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parity must compare research with each provider's configured mechanics."""
    _register(monkeypatch, _TREND, None, _trend_contract())
    _register(monkeypatch, _BREAKOUT, None, _fixed_contract(60.0, 172_800))
    _register(monkeypatch, _SOURCE, None, _source_contract())
    _register(monkeypatch, _HYPE, None, _hype_contract())
    identity = {
        "assets": [
            {"symbol": "BTC", "stop_bps": 80.0, "maximum_hold_seconds": 28_800},
            {"symbol": "SOL", "stop_bps": 80.0, "maximum_hold_seconds": 28_800},
            {"symbol": "HYPE", "stop_bps": 80.0, "maximum_hold_seconds": 28_800},
        ],
        "providers": [
            _provider(
                _TREND,
                "BTC",
                stop_policy="structural_clamped_bps",
                target_policy="reward_risk",
                maximum_hold_seconds=86_400,
                minimum_stop_bps=20.0,
                maximum_stop_bps=75.0,
                target_r_multiple=3.0,
            ),
            _provider(
                _BREAKOUT,
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

    assert rows[f"{_TREND}|BTC"]["parity_state"] == "runtime_shape_aligned"
    assert rows[f"{_BREAKOUT}|SOL"]["parity_state"] == "runtime_shape_aligned"
    source = rows[f"{_SOURCE}|BTC"]
    assert source["mismatches"] == []
    assert source["runtime_contract_source"] == "provider_execution"
    assert source["runtime_contract"]["target_policy"] == "fixed_bps"
    assert source["runtime_contract"]["target_bps"] == pytest.approx(26.6666666667)
    hype = rows[f"{_HYPE}|HYPE"]
    assert hype["mismatches"] == []
    assert report["summary"]["runtime_shape_aligned"] == 4
    assert report["summary"]["contract_mismatch"] == 0


def test_exact_symbol_contract_precedes_provider_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two symbols of one provider cannot share one liquidity assumption."""
    _register(
        monkeypatch,
        _HIP3_BREAKOUT_INDEX,
        "xyz:AAA",
        _fixed_contract(80.0, 86_400, slippage_bps=1.4, source="evidence/aaa.json"),
    )
    _register(
        monkeypatch,
        _HIP3_BREAKOUT_INDEX,
        None,
        _fixed_contract(80.0, 86_400, slippage_bps=2.75, source="evidence/index.json"),
    )
    identity = {
        "assets": [
            {"symbol": "xyz:AAA"},
            {"symbol": "xyz:BBB"},
        ],
        "providers": [
            _provider(
                _HIP3_BREAKOUT_INDEX,
                symbol,
                stop_policy="fixed_bps",
                target_policy="none",
                maximum_hold_seconds=86_400,
                stop_bps=80.0,
            )
            for symbol in ("xyz:AAA", "xyz:BBB")
        ],
    }

    report = build_friction_parity(identity, [])
    aaa = report["by_provider_symbol"][f"{_HIP3_BREAKOUT_INDEX}|xyz:AAA"]
    bbb = report["by_provider_symbol"][f"{_HIP3_BREAKOUT_INDEX}|xyz:BBB"]

    assert aaa["parity_state"] == "runtime_shape_aligned"
    assert aaa["mismatches"] == []
    assert aaa["modeled_contract"]["entry_slippage_bps"] == pytest.approx(1.4)
    assert aaa["modeled_contract"]["evidence_source"] == "evidence/aaa.json"
    assert bbb["parity_state"] == "runtime_shape_aligned"
    assert bbb["modeled_contract"]["entry_slippage_bps"] == pytest.approx(2.75)
    assert bbb["modeled_contract"]["evidence_source"] == "evidence/index.json"


def test_symbol_stop_override_requires_its_own_modeled_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deployed per-symbol stop is compared only with research for that symbol."""
    _register(monkeypatch, _BREAKOUT, None, _fixed_contract(60.0, 172_800))
    _register(monkeypatch, _BREAKOUT, "SOL", _fixed_contract(80.0, 172_800))
    identity = {
        "assets": [{"symbol": "SOL"}, {"symbol": "ETH"}],
        "providers": [
            {
                **_provider(
                    _BREAKOUT,
                    "SOL",
                    stop_policy="fixed_bps",
                    target_policy="none",
                    maximum_hold_seconds=172_800,
                    stop_bps=60.0,
                ),
                "symbols": ["SOL", "ETH"],
                "stop_bps_overrides": {"SOL": 80.0},
            }
        ],
    }

    rows = build_friction_parity(identity, [])["by_provider_symbol"]

    sol = rows[f"{_BREAKOUT}|SOL"]
    assert sol["runtime_contract_source"] == "provider_execution_symbol_override"
    assert sol["runtime_contract"]["stop_bps"] == 80.0
    assert sol["modeled_contract"]["stop_bps"] == 80.0
    assert sol["parity_state"] == "runtime_shape_aligned"
    eth = rows[f"{_BREAKOUT}|ETH"]
    assert eth["runtime_contract_source"] == "provider_execution"
    assert eth["modeled_contract"]["stop_bps"] == 60.0
    assert eth["parity_state"] == "runtime_shape_aligned"

    monkeypatch.delitem(cohort_friction_contracts._MODELED, (_BREAKOUT, "SOL"))
    rows = build_friction_parity(identity, [])["by_provider_symbol"]
    assert rows[f"{_BREAKOUT}|SOL"]["parity_state"] == "unsupported_contract"


def test_anchor_target_contract_matches_dynamic_target_and_session_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Checkpoint friction telemetry must understand an absolute-anchor target."""
    _register(
        monkeypatch,
        _ANCHOR_TARGET,
        "xyz:BBB",
        ModeledExecutionContract(
            "taker",
            0.864,
            2.75,
            "fixed_bps",
            80.0,
            None,
            None,
            22_500,
            "fixed",
            None,
            "absolute_anchor",
            "maker",
            None,
            None,
            "evidence/anchor-target.json",
        ),
    )
    identity = {
        "assets": [{"symbol": "xyz:BBB"}],
        "providers": [
            _provider(
                _ANCHOR_TARGET,
                "xyz:BBB",
                stop_policy="fixed_bps",
                stop_bps=80.0,
                target_policy="absolute_anchor",
                maximum_hold_seconds=22_500,
                provider_recipe_exit_policy="honor",
            )
        ],
    }

    row = build_friction_parity(identity, [])["by_provider_symbol"][
        f"{_ANCHOR_TARGET}|xyz:BBB"
    ]

    assert row["parity_state"] == "runtime_shape_aligned"
    assert row["mismatches"] == []
    assert row["modeled_contract"]["target_policy"] == "absolute_anchor"
    assert row["modeled_contract"]["maximum_hold_seconds"] == 22_500


def _register(
    monkeypatch: pytest.MonkeyPatch,
    strategy_id: str,
    symbol: str | None,
    contract: ModeledExecutionContract,
) -> None:
    monkeypatch.setitem(
        cohort_friction_contracts._MODELED, (strategy_id, symbol), contract
    )


def _fixed_contract(
    stop_bps: float,
    maximum_hold_seconds: int,
    *,
    slippage_bps: float = 2.0,
    source: str = "evidence/fixed.json",
) -> ModeledExecutionContract:
    return ModeledExecutionContract(
        "taker",
        4.5,
        slippage_bps,
        "fixed_bps",
        stop_bps,
        None,
        None,
        maximum_hold_seconds,
        "fixed",
        None,
        "none",
        None,
        None,
        None,
        source,
    )


def _source_contract() -> ModeledExecutionContract:
    return ModeledExecutionContract(
        "taker",
        4.5,
        2.0,
        "fixed_bps",
        80.0,
        None,
        None,
        86_400,
        "fixed",
        None,
        "fixed_bps",
        "maker",
        26.6666666667,
        None,
        "evidence/source.json",
    )


def _hype_contract() -> ModeledExecutionContract:
    return ModeledExecutionContract(
        "taker",
        4.5,
        2.0,
        "fixed_bps",
        80.0,
        None,
        None,
        28_800,
        "extend_while_regime_supported",
        86_400,
        "none",
        None,
        None,
        None,
        "evidence/hype.json",
    )


def _trend_contract() -> ModeledExecutionContract:
    return ModeledExecutionContract(
        "taker",
        4.5,
        2.0,
        "structural_clamped_bps",
        None,
        20.0,
        75.0,
        86_400,
        "fixed",
        None,
        "reward_risk",
        "maker",
        None,
        3.0,
        "evidence/trend.json",
    )


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
