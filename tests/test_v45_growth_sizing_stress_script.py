"""Publication contract for the v45 growth-sizing stress report."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_SCRIPT = Path("scripts/v45_growth_sizing_stress.py")
_V45 = Path(
    "configs/multi_asset_bidirectional_btc_specialists_growth_sizing_candidate_v45.toml"
)
_V46 = Path("configs/multi_asset_growth_first_5000_candidate_v46.toml")


def _script() -> object:
    spec = spec_from_file_location("v45_growth_sizing_stress", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v45 growth stress script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_candidate_notionals_use_largest_route_per_asset() -> None:
    """BTC shares one slot while HYPE and SP500 use their 7% base sizing."""
    script = _script()
    config = load_multi_asset_live_config(_V45, mode="observe")

    notionals = script.candidate_asset_notionals(config, 5_000.0)

    assert notionals == pytest.approx(
        {"BTC": 4_166.666666666666, "HYPE": 1_750.0, "xyz:SP500": 1_750.0}
    )


@pytest.mark.evidence
def test_report_freezes_candidate_depth_and_never_grants_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The publisher binds depth inputs while remaining execution-incapable."""
    script = _script()
    output = tmp_path / "v45.json"
    args = script.build_parser().parse_args(["--output", str(output)])
    depths = {"BTC": 0.64, "HYPE": 1.48, "xyz:SP500": 1.42}
    monkeypatch.setattr(
        script,
        "collect_candidate_depth",
        lambda *_args, **_kwargs: (depths, {"source": "fixture"}),
    )
    assert script.run(args) == 0
    report = json.loads(output.read_text())

    assert report["schema_version"] == "v45_portfolio_friction_stress_v1"
    assert report["contract"]["execution_authority"] == "none"
    assert report["visible_depth_contract"]["p99_bps_by_asset"] == depths
    assert report["candidate_depth_evidence"] == {"source": "fixture"}
    assert (
        "src/hypervector/research/v43_portfolio_friction_stress.py" in report["inputs"]
    )


@pytest.mark.evidence
def test_report_supports_explicit_v46_identity_and_leverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reusable stress command must not relabel v46 as v45/5x."""
    script = _script()
    output = tmp_path / "v46.json"
    args = script.build_parser().parse_args(
        [
            "--candidate-config",
            str(_V46),
            "--schema-version",
            "v46_portfolio_friction_stress_v1",
            "--output",
            str(output),
        ]
    )
    depths = {symbol: 2.0 for symbol in ("BTC", "ETH", "SOL", "HYPE", "xyz:SP500")}
    monkeypatch.setattr(
        script,
        "collect_candidate_depth",
        lambda *_args, **_kwargs: (depths, {"source": "fixture"}),
    )
    original_load = script._load

    def load_with_friction(path: Path, label: str) -> object:
        document = original_load(path, label)
        if path != args.friction:
            return document
        rows = dict(document["execution_friction_evidence"])
        rows["ETH"] = rows["BTC"]
        rows["SOL"] = rows["BTC"]
        return {**document, "execution_friction_evidence": rows}

    monkeypatch.setattr(script, "_load", load_with_friction)

    assert script.run(args) == 0
    report = json.loads(output.read_text())

    assert report["schema_version"] == "v46_portfolio_friction_stress_v1"
    assert report["sizing_policy"]["configured_leverage"] == 10.0


def test_explicit_live_depth_source_measures_sp500_from_bound_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Large SP500 notionals must use the explicitly requested live L2 source."""
    script = _script()
    candidate = load_multi_asset_live_config(_V46, mode="observe")
    active = load_multi_asset_live_config(
        Path(
            "configs/"
            "multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml"
        ),
        mode="observe",
    )
    observed: list[tuple[str, float]] = []

    def live_depth(asset: object, _run: str, notional: float, _limit: int) -> object:
        observed.append((str(getattr(asset, "symbol")), notional))
        return 1.0, {"source": "bounded_live_l2"}

    monkeypatch.setattr(script, "_live_depth", live_depth)
    monkeypatch.setattr(
        script,
        "active_ledger_identity",
        lambda _config: type("Identity", (), {"run_id": "run"})(),
    )

    _, evidence = script.collect_candidate_depth(
        candidate,
        active,
        account_value_usd=5_000.0,
        maximum_snapshots=240,
        sp500_depth_path=Path("unused.json"),
        sp500_depth_source="live",
    )

    assert ("xyz:SP500", 4_500.0) in observed
    assert evidence["assets"]["xyz:SP500"]["source"] == "bounded_live_l2"
