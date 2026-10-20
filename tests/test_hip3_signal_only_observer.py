"""An explicit signal-only candidate cannot depend on unused one-minute research."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.live.cohort_pressure_dependencies import pressure_dependency_commands
from hypervector.live.hip3_breakout_shadow_specs import SPCX_SHADOW_SPEC
from hypervector.live.hip3_breakout_shadow_observer import (
    ObserverDefaults,
    build_parser,
    config_from_args,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_market_bars import TransientCohortMarketDataError
from hypervector.live.mu_hip3_breakout_shadow_runner import (
    MuHip3BreakoutShadowRunner,
    MuHip3ShadowPaths,
)
from hypervector.paper.book import BookSnapshot
from test_mu_hip3_breakout_shadow_runner import _bars, _book

_OBSERVED = int(pd.Timestamp("2026-08-09T22:00:01Z").timestamp() * 1000)
_FIXTURE_PROFILES = Path("tests/fixtures/profiles")


class _LaggingAuxiliarySource:
    """Expose valid fifteen-minute candles and an unavailable auxiliary minute."""

    def __init__(self) -> None:
        self.timeframes: list[str] = []

    def book_snapshot(self) -> BookSnapshot:
        """Return an unsigned book with exact route identity."""
        return replace(_book(_OBSERVED - 100, _OBSERVED - 50), symbol="xyz:SPCX")

    def completed_candle_history(
        self, *, observed_at_ms: int, timeframe: str = "15m"
    ) -> pd.DataFrame:
        """Make the known auxiliary failure distinct from signal-source health."""
        self.timeframes.append(timeframe)
        if timeframe == "1m":
            raise TransientCohortMarketDataError(
                source="hyperliquid_public_candleSnapshot_1m",
                reason="latest_completed_minute_unavailable",
            )
        frame = _bars(40)
        frame.attrs["received_at_ms"] = observed_at_ms
        return frame


def _paths(root: Path) -> MuHip3ShadowPaths:
    return MuHip3ShadowPaths(
        root / "xyz:spcx.jsonl",
        root / "cohort.jsonl",
        root / "cursor.json",
        root / "journal.jsonl",
        root / "status.json",
    )


def test_explicit_signal_only_mode_keeps_primary_source_available(
    tmp_path: Path,
) -> None:
    """A missing auxiliary minute cannot prevent a valid signal-only bootstrap."""
    source = _LaggingAuxiliarySource()
    paths = _paths(tmp_path)
    runner = MuHip3BreakoutShadowRunner(
        source=source,
        paths=paths,
        spec=SPCX_SHADOW_SPEC,
        capture_profit_lock_candles=False,
    )
    result = runner.poll(observed_at_ms=_OBSERVED)
    assert result.bootstrap and not result.intents
    assert source.timeframes == ["15m"]
    status = json.loads(paths.status.read_text())
    assert status["profit_lock_capture_enabled"] is False
    assert status["signing_client_constructed"] is False


def test_legacy_default_preserves_auxiliary_capture_requirement(tmp_path: Path) -> None:
    """Existing index observer launches retain their explicitly captured exit data."""
    source = _LaggingAuxiliarySource()
    runner = MuHip3BreakoutShadowRunner(
        source=source, paths=_paths(tmp_path), spec=SPCX_SHADOW_SPEC
    )
    with pytest.raises(TransientCohortMarketDataError, match="latest_completed_minute"):
        runner.poll(observed_at_ms=_OBSERVED)
    assert source.timeframes == ["1m"]


def test_only_signal_only_candidate_removes_unused_spcx_auxiliary_dependency() -> None:
    """The proposed deployment declares the reduced source dependency explicitly."""
    names = (
        "seven_asset_failed_routes_retired",
        "seven_asset_sndk_durable_onset",
    )
    commands = [
        pressure_dependency_commands(
            load_multi_asset_live_config(
                _FIXTURE_PROFILES / f"{name}.toml", mode="observe"
            )
        )["xyz:SPCX"]
        for name in names
    ]
    assert "--signal-only" not in commands[0]
    assert "--signal-only" in commands[1]


def test_signal_only_cli_declares_disabled_auxiliary_capture(tmp_path: Path) -> None:
    """The standalone observer CLI carries the source choice into its configuration."""
    paths = _paths(tmp_path)
    defaults = ObserverDefaults(
        paths.asset_ledger,
        paths.cohort_ledger,
        paths.cursor,
        paths.journal,
        paths.status,
    )
    args = build_parser(defaults).parse_args(["--signal-only"])
    assert config_from_args(args).capture_profit_lock_candles is False


def test_configured_profit_lock_keeps_its_auxiliary_dependency() -> None:
    """A future exit policy cannot silently lose the minute source it consumes."""
    config = load_multi_asset_live_config(
        _FIXTURE_PROFILES
        / "seven_asset_sndk_durable_onset.toml",
        mode="observe",
    )
    providers = tuple(
        replace(
            p,
            execution=replace(
                p.execution,
                profit_lock_policy="completed_bar_trailing",
                profit_lock_activation_bps=100.0,
                profit_lock_floor_bps=40.0,
                profit_lock_giveback_bps=80.0,
            ),
        )
        if "xyz:SPCX" in p.execution_symbols
        else p
        for p in config.providers
    )
    commands = pressure_dependency_commands(replace(config, providers=providers))
    assert "--signal-only" not in commands["xyz:SPCX"]


@pytest.mark.parametrize("candidate,active_capture", [(True, True), (False, False)])
def test_dependency_reuse_rejects_wrong_capture_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    candidate: bool,
    active_capture: bool,
) -> None:
    """A healthy observer with a different source contract cannot be reused."""
    from hypervector.live import cohort_pressure_dependencies as dependencies
    from hypervector.live.hip3_fresh15_journal_contracts import DEFAULT_OBSERVER_STATES

    name = (
        "seven_asset_sndk_durable_onset"
        if candidate
        else "seven_asset_failed_routes_retired"
    )
    config = load_multi_asset_live_config(
        _FIXTURE_PROFILES / f"{name}.toml", mode="observe"
    )
    monkeypatch.chdir(tmp_path)
    path = DEFAULT_OBSERVER_STATES["xyz:SPCX"][0]
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"profit_lock_capture_enabled": active_capture}))
    monkeypatch.setattr(dependencies, "require_fresh_index_observer", lambda *a: None)
    with pytest.raises(ValueError, match="capture mode"):
        dependencies._require_symbol_health("xyz:SPCX", config)
