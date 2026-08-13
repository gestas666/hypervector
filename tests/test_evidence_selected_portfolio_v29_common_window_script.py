"""Contract tests for the fixed-window v29 shared-account diagnostic."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

from hypervector.research.current_cohort_shared_portfolio import CohortOutcome
from hypervector.research.shared_trade_portfolio import SharedTradeOutcome

SCRIPT = Path("scripts/evidence_selected_portfolio_v29_common_window.py")
FROZEN_SCRIPT = Path("scripts/evidence_selected_portfolio_v29.py")
CONFIG = Path(
    "configs/multi_asset_bidirectional_evidence_selected_portfolio_canary_v29.toml"
)
FULL_WINDOW = Path(
    "data/logs/research/"
    "evidence_selected_portfolio_v29_shared_arbitration_20260808T070837Z.json"
)
FINGERPRINT = "d1f4cd3b03197e9e7a9899ab32e2b198fd4bd2a4117f1ea64261824fcdc4a393"
START_MS = 1_781_320_500_000
END_MS = 1_783_252_800_000
ROUTES = (
    ("range_onset_bidirectional_v1", "ETH"),
    ("range_onset_bidirectional_v1", "SOL"),
    ("eth_breakout_precompression_pullback_bidirectional_v1", "ETH"),
    ("hip3_swing_ha_sp500_spcx_bidirectional_v2", "xyz:SPCX"),
    ("hip3_breakout_pressure_sp500_spcx_bidirectional_v1", "xyz:SP500"),
    ("hip3_swing_ha_sndk_gold_brent_bidirectional_v1", "xyz:GOLD"),
)


def _load(path: Path, name: str) -> ModuleType:
    """Load a versioned command without invoking its entry point."""
    spec = spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load script: {path}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _outcome(
    strategy: str,
    symbol: str,
    entry_ms: int,
    *,
    side: str = "long",
    net: float = 1.0,
) -> CohortOutcome:
    """Return one deterministic fixed-cap lifecycle."""
    source = SharedTradeOutcome(
        f"{strategy}|{symbol}|{entry_ms}|{side}",
        symbol,
        entry_ms,
        entry_ms + 5_000,
        500.0,
        0.03,
        0.01,
        net,
        "fixture_exit",
    )
    return CohortOutcome(strategy, side, source)


def _scenario(*, sol_short: bool = True) -> tuple[CohortOutcome, ...]:
    """Represent every route and optionally both sides of SOL."""
    rows = [
        _outcome(strategy, symbol, START_MS + index * 20_000, side="long")
        for index, (strategy, symbol) in enumerate(ROUTES)
    ]
    rows.extend(
        _outcome(strategy, symbol, START_MS + 200_000 + index * 20_000, side="short")
        for index, (strategy, symbol) in enumerate(ROUTES)
        if sol_short or symbol != "SOL"
    )
    return tuple(rows)


def test_parser_binds_the_frozen_full_window_reference() -> None:
    """The command must compare against the exact immutable revision-4 artifact."""
    module = _load(SCRIPT, "v29_common_window_parser")

    args = module.build_parser().parse_args(["--out", "report.json"])

    assert args.config == CONFIG
    assert args.full_window_artifact == FULL_WINDOW
    assert args.out == Path("report.json")


def test_fixed_window_filter_is_half_open() -> None:
    """Only entries inside the predeclared half-open interval are retained."""
    module = _load(SCRIPT, "v29_common_window_filter")
    strategy, symbol = ROUTES[0]
    rows = tuple(
        _outcome(strategy, symbol, entry_ms)
        for entry_ms in (START_MS - 1, START_MS, END_MS - 1, END_MS)
    )

    filtered = module.filter_entry_window(rows)

    assert [row.outcome.entry_time_ms for row in filtered] == [START_MS, END_MS - 1]


def test_route_side_coverage_reports_missing_side_without_hiding_route() -> None:
    """Sparse one-sided evidence must remain visible rather than aborting the trial."""
    module = _load(SCRIPT, "v29_common_window_coverage")

    coverage = module.route_side_coverage(_scenario(sol_short=False), ROUTES)

    assert coverage["all_routes_present"] is True
    assert coverage["missing_routes"] == []
    assert coverage["all_route_sides_present"] is False
    assert coverage["missing_route_sides"] == ["range_onset_bidirectional_v1|SOL|short"]
    assert coverage["by_route"]["range_onset_bidirectional_v1|SOL"] == 1


def test_route_side_coverage_reports_an_absent_selected_route() -> None:
    """A missing route must be explicit before the frozen builder fails closed."""
    module = _load(SCRIPT, "v29_common_window_missing_route")
    rows = tuple(
        row
        for row in _scenario()
        if (row.strategy_id, row.outcome.symbol) != ROUTES[-1]
    )

    coverage = module.route_side_coverage(rows, ROUTES)

    missing_route = "|".join(ROUTES[-1])
    assert coverage["all_routes_present"] is False
    assert coverage["missing_routes"] == [missing_route]
    assert coverage["missing_route_sides"][-2:] == [
        f"{missing_route}|long",
        f"{missing_route}|short",
    ]


def test_artifact_is_report_only_and_compares_with_frozen_full_window() -> None:
    """Common-window economics must reconcile without gaining runtime authority."""
    module = _load(SCRIPT, "v29_common_window_artifact")
    frozen = _load(FROZEN_SCRIPT, "v29_frozen_for_common_window")
    contract = frozen.load_profile_contract(CONFIG)
    full_nominal = _scenario()
    full_stress = tuple(
        _outcome(
            row.strategy_id,
            row.outcome.symbol,
            row.outcome.entry_time_ms,
            side=row.side,
            net=-0.5,
        )
        for row in full_nominal
    )
    full_artifact = frozen.build_artifact(
        contract,
        {"nominal": full_nominal, "stress": full_stress},
        data_evidence={"source": {"sha256": "0" * 64, "bytes": 1}},
    )

    artifact = module.build_common_window_artifact(
        contract,
        {"nominal": full_nominal, "stress": full_stress},
        data_evidence={"source": {"sha256": "0" * 64, "bytes": 1}},
        full_window_artifact=full_artifact,
        full_window_evidence={"sha256": "1" * 64, "bytes": 2},
    )

    assert (
        artifact["schema_version"] == "evidence_selected_portfolio_v29_common_window_v1"
    )
    assert artifact["execution_authority"] == "none"
    assert artifact["report_only"] is True
    assert artifact["automatic_promotion"] is False
    assert artifact["runtime_strategy_changed"] is False
    assert artifact["common_window"]["start_ms"] == START_MS
    assert artifact["common_window"]["end_ms_exclusive"] == END_MS
    assert artifact["common_window"]["filter_basis"] == "entry_time_ms"
    assert artifact["full_window_reference"]["profile_fingerprint"] == FINGERPRINT
    assert artifact["full_window_reference"]["evidence"]["sha256"] == "1" * 64
    assert set(artifact["full_window_comparison"]) == {"nominal", "stress"}
    for scenario in ("nominal", "stress"):
        comparison = artifact["full_window_comparison"][scenario]
        assert comparison["common_window_completed_trades"] == 12
        assert comparison["full_window_completed_trades"] == 12
        assert comparison["net_pnl_delta_usd"] == pytest.approx(0.0)
        assert comparison["all_routes_present"] is True
        assert comparison["all_route_sides_present"] is True


def test_artifact_rejects_changed_full_window_identity() -> None:
    """A nearby artifact cannot silently replace the frozen revision-4 comparison."""
    module = _load(SCRIPT, "v29_common_window_identity")
    frozen = _load(FROZEN_SCRIPT, "v29_frozen_for_identity")
    contract = frozen.load_profile_contract(CONFIG)
    full_artifact = frozen.build_artifact(
        contract,
        {"nominal": _scenario(), "stress": _scenario()},
        data_evidence={"source": {"sha256": "0" * 64, "bytes": 1}},
    )
    full_artifact["profile_contract"]["profile_fingerprint"] = "f" * 64

    with pytest.raises(ValueError, match="full-window profile fingerprint"):
        module.build_common_window_artifact(
            contract,
            {"nominal": _scenario(), "stress": _scenario()},
            data_evidence={"source": {"sha256": "0" * 64, "bytes": 1}},
            full_window_artifact=full_artifact,
            full_window_evidence={"sha256": "1" * 64, "bytes": 2},
        )


def test_artifact_exposes_path_dependent_scenario_population() -> None:
    """Friction-created lifecycle differences must not look like source drift."""
    module = _load(SCRIPT, "v29_common_window_population")
    frozen = _load(FROZEN_SCRIPT, "v29_frozen_for_population")
    contract = frozen.load_profile_contract(CONFIG)
    nominal = _scenario()
    strategy, symbol = ROUTES[3]
    extra = _outcome(strategy, symbol, START_MS + 999_000, side="short")
    stress = nominal + (extra,)
    evidence = {"source": {"sha256": "0" * 64, "bytes": 1}}
    full_artifact = frozen.build_artifact(
        contract,
        {"nominal": nominal, "stress": stress},
        data_evidence=evidence,
    )

    artifact = module.build_common_window_artifact(
        contract,
        {"nominal": nominal, "stress": stress},
        data_evidence=evidence,
        full_window_artifact=full_artifact,
        full_window_evidence={"sha256": "1" * 64, "bytes": 2},
    )

    comparison = artifact["common_window"]["scenario_population_comparison"]
    expected = f"{strategy}|{symbol}|short|{START_MS + 999_000}"
    assert comparison["path_dependent_population"] is True
    assert comparison["nominal_only"] == []
    assert comparison["stress_only"] == [{"identity": expected, "count": 1}]


def test_publish_refuses_to_replace_immutable_evidence(tmp_path: Path) -> None:
    """A rerun must use a new timestamped artifact path."""
    module = _load(SCRIPT, "v29_common_window_publish")
    output = tmp_path / "report.json"
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="immutable JSON output exists"):
        module.publish_artifact(output, {"execution_authority": "none"})
