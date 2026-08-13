"""Contract tests for the fixed HIP-3 route-authority comparison."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

_SCRIPT = Path("scripts/hip3_route_authority_pruning.py")
_SPEC = importlib.util.spec_from_file_location("hip3_route_pruning_script", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def test_fixed_variants_preserve_existing_v29_v30_and_both_sides() -> None:
    variants = {row.variant_id: row for row in _MODULE.fixed_variants()}

    assert set(variants) == {
        "full_v25_hip3",
        "weak_swing_pruned",
        "weak_swing_sndk_breakout_pruned",
        "v29_hip3",
        "v30_spcx_core",
    }
    full = set(variants["full_v25_hip3"].routes)
    assert len(full) == 10
    assert set(variants["weak_swing_pruned"].routes).issubset(full)
    assert set(variants["weak_swing_sndk_breakout_pruned"].routes).issubset(
        set(variants["weak_swing_pruned"].routes)
    )
    assert variants["v30_spcx_core"].routes == ((_MODULE.SWING_INDEX, "xyz:SPCX"),)


def test_live_reconciliation_uses_exact_route_identity_and_no_open_marks() -> None:
    audit = _reconciliation_audit()

    result = _MODULE.build_live_reconciliation(audit, _MODULE.fixed_variants())

    v30 = result["variants"]["v30_spcx_core"]
    assert v30["closed_trades"] == 2
    assert v30["net_pnl_usd"] == pytest.approx(0.9)
    assert v30["profit_factor"] == pytest.approx(2.5)
    v29 = result["variants"]["v29_hip3"]
    assert v29["closed_trades"] == 3
    assert v29["net_pnl_usd"] == pytest.approx(0.7)
    assert result["open_marks_included"] is False
    assert result["source_open_lifecycles"] == 2


def _reconciliation_audit() -> dict[str, object]:
    audit = {
        "execution_authority": "none",
        "run": {
            "profile_id": "multi_asset_bidirectional_complete_portfolio_canary_v25",
            "profile_fingerprint": "fingerprint",
            "run_id": "run",
        },
        "strategy_scorecard": {
            "by_provider_symbol": {
                f"{_MODULE.SWING_INDEX}|xyz:SPCX": {
                    "execution_performance": {
                        "closed_trades": 2,
                        "wins": 1,
                        "losses": 1,
                        "net_pnl_usd": 0.9,
                    },
                    "repeatability_evidence": {
                        "gross_profit_usd": 1.5,
                        "gross_loss_usd": 0.6,
                    },
                },
                f"{_MODULE.SWING_COMMODITY}|xyz:GOLD": {
                    "execution_performance": {
                        "closed_trades": 1,
                        "wins": 0,
                        "losses": 1,
                        "net_pnl_usd": -0.2,
                    },
                    "repeatability_evidence": {
                        "gross_profit_usd": 0.0,
                        "gross_loss_usd": 0.2,
                    },
                },
            }
        },
        "open_trade_reflections": {
            "open_lifecycles": 2,
            "trades": [
                {"marked_economics": {"active_lifecycle_marked_net_pnl_usd": 99}}
            ],
        },
    }
    return audit


def test_live_reconciliation_rejects_wrong_profile_or_authority() -> None:
    audit = {
        "execution_authority": "none",
        "run": {"profile_id": "wrong", "profile_fingerprint": "x", "run_id": "r"},
        "strategy_scorecard": {"by_provider_symbol": {}},
        "open_trade_reflections": {"open_lifecycles": 0},
    }

    with pytest.raises(ValueError, match="v25 profile"):
        _MODULE.build_live_reconciliation(audit, _MODULE.fixed_variants())

    audit["run"]["profile_id"] = (
        "multi_asset_bidirectional_complete_portfolio_canary_v25"
    )
    audit["execution_authority"] = "hyperliquid_mainnet"
    with pytest.raises(ValueError, match="no execution authority"):
        _MODULE.build_live_reconciliation(audit, _MODULE.fixed_variants())


def test_evidence_windows_use_common_clock_not_misaligned_native_phases() -> None:
    commodity = {
        "development_start_utc": "2026-03-01T00:00:00+00:00",
        "development_end_utc": "2026-06-01T00:00:00+00:00",
        "validation_end_utc": "2026-07-01T00:00:00+00:00",
        "holdout_end_utc": "2026-08-01T00:00:00+00:00",
    }
    index = {
        "development_start_utc": "2026-05-01T00:00:00+00:00",
        "development_end_utc": "2026-07-15T00:00:00+00:00",
        "validation_end_utc": "2026-07-25T00:00:00+00:00",
        "holdout_end_utc": "2026-08-01T00:00:00+00:00",
    }
    source = {
        "cases": {
            _MODULE.SWING_INDEX: {"windows": index},
            _MODULE.BREAKOUT_INDEX: {"windows": index},
            _MODULE.SWING_COMMODITY: {"windows": commodity},
            _MODULE.BREAKOUT_COMMODITY: {"windows": commodity},
        }
    }

    windows = _MODULE.evidence_windows(source)

    assert [window.window_id for window in windows] == [
        "common_early",
        "common_later_descriptive",
        "common_full",
    ]
    assert windows[0].start_ms == _MODULE.timestamp_ms("2026-05-01T00:00:00Z")
    assert windows[0].end_ms == _MODULE.timestamp_ms("2026-06-01T00:00:00Z")
    assert windows[1].start_ms == windows[0].end_ms
    assert windows[1].end_ms == _MODULE.timestamp_ms("2026-07-01T00:00:00Z")
    assert windows[2].start_ms == windows[0].start_ms
    assert windows[2].end_ms == windows[1].end_ms
