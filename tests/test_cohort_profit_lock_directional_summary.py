"""Directional normalized profit-lock summary tests."""

from __future__ import annotations

from hypervector.research.cohort_profit_lock_mechanism import (
    build_normalized_profit_lock_report,
)


def test_normalized_report_separates_provider_symbol_directions() -> None:
    """Opposing long/short effects must not disappear inside a pooled route."""
    report = build_normalized_profit_lock_report(
        [_result("long", estimated=1.0, actual=-1.0), _result("short", -1.0, 1.0)],
        policies=[{"policy_id": "lock"}],
        contract={"report_only": True, "execution_authority": "none"},
        limitations=[],
    )

    directional = report["by_provider_symbol_side"]
    long = directional["provider|BTC|long"]["summary_by_policy"]["lock"]
    short = directional["provider|BTC|short"]["summary_by_policy"]["lock"]
    assert long["mean_delta_net_return_bps"] == 200.0
    assert short["mean_delta_net_return_bps"] == -200.0


def _result(side: str, estimated: float, actual: float) -> dict[str, object]:
    return {
        "lifecycle_id": f"BTC:{side}",
        "symbol": "BTC",
        "strategy_id": "provider",
        "side": side,
        "source_run_id": "run",
        "source_profile_fingerprint": "profile",
        "entry_notional_usd": 100.0,
        "policies": {
            "lock": {
                "status": "triggered",
                "estimated_net_pnl_usd": estimated,
                "actual_net_pnl_usd": actual,
            }
        },
    }
