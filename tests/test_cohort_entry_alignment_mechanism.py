from __future__ import annotations

import pytest

from hypervector.research.cohort_entry_alignment_mechanism import (
    build_live_entry_alignment_mechanism,
)


def test_entry_alignment_normalizes_closed_live_outcomes() -> None:
    """Alignment evidence stays descriptive and comparable across trade sizes."""
    report = build_live_entry_alignment_mechanism(
        [
            _trade("aligned_with_position", "aligned", 0.20, 4.0),
            _trade("opposing_position", "opposed", 0.75, 15.0),
            _trade("opposing_position", None, -0.10, -2.0, side="short"),
            _trade("unavailable", None, 0.05, 1.0, side="short"),
        ]
    )

    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "automatic_strategy_changes": False,
        "runtime_strategy_changed": False,
        "execution_gate": False,
        "portfolio_pnl_claimed": False,
    }
    pair = report["by_provider_symbol"]["hype_breakout|HYPE"]
    assert pair["closed_trades"] == 4
    component = pair["component_stance"]
    assert component["coverage"] == {"attributable": 3, "unavailable": 1}
    assert component["aligned"]["trades"] == 1
    assert component["aligned"]["mean_net_return_on_margin_pct"] == 4.0
    assert component["opposed"] == {
        "trades": 2,
        "wins": 1,
        "losses": 1,
        "breakeven": 0,
        "net_pnl_usd": pytest.approx(0.65),
        "mean_net_return_on_margin_pct": pytest.approx(6.5),
        "median_net_return_on_margin_pct": pytest.approx(6.5),
        "usd_profit_factor": pytest.approx(7.5),
        "normalized_profit_factor": pytest.approx(7.5),
    }
    assert component["opposed_minus_aligned_mean_pct"] == pytest.approx(2.5)
    relation = pair["breakout_side_relation"]
    assert relation["coverage"] == {"attributable": 2, "unavailable": 2}
    assert relation["aligned"]["trades"] == 1
    assert relation["opposed"]["trades"] == 1
    pooled = report["pooled"]
    assert pooled["closed_trades"] == 4
    assert pooled["component_stance"]["coverage"] == {
        "attributable": 3,
        "unavailable": 1,
    }
    assert pooled["component_stance"]["aligned"]["trades"] == 1
    assert pooled["component_stance"]["opposed"]["trades"] == 2
    assert pooled["breakout_side_relation"]["coverage"] == {
        "attributable": 2,
        "unavailable": 2,
    }
    assert report["provider_symbol_sides"] == 2
    long_pair = report["by_provider_symbol_side"]["hype_breakout|HYPE|long"]
    assert long_pair["closed_trades"] == 2
    assert long_pair["side"] == "long"
    assert long_pair["outcome"]["net_pnl_usd"] == pytest.approx(0.95)
    assert long_pair["outcome"]["mean_net_return_on_margin_pct"] == 9.5
    assert long_pair["component_stance"]["aligned"]["trades"] == 1
    assert long_pair["component_stance"]["opposed"]["trades"] == 1
    short_pair = report["by_provider_symbol_side"]["hype_breakout|HYPE|short"]
    assert short_pair["closed_trades"] == 2
    assert short_pair["side"] == "short"
    assert short_pair["outcome"]["net_pnl_usd"] == pytest.approx(-0.05)
    assert short_pair["outcome"]["mean_net_return_on_margin_pct"] == -0.5
    assert short_pair["breakout_side_relation"]["coverage"] == {
        "attributable": 0,
        "unavailable": 2,
    }


def test_entry_alignment_rejects_unknown_relation() -> None:
    """Unknown categorical telemetry cannot be silently relabeled unavailable."""
    trade = _trade("aligned_with_position", "sideways", 0.20, 4.0)

    with pytest.raises(ValueError, match="breakout-side relation"):
        build_live_entry_alignment_mechanism([trade])


def test_entry_alignment_rejects_unknown_position_side() -> None:
    """Malformed position direction cannot leak into a pooled side cohort."""
    trade = _trade("aligned_with_position", "aligned", 0.20, 4.0, side="flat")

    with pytest.raises(ValueError, match="position side"):
        build_live_entry_alignment_mechanism([trade])


def test_entry_alignment_names_usd_and_margin_normalized_profit_factors() -> None:
    """Different denominators must remain explicit when trade margins vary."""
    report = build_live_entry_alignment_mechanism(
        [
            _trade("aligned_with_position", "aligned", 0.20, 10.0),
            _trade("aligned_with_position", "aligned", -0.10, -2.0),
        ]
    )

    outcome = report["by_provider_symbol_side"]["hype_breakout|HYPE|long"]["outcome"]
    assert outcome["usd_profit_factor"] == pytest.approx(2.0)
    assert outcome["normalized_profit_factor"] == pytest.approx(5.0)


def test_entry_alignment_keeps_open_mechanisms_separate_and_provisional() -> None:
    """Open marks expose mechanism context without contaminating closed results."""
    report = build_live_entry_alignment_mechanism(
        [_trade("aligned_with_position", "aligned", 0.20, 4.0)],
        open_trades=[
            _open_trade(
                "opposing_position",
                "opposed",
                marked_net=0.06,
                margin=5.0,
                mfe=50.0,
                mae=1.0,
                giveback=24.0,
            )
        ],
    )

    assert report["closed_trades"] == 1
    provisional = report["provisional_open"]
    assert provisional["positions"] == 1
    assert provisional["pooled_with_closed_performance"] is False
    pair = provisional["by_provider_symbol_side"]["hype_breakout|HYPE|short"]
    assert pair["positions"] == 1
    assert pair["protected_positions"] == 1
    assert pair["component_stance_counts"] == {"opposing_position": 1}
    assert pair["breakout_side_relation_counts"] == {"opposed": 1}
    assert pair["marked_economics_coverage"] == {"available": 1, "unavailable": 0}
    assert pair["marked_net_pnl_usd"] == pytest.approx(0.06)
    assert pair["mean_marked_return_on_margin_pct"] == pytest.approx(1.2)
    assert pair["path_coverage"] == {"available": 1, "unavailable": 0}
    assert pair["mean_mfe_bps"] == 50.0
    assert pair["mean_mae_bps"] == 1.0
    assert pair["mean_peak_giveback_bps"] == 24.0
    assert pair["lifecycles"] == [
        {
            "lifecycle_id": "HYPE:open-1",
            "component_stance": "opposing_position",
            "breakout_side_relation": "opposed",
            "provider_native_mechanism": "unavailable",
            "marked_net_pnl_usd": 0.06,
            "marked_return_on_margin_pct": pytest.approx(1.2),
            "mfe_bps": 50.0,
            "mae_bps": 1.0,
            "peak_giveback_bps": 24.0,
            "protected": True,
        }
    ]


def test_entry_alignment_attributes_hip3_provider_native_mechanism() -> None:
    """HIP-3 paths retain their causal recipe identity without fake regimes."""
    closed = _hip3_trade(side="long", net_pnl_usd=0.20, return_pct=1.4)
    opened = _hip3_trade(side="short", net_pnl_usd=None, return_pct=None)
    opened.update(
        {
            "lifecycle_id": "xyz:SNDK:open-1",
            "marked_economics": {
                "active_lifecycle_marked_net_pnl_usd": -0.10,
                "margin_used_usd": 15.0,
            },
            "path_since_entry": {
                "status": "observed",
                "maximum_favorable_excursion_bps": 2.0,
                "maximum_adverse_excursion_bps": 11.0,
                "peak_giveback_bps": 4.0,
            },
            "protective_stop": {"oid": 456},
        }
    )

    report = build_live_entry_alignment_mechanism([closed], open_trades=[opened])

    pair = report["by_provider_symbol"][
        "hip3_swing_ha_sndk_gold_brent_bidirectional_v1|xyz:SNDK"
    ]
    native = pair["provider_native_mechanism"]
    assert native["coverage"] == {"attributable": 1, "unavailable": 0}
    identity = next(iter(native["by_identity"]))
    assert identity == (
        "hip3_swing:entry=onset:exit=ha_flip:ema=aligned:ha=aligned:"
        "order_block=aligned:pivot=confirmed_by_eligible_decision"
    )
    assert native["by_identity"][identity]["trades"] == 1
    open_pair = report["provisional_open"]["by_provider_symbol_side"][
        "hip3_swing_ha_sndk_gold_brent_bidirectional_v1|xyz:SNDK|short"
    ]
    assert open_pair["provider_native_mechanism_counts"] == {identity: 1}
    assert open_pair["lifecycles"][0]["provider_native_mechanism"] == identity


def test_hip3_native_identity_discloses_legacy_partial_metric_coverage() -> None:
    """Earlier eligible HIP-3 rows retain known EMA/recipe identity explicitly."""
    trade = _hip3_trade(side="long", net_pnl_usd=0.20, return_pct=1.4)
    metrics = trade["entry_context"]["signal_provider"]["readiness"]["metrics"]
    metrics["ha_color"] = None
    metrics["active_order_block_direction"] = None

    report = build_live_entry_alignment_mechanism([trade])

    native = report["by_provider_symbol"][
        "hip3_swing_ha_sndk_gold_brent_bidirectional_v1|xyz:SNDK"
    ]["provider_native_mechanism"]
    identity = next(iter(native["by_identity"]))
    assert identity == (
        "hip3_swing:entry=onset:exit=ha_flip:ema=aligned:ha=unavailable:"
        "order_block=unavailable:pivot=confirmed_by_eligible_decision"
    )


def _trade(
    component_stance: str,
    breakout_relation: str | None,
    net_pnl_usd: float,
    return_pct: float,
    *,
    side: str = "long",
) -> dict[str, object]:
    metrics: dict[str, object] = {}
    if breakout_relation is not None:
        metrics["breakout_side_relation"] = breakout_relation
    return {
        "strategy_id": "hype_breakout",
        "symbol": "HYPE",
        "side": side,
        "net_pnl_usd": net_pnl_usd,
        "net_return_on_margin_pct": return_pct,
        "entry_regime_assessment": {"component_stance": component_stance},
        "entry_context": {"signal_provider": {"readiness": {"metrics": metrics}}},
    }


def _open_trade(
    component_stance: str,
    breakout_relation: str,
    *,
    marked_net: float,
    margin: float,
    mfe: float,
    mae: float,
    giveback: float,
) -> dict[str, object]:
    """Build one protected provisional lifecycle with causal entry attribution."""
    trade = _trade(component_stance, breakout_relation, 0.0, 0.0, side="short")
    trade.pop("net_pnl_usd")
    trade.pop("net_return_on_margin_pct")
    trade.update(
        {
            "lifecycle_id": "HYPE:open-1",
            "marked_economics": {
                "active_lifecycle_marked_net_pnl_usd": marked_net,
                "margin_used_usd": margin,
            },
            "path_since_entry": {
                "status": "observed",
                "maximum_favorable_excursion_bps": mfe,
                "maximum_adverse_excursion_bps": mae,
                "peak_giveback_bps": giveback,
            },
            "protective_stop": {"oid": 123, "trigger_price": 10.0},
        }
    )
    return trade


def _hip3_trade(
    *,
    side: str,
    net_pnl_usd: float | None,
    return_pct: float | None,
) -> dict[str, object]:
    """Build one source-identifiable HIP-3 Swing lifecycle."""
    direction = 1.0 if side == "long" else -1.0
    trade: dict[str, object] = {
        "strategy_id": "hip3_swing_ha_sndk_gold_brent_bidirectional_v1",
        "symbol": "xyz:SNDK",
        "side": side,
        "entry_regime_assessment": {"component_stance": "unavailable"},
        "entry_context": {
            "signal_provider": {
                "strategy_id": "hip3_swing_ha_sndk_gold_brent_bidirectional_v1",
                "eligible": True,
                "readiness": {
                    "blockers": [],
                    "metrics": {
                        "entry_mode": "onset",
                        "exit_mode": "ha_flip",
                        "ema_fast": 110.0 if side == "long" else 90.0,
                        "ema_slow": 100.0,
                        "ha_color": direction,
                        "active_order_block_direction": direction,
                    },
                },
            }
        },
    }
    if net_pnl_usd is not None and return_pct is not None:
        trade["net_pnl_usd"] = net_pnl_usd
        trade["net_return_on_margin_pct"] = return_pct
    return trade
