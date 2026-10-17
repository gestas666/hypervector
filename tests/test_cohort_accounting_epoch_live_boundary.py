"""Live-backend fail-closed tests for the first v49 accounting epoch."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.cohort_live_portfolio_archive import CohortAccountingEpoch

SCRIPT = Path(__file__).parents[1] / "src/hypervector/operations/multi_asset_bidirectional_live.py"
V39 = Path(
    "configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml"
)
V49 = Path("configs/multi_asset_growth_first_5000_repaired_candidate_v49.toml")


def _load() -> ModuleType:
    spec = spec_from_file_location("accounting_epoch_live_boundary", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_live_parser_accepts_an_explicit_accounting_epoch_bundle() -> None:
    module = _load()

    args = module.build_parser().parse_args(
        ["--accounting-epoch-bundle", "data/backups/epoch-v49"]
    )

    assert args.accounting_epoch_bundle == Path("data/backups/epoch-v49")


def test_v49_backend_refuses_to_start_without_the_clean_epoch() -> None:
    module = _load()
    config = load_multi_asset_live_config(V49, mode="observe")
    args = module.build_parser().parse_args(["--config", str(V49)])

    with pytest.raises(ValueError, match="requires --accounting-epoch-bundle"):
        module._accounting_epoch(args, config)


def test_existing_v39_backend_does_not_require_a_new_epoch() -> None:
    module = _load()
    config = load_multi_asset_live_config(V39, mode="observe")
    args = module.build_parser().parse_args(["--config", str(V39)])

    assert module._accounting_epoch(args, config) is None


def test_backend_validates_the_bundle_against_its_loaded_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load()
    config = load_multi_asset_live_config(V49, mode="observe")
    args = module.build_parser().parse_args(
        ["--config", str(V49), "--accounting-epoch-bundle", "epoch-v49"]
    )
    expected = CohortAccountingEpoch("growth_5000_v49", "a" * 64, 1)
    from hypervector.operations import cohort_live_construction

    monkeypatch.setattr(
        cohort_live_construction,
        "load_required_accounting_epoch",
        lambda bundle, successor: expected
        if (bundle, successor) == (Path("epoch-v49"), config)
        else None,
    )

    assert module._accounting_epoch(args, config) == expected
