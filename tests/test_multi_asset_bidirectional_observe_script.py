"""No-submit command-boundary tests for the multi-asset observer."""

from __future__ import annotations

from dataclasses import replace
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "multi_asset_bidirectional_observe.py"


def _load_module() -> ModuleType:
    spec = spec_from_file_location("multi_asset_bidirectional_observe", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_observer_command_exposes_no_live_authority_flags() -> None:
    """The observer CLI cannot be armed through an accidental flag."""
    module = _load_module()
    parser = module.build_parser()
    options = {option for action in parser._actions for option in action.option_strings}

    assert "--max-polls" in options
    assert "--ledger-root" in options
    assert "--enabled" not in options
    assert "--i-accept-live-risk" not in options
    assert parser.parse_args([]).config == Path(
        "configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml"
    )


def test_observer_script_imports_no_order_client_factory() -> None:
    """Static command assembly excludes private-account and order construction."""
    source = SCRIPT.read_text(encoding="utf-8")

    assert "create_armed_multi_asset_adapters" not in source
    assert "credential_presence_from_env" not in source
    assert "exec_client" not in source
    assert "order_submission" not in source


def test_observer_loads_every_configured_perp_namespace() -> None:
    """HIP-3 books must use the same exact namespace metadata as live."""
    source = SCRIPT.read_text(encoding="utf-8")

    assert "configured_perp_dexes(config.symbols)" in source


def test_observer_ledger_override_rebinds_every_output(tmp_path: Path) -> None:
    """A parity observer must not append any row to the armed live root."""
    module = _load_module()
    config = module.load_multi_asset_live_config(
        "configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml",
        mode="observe",
    )

    isolated = module._with_observer_ledger_root(config, tmp_path / "parity")

    assert isolated.cohort_ledger == tmp_path / "parity" / "decisions.jsonl"
    assert isolated.stop_file == tmp_path / "parity" / "STOP"
    assert {asset.live_ledger for asset in isolated.assets} == {
        tmp_path / "parity" / f"{symbol.lower()}.jsonl" for symbol in isolated.symbols
    }
    assert isolated.mode == "observe"
    assert isolated.enabled is False
    assert isolated.accepts_live_risk is False


def test_observer_rebinding_changes_only_storage_identity(tmp_path: Path) -> None:
    """A different fingerprint must not conceal a different strategy contract."""
    module = _load_module()
    config = module.load_multi_asset_live_config(
        "configs/multi_asset_bidirectional_btc_specialists_growth_sizing_candidate_v45.toml",
        mode="observe",
    )

    isolated = module._with_observer_ledger_root(config, tmp_path / "v45-observer")

    assert isolated.profile_id == config.profile_id
    assert isolated.profile_fingerprint != config.profile_fingerprint
    assert isolated.providers == config.providers
    assert (
        tuple(
            replace(
                asset,
                live_ledger=source.live_ledger,
            )
            for asset, source in zip(isolated.assets, config.assets, strict=True)
        )
        == config.assets
    )
    assert (
        replace(
            isolated,
            cohort_ledger=config.cohort_ledger,
            stop_file=config.stop_file,
            assets=config.assets,
        )
        == config
    )


def test_observer_ledger_override_refuses_configured_root() -> None:
    """An explicit override cannot alias the source profile's live ledgers."""
    module = _load_module()
    config = module.load_multi_asset_live_config(
        "configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml",
        mode="observe",
    )

    with pytest.raises(ValueError, match="must differ"):
        module._with_observer_ledger_root(config, config.cohort_ledger.parent)


def test_observer_builds_hip3_only_poller_without_fake_core_route() -> None:
    """A HIP-3 study must not need an unrelated core strategy provider."""
    module = _load_module()
    config = module.load_multi_asset_live_config(
        "configs/observers/index_fresh15_pressure_v2.toml",
        mode="observe",
    )

    poller = module._build_observer_poller(
        config,
        backtest_lab_root=Path("unused"),
        fetch_bars=lambda symbol, timeframe, days, *, end_ms=None: None,
    )

    assert isinstance(poller, module.ConfiguredMultiAssetIntentPoller)


@pytest.mark.parametrize("root", [Path("/"), Path.home(), Path.cwd()])
def test_observer_ledger_override_refuses_broad_roots(root: Path) -> None:
    """Observer output cannot target a system, home, or workspace root."""
    module = _load_module()
    config = module.load_multi_asset_live_config(
        "configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml",
        mode="observe",
    )

    with pytest.raises(ValueError, match="unsafe broad observer ledger root"):
        module._with_observer_ledger_root(config, root)
