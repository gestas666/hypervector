"""Command contract for V58 BTC development statistical disposition."""

from __future__ import annotations

from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

from hypervector.research.btc_liquidation_development_statistics import (
    BootstrapEstimate,
)

_SCRIPT = Path("scripts/v58_btc_liquidation_development_disposition.py")


def _load() -> ModuleType:
    spec = spec_from_file_location(
        "v58_btc_liquidation_development_disposition", _SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load development disposition command")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_defaults_bind_raw_development_and_new_immutable_output() -> None:
    """The disposition command cannot point at validation or pseudo-holdout."""
    module = _load()

    args = module.build_parser().parse_args([])

    assert args.raw_bundle.name.endswith("development_economics_20260822_v1")
    assert args.output.name.endswith("development_disposition_20260822_v1")
    assert args.database.name == "market.duckdb"


def test_development_advancement_requires_every_preregistered_criterion() -> None:
    """No diagnostic or single strong metric can rescue a failed primary gate."""
    module = _load()
    summary = {
        "count": 120,
        "mean_nominal_return_bps": Decimal("1.0"),
        "mean_stressed_return_bps": Decimal("0.2"),
        "largest_positive_pnl_contribution": Decimal("0.10"),
    }
    bootstrap = BootstrapEstimate(1.0, 0.2, 1.8, 0.01, 10_000, 7, 20260822)
    months = {
        "2026-01": {"count": 20, "mean_nominal_return_bps": Decimal("0.1")},
        "2026-02": {"count": 19, "mean_nominal_return_bps": Decimal("-0.1")},
    }

    accepted = module.evaluate_development_advancement(
        summary,
        bootstrap,
        holm_adjusted_p_value=0.02,
        months=months,
    )
    summary["mean_stressed_return_bps"] = Decimal("-0.01")
    rejected = module.evaluate_development_advancement(
        summary,
        bootstrap,
        holm_adjusted_p_value=0.02,
        months=months,
    )

    assert accepted["advance_to_validation"] is True
    assert all(accepted["criteria"].values())
    assert rejected["advance_to_validation"] is False
    assert rejected["criteria"]["positive_stressed_mean"] is False
