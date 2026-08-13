"""Causal replay tests for the breakout retest live-research audit."""

from __future__ import annotations

from hypervector.research.hype_breakout_retest_replay import (
    build_hype_breakout_retest_replay,
)

_MINUTE_MS = 60_000
_RUN = "live-retest-fixture"
_STRATEGY = "hype_breakout_onset_bidirectional_v1"


def test_replay_matches_routed_aligned_onset_to_delayed_confirmation() -> None:
    """An aligned live entry remains attributable while v2 waits one bar."""
    bars = _base_bars(100.0)
    bars.extend(
        (
            _bar(20, 100.2, 100.3, 99.8, 99.9),
            _bar(21, 100.05, 100.1, 99.7, 99.8),
        )
    )
    onset = _evaluation(21, onset=True, breakout="short", structural="short")
    confirmation = _evaluation(
        22,
        onset=False,
        breakout="short",
        structural="short",
    )
    rows = (
        _candles("HYPE", bars),
        _routing("HYPE", onset, action="enter"),
        _routing("HYPE", confirmation),
    )

    report = build_hype_breakout_retest_replay(rows, run_id=_RUN)

    assert report["summary"] == {
        "aligned_onsets": 1,
        "control_onsets": 1,
        "opposed_onsets": 0,
        "retest_confirmed": 1,
        "retest_expired": 0,
        "retest_pending": 0,
        "routed_entries": 1,
        "withheld_onsets": 0,
    }
    onset_report = report["onsets"][0]
    assert onset_report["v1_route"]["status"] == "routed_enter"
    assert onset_report["retest_onset"]["state"] == "armed"
    assert onset_report["retest_resolution"] == {
        "age_bars": 1,
        "decision_time_ms": 22 * _MINUTE_MS,
        "reason": "breakout_retest_confirmed",
        "reference_price": 100.0,
        "side": "short",
        "state": "confirmed",
    }


def test_replay_preserves_withheld_opposed_fade_and_expiration() -> None:
    """An opposed v1 intent stays withheld while an unconfirmed fade expires."""
    bars = _base_bars(100.0)
    bars.extend(
        (
            _bar(20, 99.9, 100.3, 99.8, 100.2),
            _bar(21, 100.1, 100.2, 100.05, 100.15),
            _bar(22, 100.15, 100.25, 100.1, 100.2),
            _bar(23, 100.2, 100.3, 100.05, 100.1),
        )
    )
    evaluations = (
        _evaluation(21, onset=True, breakout="long", structural="short"),
        _evaluation(22, onset=False, breakout=None, structural="short"),
        _evaluation(23, onset=False, breakout=None, structural="short"),
        _evaluation(24, onset=False, breakout=None, structural="short"),
    )
    rows = [_candles("SOL", bars)]
    rows.append(
        _routing(
            "SOL",
            evaluations[0],
            withheld="same_direction_position_open",
        )
    )
    rows.extend(_routing("SOL", evaluation) for evaluation in evaluations[1:])

    report = build_hype_breakout_retest_replay(rows, run_id=_RUN)

    summary = report["summary"]
    assert summary["opposed_onsets"] == 1
    assert summary["withheld_onsets"] == 1
    assert summary["retest_expired"] == 1
    onset_report = report["onsets"][0]
    assert onset_report["v1_route"] == {
        "reason": "same_direction_position_open",
        "status": "withheld",
    }
    assert onset_report["retest_onset"]["mode"] == "fade"
    assert onset_report["retest_resolution"]["state"] == "expired"
    assert onset_report["retest_resolution"]["age_bars"] == 3


def _base_bars(price: float) -> list[dict[str, object]]:
    return [_bar(minute, price, price, price, price) for minute in range(20)]


def _bar(
    minute: int,
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
) -> dict[str, object]:
    return {
        "timestamp_ms": minute * _MINUTE_MS,
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": close_price,
        "volume": 1.0,
    }


def _candles(symbol: str, bars: list[dict[str, object]]) -> dict[str, object]:
    return {
        "event_type": "market_candles",
        "run_id": _RUN,
        "payload": {"timeframe": "1m", "bars": {symbol: bars}},
    }


def _evaluation(
    decision_minute: int,
    *,
    onset: bool,
    breakout: str | None,
    structural: str,
) -> dict[str, object]:
    return {
        "strategy_id": _STRATEGY,
        "decision_time_ms": decision_minute * _MINUTE_MS,
        "eligible": onset,
        "side": structural,
        "state_1m": "BREAKOUT",
        "state_5m": "BREAKOUT" if breakout is not None else "RANGE",
        "reference_price": 100.0,
        "readiness": {
            "metrics": {
                "breakout_onset": onset,
                "breakout_side": breakout,
                "structural_direction": structural,
                "breakout_side_relation": (
                    "aligned" if breakout == structural else "opposed"
                ),
            }
        },
    }


def _routing(
    symbol: str,
    evaluation: dict[str, object],
    *,
    action: str | None = None,
    withheld: str | None = None,
) -> dict[str, object]:
    decision_time_ms = evaluation["decision_time_ms"]
    route = {
        "strategy_id": _STRATEGY,
        "symbol": symbol,
        "side": evaluation["side"],
        "decision_time_ms": decision_time_ms,
    }
    actions = [{"action": action, **route}] if action is not None else []
    withheld_rows = [{"reason": withheld, **route}] if withheld is not None else []
    return {
        "event_type": "intent_routing",
        "run_id": _RUN,
        "payload": {
            "evaluations": [{"symbol": symbol, **evaluation}],
            "actions": actions,
            "withheld": withheld_rows,
        },
    }
