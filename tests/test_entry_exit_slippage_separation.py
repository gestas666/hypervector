"""Regression tests for independent IOC entry and close price protection."""

from __future__ import annotations

from collections.abc import Mapping
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

from hypervector.live.hyperliquid_perp_adapter import HyperliquidPerpAdapter
from hypervector.live.multi_asset_cohort_payloads import asset_config_payload
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.cohort_configuration_generation import (
    configuration_generation_evidence,
    load_configuration_expectation,
)

_ADDRESS = "0x1111111111111111111111111111111111111111"
_ENTRY_CLOID = "0x00000000000000000000000000000001"
_CLOSE_CLOID = "0x00000000000000000000000000000002"
_ALL_ACTIVE = Path("tests/fixtures/profiles/seven_asset_all_active.toml")
_LIVE_SCRIPT = Path("src/hypervector/operations/multi_asset_bidirectional_live.py")


class _Info:
    """Provide the market metadata required to round an IOC order."""

    def meta(self, dex: str = "") -> object:
        """Return one BTC perpetual market."""
        return {"universe": [{"name": "BTC", "szDecimals": 5, "maxLeverage": 40}]}


class _Exchange:
    """Capture market mutations without a network call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, object]]] = []

    def market_open(
        self,
        name: str,
        is_buy: bool,
        sz: float,
        px: float | None = None,
        slippage: float = 0.05,
        cloid: object | None = None,
        builder: object | None = None,
    ) -> object:
        """Record an opening IOC and return one accepted fill."""
        self.calls.append(("entry", {"slippage": slippage}))
        return _accepted(101, sz)

    def market_close(
        self,
        coin: str,
        sz: float | None = None,
        px: float | None = None,
        slippage: float = 0.05,
        cloid: object | None = None,
        builder: object | None = None,
    ) -> object:
        """Record a closing IOC and return one accepted fill."""
        self.calls.append(("close", {"slippage": slippage}))
        return _accepted(102, sz or 0.0)


def test_entry_cap_can_be_tighter_than_close_cap() -> None:
    """Entry containment must not narrow the reduce-only exit envelope."""
    exchange = _Exchange()
    adapter = HyperliquidPerpAdapter(
        info=_Info(),
        exchange=exchange,
        account_address=_ADDRESS,
        symbol="BTC",
        max_notional_usd=500.0,
        slippage_fraction=0.01,
        entry_slippage_fraction=0.002,
    )

    adapter.submit_market_entry(
        side="long",
        requested_notional_usd=100.0,
        mark_price=50_000.0,
        client_order_id=_ENTRY_CLOID,
    )
    adapter.close_position(
        position_size_signed=0.002,
        mark_price=50_100.0,
        client_order_id=_CLOSE_CLOID,
    )

    assert exchange.calls == [
        ("entry", {"slippage": pytest.approx(0.002)}),
        ("close", {"slippage": pytest.approx(0.01)}),
    ]


def test_asset_config_parses_an_explicit_entry_cap(tmp_path: Path) -> None:
    """The tighter entry bound must be an immutable, visible profile setting."""
    config = load_multi_asset_live_config(_split_config(tmp_path), mode="observe")

    assert all(asset.entry_slippage_cap_fraction == 0.002 for asset in config.assets)
    assert all(
        asset.effective_entry_slippage_cap_fraction == 0.002 for asset in config.assets
    )
    assert all(asset.market_slippage_cap_fraction == 0.01 for asset in config.assets)


def test_live_factory_propagates_distinct_entry_and_close_caps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The armed adapter factory must receive both immutable IOC bounds."""
    module = _load_live_script()
    config = load_multi_asset_live_config(
        _split_config(tmp_path),
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    captured: list[object] = []

    def capture(envelopes: tuple[object, ...], **_kwargs: object) -> object:
        captured.extend(envelopes)
        return object()

    monkeypatch.setattr(module, "create_armed_multi_asset_adapters", capture)

    module._create_adapters(config)

    assert len(captured) == 7
    assert all(row.entry_slippage_fraction == 0.002 for row in captured)
    assert all(row.slippage_fraction == 0.01 for row in captured)


def test_identity_payload_exposes_both_ioc_caps(tmp_path: Path) -> None:
    """The backend must publish enough evidence for the TUI to distinguish caps."""
    config = load_multi_asset_live_config(_split_config(tmp_path), mode="observe")

    payload = asset_config_payload(config.assets[0])

    assert payload["entry_slippage_cap_fraction"] == pytest.approx(0.002)
    assert payload["market_slippage_cap_fraction"] == pytest.approx(0.01)


def test_configuration_generation_exposes_pending_entry_and_close_caps(
    tmp_path: Path,
) -> None:
    """Restart evidence must make the independently staged limits inspectable."""
    path = _split_config(tmp_path)
    config = load_multi_asset_live_config(path, mode="observe")
    expectation = load_configuration_expectation(path)

    evidence = configuration_generation_evidence(
        config.profile_fingerprint,
        expectation,
        {},
    )

    assert evidence["current_asset_entry_slippage_caps"] == {
        symbol: pytest.approx(0.002) for symbol in config.symbols
    }
    assert evidence["current_asset_market_slippage_caps"] == {
        symbol: pytest.approx(0.01) for symbol in config.symbols
    }


def _accepted(oid: int, size: float) -> object:
    """Return one official-SDK-shaped accepted fill acknowledgement."""
    return {
        "status": "ok",
        "response": {
            "type": "order",
            "data": {"statuses": [{"filled": {"oid": oid, "totalSz": str(size)}}]},
        },
    }


def _split_config(tmp_path: Path) -> Path:
    """Create one temporary profile with separate entry and close caps."""
    source = _ALL_ACTIVE.read_text(encoding="utf-8")
    source = source.replace(
        'profile = "fixture_seven_asset_all_active"',
        'profile = "entry_slippage_split_test"',
    )
    source = "\n".join(
        (
            "market_slippage_cap_fraction = 0.01\nentry_slippage_cap_fraction = 0.002"
            if line.startswith("market_slippage_cap_fraction = ")
            else line
        )
        for line in source.splitlines()
    )
    path = tmp_path / "split.toml"
    path.write_text(source, encoding="utf-8")
    return path


def _load_live_script() -> ModuleType:
    """Load the live launcher without invoking its command boundary."""
    spec = spec_from_file_location("entry_exit_slippage_live_script", _LIVE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
