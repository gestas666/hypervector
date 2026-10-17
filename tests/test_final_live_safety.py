"""Final live-safety review regressions.

Covers the generic ``live run`` daemon's shared-account ownership, its exit-code
contract, intent-failure handling and float-residue closes, and the observer
checkpoint's refusal to overwrite the live checkpoint. Every venue interaction
is an in-process fake; nothing opens a socket, loads a real key or touches the
repository's ``data/`` tree.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from test_fix_live_generic import (
    ENTER_SHORT,
    FakeBuilder,
    FakeExchange,
    FakeInfo,
    KEY,
    ScriptedFeed,
    ScriptedIntents,
    SimVenueTransport,
    WALLET,
    _bars,
    _daemon,
    _patch_intents,
    _rows,
    _statuses,
    _write_export,
)

OBSERVER_SCRIPT = (
    Path(__file__).parents[1]
    / "src"
    / "hypervector"
    / "operations"
    / "multi_asset_bidirectional_observer_checkpoint.py"
)


@pytest.fixture(autouse=True)
def account_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the canonical shared-account root away from the checkout."""
    root = tmp_path / "account-live"
    monkeypatch.setattr("hypervector.live.runner.canonical_live_root", lambda: root)
    return root


# --------------------------------------------------------------------------- #
# Finding 1: the generic daemon owns the shared live account
# --------------------------------------------------------------------------- #


def test_daemon_refuses_while_the_cohort_owns_the_shared_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, account_root: Path
) -> None:
    from hypervector.runtime_lock import (
        RuntimeLockError,
        bidirectional_live_runtime_lock,
    )

    _patch_intents(monkeypatch, ScriptedIntents(default=ENTER_SHORT))
    venue = SimVenueTransport()
    cohort_ledger = account_root / "bidirectional_cohort" / "decisions.jsonl"
    with bidirectional_live_runtime_lock(cohort_ledger):
        with pytest.raises(RuntimeLockError):
            _daemon(
                tmp_path,
                transport=venue,
                warm=_bars("2026-01-01 00:00", 120),
                poll_fn=ScriptedFeed(_bars("2026-01-01 02:00", 2)),
                max_live_bars=1,
            )
    assert venue.calls == []
    assert venue.position_reads == 0


def test_daemon_lock_ignores_the_honored_data_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, account_root: Path
) -> None:
    """--data-root moves the ledger, never the shared-account lock."""
    from hypervector.runtime_lock import RuntimeLockError, _shared_live_account_lock

    _patch_intents(monkeypatch, ScriptedIntents(default=ENTER_SHORT))
    venue = SimVenueTransport()
    assert account_root != tmp_path / "data" / "live"
    with _shared_live_account_lock(account_root):
        with pytest.raises(RuntimeLockError):
            _daemon(
                tmp_path,
                transport=venue,
                warm=_bars("2026-01-01 00:00", 120),
                poll_fn=ScriptedFeed(_bars("2026-01-01 02:00", 2)),
                max_live_bars=1,
            )
    assert venue.calls == []


def test_daemon_holds_the_shared_account_for_its_whole_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, account_root: Path
) -> None:
    from hypervector.runtime_lock import (
        RuntimeLockError,
        bidirectional_live_runtime_lock,
    )

    cohort_ledger = account_root / "bidirectional_cohort" / "decisions.jsonl"
    refusals: list[str] = []

    class ProbingVenue(SimVenueTransport):
        def place_market(self, **kwargs: Any) -> dict[str, Any]:
            try:
                with bidirectional_live_runtime_lock(cohort_ledger):
                    pass
            except RuntimeLockError as exc:
                refusals.append(str(exc))
            return super().place_market(**kwargs)

    _patch_intents(monkeypatch, ScriptedIntents(default=ENTER_SHORT))
    venue = ProbingVenue()
    result = _daemon(
        tmp_path,
        transport=venue,
        warm=_bars("2026-01-01 00:00", 120),
        poll_fn=ScriptedFeed(_bars("2026-01-01 02:00", 2)),
        max_live_bars=1,
    )
    assert result.places_count == 1
    assert len(refusals) == 1
    # Released once the daemon stopped: the cohort can start again.
    with bidirectional_live_runtime_lock(cohort_ledger):
        pass


def test_every_live_backend_refuses_while_the_generic_daemon_runs(
    tmp_path: Path,
) -> None:
    from hypervector import runtime_lock

    live_root = tmp_path / "live"
    backends = (
        runtime_lock.bidirectional_live_runtime_lock,
        runtime_lock.sol_live_runtime_lock,
        runtime_lock.source_follow_live_runtime_lock,
        runtime_lock.apex_mm_live_runtime_lock,
        runtime_lock.hulk_smash_live_runtime_lock,
    )
    with runtime_lock.generic_live_runtime_lock(live_root) as lock_path:
        assert lock_path == live_root / "generic_live" / "process.lock"
        for backend in backends:
            ledger = live_root / f"owner_{backend.__name__}" / "decisions.jsonl"
            with pytest.raises(runtime_lock.RuntimeLockError):
                with backend(ledger):
                    pass
    # The generic owner is named even if only its process lock is held.
    with runtime_lock._runtime_lock(
        live_root / "generic_live" / "process.lock", "generic live daemon"
    ):
        ledger = live_root / "bidirectional_cohort" / "decisions.jsonl"
        with pytest.raises(runtime_lock.RuntimeLockError, match="generic live"):
            with runtime_lock.bidirectional_live_runtime_lock(ledger):
                pass


def test_generic_lock_refuses_every_other_live_owner(tmp_path: Path) -> None:
    from hypervector import runtime_lock

    live_root = tmp_path / "live"
    owners = (
        "bidirectional_cohort",
        "hulk_smash",
        "sol_range_onset_canary",
        "apex_regime_mm",
        "hypervelocity_source_follow",
    )
    for owner in owners:
        with runtime_lock._runtime_lock(live_root / owner / "process.lock", owner):
            with pytest.raises(runtime_lock.RuntimeLockError):
                with runtime_lock.generic_live_runtime_lock(live_root):
                    pass


def test_canonical_live_root_is_the_cohort_launchd_root() -> None:
    """The generic lock lands where the supervised cohort keeps its locks."""
    from hypervector.runtime_lock import canonical_live_root
    from hypervector_supervision.cohort_supervisor_models import SupervisorPaths

    assert canonical_live_root() == SupervisorPaths().process_lock.parent.parent


# --------------------------------------------------------------------------- #
# Finding 5: refusals before any side effect exit 2
# --------------------------------------------------------------------------- #


def _forbid_daemon(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(**_kwargs: Any) -> Any:
        raise AssertionError("start_live_daemon must not be reached")

    monkeypatch.setattr("hypervector.live.runner.start_live_daemon", refuse)


@pytest.mark.parametrize(
    "flags",
    [(), ("--enabled",), ("--i-accept-live-risk",)],
)
def test_live_run_missing_authority_flags_is_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys, flags: tuple[str, ...]
) -> None:
    from hypervector.cli import main

    _forbid_daemon(monkeypatch)
    monkeypatch.setenv("HYPERVECTOR_HL_WALLET_ADDRESS", WALLET)
    monkeypatch.setenv("HYPERVECTOR_HL_API_PRIVATE_KEY", KEY)
    export = tmp_path / "export"
    export.mkdir()
    rc = main(
        ["--data-root", str(tmp_path / "data"), "live", "run", "--export", str(export)]
        + list(flags)
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "--enabled" in err and "--i-accept-live-risk" in err
    assert KEY not in err


def test_live_run_missing_secrets_is_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    from hypervector.cli import main

    _forbid_daemon(monkeypatch)
    monkeypatch.delenv("HYPERVECTOR_HL_WALLET_ADDRESS", raising=False)
    monkeypatch.delenv("HYPERVECTOR_HL_API_PRIVATE_KEY", raising=False)
    export = tmp_path / "export"
    export.mkdir()
    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "live",
            "run",
            "--export",
            str(export),
            "--enabled",
            "--i-accept-live-risk",
        ]
    )
    assert rc == 2
    assert "live run refused" in capsys.readouterr().err


def test_live_run_missing_export_is_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    from hypervector.cli import main

    _forbid_daemon(monkeypatch)
    monkeypatch.setenv("HYPERVECTOR_HL_WALLET_ADDRESS", WALLET)
    monkeypatch.setenv("HYPERVECTOR_HL_API_PRIVATE_KEY", KEY)
    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "live",
            "run",
            "--export",
            str(tmp_path / "missing"),
            "--enabled",
            "--i-accept-live-risk",
        ]
    )
    assert rc == 2
    assert "export path not found" in capsys.readouterr().err


def test_live_run_account_lock_conflict_is_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    from hypervector.cli import main
    from hypervector.runtime_lock import RuntimeLockError

    def locked(**_kwargs: Any) -> Any:
        raise RuntimeLockError("shared live account already running (pid=1)")

    monkeypatch.setattr("hypervector.live.runner.start_live_daemon", locked)
    monkeypatch.setenv("HYPERVECTOR_HL_WALLET_ADDRESS", WALLET)
    monkeypatch.setenv("HYPERVECTOR_HL_API_PRIVATE_KEY", KEY)
    export = tmp_path / "export"
    export.mkdir()
    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "live",
            "run",
            "--export",
            str(export),
            "--enabled",
            "--i-accept-live-risk",
        ]
    )
    assert rc == 2
    assert "shared live account" in capsys.readouterr().err


def test_live_run_failure_after_start_stays_exit_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    from hypervector.cli import main

    def failed(**_kwargs: Any) -> Any:
        raise RuntimeError("venue position read failed")

    monkeypatch.setattr("hypervector.live.runner.start_live_daemon", failed)
    monkeypatch.setenv("HYPERVECTOR_HL_WALLET_ADDRESS", WALLET)
    monkeypatch.setenv("HYPERVECTOR_HL_API_PRIVATE_KEY", KEY)
    export = tmp_path / "export"
    export.mkdir()
    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "live",
            "run",
            "--export",
            str(export),
            "--enabled",
            "--i-accept-live-risk",
        ]
    )
    assert rc == 1
    assert "live run failed" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# Finding 4: an armed-phase strategy failure stops the daemon and is recorded
# --------------------------------------------------------------------------- #


def test_armed_intent_failure_stops_the_daemon_and_is_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hypervector.live.exec_client import HyperliquidLiveExecClient
    from hypervector.live.session import LiveIntentError

    calls = {"n": 0}

    def intents(df: pd.DataFrame, strategy_name: str, params: dict[str, Any]):
        calls["n"] += 1
        if calls["n"] == 1:
            return ENTER_SHORT
        raise ValueError("regime bar OHLC bounds are inconsistent")

    monkeypatch.setattr("hypervector.live.session.last_bar_intent", intents)
    cancels: list[dict[str, Any]] = []
    original_cancel = HyperliquidLiveExecClient.cancel_all

    def recording_cancel(self: Any, *args: Any, **kwargs: Any) -> Any:
        cancels.append(dict(kwargs))
        return original_cancel(self, *args, **kwargs)

    monkeypatch.setattr(HyperliquidLiveExecClient, "cancel_all", recording_cancel)
    venue = SimVenueTransport()
    with pytest.raises(LiveIntentError, match="OHLC bounds"):
        _daemon(
            tmp_path,
            transport=venue,
            warm=_bars("2026-01-01 00:00", 120),
            poll_fn=ScriptedFeed(
                *[_bars(f"2026-01-01 02:{m:02d}", 1) for m in range(4)]
            ),
            max_live_bars=4,
        )
    assert calls["n"] == 2  # stopped at the first failure, not after four bars
    assert len(venue.calls) == 1
    assert cancels == [{"symbol": "BTC"}]
    rows = _rows(tmp_path / "data" / "live" / "decisions" / "decisions.jsonl")
    errors = [row for row in rows if row.get("action") == "intent_error"]
    assert len(errors) == 1
    assert "OHLC bounds" in errors[0]["error"]
    assert errors[0]["position_qty"] == pytest.approx(venue.net["BTC"])
    assert errors[0]["live_phase"] is True
    assert errors[0]["submitted"] is False


def test_unarmed_intent_failure_does_not_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without execution authority a strategy failure only skips the bar."""
    from hypervector.live.session import LiveSession

    def broken(*_args: Any, **_kwargs: Any) -> Any:
        raise ValueError("builder failed")

    monkeypatch.setattr("hypervector.live.session.last_bar_intent", broken)
    session = LiveSession(
        export_dir=_write_export(tmp_path),
        data_root=tmp_path / "data",
        client=None,  # type: ignore[arg-type]
        place_enabled=False,
    )
    assert session.process_frame(_bars("2026-01-01 00:00", 5)) == 5
    assert session.engine.position.qty == 0.0


def test_daemon_result_reports_the_final_position(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hypervector.commands.live import _live_result

    _patch_intents(monkeypatch, ScriptedIntents(default=ENTER_SHORT))
    venue = SimVenueTransport()
    result = _daemon(
        tmp_path,
        transport=venue,
        warm=_bars("2026-01-01 00:00", 120),
        poll_fn=ScriptedFeed(_bars("2026-01-01 02:00", 2)),
        max_live_bars=1,
    )
    assert result.position_qty == pytest.approx(venue.net["BTC"])
    assert result.position_qty < 0.0
    report = _live_result(result, _policy_for_report())
    assert report["position_qty"] == pytest.approx(result.position_qty)


def _policy_for_report() -> Any:
    from hypervector.live.policy import LivePolicy

    return LivePolicy(
        enabled=True, armed=True, secrets_present=True, max_notional_usd=50.0
    )


# --------------------------------------------------------------------------- #
# Finding 3: a partial close never strands a one-lot float residue
# --------------------------------------------------------------------------- #


class PartialFillExchange(FakeExchange):
    """Venue that fills each order up to a planned size and tracks the net."""

    def __init__(self, info: "TrackingInfo") -> None:
        super().__init__()
        self.info = info
        self.fill_plan: list[float] = []

    def order(self, name: str, is_buy: bool, sz: float, *args: Any, **kwargs: Any):
        super().order(name, is_buy, sz, *args, **kwargs)
        filled = min(self.fill_plan.pop(0), sz) if self.fill_plan else sz
        self.info.net = round(self.info.net + (filled if is_buy else -filled), 8)
        fill = {"totalSz": repr(filled), "avgPx": "150.0", "oid": 1}
        return _statuses({"filled": fill})


class TrackingInfo(FakeInfo):
    def __init__(self) -> None:
        super().__init__(
            metas={"": {"universe": [{"name": "SOL", "szDecimals": 2}]}},
            mids={"": {"SOL": "150.0"}},
        )
        self.net = 0.0

    def user_state(self, address: str, dex: str = "") -> dict[str, Any]:
        position = {"coin": "SOL", "szi": repr(self.net)}
        return {"assetPositions": [{"position": position}]}


def test_partial_close_then_close_sends_the_exact_venue_size(tmp_path: Path) -> None:
    from hypervector.live.engine import LiveFillEngine
    from hypervector.live.exec_client import (
        HyperliquidLiveExecClient,
        _SdkPlaceTransport,
    )
    from hypervector.paper.costs import CostProvider

    info = TrackingInfo()
    exchange = PartialFillExchange(info)
    client = HyperliquidLiveExecClient(
        wallet_address=WALLET,
        private_key=KEY,
        transport=_SdkPlaceTransport(sdk_builder=FakeBuilder(info, exchange)),
        max_notional_usd=50.0,
    )
    engine = LiveFillEngine(
        tmp_path,
        cost_provider=CostProvider(
            fee_tier=0, slippage_bps=0.0, funding_rate_hourly=0.0
        ),
        run_id="r",
        export_id="e",
        strategy_name="s",
        symbol="SOL",
        timeframe="1m",
        conviction=0.5,
        client=client,
        place_enabled=True,
        max_notional_usd=50.0,
    )

    def close(ts: str) -> dict[str, Any]:
        return engine.apply_market_fill(
            feed_ts=ts,
            action="close",
            side="sell",
            qty=abs(engine.position.qty),
            mark_px=150.0,
            reduce_only=True,
        )

    engine.apply_market_fill(
        feed_ts="t1", action="enter_long", side="buy", qty=0.3, mark_px=150.0
    )
    exchange.fill_plan = [0.1]  # the IOC close only partially fills
    close("t2")
    assert engine.position.qty == 0.2
    assert info.net == 0.2
    record = close("t3")
    assert record["submitted"] is True
    assert exchange.orders[-1]["sz"] == 0.2
    assert exchange.orders[-1]["reduce_only"] is True
    assert info.net == 0.0
    assert engine.position.qty == 0.0
    assert engine.position.avg_px == 0.0


def test_reconciliation_snaps_engine_float_residue_to_the_venue(
    tmp_path: Path,
) -> None:
    from hypervector.live.engine import LiveFillEngine
    from hypervector.live.exec_client import HyperliquidLiveExecClient
    from hypervector.paper.costs import CostProvider

    class PartialVenue(SimVenueTransport):
        def __init__(self) -> None:
            super().__init__()
            self.plan: list[float] = []

        def place_market(self, **kwargs: Any) -> dict[str, Any]:
            if self.plan:
                kwargs["sz"] = self.plan.pop(0)
            return super().place_market(**kwargs)

        def position(self, **kwargs: Any) -> float:
            return round(super().position(**kwargs), 8)

    venue = PartialVenue()
    client = HyperliquidLiveExecClient(
        wallet_address=WALLET, private_key=KEY, transport=venue, max_notional_usd=50.0
    )
    engine = LiveFillEngine(
        tmp_path,
        cost_provider=CostProvider(
            fee_tier=0, slippage_bps=0.0, funding_rate_hourly=0.0
        ),
        run_id="r",
        export_id="e",
        strategy_name="s",
        symbol="BTC",
        timeframe="1m",
        conviction=0.5,
        client=client,
        place_enabled=True,
        max_notional_usd=50.0,
    )
    engine.apply_market_fill(
        feed_ts="t1", action="enter_short", side="sell", qty=0.0003, mark_px=40_000.0
    )
    venue.plan = [0.0001]
    engine.apply_market_fill(
        feed_ts="t2",
        action="close",
        side="buy",
        qty=0.0003,
        mark_px=40_000.0,
        reduce_only=True,
    )
    assert 0.0003 - 0.0001 != 0.0002  # the float residue this guards against
    assert engine.position.qty == -0.0002


# --------------------------------------------------------------------------- #
# Finding 2: the observer never overwrites the live checkpoint
# --------------------------------------------------------------------------- #


def _observer_module() -> Any:
    from importlib.util import module_from_spec, spec_from_file_location
    import sys

    spec = spec_from_file_location("final_observer_checkpoint", OBSERVER_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_LIVE_DOCUMENT = {
    "mode": "multi_asset_bidirectional_live_checkpoint",
    "protection_warnings": ["LIVE"],
}


def test_observer_refuses_the_live_checkpoint_directory_without_a_writer(
    tmp_path: Path, capsys
) -> None:
    module = _observer_module()
    live = tmp_path / "data/runtime/bidirectional_cohort/latest_checkpoint.json"
    live.parent.mkdir(parents=True)
    live.write_text(json.dumps(_LIVE_DOCUMENT), encoding="utf-8")
    before = live.read_bytes()
    decisions = str(tmp_path / "missing.jsonl")
    assert module.main(["--decisions", decisions, "--out", str(live), "--once"]) == 2
    assert live.read_bytes() == before
    assert "live checkpoint" in capsys.readouterr().err
    # A fresh file in that directory is refused too, whatever its name.
    other = live.parent / "observer.json"
    assert module.main(["--decisions", decisions, "--out", str(other), "--once"]) == 2
    assert not other.exists()


def test_observer_refuses_the_canonical_live_checkpoint_path() -> None:
    from hypervector_supervision.cohort_supervisor_models import SupervisorPaths

    module = _observer_module()
    assert module.refuse_live_checkpoint_output(SupervisorPaths().checkpoint)
    assert module.refuse_live_checkpoint_output(
        SupervisorPaths().checkpoint.parent / "anything.json"
    )


def test_observer_refuses_to_replace_a_foreign_document(tmp_path: Path) -> None:
    module = _observer_module()
    output = tmp_path / "custom" / "latest.json"
    output.parent.mkdir(parents=True)
    output.write_text(json.dumps(_LIVE_DOCUMENT), encoding="utf-8")
    before = output.read_bytes()
    argv = ["--decisions", str(tmp_path / "missing.jsonl"), "--out", str(output)]
    assert module.main([*argv, "--once"]) == 2
    assert output.read_bytes() == before
    output.write_text("{not json", encoding="utf-8")
    assert module.main([*argv, "--once"]) == 2
    assert output.read_text(encoding="utf-8") == "{not json"


def test_observer_replaces_its_own_previous_document(tmp_path: Path) -> None:
    from hypervector.research.cohort_observer_checkpoint import (
        publish_unavailable_observer_checkpoint,
    )

    module = _observer_module()
    output = tmp_path / "observer" / "latest.json"
    publish_unavailable_observer_checkpoint(output, "earlier")
    published: list[Path] = []

    def publish(_ledger: Path, out: Path, *, run_id: str | None) -> dict[str, object]:
        published.append(out)
        return {}

    args = module.build_parser().parse_args(["--out", str(output), "--once"])
    assert module.run_checkpoint_loop(args, publish_fn=publish) == 0
    assert published == [output]


def test_observer_owns_its_output_while_publishing(tmp_path: Path) -> None:
    """A writer that starts later cannot race the observer's publication."""
    from hypervector.runtime_lock import (
        RuntimeLockError,
        cohort_checkpoint_runtime_lock,
    )

    module = _observer_module()
    output = tmp_path / "observer" / "latest.json"
    refusals: list[str] = []

    def publish(_ledger: Path, out: Path, *, run_id: str | None) -> dict[str, object]:
        try:
            with cohort_checkpoint_runtime_lock(out):
                pass
        except RuntimeLockError as exc:
            refusals.append(str(exc))
        return {}

    args = module.build_parser().parse_args(["--out", str(output), "--once"])
    assert module.run_checkpoint_loop(args, publish_fn=publish) == 0
    assert len(refusals) == 1
    with cohort_checkpoint_runtime_lock(output):
        pass  # released after the loop ended


def test_a_second_observer_on_the_same_output_is_refused(
    tmp_path: Path, capsys
) -> None:
    from hypervector.runtime_lock import cohort_checkpoint_runtime_lock

    module = _observer_module()
    output = tmp_path / "observer" / "latest.json"
    published: list[Path] = []

    def publish(_ledger: Path, out: Path, *, run_id: str | None) -> dict[str, object]:
        published.append(out)
        return {}

    args = module.build_parser().parse_args(["--out", str(output), "--once"])
    with cohort_checkpoint_runtime_lock(output):
        assert module.run_checkpoint_loop(args, publish_fn=publish) == 2
    assert published == []
    assert "refused" in capsys.readouterr().err
