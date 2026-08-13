"""Command-surface tests for immutable impulse development evidence."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd
import pytest


_SCRIPT = Path("scripts/cross_asset_impulse_development.py")


def _module() -> ModuleType:
    spec = spec_from_file_location("cross_asset_impulse_development", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load impulse script: {_SCRIPT}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _residual_report(path: Path) -> None:
    payload = {
        "schema_version": "cross_asset_residual_exit_surface_v2",
        "trial_count": 90,
        "report_only": True,
        "execution_authority": "none",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _screen_fixture() -> tuple[
    dict[str, pd.DataFrame],
    dict[str, dict[str, object]],
    pd.DataFrame,
    dict[str, object],
]:
    identity = {
        symbol: {
            "bars": {"sha256": symbol.lower(), "bytes": 1},
            "native_rows": 100,
            "gap_fill_rows": 1,
        }
        for symbol in ("BTC", "ETH", "SOL", "HYPE")
    }
    frames = {symbol: pd.DataFrame() for symbol in identity}
    rows = pd.DataFrame(
        {
            "signal_variant": ["primary"],
            "value": [1.0],
            "report_only": [True],
            "execution_authority": ["none"],
        }
    )
    artifact: dict[str, object] = {
        "schema_version": "cross_asset_impulse_development_v1",
        "searched_set_count": 15,
        "report_only": True,
        "execution_authority": "none",
        "source_identity": identity,
        "search_accounting": {
            "within_family_selectable_cells": 15,
            "nonselectable_control_cells": 45,
            "prior_residual_selectable_cells": 90,
            "known_cumulative_selectable_cells": 105,
            "prior_residual_artifact": {},
            "shared_development_window_disclosed": True,
            "project_trial_ledger_complete": False,
            "deflated_sharpe_ratio_computed": False,
        },
    }
    return frames, identity, rows, artifact


def test_parser_freezes_v1_report_only_paths() -> None:
    args = _module().build_parser().parse_args([])

    assert args.data_root == Path("data")
    assert args.run_id == "cross_asset_impulse_development_v1"
    assert args.output == Path(
        "data/logs/research/cross_asset_impulse_development_v1.json"
    )
    assert args.events_output.name.endswith("v1.events.parquet")
    assert args.prior_residual.name == "cross_asset_residual_exit_surface_v2.json"


def test_runner_publishes_sidecar_and_complete_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    output = tmp_path / "result.json"
    events_output = tmp_path / "events.parquet"
    prior = tmp_path / "residual.json"
    _residual_report(prior)
    frames, source_identity, event_rows, artifact = _screen_fixture()
    monkeypatch.setattr(
        module,
        "load_impulse_development_inputs",
        lambda data_root, config: (frames, source_identity),
    )
    observed: dict[str, object] = {}

    def _screen(**kwargs: object) -> tuple[dict[str, object], pd.DataFrame]:
        observed.update(kwargs)
        result = artifact.copy()
        accounting = dict(result["search_accounting"])
        accounting["prior_residual_artifact"] = kwargs["prior_search_identity"]
        result["search_accounting"] = accounting
        return result, event_rows

    monkeypatch.setattr(
        module.impulse_screen,
        "build_impulse_development",
        _screen,
        raising=False,
    )
    validated: list[Path] = []
    monkeypatch.setattr(
        module,
        "validate_cross_asset_impulse_artifact",
        lambda path: validated.append(path),
    )

    module.run_development(
        data_root=tmp_path,
        run_id="fixture",
        output=output,
        events_output=events_output,
        prior_residual=prior,
        runner_path=_SCRIPT,
    )

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["event_storage"]["rows"] == 1
    assert persisted["event_storage"]["sha256"]
    assert persisted["generator_identity"]["generator_modules"]
    assert persisted["prior_cross_asset_search"]["selectable_cells"] == 90
    assert observed["prior_search_identity"] == persisted["prior_cross_asset_search"]
    assert persisted["search_accounting"] == {
        "within_family_selectable_cells": 15,
        "nonselectable_control_cells": 45,
        "prior_residual_selectable_cells": 90,
        "known_cumulative_selectable_cells": 105,
        "prior_residual_artifact": persisted["prior_cross_asset_search"],
        "shared_development_window_disclosed": True,
        "project_trial_ledger_complete": False,
        "deflated_sharpe_ratio_computed": False,
    }
    assert persisted["contract_identity"]["warmup_start_utc"] == (
        "2025-07-20T23:55:00+00:00"
    )
    assert persisted["contract_identity"]["development_end_utc"] == (
        "2026-01-28T00:00:00+00:00"
    )
    assert pd.read_parquet(events_output).equals(event_rows)
    assert validated == [output]


def test_runner_refuses_existing_or_incoherent_evidence(tmp_path: Path) -> None:
    module = _module()
    existing = tmp_path / "existing.json"
    existing.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="immutable impulse output"):
        module._require_new_outputs(existing, tmp_path / "events.parquet")
    with pytest.raises(ValueError, match="searched-set count"):
        module._validate_screen_artifact(
            {
                "schema_version": "cross_asset_impulse_development_v1",
                "searched_set_count": 14,
                "report_only": True,
                "execution_authority": "none",
                "source_identity": {
                    symbol: {"bars": {"sha256": "x"}}
                    for symbol in ("BTC", "ETH", "SOL", "HYPE")
                },
            }
        )


def test_invalid_prior_does_not_publish_a_partial_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    frames, identity, rows, artifact = _screen_fixture()
    prior = tmp_path / "invalid-prior.json"
    prior.write_text("{}", encoding="utf-8")
    events_output = tmp_path / "events.parquet"
    monkeypatch.setattr(
        module,
        "load_impulse_development_inputs",
        lambda data_root, config: (frames, identity),
    )
    monkeypatch.setattr(
        module.impulse_screen,
        "build_impulse_development",
        lambda **kwargs: (artifact.copy(), rows),
        raising=False,
    )

    with pytest.raises(ValueError, match="schema"):
        module.run_development(
            data_root=tmp_path,
            run_id="fixture",
            output=tmp_path / "result.json",
            events_output=events_output,
            prior_residual=prior,
            runner_path=_SCRIPT,
        )
    assert not events_output.exists()


def test_command_surface_has_no_order_credentials_or_arm_flags() -> None:
    source = _SCRIPT.read_text(encoding="utf-8").lower()
    for forbidden in (
        "i-accept-live-risk",
        "private_key",
        "wallet",
        "submit_order",
        "--enabled",
    ):
        assert forbidden not in source
