"""Report-only V58 eight-asset growth-stress command tests."""

import argparse
from pathlib import Path
from importlib.util import module_from_spec, spec_from_file_location
import subprocess
import sys

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.cohort_candidate_notionals import candidate_asset_notionals


SCRIPT = Path(__file__).parents[1] / "scripts" / "v58_eight_asset_growth_stress.py"
CONFIG = Path(__file__).parents[1] / (
    "configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml"
)
VENUE_STRESS = Path(__file__).parents[1] / (
    "data/logs/research/bidirectional_cohort/"
    "v40_growth_sizing_stress_20260811T0200Z.json"
)
RESEARCH = Path(__file__).parents[1] / "data/logs/research"


def _module() -> object:
    """Load the report script without executing its CLI."""
    spec = spec_from_file_location("v58_eight_asset_growth_stress", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _visible_profile(symbol: str, notional: float, p99: float) -> dict[str, object]:
    """Return one exact-notional depth profile fixture."""
    return {
        "profile": {
            "symbol": symbol,
            "notionals": [
                {
                    "notional_usd": notional,
                    "samples": 100,
                    "buy_complete_rate": 1.0,
                    "sell_complete_rate": 1.0,
                    "both_complete_rate": 1.0,
                    "buy_visible_cost_bps": {"count": 100, "p99": p99 - 0.1},
                    "sell_visible_cost_bps": {"count": 100, "p99": p99},
                }
            ],
        }
    }


def _preflight_fixture() -> tuple[object, dict[str, object], dict[str, object]]:
    """Return a candidate-bound preflight and conservative fee stress."""
    config = load_multi_asset_live_config(CONFIG, mode="observe")
    notionals = candidate_asset_notionals(config, 5000.0)
    fees = {
        symbol: 4.5 if not symbol.startswith("xyz:") else 0.864
        for symbol in config.symbols
    }
    preflight = {
        "identity": {
            "candidate_profile_id": config.profile_id,
            "candidate_profile_fingerprint": config.profile_fingerprint,
        },
        "portfolio": {
            "configured_assets": 8,
            "maximum_positions": 10,
            "maximum_configured_margin_fraction": 0.46,
            "sizing_reference_equity_usd": 5000.0,
        },
        "assets": [
            {
                "symbol": symbol,
                "sizing": {"planned_notional_usd": notionals[symbol]},
                "venue": {"one_way_taker_fee_bps": fees[symbol] - 0.18},
            }
            for symbol in config.symbols
        ],
    }
    venue = {
        "by_asset": {
            symbol: {"round_trip_taker_fee_bps": fee * 2.0}
            for symbol, fee in fees.items()
        }
    }
    return config, preflight, venue


def _friction_fixture(symbols: tuple[str, ...]) -> dict[str, dict[str, object]]:
    """Return complete positive empirical-friction fixtures."""
    return {
        symbol: {
            "entry": {"sample_count": 2, "p99_bps": 1.0},
            "adverse_exit": {"sample_count": 2, "p99_bps": 2.0},
            "target_exit": {"sample_count": 1, "p99_bps": 1.0},
            "exit_evidence_scope": "exact_symbol",
        }
        for symbol in symbols
    }


def test_v58_growth_stress_exposes_a_report_only_command() -> None:
    """The bounded evidence adapter must expose a callable CLI."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "report-only" in result.stdout.lower()


def test_v58_depth_sources_bind_every_exact_candidate_notional() -> None:
    """Each asymmetric V58 slot must use depth measured at its own notional."""
    module = _module()
    config = load_multi_asset_live_config(CONFIG, mode="observe")
    core = {
        "candidate_depth_evidence": {
            "notionals_usd": {"BTC": 5000.0, "HYPE": 5000.0},
            "assets": {
                symbol: {
                    "profile": {
                        "buy_visible_cost_bps": {"count": 240, "p99": p99 - 0.1},
                        "sell_visible_cost_bps": {"count": 240, "p99": p99},
                    }
                }
                for symbol, p99 in (("BTC", 1.0), ("HYPE", 2.0))
            },
        }
    }
    venue = {
        "sizing_plan": {"planned_notional_usd_per_slot": 750.0},
        "by_asset": {
            "ETH": {"p99": {"adverse_exit_visible_cost_bps": 3.0}},
            "SOL": {"p99": {"adverse_exit_visible_cost_bps": 4.0}},
        },
    }
    hip3 = {
        symbol: _visible_profile(symbol, notional, p99)
        for symbol, notional, p99 in (
            ("xyz:SP500", 1750.0, 5.0),
            ("xyz:SPCX", 1750.0, 6.0),
            ("xyz:SNDK", 750.0, 7.0),
            ("xyz:BRENTOIL", 750.0, 8.0),
        )
    }

    depths, evidence = module.exact_depth_overrides(
        config,
        equity_usd=5000.0,
        core_document=core,
        venue_document=venue,
        hip3_documents=hip3,
    )

    assert depths == {
        "BTC": 1.0,
        "ETH": 3.0,
        "SOL": 4.0,
        "HYPE": 2.0,
        "xyz:SP500": 5.0,
        "xyz:SPCX": 6.0,
        "xyz:SNDK": 7.0,
        "xyz:BRENTOIL": 8.0,
    }
    assert evidence["notionals_usd"]["xyz:SP500"] == 1750.0
    assert evidence["sources"]["xyz:SNDK"]["both_complete_rate"] == 1.0


def test_v58_preflight_reconciles_identity_sizing_and_conservative_fees() -> None:
    """Point-in-time venue evidence must match V58 and not exceed stress fees."""
    module = _module()
    config, preflight, venue = _preflight_fixture()

    result = module.validate_preflight(config, preflight, venue)

    assert result["configured_assets"] == 8
    assert result["maximum_configured_margin_fraction"] == 0.46
    assert result["fee_stress_conservative_for_current_inputs"] is True


def test_v58_preflight_rejects_a_current_fee_above_the_stress_input() -> None:
    """A stale lower fee must not understate the candidate loss stack."""
    module = _module()
    config, preflight, venue = _preflight_fixture()
    preflight["assets"][0]["venue"]["one_way_taker_fee_bps"] = 9.0

    with pytest.raises(ValueError, match="current fee exceeds stress fee for BTC"):
        module.validate_preflight(config, preflight, venue)


def test_v58_report_binds_eight_slots_and_retains_zero_authority() -> None:
    """The report must expose exact V58 topology without becoming an execution gate."""
    module = _module()
    config = load_multi_asset_live_config(CONFIG, mode="observe")
    depths = {symbol: float(index + 1) for index, symbol in enumerate(config.symbols)}

    report = module.build_v58_report(
        CONFIG,
        venue_stress_path=VENUE_STRESS,
        friction=_friction_fixture(config.symbols),
        depths=depths,
        preflight_evidence={"configured_assets": 8},
        depth_evidence={"notionals_usd": candidate_asset_notionals(config, 5000.0)},
    )

    scenario = report["scenarios"][0]
    assert set(scenario["asset_slots"]) == set(config.symbols)
    assert scenario["maximum_simultaneous_positions"] == 8
    assert scenario["account_position_capacity"] == 10
    assert scenario["route_aware_maximum_margin_fraction"] == pytest.approx(0.46)
    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["performance_gate"] is False
    assert report["v58_preflight_evidence"] == {"configured_assets": 8}


def test_v58_command_publishes_one_immutable_source_bound_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The adapter must wire exact sources and publish no live authority."""
    module = _module()
    config = load_multi_asset_live_config(CONFIG, mode="observe")

    def _friction(
        database: Path, checkpoint: Path, *, symbols: tuple[str, ...]
    ) -> tuple[dict[str, dict[str, object]], dict[str, object]]:
        assert database.name == "market.duckdb"
        assert checkpoint.name == "latest_checkpoint.json"
        return _friction_fixture(symbols), {"canonical_fill_rows": 10}

    monkeypatch.setattr(module, "collect_execution_friction", _friction)
    output = tmp_path / "v58-stress.json"
    args = argparse.Namespace(
        config=CONFIG,
        venue_stress=VENUE_STRESS,
        core_depth=RESEARCH
        / "bidirectional_cohort/v51_growth_sizing_stress_20260813_v1.json",
        sp500_depth=RESEARCH
        / "xyz_sp500_liquidity_profile_notional750_1250_1750_20260810.json",
        spcx_depth=RESEARCH
        / "xyz_spcx_liquidity_profile_notional750_1250_1750_20260810.json",
        sndk_depth=RESEARCH
        / "xyz_sndk_liquidity_profile_notional750_1250_1750_20260810.json",
        brentoil_depth=RESEARCH
        / "xyz_brentoil_liquidity_profile_notional750_1250_1750_20260810.json",
        preflight=RESEARCH
        / "bidirectional_cohort/v58_eight_asset_preflight_20260818_v1.json",
        database=Path("data/research/market.duckdb"),
        checkpoint=Path("data/runtime/bidirectional_cohort/latest_checkpoint.json"),
        output=output,
    )

    assert module.run(args) == 0

    document = __import__("json").loads(output.read_text(encoding="utf-8"))
    assert document["profile_id"] == config.profile_id
    assert document["source_execution_evidence"]["canonical_fill_rows"] == 10
    assert set(document["execution_friction_evidence"]) == set(config.symbols)
    assert document["contract"]["execution_authority"] == "none"
