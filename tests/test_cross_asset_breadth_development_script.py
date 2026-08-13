"""Command-surface tests for immutable breadth development evidence."""

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest

_SCRIPT = Path("scripts/cross_asset_breadth_development.py")


def _module() -> ModuleType:
    spec = spec_from_file_location("cross_asset_breadth_development", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load breadth script: {_SCRIPT}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parser_freezes_report_only_paths() -> None:
    args = _module().build_parser().parse_args([])

    assert args.data_root == Path("data")
    assert args.run_id == "cross_asset_breadth_development_v1"
    assert args.output.name == "cross_asset_breadth_development_v1.json"
    assert args.events_output.name.endswith("v1.events.parquet")
    assert args.prior_impulse.name == "cross_asset_impulse_development_v1.json"


def test_runner_publishes_source_bound_report_only_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    output = tmp_path / "report.json"
    events = tmp_path / "events.parquet"
    source = {
        symbol: {
            "bars_path": f"data/cache/{symbol}.parquet",
            "bars": {"sha256": symbol},
        }
        for symbol in ("BTC", "ETH", "SOL", "HYPE")
    }
    rows = pd.DataFrame(
        {"report_only": [True], "execution_authority": ["none"], "value": [1.0]}
    )
    artifact: dict[str, object] = {
        "schema_version": "cross_asset_breadth_development_v1",
        "report_only": True,
        "execution_authority": "none",
        "searched_set_count": 1,
        "source_identity": source,
    }
    prior = {"artifact": "prior.json", "sha256": "prior", "selectable_cells": 105}
    monkeypatch.setattr(module, "build_prior_impulse_identity", lambda path: prior)
    monkeypatch.setattr(
        module,
        "load_breadth_development_inputs",
        lambda data_root, config: SimpleNamespace(
            closes_15m=pd.DataFrame(),
            validity_15m=pd.DataFrame(),
            minute_frames={"BTC": pd.DataFrame()},
            source_identity=source,
        ),
    )
    monkeypatch.setattr(
        module, "build_breadth_development", lambda **kwargs: (artifact.copy(), rows)
    )
    monkeypatch.setattr(
        module,
        "build_breadth_generator_identity",
        lambda path: {
            "generator_modules": {str(path): {"sha256": "runner", "bytes": 1}}
        },
    )
    validated: list[Path] = []
    monkeypatch.setattr(
        module, "validate_cross_asset_breadth_artifact", validated.append
    )

    module.run_development(
        data_root=tmp_path,
        run_id="fixture",
        output=output,
        events_output=events,
        prior_impulse=tmp_path / "prior.json",
        runner_path=_SCRIPT,
    )

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["event_storage"]["rows"] == 1
    assert persisted["event_storage"]["sha256"]
    assert persisted["prior_cross_asset_search"] == prior
    assert persisted["contract_identity"]["execution_authority"] == "none"
    assert pd.read_parquet(events).equals(rows)
    assert validated == [output]


def test_runner_refuses_existing_evidence_before_loading_sources(
    tmp_path: Path,
) -> None:
    module = _module()
    existing = tmp_path / "existing.json"
    existing.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="immutable breadth output"):
        module._require_new_outputs(existing, tmp_path / "events.parquet")


def test_command_surface_has_no_credentials_orders_or_arm_flags() -> None:
    source = _SCRIPT.read_text(encoding="utf-8").lower()
    for forbidden in (
        "i-accept-live-risk",
        "private_key",
        "wallet",
        "submit_order",
        "--enabled",
    ):
        assert forbidden not in source
