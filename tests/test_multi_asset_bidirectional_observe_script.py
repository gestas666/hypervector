"""No-submit command-boundary tests for the multi-asset observer."""

from __future__ import annotations

from dataclasses import replace
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd
import pytest

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig

SCRIPT = Path(__file__).parents[1] / "src" / "hypervector" / "operations" / "multi_asset_bidirectional_observe.py"


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
    assert "--resume-run-id" in options
    assert "--enabled" not in options
    assert "--i-accept-live-risk" not in options
    # The deleted-profile default is gone: the observed profile is explicit.
    with pytest.raises(SystemExit) as exc:
        parser.parse_args([])
    assert exc.value.code == 2
    assert parser.parse_args(["--config", "p.toml"]).config == Path("p.toml")


def test_observer_requires_explicit_resume_for_existing_ledger(
    tmp_path: Path,
) -> None:
    """An existing observer ledger must not silently acquire a new run ID."""
    module = _load_module()
    config = _observer_config(module, tmp_path)
    _seed_observer_ledger(module, config, "bidirectional-observe-1")

    with pytest.raises(module.SolLiveLedgerError, match="explicit resume"):
        module._build_observer_ledger(config, None, module.datetime.now(module.UTC))


def test_observer_resume_reuses_exact_existing_run(tmp_path: Path) -> None:
    """A matching frozen observer identity can resume its append-only ledger."""
    module = _load_module()
    config = _observer_config(module, tmp_path)
    run_id = "bidirectional-observe-1"
    _seed_observer_ledger(module, config, run_id)

    ledger = module._build_observer_ledger(
        config,
        run_id,
        module.datetime.now(module.UTC),
    )

    assert ledger.run_id == run_id
    assert ledger.end_cursor().next_sequence == 2


def test_observer_resume_accepts_exact_latest_run_suffix(tmp_path: Path) -> None:
    """Earlier frozen runs may precede the exact latest resumable run."""
    module = _load_module()
    config = _observer_config(module, tmp_path)
    _seed_observer_ledger(module, config, "bidirectional-observe-1")
    _seed_observer_ledger(module, config, "bidirectional-observe-2")

    ledger = module._build_observer_ledger(
        config,
        "bidirectional-observe-2",
        module.datetime.now(module.UTC),
    )

    assert ledger.run_id == "bidirectional-observe-2"
    assert ledger.end_cursor().next_sequence == 3


def test_observer_resume_rejects_mismatched_existing_run(tmp_path: Path) -> None:
    """Resume must fail closed when any persisted run identity differs."""
    module = _load_module()
    config = _observer_config(module, tmp_path)
    _seed_observer_ledger(module, config, "bidirectional-observe-1")

    with pytest.raises(module.SolLiveLedgerError, match="identity mismatch"):
        module._build_observer_ledger(
            config,
            "bidirectional-observe-2",
            module.datetime.now(module.UTC),
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
        "tests/fixtures/profiles/multi_asset_bidirectional_btc_specialists_growth_sizing_candidate_v45.toml",
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
        "tests/fixtures/profiles/index_fresh15_pressure_v2.toml",
        mode="observe",
    )

    poller = module._build_observer_poller(
        config,
        backtest_lab_root=Path("unused"),
        fetch_bars=lambda symbol, timeframe, days, *, end_ms=None: None,
    )

    assert isinstance(poller, module.ConfiguredMultiAssetIntentPoller)


def test_observer_cache_bypasses_completed_bar_profit_lock_symbols() -> None:
    """Observer transport must retain raw polling for lock-sensitive symbols."""
    module = _load_module()
    config = module.load_multi_asset_live_config(
        "tests/fixtures/profiles/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml",
        mode="observe",
    )
    calls: list[str] = []

    def fetch(
        symbol: str,
        timeframe: str,
        lookback_days: float,
        *,
        end_ms: int | None = None,
    ) -> pd.DataFrame:
        del timeframe, lookback_days, end_ms
        calls.append(symbol)
        return pd.DataFrame(
            {
                "timestamp": [pd.Timestamp("2026-08-21T06:00:00Z")],
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.0],
                "volume": [1.0],
            }
        )

    cached = module._observer_candle_fetcher(config, fetch)
    end_ms = int(pd.Timestamp("2026-08-21T06:01:15Z").timestamp() * 1_000)
    for symbol in ("BTC", "xyz:SP500"):
        cached(symbol, "1m", 1.0, end_ms=end_ms)
        cached(symbol, "1m", 1.0, end_ms=end_ms + 10_000)

    assert calls == ["BTC", "xyz:SP500", "xyz:SP500"]


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


def _observer_config(module: ModuleType, tmp_path: Path) -> MultiAssetLiveConfig:
    config = module.load_multi_asset_live_config(
        "configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml",
        mode="observe",
    )
    return module._with_observer_ledger_root(config, tmp_path / "observe" / "observer")


def _seed_observer_ledger(
    module: ModuleType,
    config: MultiAssetLiveConfig,
    run_id: str,
) -> None:
    ledger = module.SolLiveLedger(
        path=config.cohort_ledger,
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id=run_id,
        execution_mode="observe",
    )
    ledger.append(
        event_type="heartbeat",
        observed_at_utc="2026-08-19T00:00:00+00:00",
        live_armed=False,
        execution_authority="none",
        payload={"status": "running"},
    )
