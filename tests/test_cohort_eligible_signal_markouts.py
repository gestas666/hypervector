"""Executable-BBO outcomes for causal eligible-signal annotations."""

from datetime import datetime, timezone

import pytest

from hypervector.research import cohort_friction_contracts
from hypervector.research.cohort_friction_contract_models import (
    ModeledExecutionContract,
)
from hypervector.research.cohort_signal_orderbook_context import (
    build_orderbook_opportunity_diagnostics,
)

_DECISION_MS = 1_800_000_000_000
_STRATEGY = "test_fade_1m"


@pytest.fixture(autouse=True)
def _modeled_friction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        cohort_friction_contracts._MODELED,
        (_STRATEGY, None),
        ModeledExecutionContract(
            "taker",
            4.5,
            2.0,
            "fixed_bps",
            80.0,
            None,
            None,
            28_800,
            "fixed",
            None,
            "none",
            None,
            None,
            None,
            "evidence/hype.json",
        ),
    )


def test_markout_uses_post_publication_executable_bbo() -> None:
    """Signal outcomes start after publication and cross the observed BBO."""
    available_ms = _DECISION_MS + 2_000
    entry_ms = _DECISION_MS + 3_000
    exit_ms = entry_ms + 5 * 60_000
    report = _report(
        [_routing(_DECISION_MS, available_ms, side="long")],
        [
            _book_row(_DECISION_MS + 1_000, 100.0, 0.4),
            _book_row(entry_ms, 100.0, 0.3),
            _book_row(exit_ms - 1, 90.0, -0.9),
            _book_row(exit_ms, 101.0, 0.2),
        ],
    )

    markouts = _markouts(report)
    assert markouts["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "fills_assumed": False,
        "pnl_claimed": False,
        "entry_anchor": "first_book_at_or_after_signal_publication",
        "exit_anchor": "first_book_at_or_after_entry_plus_horizon",
        "entry_liquidity": "taker_bbo_cross",
        "exit_liquidity": "taker_bbo_cross",
        "funding_included": False,
        "thresholds_selected": False,
        "episode_cadence_source": "explicit_provider_timeframe_mapping",
        "episode_onset_definition": (
            "first_signal_after_gap_direction_change_or_stream_boundary"
        ),
    }
    horizon = markouts["horizons"]["5"]
    assert horizon["coverage"] == _coverage(resolved=1)
    assert horizon["independent_resolved"] == 1
    aligned = horizon["by_pressure_stance"]["aligned"]
    entry_ask = 100.0 * (1.0 + 0.20 / 20_000.0)
    exit_bid = 101.0 * (1.0 - 0.20 / 20_000.0)
    gross = (exit_bid / entry_ask - 1.0) * 10_000.0
    cost_multiplier = 1.0 + exit_bid / entry_ask
    assert aligned["paths"] == 1
    assert aligned["mean_gross_bbo_bps"] == pytest.approx(gross)
    assert aligned["mean_after_fee_bps"] == pytest.approx(gross - 4.5 * cost_multiplier)
    assert aligned["mean_after_modeled_friction_bps"] == pytest.approx(
        gross - (4.5 + 2.0) * cost_multiplier
    )
    latest = markouts["latest_markouts"][0]
    assert latest["signal_available_time_ms"] == available_ms
    assert latest["entry_book_time_ms"] == entry_ms
    assert latest["exit_book_time_ms"] == exit_ms
    assert latest["pressure_stance"] == "aligned"


def test_markout_without_modeled_friction_keeps_only_gross_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unmodeled route resolves gross BBO paths without inventing costs."""
    monkeypatch.delitem(cohort_friction_contracts._MODELED, (_STRATEGY, None))
    entry_ms = _DECISION_MS + 3_000
    exit_ms = entry_ms + 5 * 60_000
    report = _report(
        [_routing(_DECISION_MS, _DECISION_MS + 2_000, side="long")],
        [
            _book_row(_DECISION_MS + 1_000, 100.0, 0.4),
            _book_row(entry_ms, 100.0, 0.3),
            _book_row(exit_ms, 101.0, 0.2),
        ],
    )

    horizon = _markouts(report)["horizons"]["5"]
    assert horizon["coverage"] == {
        **_coverage(resolved=1),
        "friction_contract_missing": 1,
    }
    aligned = horizon["by_pressure_stance"]["aligned"]
    entry_ask = 100.0 * (1.0 + 0.20 / 20_000.0)
    exit_bid = 101.0 * (1.0 - 0.20 / 20_000.0)
    assert aligned["mean_gross_bbo_bps"] == pytest.approx(
        (exit_bid / entry_ask - 1.0) * 10_000.0
    )
    assert aligned["mean_after_fee_bps"] is None
    assert aligned["mean_after_modeled_friction_bps"] is None


def test_markout_is_censored_without_a_future_exit_book() -> None:
    """An unfinished horizon remains censored rather than becoming a loss."""
    available_ms = _DECISION_MS + 2_000
    report = _report(
        [_routing(_DECISION_MS, available_ms, side="long")],
        [
            _book_row(_DECISION_MS + 1_000, 100.0, 0.4),
            _book_row(_DECISION_MS + 3_000, 100.0, 0.3),
        ],
    )

    horizon = _markouts(report)["horizons"]["5"]
    assert horizon["coverage"] == _coverage(exit_censored=1)
    assert horizon["independent_resolved"] == 0
    assert horizon["all"]["mean_after_modeled_friction_bps"] is None


def test_markout_rejects_an_entry_book_outside_the_lateness_budget() -> None:
    """A delayed book cannot masquerade as an executable signal-time quote."""
    available_ms = _DECISION_MS + 2_000
    report = _report(
        [_routing(_DECISION_MS, available_ms, side="long")],
        [
            _book_row(_DECISION_MS + 1_000, 100.0, 0.4),
            _book_row(available_ms + 30_001, 100.0, 0.3),
        ],
    )

    horizon = _markouts(report)["horizons"]["5"]
    assert horizon["coverage"] == _coverage(entry_gap=1, entry_matched=0)
    assert horizon["independent_resolved"] == 0


def test_overlapping_signal_markouts_report_one_independent_path() -> None:
    """Dense repeated signals cannot inflate fixed-horizon effective count."""
    first_available = _DECISION_MS + 2_000
    second_decision = _DECISION_MS + 60_000
    second_available = second_decision + 2_000
    first_entry = _DECISION_MS + 3_000
    second_entry = second_decision + 3_000
    report = _report(
        [
            _routing(_DECISION_MS, first_available, side="long"),
            _routing(second_decision, second_available, side="long"),
        ],
        [
            _book_row(_DECISION_MS + 1_000, 100.0, 0.4),
            _book_row(first_entry, 100.0, 0.3),
            _book_row(second_decision + 1_000, 100.2, 0.2),
            _book_row(second_entry, 100.2, 0.2),
            _book_row(first_entry + 5 * 60_000, 101.0, 0.2),
            _book_row(second_entry + 5 * 60_000, 101.2, 0.2),
        ],
    )

    horizon = _markouts(report)["horizons"]["5"]
    assert horizon["coverage"] == _coverage(
        eligible_signals=2,
        entry_matched=2,
        resolved=2,
    )
    assert horizon["independent_resolved"] == 1


def test_configured_cadence_collapses_persistent_signal_episode() -> None:
    """Only the first signal in one uninterrupted provider state is an onset."""
    first_available = _DECISION_MS + 2_000
    second_decision = _DECISION_MS + 60_000
    third_decision = _DECISION_MS + 7 * 60_000
    report = _report(
        [
            _routing(_DECISION_MS, first_available, side="long"),
            _routing(second_decision, second_decision + 2_000, side="long"),
            _routing(third_decision, third_decision + 2_000, side="long"),
        ],
        [
            _book_row(_DECISION_MS + 1_000, 100.0, 0.4),
            _book_row(_DECISION_MS + 3_000, 100.0, 0.3),
            _book_row(second_decision + 3_000, 100.1, 0.2),
            _book_row(_DECISION_MS + 5 * 60_000 + 3_000, 100.5, 0.2),
            _book_row(_DECISION_MS + 6 * 60_000 + 3_000, 100.6, 0.2),
            _book_row(third_decision + 3_000, 100.7, 0.2),
            _book_row(third_decision + 5 * 60_000 + 3_000, 101.2, 0.2),
        ],
    )

    onset = _markouts(report)["horizons"]["5"]["episode_onsets"]
    assert onset["status"] == "available"
    assert onset["provider_cadence_minutes"] == 1
    assert onset["coverage"] == _coverage(
        eligible_signals=2,
        entry_matched=2,
        resolved=2,
    )
    assert onset["independent_resolved"] == 2
    assert onset["all"]["paths"] == 2
    assert onset["by_side"]["long"]["paths"] == 2
    assert onset["by_side"]["short"]["paths"] == 0
    assert [path["decision_time_ms"] for path in onset["independent_paths"]] == [
        _DECISION_MS,
        third_decision,
    ]
    assert all(path["source_run_id"] is None for path in onset["independent_paths"])


def test_explicit_cadence_map_rejects_a_missing_provider() -> None:
    """A partial identity cannot silently turn missing cadence into zero onsets."""
    with pytest.raises(ValueError, match="provider cadence is missing"):
        _report(
            [_routing(_DECISION_MS, _DECISION_MS + 2_000, side="long")],
            [_book_row(_DECISION_MS + 3_000, 100.0, 0.3)],
            provider_cadence_minutes={},
        )


def _report(
    routing_rows: list[dict[str, object]],
    book_rows: list[dict[str, object]],
    *,
    provider_cadence_minutes: dict[str, int] | None = None,
) -> dict[str, object]:
    records = [_row("configuration_identity", {}, _DECISION_MS - 60_000)]
    records.extend(routing_rows)
    return build_orderbook_opportunity_diagnostics(
        records,
        {"HYPE": book_rows},
        horizons_minutes=(5,),
        provider_cadence_minutes=(
            {_STRATEGY: 1}
            if provider_cadence_minutes is None
            else provider_cadence_minutes
        ),
    )


def _routing(decision_ms: int, available_ms: int, *, side: str) -> dict[str, object]:
    return _row(
        "intent_routing",
        {
            "evaluations": [
                {
                    "strategy_id": _STRATEGY,
                    "symbol": "HYPE",
                    "decision_time_ms": decision_ms,
                    "reference_price": 100.0,
                    "side": side,
                    "eligible": True,
                    "state_5m": "TREND_UP",
                    "context_15m": "TREND_UP",
                    "readiness": {"side": side, "blockers": [], "metrics": {}},
                }
            ]
        },
        available_ms,
    )


def _book_row(recv_ms: int, mid_px: float, opi: float) -> dict[str, object]:
    return _row(
        "book_observation",
        {
            "exchange_ts_ms": recv_ms - 100,
            "recv_ts_ms": recv_ms,
            "mid_px": mid_px,
            "spread_bps": 0.20,
            "bid_depth_ratio": 3.0 if opi > 0.0 else 1.0 / 3.0,
            "opi": opi,
        },
        recv_ms + 100,
    )


def _markouts(report: dict[str, object]) -> dict[str, object]:
    context = report["eligible_signal_context"]
    assert isinstance(context, dict)
    providers = context["by_provider_symbol"]
    assert isinstance(providers, dict)
    provider = providers[f"{_STRATEGY}|HYPE"]
    assert isinstance(provider, dict)
    markouts = provider["executable_bbo_markouts"]
    assert isinstance(markouts, dict)
    return markouts


def _coverage(
    *,
    eligible_signals: int = 1,
    entry_matched: int = 1,
    entry_censored: int = 0,
    entry_gap: int = 0,
    resolved: int = 0,
    exit_censored: int = 0,
    exit_gap: int = 0,
) -> dict[str, int]:
    return {
        "eligible_signals": eligible_signals,
        "entry_matched": entry_matched,
        "entry_censored": entry_censored,
        "entry_gap": entry_gap,
        "resolved": resolved,
        "exit_censored": exit_censored,
        "exit_gap": exit_gap,
        "friction_contract_missing": 0,
    }


def _row(
    event_type: str, payload: dict[str, object], observed_ms: int
) -> dict[str, object]:
    return {
        "event_type": event_type,
        "observed_at_utc": datetime.fromtimestamp(
            observed_ms / 1_000, timezone.utc
        ).isoformat(),
        "payload": payload,
    }
