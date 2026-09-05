"""Command contract for V58 BTC development economic materialization."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/v58_btc_liquidation_development_materialize.py")


def _load() -> ModuleType:
    spec = spec_from_file_location(
        "v58_btc_liquidation_development_materialize", _SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load development materialization command")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_defaults_bind_revision_ten_and_development_only_output() -> None:
    """The command consumes the last outcome-unopened input contract."""
    module = _load()

    args = module.build_parser().parse_args([])

    assert args.journal.name.endswith("20260822-v10.json")
    assert args.output.name.endswith("development_economics_20260822_v1")
    assert args.database.name == "market.duckdb"


def test_preregistration_requires_current_matching_results_uninspected_revision() -> (
    None
):
    """A rerun fails closed unless a later immutable revision binds the correction."""
    module = _load()
    valid = {
        "current_revision_id": "b" * 64,
        "execution_authority": "none",
        "revisions": [
            {
                "revision_number": 12,
                "revision_id": "b" * 64,
                "evidence": [{"integrity": "matching"}],
                "metrics": {
                    "stage": "development_materializer_boundary_dedupe_frozen_results_uninspected",
                    "strategy_outcomes_inspected": False,
                    "validation_outcomes_opened": False,
                    "pseudo_holdout_outcomes_opened": False,
                },
            }
        ],
    }

    module.validate_preregistration(valid)
    valid["revisions"][0]["metrics"]["strategy_outcomes_inspected"] = True
    with pytest.raises(ValueError, match="results-uninspected"):
        module.validate_preregistration(valid)
