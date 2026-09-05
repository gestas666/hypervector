"""Tests for exact-contract prospective HYPE-native lifecycle evidence."""

from importlib import import_module
from importlib.util import find_spec
from types import ModuleType

import pytest


_RUN = "bidirectional-observe-1"
_PROFILE = "multi_asset_growth_first_5000_hype_native_long_challenger_v54"
_PROFILE_FINGERPRINT = "profile-fingerprint"
_RUN_FINGERPRINT = "run-fingerprint"
_STRATEGY = "hype_native_breakout_onset_long_v3"
_BASELINE_STRATEGY = "hype_breakout_compression_alignment_bidirectional_v2"


def _envelope(event_type: str, observed_ms: int, payload: object) -> dict[str, object]:
    """Build one exact report-only observer row."""
    return {
        "schema_version": 1,
        "sequence": observed_ms,
        "event_type": event_type,
        "observed_at_utc": _iso(observed_ms),
        "execution_mode": "observe",
        "effective_mode": "OBSERVE ONLY",
        "live_armed": False,
        "execution_authority": "none",
        "profile_id": _PROFILE,
        "profile_fingerprint": _PROFILE_FINGERPRINT,
        "run_fingerprint": _RUN_FINGERPRINT,
        "run_id": _RUN,
        "payload": payload,
    }


def _identity() -> dict[str, object]:
    """Build the frozen v54 long-only observer identity."""
    execution = {
        "entry_liquidity": "taker_ioc",
        "stop_policy": "fixed_bps",
        "target_policy": "none",
        "maximum_hold_seconds": 28_800,
        "stop_bps": 80.0,
        "maximum_hold_policy": "fixed",
        "hard_maximum_hold_seconds": None,
        "provider_recipe_exit_policy": "honor",
    }
    return _envelope(
        "configuration_identity",
        0,
        {
            "symbol": "MULTI",
            "strategy_name": "multi_asset_bidirectional_cohort",
            "profile_fingerprint": _PROFILE_FINGERPRINT,
            "enabled_symbols": ["BTC", "HYPE"],
            "assets": [
                {
                    "symbol": "HYPE",
                    "sides": ["long", "short"],
                    "leverage": 5.0,
                    "margin_fraction": 0.05,
                    "max_notional_usd": 1_250.0,
                    "stop_bps": 80.0,
                    "maximum_hold_seconds": 86_400,
                }
            ],
            "providers": [
                {
                    "strategy_id": _STRATEGY,
                    "symbols": ["HYPE"],
                    "sides": ["long", "short"],
                    "execution_symbols": ["HYPE"],
                    "execution_side_overrides": {"HYPE": ["long"]},
                    "maximum_entry_delay_seconds": 60,
                    "execution": execution,
                }
            ],
            "runtime": {"poll_seconds": 15.0},
        },
    )


def _book(
    observed_ms: int, bid: float = 99.99, ask: float = 100.01
) -> dict[str, object]:
    """Build one uncrossed exact 20-level-equivalent HYPE book."""
    book = {
        "symbol": "HYPE",
        "source": "hyperliquid_mainnet_l2_rest",
        "exchange_ts_ms": observed_ms - 1,
        "recv_ts_ms": observed_ms,
        "bids": [{"price": bid, "size": 100.0, "orders": 1}],
        "asks": [{"price": ask, "size": 100.0, "orders": 1}],
    }
    return _envelope("market_books", observed_ms, {"books": {"HYPE": book}})


def _books_through(start_ms: int, end_ms: int) -> tuple[dict[str, object], ...]:
    """Build continuous 30-second book coverage through an exact boundary."""
    return tuple(_book(value) for value in range(start_ms, end_ms + 1, 30_000))


def _entry_evaluation(decision_ms: int = 60_000) -> dict[str, object]:
    """Build one exact eligible v54 native long evaluation."""
    return {
        "strategy_id": _STRATEGY,
        "symbol": "HYPE",
        "decision_time_ms": decision_ms,
        "reference_price": 100.0,
        "decision_action": "enter_long",
        "eligible": True,
        "reason": "breakout_onset_directional",
        "side": "long",
        "primary_regime": "BREAKOUT",
        "state_1m": "TREND_UP",
        "state_5m": "BREAKOUT",
        "context_15m": "RANGE",
        "readiness": {
            "side": "long",
            "conditions_met": 3,
            "conditions_required": 3,
            "blockers": [],
            "indicators": ["ONSET YES"],
            "metrics": {
                "authoritative_5m_bbwp_percentile": 90.4,
                "breakout_onset": True,
                "breakout_side": "long",
                "breakout_side_relation": "aligned",
                "breakout_volume_ratio": 7.2,
                "current_bbwp_percentile": 90.8,
                "directional_bar_body_bps": 15.8,
                "ema_gap_directional_bps": 23.3,
                "prior_bbwp_min_15m": 78.8,
                "structural_direction": "long",
            },
        },
    }


def _baseline_evaluation(decision_ms: int = 60_000) -> dict[str, object]:
    """Build the exact same-bar v53 compression rejection."""
    row = _entry_evaluation(decision_ms)
    row.update(
        strategy_id=_BASELINE_STRATEGY,
        decision_action="hold",
        eligible=False,
        reason="authoritative_5m_compression_absent",
    )
    readiness = dict(row["readiness"])
    readiness.update(
        conditions_met=2,
        conditions_required=5,
        blockers=[
            "authoritative_5m_compression_absent",
            "prior_compression_absent",
            "directional_pullback_absent",
        ],
    )
    row["readiness"] = readiness
    return row


def _exit_evaluation(decision_ms: int = 120_000) -> dict[str, object]:
    """Build the v54 short-onset exit-only evaluation."""
    row = _entry_evaluation(decision_ms)
    row.update(
        decision_action="close_long",
        eligible=False,
        reason="opposite_native_onset_exit_only",
        side="short",
        exit_sides=["long"],
        exit_reason="opposite_native_onset",
    )
    readiness = dict(row["readiness"])
    readiness["side"] = "short"
    row["readiness"] = readiness
    return row


def _routing(
    observed_ms: int, evaluations: list[dict[str, object]]
) -> dict[str, object]:
    """Build one observer routing row with no executable actions."""
    return _envelope(
        "intent_routing",
        observed_ms,
        {
            "evaluations": evaluations,
            "setup_coverage": {
                "expected_provider_symbols": 1,
                "observed_provider_symbols": 1,
                "missing_provider_symbols": [],
                "complete": True,
            },
            "actions": [],
            "withheld": [],
        },
    )


def _iso(milliseconds: int) -> str:
    """Return a UTC timestamp accepted by observer readers."""
    import pandas as pd

    return pd.Timestamp(milliseconds, unit="ms", tz="UTC").isoformat()


def _spec(module: ModuleType) -> object:
    """Build the frozen prospective tracker specification."""
    spec_type = getattr(module, "HypeNativeProspectiveSpec", None)
    assert callable(spec_type)
    return spec_type(
        run_id=_RUN,
        profile_id=_PROFILE,
        profile_fingerprint=_PROFILE_FINGERPRINT,
        run_fingerprint=_RUN_FINGERPRINT,
        strategy_id=_STRATEGY,
        symbol="HYPE",
        notional_usd=1_250.0,
        stop_bps=80.0,
        maximum_hold_seconds=28_800,
        maximum_entry_delay_ms=60_000,
        maximum_exit_delay_ms=60_000,
        fee_bps_per_side=4.32,
        residual_slippage_bps_per_side=2.0,
        maximum_book_gap_ms=45_000,
    )


def test_prospective_lifecycle_module_exists() -> None:
    """Prospective v54 evidence has a dedicated report-only boundary."""
    assert (
        find_spec("hypervector.research.hype_native_prospective_lifecycle") is not None
    )


def test_report_waits_without_inventing_a_trade_or_pnl() -> None:
    """A quiet observer window is explicit zero-signal evidence."""
    module = import_module("hypervector.research.hype_native_prospective_lifecycle")
    build = getattr(module, "build_hype_native_prospective_report", None)
    assert callable(build)

    report = build((_identity(), _book(15_000)), _spec(module))

    assert report["status"] == "waiting_for_first_eligible_long"
    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["realized_pnl_claimed"] is False
    assert report["signal_counts"] == {
        "eligible_long_entries": 0,
        "exit_only_short_onsets": 0,
    }
    assert report["attempts"] == []
    assert report["resolved_proxy_summary"]["trades"] == 0
    assert report["resolved_proxy_summary"]["net_pnl_usd_before_funding"] is None


def test_long_entry_resolves_at_native_short_onset_before_deadline() -> None:
    """The candidate's disabled short side remains exact long-exit authority."""
    module = import_module("hypervector.research.hype_native_prospective_lifecycle")
    records = (
        _identity(),
        _routing(67_000, [_entry_evaluation(), _baseline_evaluation()]),
        _book(70_000),
        _book(100_000, bid=100.49, ask=100.51),
        _routing(125_000, [_exit_evaluation()]),
        _book(130_000, bid=100.99, ask=101.01),
    )

    report = module.build_hype_native_prospective_report(records, _spec(module))

    assert report["signal_counts"] == {
        "eligible_long_entries": 1,
        "exit_only_short_onsets": 1,
    }
    assert len(report["attempts"]) == 1
    lifecycle = report["lifecycles"][0]
    assert lifecycle["side"] == "long"
    assert lifecycle["entry_book_time_ms"] == 70_000
    assert lifecycle["exit_reason"] == "opposite_native_onset"
    assert lifecycle["exit_book_time_ms"] == 130_000
    assert lifecycle["net_pnl_usd_before_funding"] > 0.0
    assert lifecycle["funding_bps"] is None
    assert lifecycle["mark_stop_truth"] == "unavailable"
    assert lifecycle["maximum_book_gap_ms"] == 30_000
    assert lifecycle["maximum_favorable_excursion_bps"] > 90.0
    assert lifecycle["maximum_adverse_excursion_bps"] > 0.0
    assert lifecycle["entry_context"]["context_15m"] == "RANGE"
    assert report["resolved_proxy_summary"]["trades"] == 1
    assert report["resolved_proxy_summary"]["wins"] == 1


def test_native_entry_explains_exact_same_bar_baseline_rejection() -> None:
    """Every native opportunity records why the active compression route abstained."""
    module = import_module("hypervector.research.hype_native_prospective_lifecycle")
    records = (
        _identity(),
        _routing(67_000, [_entry_evaluation(), _baseline_evaluation()]),
        _book(70_000),
        _book(100_000, bid=100.49, ask=100.51),
    )

    report = module.build_hype_native_prospective_report(records, _spec(module))

    assert report["baseline_comparisons"] == [
        {
            "symbol": "HYPE",
            "decision_time_ms": 60_000,
            "reference_price": 100.0,
            "native_strategy_id": _STRATEGY,
            "native_eligible": True,
            "baseline_strategy_id": _BASELINE_STRATEGY,
            "baseline_eligible": False,
            "baseline_reason": "authoritative_5m_compression_absent",
            "baseline_blockers": [
                "authoritative_5m_compression_absent",
                "prior_compression_absent",
                "directional_pullback_absent",
            ],
            "baseline_conditions_met": 2,
            "baseline_conditions_required": 5,
            "common_feature_parity": True,
            "opportunity_class": (
                "native_breakout_admitted_compression_pullback_rejected"
            ),
        }
    ]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing", "lacks exact baseline comparison"),
        ("reference", "reference prices differ"),
        ("feature", "breakout_onset differ"),
    ],
)
def test_native_baseline_comparison_fails_closed(mutation: str, message: str) -> None:
    """Missing or nonidentical same-bar evidence cannot support comparison."""
    module = import_module("hypervector.research.hype_native_prospective_lifecycle")
    baseline = _baseline_evaluation()
    if mutation == "reference":
        baseline["reference_price"] = 101.0
    if mutation == "feature":
        readiness = dict(baseline["readiness"])
        metrics = dict(readiness["metrics"])
        metrics["breakout_onset"] = False
        readiness["metrics"] = metrics
        baseline["readiness"] = readiness
    evaluations = [_entry_evaluation()]
    if mutation != "missing":
        evaluations.append(baseline)

    with pytest.raises(ValueError, match=message):
        module.build_hype_native_prospective_report(
            (_identity(), _routing(67_000, evaluations), _book(70_000)),
            _spec(module),
        )


def test_protective_stop_precedes_later_opposite_onset() -> None:
    """The first sampled stop crossing wins over a later native exit."""
    module = import_module("hypervector.research.hype_native_prospective_lifecycle")
    records = (
        _identity(),
        _routing(67_000, [_entry_evaluation(), _baseline_evaluation()]),
        _book(70_000),
        _book(100_000, bid=99.0, ask=99.02),
        _routing(125_000, [_exit_evaluation()]),
        _book(130_000, bid=100.99, ask=101.01),
    )

    report = module.build_hype_native_prospective_report(records, _spec(module))

    lifecycle = report["lifecycles"][0]
    assert lifecycle["exit_reason"] == "protective_stop_bbo_proxy"
    assert lifecycle["exit_book_time_ms"] == 100_000
    assert lifecycle["status"] == "resolved_bbo_stop_proxy_mark_trigger_unverified"
    assert lifecycle["net_pnl_usd_before_funding"] < 0.0


def test_fixed_eight_hour_exit_is_secondary_fallback() -> None:
    """No stop or opposite onset falls back to the frozen eight-hour close."""
    module = import_module("hypervector.research.hype_native_prospective_lifecycle")
    deadline = 70_000 + 28_800_000
    records = (
        _identity(),
        _routing(67_000, [_entry_evaluation(), _baseline_evaluation()]),
        *_books_through(70_000, deadline),
    )

    report = module.build_hype_native_prospective_report(records, _spec(module))

    lifecycle = report["lifecycles"][0]
    assert lifecycle["exit_reason"] == "maximum_hold"
    assert lifecycle["exit_book_time_ms"] == deadline
    assert lifecycle["technical_path_resolved"] is True
    assert report["resolved_proxy_summary"]["trades"] == 1


def test_open_lifecycle_is_not_counted_as_a_resolved_trade() -> None:
    """An entry before its exit remains pending and contributes no closed PnL."""
    module = import_module("hypervector.research.hype_native_prospective_lifecycle")
    records = (
        _identity(),
        _routing(67_000, [_entry_evaluation(), _baseline_evaluation()]),
        _book(70_000),
        _book(100_000, bid=100.49, ask=100.51),
    )

    report = module.build_hype_native_prospective_report(records, _spec(module))

    assert report["status"] == "tracking_open_lifecycle"
    assert report["lifecycles"][0]["exit_book_time_ms"] is None
    assert report["lifecycles"][0]["net_pnl_usd_before_funding"] is None
    assert report["resolved_proxy_summary"]["trades"] == 0


def test_second_entry_is_withheld_while_prior_lifecycle_is_open() -> None:
    """Portfolio occupancy prevents overlapping HYPE proxy positions."""
    module = import_module("hypervector.research.hype_native_prospective_lifecycle")
    records = (
        _identity(),
        _routing(67_000, [_entry_evaluation(), _baseline_evaluation()]),
        _book(70_000),
        _book(100_000),
        _routing(
            127_000,
            [_entry_evaluation(120_000), _baseline_evaluation(120_000)],
        ),
        _book(130_000),
        _book(160_000),
        _routing(185_000, [_exit_evaluation(180_000)]),
        _book(190_000, bid=100.99, ask=101.01),
    )

    report = module.build_hype_native_prospective_report(records, _spec(module))

    assert len(report["attempts"]) == 2
    assert report["attempts"][1]["status"] == "occupied_by_prior_lifecycle"
    assert len(report["lifecycles"]) == 1


def test_book_gap_keeps_closed_proxy_out_of_resolved_summary() -> None:
    """A sampled exit cannot success-shape an unresolved observation path."""
    module = import_module("hypervector.research.hype_native_prospective_lifecycle")
    records = (
        _identity(),
        _routing(67_000, [_entry_evaluation(), _baseline_evaluation()]),
        _book(70_000),
        _routing(125_000, [_exit_evaluation()]),
        _book(180_000, bid=100.99, ask=101.01),
    )

    report = module.build_hype_native_prospective_report(records, _spec(module))

    lifecycle = report["lifecycles"][0]
    assert lifecycle["exit_reason"] == "opposite_native_onset"
    assert lifecycle["maximum_book_gap_ms"] == 110_000
    assert lifecycle["technical_path_resolved"] is False
    assert report["status"] == "technical_evidence_unresolved"
    assert report["resolved_proxy_summary"]["trades"] == 0


def test_invalid_exit_only_contract_fails_closed() -> None:
    """A mislabeled short evaluation cannot silently become long exit authority."""
    module = import_module("hypervector.research.hype_native_prospective_lifecycle")
    invalid = _exit_evaluation()
    invalid["exit_sides"] = ["short"]
    records = (_identity(), _routing(125_000, [invalid]), _book(130_000))

    with pytest.raises(ValueError, match="exit-only onset contract"):
        module.build_hype_native_prospective_report(records, _spec(module))


def test_runtime_identity_drift_fails_closed() -> None:
    """Evidence from a different observer profile cannot enter this window."""
    module = import_module("hypervector.research.hype_native_prospective_lifecycle")
    identity = _identity()
    identity["profile_fingerprint"] = "different-profile"

    with pytest.raises(ValueError, match="profile fingerprint"):
        module.build_hype_native_prospective_report((identity,), _spec(module))
