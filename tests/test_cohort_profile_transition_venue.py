"""Fail-closed startup checks for retained and retired cohort venue state."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from hypervector.live.cohort_transition_drain import CohortTransitionDrainError
from hypervector.live.cohort_profile_transition_venue import (
    require_profile_transition_venue_boundary,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_SCRIPT = Path(__file__).parents[1] / "scripts/multi_asset_bidirectional_live.py"
_V63 = Path(
    "configs/multi_asset_growth_first_5000_nine_asset_bankroll_builder_candidate_v63.toml"
)
_V64 = Path(
    "configs/multi_asset_growth_first_5000_eight_asset_gold_removed_candidate_v64.toml"
)


def test_changed_profile_rejects_retired_gold_venue_exposure() -> None:
    """Removing GOLD from the config cannot hide a live GOLD position or order."""
    live_script = _load_script()
    previous = load_multi_asset_live_config(_V63, mode="observe")
    candidate = load_multi_asset_live_config(
        _V64,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    adapters = SimpleNamespace(
        by_symbol={symbol: _reader() for symbol in candidate.symbols}
    )
    retired = _reader(size=0.2, order_ids=(901,))
    captured: list[tuple[str, ...]] = []

    def retired_reader_factory(symbols: tuple[str, ...]) -> dict[str, Mock]:
        captured.append(symbols)
        return {"xyz:GOLD": retired}

    with pytest.raises(
        CohortTransitionDrainError,
        match="retired asset xyz:GOLD.*not flat and order-free",
    ):
        live_script._verify_profile_transition_venue_boundary(
            candidate,
            SimpleNamespace(strategy_changed=True),
            adapters,
            previous_config=previous,
            retired_reader_factory=retired_reader_factory,
        )

    assert captured == [("xyz:GOLD",)]
    retired.reconcile.assert_called_once_with()


def test_changed_profile_reconciles_retained_and_flat_retired_symbols() -> None:
    """A flat removal checks every candidate adapter and retired reader once."""
    previous = load_multi_asset_live_config(_V63, mode="observe")
    candidate = load_multi_asset_live_config(
        _V64,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    candidate_readers = {symbol: _reader() for symbol in candidate.symbols}
    retired = _reader()

    require_profile_transition_venue_boundary(
        candidate,
        SimpleNamespace(strategy_changed=True),
        SimpleNamespace(by_symbol=candidate_readers),
        previous_config=previous,
        retired_reader_factory=lambda symbols: {symbols[0]: retired},
    )

    assert all(
        reader.reconcile.call_count == 1 for reader in candidate_readers.values()
    )
    retired.reconcile.assert_called_once_with()


def _load_script() -> ModuleType:
    spec = spec_from_file_location("multi_asset_bidirectional_live_venue", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _reader(*, size: float = 0.0, order_ids: tuple[int, ...] = ()) -> Mock:
    return Mock(
        reconcile=Mock(
            return_value=SimpleNamespace(
                position=SimpleNamespace(size_signed=size),
                open_orders=tuple(SimpleNamespace(oid=oid) for oid in order_ids),
            )
        )
    )
