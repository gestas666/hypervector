"""Live-backend fail-closed tests for a declared clean accounting epoch."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

from hypervector.live import cohort_accounting_rollover
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.cohort_live_portfolio_archive import CohortAccountingEpoch

SCRIPT = Path(__file__).parents[1] / "src/hypervector/operations/multi_asset_bidirectional_live.py"
PRIOR = Path("tests/fixtures/profiles/ten_asset_base.toml")
SUCCESSOR = Path("tests/fixtures/profiles/four_asset_mixed_sides.toml")


def _load() -> ModuleType:
    spec = spec_from_file_location("accounting_epoch_live_boundary", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_live_parser_accepts_an_explicit_accounting_epoch_bundle() -> None:
    module = _load()

    # --config is required (an armed start never falls back to a default profile).
    args = module.build_parser().parse_args(
        [
            "--config",
            str(SUCCESSOR),
            "--accounting-epoch-bundle",
            "data/backups/epoch-clean",
        ]
    )

    assert args.accounting_epoch_bundle == Path("data/backups/epoch-clean")


def test_declared_backend_refuses_to_start_without_the_clean_epoch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load()
    config = load_multi_asset_live_config(SUCCESSOR, mode="observe")
    monkeypatch.setattr(
        cohort_accounting_rollover,
        "_CLEAN_ACCOUNTING_REQUIRED_PROFILE_FINGERPRINTS",
        frozenset({config.profile_fingerprint}),
    )
    args = module.build_parser().parse_args(["--config", str(SUCCESSOR)])

    with pytest.raises(ValueError, match="requires --accounting-epoch-bundle"):
        module._accounting_epoch(args, config)


def test_existing_backend_does_not_require_a_new_epoch() -> None:
    module = _load()
    config = load_multi_asset_live_config(PRIOR, mode="observe")
    args = module.build_parser().parse_args(["--config", str(PRIOR)])

    assert module._accounting_epoch(args, config) is None


def test_backend_validates_the_bundle_against_its_loaded_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load()
    config = load_multi_asset_live_config(SUCCESSOR, mode="observe")
    args = module.build_parser().parse_args(
        ["--config", str(SUCCESSOR), "--accounting-epoch-bundle", "epoch-clean"]
    )
    expected = CohortAccountingEpoch("fixture_epoch_2", "a" * 64, 1)
    from hypervector.operations import cohort_live_construction

    monkeypatch.setattr(
        cohort_live_construction,
        "load_required_accounting_epoch",
        lambda bundle, successor: expected
        if (bundle, successor) == (Path("epoch-clean"), config)
        else None,
    )

    assert module._accounting_epoch(args, config) == expected
