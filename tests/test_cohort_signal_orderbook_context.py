"""Causal L2 context for report-only signal-opportunity diagnostics."""

from datetime import datetime, timezone

from hypervector.research.cohort_signal_orderbook_context import (
    build_orderbook_opportunity_diagnostics,
)

_DECISION_MS = 1_800_000_000_000


def test_orderbook_context_separates_aligned_and_opposed_independent_paths() -> None:
    """Decision-time OPI must stay causal and side-relative in missed-path evidence."""
    report = build_orderbook_opportunity_diagnostics(
        _cohort_records(),
        {"HYPE": _book_records()},
        horizons_minutes=(5,),
    )

    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "fills_assumed": False,
        "pnl_claimed": False,
        "thresholds_selected": False,
        "orderbook_alignment_rule": (
            "directional_opi_above_zero_at_routing_publication"
        ),
        "path_start_policy": ("first_full_minute_at_or_after_candidate_availability"),
    }
    assert report["coverage"] == {
        "exact_one_blocker_candidates": 2,
        "book_matched": 2,
        "book_stale": 0,
        "book_missing": 0,
    }
    horizon = report["by_provider_symbol"]["provider|HYPE"]["by_blocker"][
        "awaiting_breakout"
    ]["by_side"]["long"]["horizons"]["5"]
    assert horizon["independent_resolved"] == 2
    assert horizon["aligned"]["paths"] == 1
    assert horizon["aligned"]["opportunity_capture"]["robust_mfe_count"] == 1
    assert horizon["opposed"]["paths"] == 1
    assert horizon["opposed"]["opportunity_capture"]["robust_mfe_count"] == 0


def test_future_book_is_not_used_as_decision_availability_context() -> None:
    """A snapshot received after routing publication cannot leak into features."""
    books = _book_records()
    first_payload = books[0]["payload"]
    assert isinstance(first_payload, dict)
    first_payload["recv_ts_ms"] = _DECISION_MS + 2_001

    report = build_orderbook_opportunity_diagnostics(
        _cohort_records(),
        {"HYPE": books},
        horizons_minutes=(5,),
    )

    assert report["coverage"]["book_matched"] == 1
    assert report["coverage"]["book_missing"] == 1


def test_book_after_bar_boundary_but_before_routing_publication_is_causal() -> None:
    """Execution context may use L2 observed before the decision became available."""
    books = _book_records()
    first_payload = books[0]["payload"]
    assert isinstance(first_payload, dict)
    first_payload.update({"recv_ts_ms": _DECISION_MS + 1_000, "opi": -0.5})

    report = build_orderbook_opportunity_diagnostics(
        _cohort_records(),
        {"HYPE": books},
        horizons_minutes=(5,),
    )

    horizon = report["by_provider_symbol"]["provider|HYPE"]["by_blocker"][
        "awaiting_breakout"
    ]["by_side"]["long"]["horizons"]["5"]
    assert horizon["opposed"]["paths"] == 2
    assert horizon["aligned"]["paths"] == 0


def test_pressure_clock_reports_causal_same_cycle_book_for_multi_blocker() -> None:
    """A post-decision book published before routing exposes clock exclusion."""
    available_ms = _DECISION_MS + 25_000
    report = build_orderbook_opportunity_diagnostics(
        [
            _row("configuration_identity", {}, _DECISION_MS - 60_000),
            _row(
                "intent_routing",
                {"evaluations": [_pressure_evaluation(_DECISION_MS)]},
                available_ms,
            ),
        ],
        {
            "xyz:DDD": [
                _row(
                    "book_observation",
                    _book(_DECISION_MS + 24_000, 0.4, 0.25),
                    available_ms - 500,
                )
            ]
        },
        horizons_minutes=(5,),
    )

    assert report["provider_pressure_clock"] == {
        "pressure_unavailable_evaluations": 1,
        "causal_book_available": 1,
        "book_absent_or_stale": 0,
        "by_provider_symbol": {
            "hip3_breakout_pressure_test|xyz:DDD": {
                "pressure_unavailable_evaluations": 1,
                "causal_book_available": 1,
                "book_absent_or_stale": 0,
            }
        },
    }


def test_pressure_clock_rejects_books_outside_causal_publication_window() -> None:
    """Pre-decision and post-publication books cannot explain a provider miss."""
    second_decision_ms = _DECISION_MS + 300_000
    report = build_orderbook_opportunity_diagnostics(
        [
            _row("configuration_identity", {}, _DECISION_MS - 60_000),
            _row(
                "intent_routing",
                {"evaluations": [_pressure_evaluation(_DECISION_MS)]},
                _DECISION_MS + 25_000,
            ),
            _row(
                "intent_routing",
                {"evaluations": [_pressure_evaluation(second_decision_ms)]},
                second_decision_ms + 25_000,
            ),
        ],
        {
            "xyz:DDD": [
                _row(
                    "book_observation",
                    _book(_DECISION_MS - 1_000, 0.4, 0.25),
                    _DECISION_MS - 500,
                ),
                _row(
                    "book_observation",
                    _book(second_decision_ms + 25_001, 0.4, 0.25),
                    second_decision_ms + 25_500,
                ),
            ]
        },
        horizons_minutes=(5,),
    )

    clock = report["provider_pressure_clock"]
    assert clock["pressure_unavailable_evaluations"] == 2
    assert clock["causal_book_available"] == 0
    assert clock["book_absent_or_stale"] == 2


def test_eligible_signals_receive_causal_pressure_and_regime_annotations() -> None:
    """Eligible signals retain pressure and MTF context without claiming fills."""
    second_decision_ms = _DECISION_MS + 300_000
    report = build_orderbook_opportunity_diagnostics(
        [
            _row("configuration_identity", {}, _DECISION_MS - 60_000),
            _row(
                "intent_routing",
                {
                    "evaluations": [
                        _eligible_evaluation(
                            _DECISION_MS,
                            side="long",
                            state_5m="TREND_UP",
                            context_15m="TREND_UP",
                        )
                    ]
                },
                _DECISION_MS + 2_000,
            ),
            _row(
                "intent_routing",
                {
                    "evaluations": [
                        _eligible_evaluation(second_decision_ms, side="short")
                    ]
                },
                second_decision_ms + 2_000,
            ),
        ],
        {
            "HYPE": [
                _row(
                    "book_observation",
                    _book(_DECISION_MS + 1_000, 0.4, 0.25),
                    _DECISION_MS + 1_500,
                ),
                _row(
                    "book_observation",
                    _book(second_decision_ms + 1_000, 0.5, 0.30),
                    second_decision_ms + 1_500,
                ),
            ]
        },
        horizons_minutes=(5,),
    )

    context = report["eligible_signal_context"]
    assert context["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "signals_are_annotations": True,
        "routing_or_fill_claimed": False,
        "thresholds_selected": False,
        "signal_eligibility_changed": False,
    }
    assert context["coverage"] == {
        "eligible_signals": 2,
        "book_matched": 2,
        "book_stale": 0,
        "book_missing": 0,
    }
    provider = context["by_provider_symbol"]["provider|HYPE"]
    assert provider["pressure_stance"] == {
        "aligned": 1,
        "neutral": 0,
        "opposed": 1,
        "unavailable": 0,
    }
    assert provider["state_5m_stance"] == {
        "aligned": 1,
        "neutral": 0,
        "opposed": 0,
        "unavailable": 1,
    }
    assert provider["context_15m_stance"] == {
        "aligned": 1,
        "neutral": 0,
        "opposed": 0,
        "unavailable": 1,
    }
    assert provider["latest_signals"][0] == {
        "available_time_ms": _DECISION_MS + 2_000,
        "book_age_ms": 1_000,
        "book_time_ms": _DECISION_MS + 1_000,
        "context_15m": "TREND_UP",
        "context_15m_stance": "aligned",
        "decision_time_ms": _DECISION_MS,
        "directional_opi": 0.4,
        "pressure_stance": "aligned",
        "side": "long",
        "spread_bps": 0.25,
        "state_5m": "TREND_UP",
        "state_5m_stance": "aligned",
    }


def test_orderbook_diagnostic_reports_native_pressure_translation() -> None:
    """The audit must expose provider pressure that flips before publication."""
    evaluation = _eligible_evaluation(_DECISION_MS, side="long")
    readiness = evaluation["readiness"]
    assert isinstance(readiness, dict)
    metrics = readiness["metrics"]
    assert isinstance(metrics, dict)
    metrics["imbalance_10"] = 0.20
    report = build_orderbook_opportunity_diagnostics(
        [
            _row("configuration_identity", {}, _DECISION_MS - 60_000),
            _row(
                "intent_routing",
                {"evaluations": [evaluation]},
                _DECISION_MS + 2_000,
            ),
        ],
        {
            "HYPE": [
                _row(
                    "book_observation",
                    _book(_DECISION_MS + 1_000, -0.40, 0.25),
                    _DECISION_MS + 1_500,
                )
            ]
        },
        horizons_minutes=(5,),
    )

    translation = report["eligible_pressure_translation"]
    provider = translation["by_provider_symbol"]["provider|HYPE"]
    assert provider["translation_state"]["flipped"] == 1


def _cohort_records() -> list[dict[str, object]]:
    return [
        _row(
            "configuration_identity",
            {},
            _DECISION_MS - 60_000,
        ),
        _row(
            "intent_routing",
            {"evaluations": [_evaluation(_DECISION_MS, 100.0)]},
            _DECISION_MS + 2_000,
        ),
        _row(
            "intent_routing",
            {"evaluations": [_evaluation(_DECISION_MS + 300_000, 101.0)]},
            _DECISION_MS + 302_000,
        ),
        _row(
            "market_candles",
            {"timeframe": "1m", "bars": {"HYPE": _bars()}},
            _DECISION_MS + 602_000,
        ),
    ]


def _evaluation(decision_ms: int, reference: float) -> dict[str, object]:
    return {
        "strategy_id": "provider",
        "symbol": "HYPE",
        "decision_time_ms": decision_ms,
        "reference_price": reference,
        "side": None,
        "eligible": False,
        "readiness": {
            "side": "long",
            "blockers": ["awaiting_breakout"],
            "metrics": {},
        },
    }


def _pressure_evaluation(decision_ms: int) -> dict[str, object]:
    return {
        "strategy_id": "hip3_breakout_pressure_test",
        "symbol": "xyz:DDD",
        "decision_time_ms": decision_ms,
        "reference_price": 4_300.0,
        "side": "long",
        "eligible": False,
        "readiness": {
            "side": "long",
            "blockers": [
                "breakout_level_not_crossed",
                "order_pressure_unavailable",
            ],
            "metrics": {
                "imbalance_10": None,
                "pressure_age_seconds": None,
            },
        },
    }


def _eligible_evaluation(
    decision_ms: int,
    *,
    side: str,
    state_5m: str | None = None,
    context_15m: str | None = None,
) -> dict[str, object]:
    evaluation: dict[str, object] = {
        "strategy_id": "provider",
        "symbol": "HYPE",
        "decision_time_ms": decision_ms,
        "reference_price": 100.0,
        "side": side,
        "eligible": True,
        "readiness": {
            "side": side,
            "blockers": [],
            "metrics": {},
        },
    }
    if state_5m is not None:
        evaluation["state_5m"] = state_5m
    if context_15m is not None:
        evaluation["context_15m"] = context_15m
    return evaluation


def _bars() -> list[dict[str, object]]:
    closes = [
        100.10,
        100.20,
        100.30,
        100.35,
        100.30,
        100.90,
        100.80,
        100.70,
        100.60,
        100.50,
        100.40,
    ]
    return [
        {
            "timestamp_ms": _DECISION_MS + offset * 60_000,
            "open": close,
            "high": close + 0.10,
            "low": close - 0.10,
            "close": close,
        }
        for offset, close in enumerate(closes)
    ]


def _book_records() -> list[dict[str, object]]:
    return [
        _row(
            "book_observation",
            _book(_DECISION_MS - 1_000, 0.5, 0.20),
            _DECISION_MS - 500,
        ),
        _row(
            "book_observation",
            _book(_DECISION_MS + 299_000, -0.5, 0.30),
            _DECISION_MS + 299_500,
        ),
    ]


def _book(
    recv_ms: int,
    opi: float,
    spread_bps: float,
    *,
    mid_px: float = 100.0,
) -> dict[str, object]:
    return {
        "exchange_ts_ms": recv_ms - 100,
        "recv_ts_ms": recv_ms,
        "mid_px": mid_px,
        "spread_bps": spread_bps,
        "bid_depth_ratio": 3.0 if opi > 0.0 else 1.0 / 3.0,
        "opi": opi,
    }


def _row(
    event_type: str,
    payload: dict[str, object],
    observed_ms: int,
) -> dict[str, object]:
    return {
        "event_type": event_type,
        "observed_at_utc": datetime.fromtimestamp(
            observed_ms / 1_000, timezone.utc
        ).isoformat(),
        "payload": payload,
    }
