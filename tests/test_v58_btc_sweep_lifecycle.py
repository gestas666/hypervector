"""Exact report-only V58 BTC liquidity-sweep lifecycle tests."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.cohort_eligible_policy_funding import (
    EligiblePolicyFundingEvidence,
)
from hypervector.research.v58_btc_sweep_lifecycle import (
    BTC_SWEEP_STRATEGY,
    build_v58_btc_sweep_resolution,
)

_CONFIG = "configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml"
_RUN = "bidirectional-observe-test"
_RUN_FINGERPRINT = "observer-run-test"
_START_MS = 60_000


def test_fixed_target_resolves_with_exact_depth_and_complete_mark_path() -> None:
    """The frozen 60-bps target must precede a later stop and maximum hold."""
    records = _records(
        _evaluation(BTC_SWEEP_STRATEGY, 60_000, "long", eligible=True),
        books=(
            _book(62_000, 99.9, 100.1),
            _book(90_000, 100.8, 100.9),
        ),
    )

    report = _resolution(records, _marks((62_000, 100.0), (90_000, 100.7)))

    execution = report["latest_executions"][0]
    assert execution["exit_reason"] == "fixed_target"
    assert execution["exit_time_ms"] == 90_000
    assert execution["technical_complete"] is True
    assert report["summary"] == {
        "selected_non_overlapping": 1,
        "overlapping_excluded": 0,
        "resolved": 1,
        "pending": 0,
        "technical_incomplete": 0,
    }


def test_mark_stop_wins_a_same_observation_tie_with_target() -> None:
    """A same-receipt target/stop ambiguity must resolve pessimistically."""
    records = _records(
        _evaluation(BTC_SWEEP_STRATEGY, 60_000, "long", eligible=True),
        books=(
            _book(62_000, 99.9, 100.1),
            _book(90_000, 100.8, 100.9),
        ),
    )

    report = _resolution(records, _marks((62_000, 100.0), (90_000, 99.4)))

    execution = report["latest_executions"][0]
    assert execution["exit_reason"] == "protective_stop_mark"
    assert execution["exit_time_ms"] == 90_000


def test_cross_provider_hulk_short_closes_the_open_sweep_long() -> None:
    """A selected BTC short mechanism is an exit even with another provider ID."""
    records = _records(
        _evaluation(BTC_SWEEP_STRATEGY, 60_000, "long", eligible=True),
        _evaluation("hulk_expansion_short_robust_v3", 120_000, "short", eligible=True),
        books=(
            _book(62_000, 99.9, 100.1),
            _book(122_000, 100.2, 100.3),
        ),
    )

    report = _resolution(records, _marks((62_000, 100.0), (122_000, 100.2)))

    execution = report["latest_executions"][0]
    assert execution["exit_reason"] == "eligible_cross_provider_opposite_intent"
    assert execution["opposite_strategy_id"] == "hulk_expansion_short_robust_v3"


def test_incomplete_mark_cadence_censors_an_apparent_target_win() -> None:
    """A target cannot be called resolved when the venue-mark path is unknown."""
    records = _records(
        _evaluation(BTC_SWEEP_STRATEGY, 60_000, "long", eligible=True),
        books=(
            _book(62_000, 99.9, 100.1),
            _book(250_000, 100.8, 100.9),
        ),
    )

    report = _resolution(records, _marks((62_000, 100.0), (250_000, 100.7)))

    assert report["latest_attempts"][0]["status"] == "mark_path_incomplete"
    assert report["summary"]["resolved"] == 0
    assert report["summary"]["technical_incomplete"] == 1


def test_insufficient_exit_depth_is_not_counted_as_resolved() -> None:
    """A target touch without enough exit depth must remain technical evidence."""
    records = _records(
        _evaluation(BTC_SWEEP_STRATEGY, 60_000, "long", eligible=True),
        books=(
            _book(62_000, 99.9, 100.1),
            _book(90_000, 100.8, 100.9, size=0.001),
        ),
    )

    report = _resolution(records, _marks((62_000, 100.0), (90_000, 100.7)))

    assert report["latest_attempts"][0]["status"] == "exit_capacity_insufficient"
    assert report["latest_executions"] == []
    assert report["summary"]["resolved"] == 0
    assert report["summary"]["technical_incomplete"] == 1


def test_insufficient_current_exit_depth_is_not_reported_as_pending() -> None:
    """An open path needs enough visible exit depth for a current valuation."""
    records = _records(
        _evaluation(BTC_SWEEP_STRATEGY, 60_000, "long", eligible=True),
        books=(
            _book(62_000, 99.9, 100.1),
            _book(90_000, 100.2, 100.3, size=0.001),
        ),
    )

    report = _resolution(records, _marks((62_000, 100.0), (90_000, 100.2)))

    assert (
        report["latest_attempts"][0]["status"] == "current_exit_capacity_insufficient"
    )
    assert report["summary"]["pending"] == 0
    assert report["summary"]["technical_incomplete"] == 1


def test_exact_v58_config_freezes_the_sweep_route_and_exit_contract() -> None:
    """The report must reject a relabeled or drifted provider contract."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    records = _records(
        _evaluation(BTC_SWEEP_STRATEGY, 60_000, "long", eligible=False),
        books=(_book(62_000, 99.9, 100.1),),
    )

    report = build_v58_btc_sweep_resolution(
        records,
        marks=_marks((62_000, 100.0)),
        config=config,
        run_id=_RUN,
        prospective_start_ms=_START_MS,
        funding_evidence=None,
        taker_fee_rate=0.00045,
    )

    assert report["contract"]["stop_bps"] == 60.0
    assert report["contract"]["target_bps"] == 60.0
    assert report["contract"]["maximum_hold_minutes"] == 1_440
    assert report["contract"]["execution_authority"] == "none"


def _resolution(
    records: list[dict[str, object]], marks: list[dict[str, object]]
) -> dict[str, object]:
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    return build_v58_btc_sweep_resolution(
        records,
        marks=marks,
        config=config,
        run_id=_RUN,
        prospective_start_ms=_START_MS,
        funding_evidence=EligiblePolicyFundingEvidence("BTC", 0, 300_000, ()),
        taker_fee_rate=0.00045,
    )


def _records(
    *evaluations: Mapping[str, object], books: tuple[dict[str, object], ...]
) -> list[dict[str, object]]:
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    identity = _envelope(
        "configuration_identity",
        0,
        {
            "strategy_name": "multi_asset_bidirectional_cohort",
            "profile_fingerprint": config.profile_fingerprint,
            "providers": [
                {
                    "strategy_id": BTC_SWEEP_STRATEGY,
                    "symbols": ["BTC"],
                    "sides": ["long"],
                },
                {
                    "strategy_id": "hulk_expansion_short_robust_v3",
                    "symbols": ["BTC"],
                    "sides": ["short"],
                },
            ],
        },
    )
    routed = [
        _envelope(
            "intent_routing",
            int(row["decision_time_ms"]) + 1_000,
            {"evaluations": [dict(row)]},
        )
        for row in evaluations
    ]
    market = [
        _envelope("market_books", int(row["recv_ts_ms"]), {"books": {"BTC": row}})
        for row in books
    ]
    return [identity, *routed, *market]


def _evaluation(
    strategy: str, decision_ms: int, side: str, *, eligible: bool
) -> dict[str, object]:
    return {
        "strategy_id": strategy,
        "symbol": "BTC",
        "decision_time_ms": decision_ms,
        "reference_price": 100.0,
        "eligible": eligible,
        "side": side if eligible else None,
        "readiness": {"side": side, "blockers": [], "metrics": {}},
    }


def _book(
    time_ms: int, bid: float, ask: float, *, size: float = 100.0
) -> dict[str, object]:
    return {
        "symbol": "BTC",
        "source": "hyperliquid_mainnet_l2_rest",
        "exchange_ts_ms": time_ms - 1,
        "recv_ts_ms": time_ms,
        "bids": [{"price": bid, "size": size}],
        "asks": [{"price": ask, "size": size}],
    }


def _marks(*rows: tuple[int, float]) -> list[dict[str, object]]:
    return [
        {
            "schema_version": 1,
            "symbol": "BTC",
            "source": "hyperliquid_info_metaAndAssetCtxs_rest",
            "run_id": _RUN,
            "received_ts_ms": timestamp,
            "received_ts_ns": timestamp * 1_000_000,
            "mark_price": mark,
            "oracle_price": mark,
            "funding_rate_hourly": 0.0,
            "open_interest": 1.0,
        }
        for timestamp, mark in rows
    ]


def _envelope(
    event_type: str, observed_ms: int, values: Mapping[str, object]
) -> dict[str, object]:
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    return {
        "event_type": event_type,
        "run_id": _RUN,
        "observed_at_utc": f"1970-01-01T00:{observed_ms // 60_000:02d}:{(observed_ms % 60_000) / 1000:06.3f}+00:00",
        "execution_mode": "observe",
        "effective_mode": "OBSERVE ONLY",
        "live_armed": False,
        "execution_authority": "none",
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
        "run_fingerprint": _RUN_FINGERPRINT,
        "payload": dict(values),
    }
