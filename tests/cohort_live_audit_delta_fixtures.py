"""Compact source-backed fixtures for cohort live-audit delta tests."""

from __future__ import annotations

from copy import deepcopy


def audit(*, row_count: int, timestamp: str) -> dict[str, object]:
    """Return one minimal source-backed live-audit prefix."""
    return {
        "mode": "multi_asset_bidirectional_live_audit",
        "experiment_contract": {
            "execution_authority": "none",
            "report_only": True,
            "runtime_strategy_changed": False,
        },
        "run": {
            "run_id": "run-1",
            "profile_id": "profile-1",
            "profile_fingerprint": "a" * 64,
            "row_count": row_count,
            "last_observed_at_utc": timestamp,
        },
        "coverage": {
            "complete": False,
            "technical_gaps": ["provider_metric_telemetry_missing"],
        },
        "execution": {
            "closed_trades": 1,
            "wins": 1,
            "losses": 0,
            "net_pnl_usd": 0.5,
            "fees_usd": 0.1,
            "funding_usd": -0.01,
            "fills": 2,
        },
        "signal_outcomes": _empty_signal_outcomes(),
        "trade_reflections": {
            "trades": [{"lifecycle_id": "BTC:closed", "net_pnl_usd": 0.5}]
        },
        "open_trade_reflections": {"trades": _open_trade_fixtures()},
    }


def audit_with_resolved_open_changes() -> dict[str, object]:
    """Return the later prefix used to separate resolved and open economics."""
    result = audit(row_count=20, timestamp="2026-08-08T11:00:00+00:00")
    execution = result["execution"]
    assert isinstance(execution, dict)
    execution.update(
        closed_trades=2,
        wins=1,
        losses=1,
        net_pnl_usd=0.2,
        fees_usd=0.15,
        funding_usd=-0.02,
        fills=4,
    )
    signal_outcomes = result["signal_outcomes"]
    assert isinstance(signal_outcomes, dict)
    coverage = signal_outcomes["coverage"]
    assert isinstance(coverage, dict)
    coverage.update(metric_value_gaps=4, right_censored_observations=3)
    reflections = result["trade_reflections"]
    assert isinstance(reflections, dict)
    trades = reflections["trades"]
    assert isinstance(trades, list)
    trades.append({"lifecycle_id": "SOL:2", "net_pnl_usd": -0.3})
    open_reflections = result["open_trade_reflections"]
    assert isinstance(open_reflections, dict)
    open_reflections["trades"] = _changed_open_trade_fixtures()
    return result


def signal_outcomes(*, resolved: int, censored: int) -> dict[str, object]:
    """Return compact causal provider-outcome evidence for one horizon."""
    cost_count = resolved // 2
    horizon = _signal_horizon(resolved, censored, cost_count)
    blocker_count = max(0, cost_count - 1)
    blocker_horizon = _signal_horizon(blocker_count, censored, cost_count)
    return {
        "evaluations": 10 + resolved,
        "eligible_evaluations": resolved - 1,
        "directional_evaluations": 10 + resolved,
        "by_provider_symbol": {
            "strategy-1|BTC": {
                "evaluations": 10 + resolved,
                "eligible_evaluations": resolved - 1,
                "readiness_annotations": 4,
                "horizons": {"5": horizon},
                "one_blocker_near_misses": {
                    "evaluations": blocker_count,
                    "by_blocker": {
                        "expansion_trigger_not_present": {
                            "evaluations": blocker_count,
                            "horizons": {"5": blocker_horizon},
                        }
                    },
                },
            }
        },
    }


def portfolio_dedup(
    *, resolved: int, provider_observations: int, unique_paths: int
) -> dict[str, object]:
    """Return compact cumulative portfolio-path evidence for one horizon."""
    capture = _capture(resolved)
    episode_onsets = {
        "resolved": resolved,
        "non_overlapping_resolved": resolved,
        "censored": 0,
        "opportunity_capture": capture,
        "independent_opportunity_capture": capture,
        "independent_paths": _independent_paths(resolved),
    }
    return {
        "provider_observations": provider_observations,
        "unique_directional_paths": unique_paths,
        "duplicate_provider_observations_removed": (
            provider_observations - unique_paths
        ),
        "cross_provider_path_groups": provider_observations - unique_paths,
        "direction_competition_groups": 0,
        "reference_price_conflict_groups": 0,
        "by_attribution": [_attribution(unique_paths, resolved, episode_onsets)],
        "horizons": {"5": _portfolio_horizon(resolved, capture)},
    }


def episode_paths(portfolio: dict[str, object]) -> list[dict[str, object]]:
    """Return the mutable independent episode-path fixture list."""
    attributions = portfolio["by_attribution"]
    assert isinstance(attributions, list)
    attribution = attributions[0]
    assert isinstance(attribution, dict)
    horizons = attribution["horizons"]
    assert isinstance(horizons, dict)
    horizon = horizons["5"]
    assert isinstance(horizon, dict)
    episode_onsets = horizon["episode_onsets"]
    assert isinstance(episode_onsets, dict)
    paths = episode_onsets["independent_paths"]
    assert isinstance(paths, list)
    return paths


def add_unchanged_attribution_pair(
    before: dict[str, object], after: dict[str, object]
) -> None:
    """Append one identical attribution row to both cumulative prefixes."""
    before_rows = _attribution_rows(before)
    after_rows = _attribution_rows(after)
    template = deepcopy(before_rows[0])
    template["symbol"] = "ETH"
    before_rows.append(deepcopy(template))
    after_rows.append(deepcopy(template))


def open_trade(
    lifecycle_id: str,
    *,
    marked_net: float,
    return_bps: float,
    mfe_bps: float,
    mae_bps: float,
    ignored_signals: int,
    ignored_return_bps: float | None,
    action: str,
    lock_status: str,
) -> dict[str, object]:
    """Return one compact open-lifecycle reflection fixture."""
    return {
        "lifecycle_id": lifecycle_id,
        "symbol": lifecycle_id.split(":", maxsplit=1)[0],
        "strategy_id": "strategy-1",
        "side": "long",
        "holding_time_ms": 1_000,
        "marked_economics": {
            "active_lifecycle_marked_net_pnl_usd": marked_net,
        },
        "path_since_entry": {
            "current_directional_return_bps": return_bps,
            "maximum_favorable_excursion_bps": mfe_bps,
            "maximum_adverse_excursion_bps": mae_bps,
            "peak_giveback_bps": mfe_bps - return_bps,
        },
        "ignored_provider_exit_observer": {
            "ignored_signal_count": ignored_signals,
            "path_since_first_signal": {
                "current_directional_return_bps": ignored_return_bps,
            },
        },
        "current_context": {"signal_provider": {"decision_action": action}},
        "open_profit_lock_challenger": {
            "policies": {"a25_floor15_trail10": {"status": lock_status}}
        },
    }


def _empty_signal_outcomes() -> dict[str, object]:
    return {
        "evaluations": 0,
        "eligible_evaluations": 0,
        "directional_evaluations": 0,
        "by_provider_symbol": {},
        "coverage": {
            "metric_value_gaps": 2,
            "right_censored_observations": 4,
        },
    }


def _open_trade_fixtures() -> list[dict[str, object]]:
    return [
        open_trade(
            "BTC:1",
            marked_net=0.2,
            return_bps=20.0,
            mfe_bps=40.0,
            mae_bps=10.0,
            ignored_signals=2,
            ignored_return_bps=5.0,
            action="hold",
            lock_status="not_activated",
        ),
        open_trade(
            "SOL:2",
            marked_net=-0.2,
            return_bps=-15.0,
            mfe_bps=3.0,
            mae_bps=20.0,
            ignored_signals=1,
            ignored_return_bps=-2.0,
            action="close_open_position",
            lock_status="not_activated",
        ),
    ]


def _changed_open_trade_fixtures() -> list[dict[str, object]]:
    return [
        open_trade(
            "BTC:1",
            marked_net=0.25,
            return_bps=30.0,
            mfe_bps=45.0,
            mae_bps=12.0,
            ignored_signals=3,
            ignored_return_bps=8.0,
            action="hold",
            lock_status="triggered_before_current_boundary",
        ),
        open_trade(
            "ETH:3",
            marked_net=-0.1,
            return_bps=-5.0,
            mfe_bps=2.0,
            mae_bps=7.0,
            ignored_signals=0,
            ignored_return_bps=None,
            action="hold",
            lock_status="not_activated",
        ),
    ]


def _signal_horizon(resolved: int, censored: int, cost_count: int) -> dict[str, object]:
    capture = {
        "resolved": resolved,
        "cost_clearing_close_count": cost_count,
        "cost_clearing_mfe_count": cost_count,
        "failed_to_clear_cost_count": 2,
        "reversed_after_cost_clear_count": cost_count,
        "robust_mfe_count": cost_count,
    }
    return {
        "censored": censored,
        "resolved": resolved,
        "non_overlapping_resolved": resolved,
        "opportunity_capture": capture,
        "independent_opportunity_capture": dict(capture),
    }


def _capture(resolved: int) -> dict[str, int]:
    captured = resolved // 2
    return {
        "resolved": resolved,
        "cost_clearing_close_count": captured,
        "cost_clearing_mfe_count": captured,
        "failed_to_clear_cost_count": resolved - captured,
        "reversed_after_cost_clear_count": 0,
        "robust_mfe_count": captured,
    }


def _independent_paths(resolved: int) -> list[dict[str, object]]:
    return [
        {
            "source_run_id": "run-1",
            "decision_time_ms": 1 + index * 60_000,
            "reference_price": 100.0 + index,
            "directional_close_return_bps": 20.0 + index,
            "favorable_excursion_bps": 30.0 + index,
            "adverse_excursion_bps": 5.0,
        }
        for index in range(resolved)
    ]


def _attribution(
    unique_paths: int,
    resolved: int,
    episode_onsets: dict[str, object],
) -> dict[str, object]:
    return {
        "source_run_id": "run-1",
        "symbol": "BTC",
        "side": "long",
        "path_groups": unique_paths,
        "decision_cadence": {
            "decision_minutes": unique_paths,
            "episode_count": resolved,
        },
        "providers": [
            {
                "strategy_id": "strategy-1",
                "blocker": "expansion_trigger_not_present",
            }
        ],
        "horizons": {"5": {"episode_onsets": episode_onsets}},
    }


def _attribution_rows(portfolio: dict[str, object]) -> list[dict[str, object]]:
    rows = portfolio["by_attribution"]
    assert isinstance(rows, list)
    assert all(isinstance(row, dict) for row in rows)
    return rows


def _portfolio_horizon(resolved: int, capture: dict[str, int]) -> dict[str, object]:
    return {
        "resolved": resolved,
        "non_overlapping_resolved": resolved,
        "censored": 0,
        "opportunity_capture": capture,
        "independent_opportunity_capture": capture,
    }
