"""Contract tests for the immutable v29 shared-portfolio diagnostic."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

from hypervector.research.current_cohort_shared_portfolio import CohortOutcome
from hypervector.research.shared_trade_portfolio import SharedTradeOutcome

SCRIPT = Path("scripts/evidence_selected_portfolio_v29.py")
CONFIG = Path(
    "configs/multi_asset_bidirectional_evidence_selected_portfolio_canary_v29.toml"
)
FINGERPRINT = "d1f4cd3b03197e9e7a9899ab32e2b198fd4bd2a4117f1ea64261824fcdc4a393"
ROUTES = (
    ("range_onset_bidirectional_v1", "ETH"),
    ("range_onset_bidirectional_v1", "SOL"),
    ("eth_breakout_precompression_pullback_bidirectional_v1", "ETH"),
    ("hip3_swing_ha_sp500_spcx_bidirectional_v2", "xyz:SPCX"),
    ("hip3_breakout_pressure_sp500_spcx_bidirectional_v1", "xyz:SP500"),
    ("hip3_swing_ha_sndk_gold_brent_bidirectional_v1", "xyz:GOLD"),
)


def _load() -> ModuleType:
    """Load the command without invoking its entry point."""
    spec = spec_from_file_location("evidence_selected_portfolio_v29_script", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v29 shared-portfolio script")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _outcome(
    strategy: str,
    symbol: str,
    index: int,
    *,
    net: float = 1.0,
) -> CohortOutcome:
    """Return one fixed-cap synthetic lifecycle."""
    entry_ms = 1_700_000_000_000 + index * 10_000
    source = SharedTradeOutcome(
        f"{strategy}|{symbol}|{index}",
        symbol,
        entry_ms,
        entry_ms + 5_000,
        500.0,
        0.03,
        0.01,
        net,
        "fixture_exit",
    )
    return CohortOutcome(strategy, "long" if index % 2 == 0 else "short", source)


def _scenario() -> tuple[CohortOutcome, ...]:
    """Represent every exact v29 route once."""
    return tuple(
        _outcome(strategy, symbol, index)
        for index, (strategy, symbol) in enumerate(ROUTES)
    )


def test_parser_defaults_to_exact_local_v29_sources() -> None:
    """The diagnostic must require only explicit local immutable sources."""
    module = _load()

    args = module.build_parser().parse_args(["--out", "report.json"])

    assert args.config == CONFIG
    assert args.range_context.name.endswith("_v2.json")
    assert args.hip3_sidecar.name.endswith(".trades.parquet")
    assert args.eth_bars.name == "ETH_1m_365d.parquet"
    assert len(args.sol_artifact) == 12
    assert args.out == Path("report.json")


def test_profile_contract_binds_six_routes_and_zero_observe_filler() -> None:
    """The report must use the exact staged profile rather than a nearby config."""
    module = _load()

    contract = module.load_profile_contract(CONFIG)

    assert contract.profile_fingerprint == FINGERPRINT
    assert contract.initial_equity_usd == 500.0
    assert contract.maximum_positions == 5
    assert contract.execution_scope == ROUTES
    assert contract.observe_only_scope == ()
    assert contract.strategy_priority == tuple(dict.fromkeys(row[0] for row in ROUTES))
    assert contract.notional_caps == {
        "ETH": 25.0,
        "SOL": 75.0,
        "xyz:SP500": 75.0,
        "xyz:SPCX": 75.0,
        "xyz:GOLD": 75.0,
    }


def test_profile_contract_rejects_missing_execution_route(tmp_path: Path) -> None:
    """An edited profile may not silently turn a selected route into observe-only."""
    changed = CONFIG.read_text(encoding="utf-8").replace(
        'execution_symbols = ["xyz:GOLD"]',
        "execution_symbols = []",
    )
    path = tmp_path / "changed.toml"
    path.write_text(changed, encoding="utf-8")

    with pytest.raises(ValueError, match="execution scope"):
        _load().load_profile_contract(path)


def test_artifact_reconciles_both_scenarios_without_execution_authority() -> None:
    """Nominal and stress results must remain report-only and equity-reconciled."""
    module = _load()
    contract = module.load_profile_contract(CONFIG)
    nominal = _scenario()
    stress = tuple(
        _outcome(strategy, symbol, index, net=-0.5)
        for index, (strategy, symbol) in enumerate(ROUTES)
    )

    artifact = module.build_artifact(
        contract,
        {"nominal": nominal, "stress": stress},
        data_evidence={"fixture": {"sha256": "0" * 64, "bytes": 1}},
    )

    assert artifact["execution_authority"] == "none"
    assert artifact["report_only"] is True
    assert artifact["automatic_promotion"] is False
    assert artifact["runtime_strategy_changed"] is False
    assert artifact["source_phase_contract"] == {
        "allowed": ["development", "validation"],
        "sealed_holdout_accessed": False,
    }
    assert set(artifact["scenarios"]) == {"nominal", "stress"}
    for name in ("nominal", "stress"):
        report = artifact["scenarios"][name]
        assert report["completed_trades"] == 6
        accepted_net = sum(row["net_pnl_usd"] for row in report["accepted"])
        assert report["net_pnl_usd"] == pytest.approx(accepted_net)
        assert report["final_equity_usd"] == pytest.approx(500.0 + accepted_net)
    assert artifact["scenarios"]["nominal"]["net_pnl_usd"] == pytest.approx(6.0)
    assert -3.0 < artifact["scenarios"]["stress"]["net_pnl_usd"] < -2.9
    assert artifact["input_trade_counts"]["nominal"]["total"] == 6
    assert set(artifact["input_trade_counts"]["nominal"]["by_route_side"]) == {
        f"{row.strategy_id}|{row.outcome.symbol}|{row.side}" for row in nominal
    }


def test_publish_refuses_to_overwrite_immutable_evidence(tmp_path: Path) -> None:
    """A rerun must select a new artifact path rather than replace evidence."""
    module = _load()
    output = tmp_path / "report.json"
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="immutable JSON output exists"):
        module.publish_artifact(output, {"execution_authority": "none"})
