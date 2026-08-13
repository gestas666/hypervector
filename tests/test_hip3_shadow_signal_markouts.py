"""Causal executable-BBO markouts for HIP-3 shadow onsets."""

from __future__ import annotations

import pytest

from hypervector.research.hip3_shadow_signal_markouts import (
    Hip3ShadowMarkoutConfig,
    build_hip3_shadow_signal_markouts,
)


def _decision(
    *,
    decision_ms: int,
    observed_ms: int,
    side: str,
    eligible: bool = True,
) -> dict[str, object]:
    provider = "hip3_mu_full_l2_breakout_pressure_bidirectional_15m_v1"
    profile = "mu_full_l2_breakout_pressure_bidirectional_15m_research_v1"
    return {
        "schema_version": 1,
        "event_type": "mu_hip3_breakout_shadow_decision",
        "event_id": f"{provider}|xyz:MU|{decision_ms}",
        "report_only": True,
        "execution_authority": "none",
        "intents": [],
        "runtime_strategy_changed": False,
        "decision": {
            "provider_id": provider,
            "profile_id": profile,
            "symbol": "xyz:MU",
            "decision_time_ms": decision_ms,
            "observed_at_ms": observed_ms,
            "side": side,
            "eligible": eligible,
            "prospective": True,
            "pressure_fresh": True,
            "pressure_scan_complete": True,
            "pressure_state_history_complete": True,
            "execution_authority": "none",
        },
    }


def _book(recv_ms: int, bid: float, ask: float) -> dict[str, object]:
    return {
        "event_type": "book_observation",
        "profile_id": "mu_breakout_shadow_xyz:mu",
        "execution_authority": "none",
        "payload": {
            "symbol": "xyz:MU",
            "source": "hyperliquid_mainnet_l2_rest",
            "exchange_ts_ms": recv_ms - 2,
            "recv_ts_ms": recv_ms,
            "bids": [{"price": bid - index * 0.01, "size": 2.0} for index in range(10)],
            "asks": [{"price": ask + index * 0.01, "size": 1.0} for index in range(10)],
        },
    }


def _config() -> Hip3ShadowMarkoutConfig:
    return Hip3ShadowMarkoutConfig(
        symbol="xyz:MU",
        provider_id="hip3_mu_full_l2_breakout_pressure_bidirectional_15m_v1",
        profile_id="mu_full_l2_breakout_pressure_bidirectional_15m_research_v1",
        ledger_profile_id="mu_breakout_shadow_xyz:mu",
        fee_bps_per_side=0.864,
        residual_latency_bps_per_side=1.0,
        friction_source="exact-test-evidence",
        horizons_minutes=(15, 60),
        maximum_book_lateness_ms=15_000,
    )


def test_markouts_use_first_post_publication_bbo_and_exact_direction() -> None:
    """Entries cannot use a pre-publication quote or mid-price shortcut."""
    start = 1_000_000
    decisions = (
        _decision(decision_ms=start - 10_000, observed_ms=start, side="long"),
        _decision(
            decision_ms=start + 4_000_000,
            observed_ms=start + 4_010_000,
            side="short",
        ),
    )
    books = (
        _book(start - 1, 99.0, 99.2),
        _book(start + 5, 100.0, 100.2),
        _book(start + 900_005, 101.0, 101.2),
        _book(start + 4_010_005, 102.0, 102.2),
        _book(start + 4_910_005, 100.8, 101.0),
    )

    report = build_hip3_shadow_signal_markouts(
        decision_rows=decisions,
        book_rows=books,
        config=_config(),
    )

    rows = report["markouts"]["horizons"]["15"]["independent_paths"]
    assert [row["side"] for row in rows] == ["long", "short"]
    assert rows[0]["entry_price"] == 100.2
    assert rows[0]["exit_price"] == 101.0
    assert rows[1]["entry_price"] == 102.0
    assert rows[1]["exit_price"] == 101.0
    assert all(row["after_modeled_friction_bps"] > 0.0 for row in rows)


def test_markouts_report_censored_and_late_books_without_fabrication() -> None:
    """Missing executable quotes remain explicit coverage failures."""
    start = 2_000_000
    decisions = (
        _decision(decision_ms=start - 10_000, observed_ms=start, side="long"),
        _decision(
            decision_ms=start + 1_000_000,
            observed_ms=start + 1_000_000,
            side="short",
        ),
    )
    books = (
        _book(start + 20_000, 100.0, 100.2),
        _book(start + 1_000_005, 101.0, 101.2),
    )

    report = build_hip3_shadow_signal_markouts(
        decision_rows=decisions,
        book_rows=books,
        config=_config(),
    )

    coverage = report["markouts"]["horizons"]["15"]["coverage"]
    assert coverage == {
        "eligible_signals": 2,
        "entry_matched": 1,
        "entry_censored": 0,
        "entry_gap": 1,
        "resolved": 0,
        "exit_censored": 1,
        "exit_gap": 0,
    }
    assert report["contract"]["pnl_claimed"] is False
    assert report["execution_authority"] == "none"


def test_markouts_reject_aliased_or_duplicate_evidence() -> None:
    """Exact route and append-once identities are mandatory."""
    decision = _decision(decision_ms=3_000_000, observed_ms=3_000_010, side="long")
    wrong_book = _book(3_000_011, 100.0, 100.2)
    wrong_book["payload"]["symbol"] = "xyz:SP500"

    with pytest.raises(ValueError, match="book symbol"):
        build_hip3_shadow_signal_markouts(
            decision_rows=(decision,),
            book_rows=(wrong_book,),
            config=_config(),
        )
    with pytest.raises(ValueError, match="duplicate decision"):
        build_hip3_shadow_signal_markouts(
            decision_rows=(decision, decision),
            book_rows=(),
            config=_config(),
        )
