"""Tests for the immutable cohort growth stress command helpers."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "cohort_growth_sizing_stress.py"


def _load_module() -> ModuleType:
    spec = spec_from_file_location("cohort_growth_sizing_stress", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parses_core_schedule_fee_without_selecting_a_later_fill_fee() -> None:
    """Fill-fee events cannot hide the explicit core venue schedule."""
    command = _load_module()
    fee, evidence = command.resolve_one_way_taker_fee_bps(
        [
            {
                "event_type": "fee",
                "profile_id": "profile-btc",
                "profile_fingerprint": "a" * 64,
                "payload": {
                    "source": "venue_fee_schedule",
                    "taker_rate": 0.00045,
                },
            },
            {
                "event_type": "fee",
                "profile_id": "profile-btc",
                "profile_fingerprint": "a" * 64,
                "payload": {"source": "fill", "fee_usd": 0.01},
            },
        ],
        symbol="BTC",
        profile_id="profile-btc",
        profile_fingerprint="a" * 64,
        hip3_roster=None,
    )

    assert fee == pytest.approx(4.5)
    assert evidence["source"] == "core_venue_fee_schedule"


def test_uses_conservative_one_way_exit_depth_not_round_trip_depth() -> None:
    """A fill-anchored stop adds only the adverse exit leg's visible depth."""
    command = _load_module()
    quantiles = command.visible_quantiles(
        {
            "snapshot_count": 240,
            "buy_complete_rate": 1.0,
            "sell_complete_rate": 0.99,
            "buy_visible_cost_bps": {
                "count": 240,
                "p50": 1.0,
                "p90": 2.0,
                "p99": 4.0,
            },
            "sell_visible_cost_bps": {
                "count": 238,
                "p50": 1.5,
                "p90": 3.0,
                "p99": 5.0,
            },
            "round_trip_visible_cost_bps": {
                "count": 238,
                "p50": 2.5,
                "p90": 5.0,
                "p99": 9.0,
            },
        }
    )

    assert quantiles.sample_count == 238
    assert quantiles.complete_rate == pytest.approx(238 / 240)
    assert (quantiles.p50, quantiles.p90, quantiles.p99) == pytest.approx(
        (1.5, 3.0, 5.0)
    )

    invalid = {
        "snapshot_count": 2,
        "buy_complete_rate": 1.0,
        "sell_complete_rate": 1.0,
        "buy_visible_cost_bps": {"count": 3, "p50": 1.0, "p90": 1.0, "p99": 1.0},
        "sell_visible_cost_bps": {"count": 2, "p50": 1.0, "p90": 1.0, "p99": 1.0},
    }
    with pytest.raises(ValueError, match="cannot exceed samples"):
        command.visible_quantiles(invalid)


def test_resolves_hip3_fee_from_roster_or_compatible_observed_fill() -> None:
    """HIP-3 never reuses the generic core schedule as its effective fee."""
    command = _load_module()
    roster = _hip3_roster("resolved", 0.0000864)

    fee, evidence = command.resolve_one_way_taker_fee_bps(
        [],
        symbol="xyz:SP500",
        profile_id="profile-sp500",
        profile_fingerprint="b" * 64,
        hip3_roster=roster,
    )

    assert fee == pytest.approx(0.864)
    assert evidence["source"] == "hip3_roster_effective_fee"

    unresolved = _hip3_roster("unresolved_growth_mode", None, symbol="xyz:GOLD")
    fee, evidence = command.resolve_one_way_taker_fee_bps(
        [
            {
                "event_type": "fill",
                "profile_id": "profile-gold",
                "profile_fingerprint": "c" * 64,
                "payload": {
                    "trade_id": 7,
                    "venue_timestamp_ms": 100,
                    "crossed": True,
                    "price": 4_362.0,
                    "size": 0.0171,
                    "fee_usd": 0.064445,
                    "fee_token": "USDC",
                },
            }
        ],
        symbol="xyz:GOLD",
        profile_id="profile-gold",
        profile_fingerprint="c" * 64,
        hip3_roster=unresolved,
    )

    assert fee == pytest.approx(8.64, abs=0.001)
    assert evidence["source"] == "compatible_profile_observed_taker_fill"


def test_parses_wrapped_hip3_liquidity_at_exact_notional() -> None:
    """Historical HIP-3 evidence must match the proposed $750 notional."""
    command = _load_module()
    profile = {
        "ok": True,
        "report_only": True,
        "execution_authority": "none",
        "profile": {
            "notionals": [
                {
                    "notional_usd": 750.0,
                    "samples": 1_000,
                    "buy_complete_rate": 1.0,
                    "sell_complete_rate": 1.0,
                    "both_complete_rate": 1.0,
                    "buy_visible_cost_bps": {
                        "count": 1_000,
                        "p50": 0.2,
                        "p90": 1.0,
                        "p99": 2.0,
                    },
                    "sell_visible_cost_bps": {
                        "count": 1_000,
                        "p50": 0.3,
                        "p90": 1.5,
                        "p99": 3.0,
                    },
                    "round_trip_visible_cost_bps": {
                        "count": 1_000,
                        "p50": 0.5,
                        "p90": 1.5,
                        "p99": 3.0,
                    },
                }
            ]
        },
    }

    quantiles = command.hip3_visible_quantiles(profile, notional_usd=750.0)

    assert quantiles.sample_count == 1_000
    assert quantiles.p99 == pytest.approx(3.0)
    profile["profile"]["notionals"][0]["notional_usd"] = 1_750.0
    rounded = command.hip3_visible_quantiles(profile, notional_usd=1_750.0000000000002)
    assert rounded.p99 == pytest.approx(3.0)
    with pytest.raises(ValueError, match="exact notional"):
        command.hip3_visible_quantiles(profile, notional_usd=500.0)


def test_latest_funding_requires_exact_symbol_and_ordered_rows() -> None:
    """Funding sensitivity cannot borrow another market or future-order rows."""
    command = _load_module()
    rows = [
        {"coin": "BTC", "fundingRate": "0.00001", "time": 100},
        {"coin": "BTC", "fundingRate": "0.00002", "time": 200},
    ]

    assert command.latest_funding_rate(
        rows, symbol="BTC", start_ms=100, end_ms=200
    ) == pytest.approx(0.00002)
    with pytest.raises(ValueError, match="ordered and unique"):
        command.latest_funding_rate(
            list(reversed(rows)), symbol="BTC", start_ms=100, end_ms=200
        )
    with pytest.raises(ValueError, match="does not match"):
        command.latest_funding_rate(rows, symbol="ETH", start_ms=100, end_ms=200)
    with pytest.raises(ValueError, match="outside requested bounds"):
        command.latest_funding_rate(rows, symbol="BTC", start_ms=101, end_ms=200)


def test_candidate_margin_override_is_explicit_and_validated() -> None:
    """Research scenarios may vary sizing without mutating the source config."""
    command = _load_module()

    assert command.candidate_margin_fraction(0.03, None) == pytest.approx(0.03)
    assert command.candidate_margin_fraction(0.03, 0.05) == pytest.approx(0.05)
    with pytest.raises(ValueError, match="not exceed one"):
        command.candidate_margin_fraction(0.03, 1.01)


def test_parser_accepts_a_report_only_margin_scenario() -> None:
    """The CLI exposes candidate sizing separately from the live profile."""
    command = _load_module()

    args = command.build_parser().parse_args(
        ["--margin-fraction", "0.07", "--out", "candidate.json"]
    )

    assert args.margin_fraction == pytest.approx(0.07)


def test_parser_accepts_separate_active_evidence_config() -> None:
    """A staged candidate can consume evidence from the actual live profile."""
    command = _load_module()

    args = command.build_parser().parse_args(
        [
            "--active-config",
            "configs/active.toml",
            "--out",
            "candidate.json",
        ]
    )

    assert args.active_config == Path("configs/active.toml")


def test_candidate_assets_pair_to_exact_active_evidence_symbols() -> None:
    """The staged Gold-retired roster must not inherit the active Gold asset."""
    command = _load_module()
    root = SCRIPT.parents[1]
    candidate = command.load_multi_asset_live_config(
        root / "configs/multi_asset_bidirectional_growth_5000_candidate_v37.toml",
        mode="observe",
    )
    active = command.load_multi_asset_live_config(
        root / "configs/multi_asset_bidirectional_all_live_canary_v35.toml",
        mode="observe",
    )

    pairs = command.candidate_evidence_asset_pairs(candidate, active)

    assert len(pairs) == 8
    assert {candidate_asset.symbol for candidate_asset, _ in pairs} == set(
        candidate.symbols
    )
    assert all(
        candidate_asset.symbol == evidence_asset.symbol
        for candidate_asset, evidence_asset in pairs
    )
    assert all(
        candidate_asset.parent_profile_id == candidate.profile_id
        for candidate_asset, _ in pairs
    )
    assert all(
        evidence_asset.parent_profile_id == active.profile_id
        for _, evidence_asset in pairs
    )
    assert "xyz:GOLD" not in {asset.symbol for asset, _ in pairs}


def test_candidate_asset_pairing_rejects_missing_active_symbol() -> None:
    """A candidate cannot borrow evidence from a different market identity."""
    command = _load_module()
    root = SCRIPT.parents[1]
    candidate_with_gold = command.load_multi_asset_live_config(
        root / "configs/multi_asset_bidirectional_all_live_canary_v35.toml",
        mode="observe",
    )
    active_without_gold = command.load_multi_asset_live_config(
        root / "configs/multi_asset_bidirectional_growth_5000_candidate_v37.toml",
        mode="observe",
    )

    with pytest.raises(ValueError, match="missing candidate symbols.*xyz:GOLD"):
        command.candidate_evidence_asset_pairs(
            candidate_with_gold,
            active_without_gold,
        )


def test_immutable_writer_refuses_an_existing_artifact(tmp_path: Path) -> None:
    """A prior sizing conclusion cannot be overwritten in place."""
    command = _load_module()
    output = tmp_path / "stress.json"
    output.write_text("{}\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        command.write_immutable_report(output, {"report_only": True})

    fresh = tmp_path / "fresh.json"
    command.write_immutable_report(fresh, {"report_only": True})
    assert json.loads(fresh.read_text(encoding="utf-8")) == {"report_only": True}


def test_immutable_writer_has_one_winner_under_concurrent_creation(
    tmp_path: Path,
) -> None:
    """Exclusive publication cannot race into overwriting immutable evidence."""
    command = _load_module()
    output = tmp_path / "race.json"

    def publish(value: int) -> str:
        try:
            command.write_immutable_report(output, {"value": value})
        except FileExistsError:
            return "exists"
        return "written"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(publish, (1, 2)))

    assert sorted(outcomes) == ["exists", "written"]
    assert json.loads(output.read_text(encoding="utf-8"))["value"] in {1, 2}


def _hip3_roster(
    status: str,
    taker_rate: float | None,
    *,
    symbol: str = "xyz:SP500",
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "hip3_roster_observer_checkpoint",
        "status": "available",
        "report_only": True,
        "execution_authority": "none",
        "observed_at_utc": "2026-08-10T16:00:00+00:00",
        "markets": [
            {
                "symbol": symbol,
                "venue": {
                    "effective_fee_status": status,
                    "taker_fee_rate": taker_rate,
                },
            }
        ],
    }
