"""Exact prospective BRENTOIL oil-shock lifecycle tests."""

from __future__ import annotations

from dataclasses import replace

from pytest import raises

from hypervector.data.hl_events import AssetContextEvent
from hypervector.research.brentoil_oil_shock_lifecycle import (
    BrentoilOilShockLifecycleConfig,
    build_brentoil_oil_shock_lifecycle_report,
)

_DECISION_MS = 1_800_000_300_000


def test_target_lifecycle_uses_post_publication_depth_and_exact_mark_path() -> None:
    """The first complete target lifecycle uses causal BBO and mark evidence."""
    observed = _DECISION_MS + 500
    entry = observed + 100
    trigger = entry + 10_000
    report = build_brentoil_oil_shock_lifecycle_report(
        decision_rows=(_decision(_DECISION_MS, observed, "long"),),
        candle_rows=(_candle(_DECISION_MS, prospective=True),),
        book_rows=(
            _book(entry, 100.0, 100.2),
            _book(trigger + 100, 100.62, 100.64),
        ),
        marks=_marks(entry, trigger, final_price=100.7),
        observed_at_ms=trigger + 100,
        config=_config(),
    )

    row = report["nominal"]["resolved_lifecycles"][0]
    assert row["exit_reason"] == "target"
    assert row["entry_time_ms"] == entry
    assert row["exit_time_ms"] == trigger + 100
    assert row["entry_price"] == 100.2
    assert row["exit_price"] == 100.62
    assert row["notional_usd"] == 750.0
    assert row["modeled_net_usd_excluding_funding"] > 0.0
    assert (
        report["stress"]["resolved_lifecycles"][0]["modeled_net_usd_excluding_funding"]
        < row["modeled_net_usd_excluding_funding"]
    )
    assert report["technical_assessment"]["all_observed_paths_resolved"] is True
    assert report["execution_authority"] == "none"


def test_opposite_fresh_shock_closes_before_the_timer() -> None:
    """A later eligible opposite onset is an explicit strategy exit."""
    first_observed = _DECISION_MS + 500
    second_decision = _DECISION_MS + 300_000
    second_observed = second_decision + 500
    entry = first_observed + 100
    report = build_brentoil_oil_shock_lifecycle_report(
        decision_rows=(
            _decision(_DECISION_MS, first_observed, "long"),
            _decision(second_decision, second_observed, "short"),
        ),
        candle_rows=(
            _candle(_DECISION_MS, prospective=True),
            _candle(second_decision, prospective=True),
        ),
        book_rows=(
            _book(entry, 100.0, 100.2),
            _book(second_observed + 100, 100.1, 100.3),
        ),
        marks=_marks(entry, second_observed, final_price=100.1),
        observed_at_ms=second_observed + 100,
        config=_config(),
    )

    row = report["nominal"]["resolved_lifecycles"][0]
    assert row["exit_reason"] == "opposite_signal"
    assert row["exit_trigger_time_ms"] == second_observed
    assert report["source"]["eligible_decisions"] == 2
    assert report["source"]["overlapping_decisions_suppressed"] == 1


def test_incomplete_mark_path_is_censored_instead_of_success_shaped() -> None:
    """A target observation after a mark outage cannot prove first passage."""
    observed = _DECISION_MS + 500
    entry = observed + 100
    trigger = entry + 10_000
    report = build_brentoil_oil_shock_lifecycle_report(
        decision_rows=(_decision(_DECISION_MS, observed, "long"),),
        candle_rows=(_candle(_DECISION_MS, prospective=True),),
        book_rows=(_book(entry, 100.0, 100.2),),
        marks=(
            _mark(entry, 100.2),
            _mark(trigger, 100.7),
        ),
        observed_at_ms=trigger,
        config=_config(),
    )

    assert report["nominal"]["resolved_lifecycles"] == []
    assert report["nominal"]["censored_lifecycles"][0]["reason"] == (
        "mark_path_unresolved"
    )
    assert report["technical_assessment"]["all_observed_paths_resolved"] is False


def test_late_candle_inside_open_lifecycle_censors_exit() -> None:
    """A missed prospective decision cannot success-shape the timer exit."""
    observed = _DECISION_MS + 500
    entry = observed + 100
    deadline = entry + 600_000
    missed_boundary = _DECISION_MS + 300_000
    report = build_brentoil_oil_shock_lifecycle_report(
        decision_rows=(_decision(_DECISION_MS, observed, "long"),),
        candle_rows=(
            _candle(_DECISION_MS, prospective=True),
            _candle(
                missed_boundary,
                prospective=False,
                historical_warmup=False,
                observed_ms=missed_boundary + 60_000,
            ),
        ),
        book_rows=(
            _book(entry, 100.0, 100.2),
            _book(deadline + 100, 100.1, 100.3),
        ),
        marks=_marks(entry, deadline, final_price=100.2),
        observed_at_ms=deadline + 100,
        config=replace(_config(), maximum_hold_ms=600_000),
    )

    assert report["nominal"]["resolved_lifecycles"] == []
    assert report["nominal"]["censored_lifecycles"][0]["reason"] == (
        "decision_path_unresolved"
    )
    assert report["technical_assessment"]["all_observed_paths_resolved"] is False


def test_quiet_window_and_candle_identity_are_explicit() -> None:
    """No onset is valid evidence, while mismatched source candles fail closed."""
    quiet = _decision(_DECISION_MS, _DECISION_MS + 500, None, eligible=False)
    report = build_brentoil_oil_shock_lifecycle_report(
        decision_rows=(quiet,),
        candle_rows=(_candle(_DECISION_MS, prospective=True),),
        book_rows=(),
        marks=(),
        observed_at_ms=_DECISION_MS + 500,
        config=_config(),
    )

    assert report["source"]["observed_decisions"] == 1
    assert report["source"]["eligible_decisions"] == 0
    assert report["nominal"]["resolved_lifecycles"] == []
    assert report["technical_assessment"]["status"] == "WAITING_ELIGIBLE_ONSET"

    wrong = dict(_candle(_DECISION_MS, prospective=True))
    wrong["close"] = 99.0
    with raises(ValueError, match="candle"):
        build_brentoil_oil_shock_lifecycle_report(
            decision_rows=(quiet,),
            candle_rows=(wrong,),
            book_rows=(),
            marks=(),
            observed_at_ms=_DECISION_MS + 500,
            config=_config(),
        )


def test_stale_quiet_decision_is_retained_without_becoming_eligible() -> None:
    """A causally recorded stale bar remains context, never an entry."""
    stale = _decision(
        _DECISION_MS,
        _DECISION_MS + 60_000,
        None,
        eligible=False,
        prospective=False,
    )
    report = build_brentoil_oil_shock_lifecycle_report(
        decision_rows=(stale,),
        candle_rows=(
            _candle(
                _DECISION_MS,
                prospective=False,
                historical_warmup=False,
                observed_ms=_DECISION_MS + 60_000,
            ),
        ),
        book_rows=(),
        marks=(),
        observed_at_ms=_DECISION_MS + 60_000,
        config=_config(),
    )

    assert report["source"]["observed_decisions"] == 1
    assert report["source"]["eligible_decisions"] == 0
    assert report["technical_assessment"]["status"] == "WAITING_ELIGIBLE_ONSET"


def _config() -> BrentoilOilShockLifecycleConfig:
    return BrentoilOilShockLifecycleConfig(
        fee_bps_per_side=0.864,
        nominal_residual_bps_per_side=1.2230537631076595,
        stress_residual_bps_per_side=8.464583786205068,
        notional_usd=750.0,
        maximum_book_lateness_ms=15_000,
        maximum_mark_gap_ms=5_000,
        target_bps=40.0,
        stop_bps=30.0,
        maximum_hold_ms=3_600_000,
        friction_source="canary+development-v4",
    )


def _decision(
    decision_ms: int,
    observed_ms: int,
    side: str | None,
    *,
    eligible: bool = True,
    prospective: bool = True,
) -> dict[str, object]:
    provider = "hip3_brentoil_oil_shock_reversion_bidirectional_5m_shadow_v1"
    return {
        "schema_version": 1,
        "event_type": "brentoil_oil_shock_shadow_decision",
        "event_id": f"{provider}|xyz:BRENTOIL|{decision_ms}",
        "report_only": True,
        "execution_authority": "none",
        "intents": [],
        "runtime_strategy_changed": False,
        "decision": {
            "provider_id": provider,
            "profile_id": "brentoil_oil_shock_reversion_5m_shadow_v1",
            "symbol": "xyz:BRENTOIL",
            "decision_time_ms": decision_ms,
            "observed_at_ms": observed_ms,
            "decision_delay_ms": observed_ms - decision_ms,
            "prior_decision_boundary_ms": decision_ms - 300_000,
            "side": side,
            "eligible": eligible,
            "prospective": prospective,
            "non_action_reason": None if eligible else "no_shock_onset",
            "trailing_return_bps": -100.0 if side == "long" else 100.0,
            "shock_threshold_bps": 90.0,
            "candle_open": 100.0,
            "candle_high": 100.3,
            "candle_low": 99.8,
            "candle_close": 100.1,
            "candle_volume": 20.0,
            "signal_window_sha256": "a" * 64,
            "signal_ohlc_source": "hyperliquid_public_candleSnapshot_5m",
            "execution_authority": "none",
        },
    }


def _candle(
    decision_ms: int,
    *,
    prospective: bool,
    historical_warmup: bool | None = None,
    observed_ms: int | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "event_type": "brentoil_oil_shock_candle_observation",
        "symbol": "xyz:BRENTOIL",
        "source": "hyperliquid_public_candleSnapshot_5m",
        "bar_open_ms": decision_ms - 300_000,
        "bar_close_ms": decision_ms,
        "observed_at_ms": observed_ms or decision_ms + 500,
        "open": 100.0,
        "high": 100.3,
        "low": 99.8,
        "close": 100.1,
        "volume": 20.0,
        "historical_warmup": (
            not prospective if historical_warmup is None else historical_warmup
        ),
        "prospective": prospective,
        "execution_authority": "none",
    }


def _book(recv_ms: int, bid: float, ask: float) -> dict[str, object]:
    return {
        "event_type": "book_observation",
        "profile_id": "brentoil_oil_shock_rest_books_v1",
        "execution_authority": "none",
        "payload": {
            "symbol": "xyz:BRENTOIL",
            "source": "hyperliquid_mainnet_l2_rest",
            "exchange_ts_ms": recv_ms - 2,
            "recv_ts_ms": recv_ms,
            "bids": [
                {"price": bid - index * 0.01, "size": 100.0} for index in range(10)
            ],
            "asks": [
                {"price": ask + index * 0.01, "size": 100.0} for index in range(10)
            ],
        },
    }


def _marks(
    start: int, end: int, *, final_price: float
) -> tuple[AssetContextEvent, ...]:
    values = []
    for timestamp in range(start, end + 1, 5_000):
        price = final_price if timestamp == end else 100.2
        values.append(_mark(timestamp, price))
    return tuple(values)


def _mark(timestamp_ms: int, price: float) -> AssetContextEvent:
    row = AssetContextEvent(
        "xyz:BRENTOIL",
        timestamp_ms,
        timestamp_ms * 1_000_000,
        price,
        price,
        0.0,
        1_000_000.0,
        price,
    )
    return replace(row, source="hyperliquid_ws_activeAssetCtx")
