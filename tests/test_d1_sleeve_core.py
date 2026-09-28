"""D1 sleeve executor core contracts: pure rules, parsers, journal and planning.

Nothing here touches the network; the shadow ledgers are synthetic.
"""

from __future__ import annotations

import ast
from dataclasses import asdict, fields, replace
from datetime import UTC, date, datetime, timedelta
import math
import os
from pathlib import Path
import socket
import sys

import d1_shadow_runner as runner
import d1_sleeve_core as core
import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[1]
_CORE = _ROOT / "scripts" / "d1_sleeve_core.py"
SHADOW_FP = runner.ShadowConfig().fingerprint()
CFG = core.SleeveConfig()
SUB = "0x" + "b2" * 20


# ----------------------------------------------------------------- fixtures


def _refuse(*args: object, **kwargs: object) -> None:
    raise AssertionError("real network or credential lookup attempted")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test runs with DNS and outbound connections refused."""
    monkeypatch.setattr(socket, "getaddrinfo", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse)


def vtrade(
    coin: str,
    *,
    side: str = "long",
    entry_date: str = "2026-09-20",
    entry_px: float = 100.0,
    atr: float = 2.0,
    taken: bool = True,
    rank: int = 1,
    max_leverage: float = 10.0,
) -> dict:
    d = 1 if side == "long" else -1
    stop = entry_px - d * 2 * atr
    trade = runner.VirtualTrade(
        trade_id=f"{coin}:{side}:{entry_date}",
        coin=coin,
        binance_symbol=runner.binance_symbol_for(coin),
        direction=d,
        signal_date=entry_date,
        entry_date=entry_date,
        entry_px=entry_px,
        stop_px=stop,
        stop_fraction=abs(entry_px - stop) / entry_px,
        atr=atr,
        leverage=3 if d > 0 else 2,
        mmr=1 / (2 * max_leverage),
        max_leverage=max_leverage,
        liq_px=entry_px * 0.7,
        liq_distance=0.28,
        liq_buffer_ok=True,
        taken=taken,
        skip_reason=None if taken else "slots_full",
        risk_usd=24.0 if taken else 0.0,
        want_notional_usd=600.0,
        notional_usd=600.0 if taken else 0.0,
        margin_usd=200.0 if taken else 0.0,
        priority_rank=rank,
        priority_quote_volume_30d=1e9,
        census_rank=rank,
    )
    return asdict(trade)


def pending_order(
    coin: str,
    *,
    signal_date: str,
    exit_direction: int = 0,
    entry_direction: int = 0,
    atr: float | None = 2.0,
) -> dict:
    return asdict(
        runner.PendingOrder(
            coin=coin,
            binance_symbol=runner.binance_symbol_for(coin),
            signal_date=signal_date,
            exit_direction=exit_direction,
            entry_direction=entry_direction,
            atr=atr if entry_direction else None,
            max_leverage=10.0 if entry_direction else None,
            census_rank=1 if entry_direction else None,
            priority_quote_volume_30d=1e9 if entry_direction else None,
        )
    )


class ShadowLedger:
    """Hand-built shadow ledger with the runner's own event and chain code."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.modes: list[str] = []

    def _add(self, event: dict, mode: str) -> dict:
        self.events.append(event)
        self.modes.append(mode)
        return event

    def entry(
        self,
        coin: str,
        day: date,
        *,
        side: str = "long",
        entry_px: float = 100.0,
        atr: float | None = 2.0,
        rank: int = 1,
        taken: bool = True,
        skip_reason: str | None = None,
        mode: str = "daily",
        max_leverage: float = 10.0,
    ) -> dict:
        d = 1 if side == "long" else -1
        trade_id = f"{coin}:{side}:{day.isoformat()}"
        payload: dict = {
            "trade_id": trade_id,
            "coin": coin,
            "binance_symbol": runner.binance_symbol_for(coin),
            "side": side,
            "label": "trend" if d > 0 else "hedge",
            "signal_date": (day - timedelta(days=1)).isoformat(),
            "entry_date": day.isoformat(),
            "entry_px": entry_px,
            "fill_basis": "binance_1d_open",
            "atr_signal": atr,
            "priority_rank": rank,
            "priority_quote_volume_30d": 1e9 / rank,
            "census_rank": rank,
            "taken": taken if skip_reason != "invalid_stop" else False,
            "skip_reason": skip_reason
            if skip_reason
            else (None if taken else "slots_full"),
        }
        if skip_reason != "invalid_stop" and atr:
            payload["stop_px"] = entry_px - d * 2 * atr
            payload["max_leverage"] = max_leverage
        event = runner.make_event("hypothetical_entry", day, trade_id, payload)
        return self._add(event, mode)

    def close(
        self,
        trade_id: str,
        day: date,
        *,
        reason: str = "channel_exit",
        exit_px: float = 101.0,
        net_r: float = 0.5,
        mode: str = "daily",
    ) -> dict:
        kind = (
            "hypothetical_exit" if reason == "channel_exit" else "hypothetical_stop_hit"
        )
        payload = {
            "trade_id": trade_id,
            "coin": trade_id.split(":")[0],
            "exit_reason": reason,
            "exit_px": exit_px,
            "net_r": net_r,
            "taken": True,
        }
        return self._add(runner.make_event(kind, day, trade_id, payload), mode)

    def mark(
        self,
        day: date,
        *,
        trades: list[dict] = (),  # type: ignore[assignment]
        pending: list[dict] = (),  # type: ignore[assignment]
        mode: str = "daily",
        fingerprint: str = SHADOW_FP,
    ) -> dict:
        state = {
            "last_bar_date": day.isoformat(),
            "trades": list(trades),
            "pending": list(pending),
            "realized_net_usd": 0.0,
            "closed_trades": 0,
            "closed_taken_trades": 0,
            "btc_beta_state": None,
            "config": runner.ShadowConfig().as_record(),
            "config_fingerprint": fingerprint,
        }
        event = runner.make_event(
            "daily_mark", day, "mark", {"state": state, "execution_authority": "none"}
        )
        return self._add(event, mode)

    def finalized(self) -> list[dict]:
        chain = runner.CHAIN_GENESIS
        out: list[dict] = []
        for event, mode in zip(self.events, self.modes, strict=True):
            event = dict(event)
            if event["event"] == "daily_mark":
                event["ledger_chain_before"] = chain
                event["content_digest"] = runner.content_digest(event)
            chain = runner._chain_step(chain, event)
            event["recorded_at"] = "2026-09-27T00:10:00+00:00"
            event["mode"] = mode
            out.append(event)
        return out

    def write(self, path: Path) -> list[dict]:
        events = self.finalized()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(runner._canonical(event) + "\n" for event in events))
        assert runner.load_ledger(path) == events
        return events


T = date(2026, 9, 27)
D = T - timedelta(days=1)
NOW = datetime(2026, 9, 27, 0, 15, tzinfo=UTC)


def entry_of(
    coin: str = "BTC",
    *,
    direction: int = 1,
    entry_px: float = 100_000.0,
    atr: float = 2_000.0,
    rank: int = 1,
    max_leverage: float | None = 40.0,
) -> core.VirtualEntry:
    side = "long" if direction > 0 else "short"
    return core.VirtualEntry(
        trade_id=f"{coin}:{side}:{T.isoformat()}",
        coin=coin,
        direction=direction,
        signal_date=D.isoformat(),
        entry_date=T.isoformat(),
        entry_px=entry_px,
        atr_signal=atr,
        priority_rank=rank,
        taken=True,
        skip_reason=None,
        stop_px=entry_px - direction * 2 * atr,
        binance_symbol=runner.binance_symbol_for(coin),
        max_leverage=max_leverage,
    )


def market(
    name: str = "BTC",
    *,
    szd: int = 5,
    max_leverage: float = 40.0,
    delisted: bool = False,
) -> core.MarketInfo:
    return core.MarketInfo(name, 0, szd, max_leverage, delisted, False)


def size(
    entry: core.VirtualEntry,
    mid: float,
    info: core.MarketInfo,
    *,
    book: float = 4800.0,
    gross: float = 0.0,
    slots: int = 0,
    free: float = 2500.0,
    equity: float = 2500.0,
) -> core.EntrySizing:
    return core.size_entry(entry, mid, info, book, gross, slots, free, equity, CFG)


# ----------------------------------------------------------------- config


def test_config_fingerprint_is_stable_and_covers_every_field() -> None:
    assert core.SleeveConfig().fingerprint() == CFG.fingerprint()
    assert len(CFG.fingerprint()) == 16
    seen = {CFG.fingerprint()}
    for item in fields(core.SleeveConfig):
        value = getattr(CFG, item.name)
        if isinstance(value, bool):
            changed = not value
        elif isinstance(value, (int, float)):
            changed = value + 1
        elif isinstance(value, tuple):
            changed = (*value, 999)
        else:
            changed = f"{value}x"
        other = replace(CFG, **{item.name: changed})
        assert other.fingerprint() not in seen, item.name
        seen.add(other.fingerprint())


def test_config_defaults_pin_the_operator_decisions() -> None:
    assert CFG.risk_fraction == 0.01 and CFG.max_slots == 10 and CFG.gross_cap == 1.5
    assert CFG.shadow_runner_sha256 == (
        "3496738ee6e98c8dd54ecb75f933b17aae80c36466b7eef3ca48ed713fba4471"
    )
    assert CFG.shadow_config_fingerprint == SHADOW_FP == "c9ea5f06dd1658e4"
    assert core.HL_URL == "https://api.hyperliquid.xyz"
    names = {f.name for f in fields(core.SleeveConfig)}
    assert not any(
        token in name for name in names for token in ("drawdown", "kill", "pnl", "loss")
    )


def test_default_paths_follow_the_data_layout(tmp_path: Path) -> None:
    paths = core.Paths.default(tmp_path)
    assert paths.journal == tmp_path / "data/live/d1_sleeve/journal.jsonl"
    assert paths.stop_file == tmp_path / "data/live/d1_sleeve/STOP"
    assert paths.lock == tmp_path / "data/live/d1_sleeve/executor.lock"
    assert paths.status == tmp_path / "data/runtime/d1_sleeve/status.json"
    assert paths.alerts == tmp_path / "data/runtime/d1_sleeve/alerts.jsonl"
    assert paths.shadow_ledger == tmp_path / "data/research/d1_shadow/ledger.jsonl"
    assert paths.host_lock("abc") == tmp_path / "host-locks/d1_sleeve.abc.lock"
    default = core.Paths.default()
    assert default.repo_root == core.REPO_ROOT
    # The host lock is shared by every checkout on this machine (not repo-relative).
    assert default.host_lock_dir == Path.home() / ".config" / "hypervector"


# ----------------------------------------------------------------- addresses


def test_addresses_normalise_and_fingerprint_without_echo() -> None:
    upper = "0x" + "AB" * 20
    assert core.normalize_address(f"  {upper} ", "X") == upper.lower()
    for bad in (None, "", "0x1234", "ab" * 20, "0x" + "g" * 40, 42):
        with pytest.raises(core.RefusalError) as info:
            core.normalize_address(bad, "LABEL")
        assert "LABEL" in str(info.value)
        assert "1234" not in str(info.value) and "ggg" not in str(info.value)
    fp = core.address_fp(upper)
    assert fp == core.address_fp(upper.lower()) and len(fp) == 12
    assert fp != core.address_fp(upper, "other_sleeve")


def test_redact_hides_addresses_keys_and_truncates() -> None:
    address = "0x" + "aB" * 20
    key = "0x" + "c" * 64
    text = f"user {address} key {key} bare {'d' * 64} tail"
    out = core.redact(text)
    assert address not in out and key not in out and "d" * 64 not in out
    assert "0x<addr>" in out and out.count("<hex64>") == 2
    assert len(core.redact("x" * 500)) == 200
    assert core.redact("y" * 50, 10) == "y" * 10


# ----------------------------------------------------------------- venue math


@pytest.mark.parametrize(
    ("px", "szd", "expected"),
    [
        (123456.7, 5, 123460.0),
        (96100.0, 5, 96100.0),
        (0.012345678, 0, 0.012346),
        (2345.678, 4, 2345.7),
        (1.23456789, 2, 1.2346),
    ],
)
def test_normalize_price_matches_the_sdk_formula(
    px: float, szd: int, expected: float
) -> None:
    sdk = round(float(f"{px:.5g}"), 6 - szd)
    assert core.normalize_price(px, szd) == sdk == pytest.approx(expected)
    with pytest.raises(core.TechnicalError):
        core.normalize_price(0.0, 2)


def test_round_size_down_and_ioc_limits() -> None:
    assert core.round_size_down(0.012, 5) == 0.012
    assert core.round_size_down(0.0129999, 3) == 0.012
    assert core.round_size_down(60396.0396, 0) == 60396.0
    with pytest.raises(core.TechnicalError):
        core.round_size_down(0.00049, 3)
    with pytest.raises(core.TechnicalError):
        core.round_size_down(-1.0, 3)
    assert core.ioc_limit(100.0, True, 50, 2) == 100.5
    assert core.ioc_limit(100.0, False, 50, 2) == 99.5
    assert core.ioc_limit(100_000.0, True, 100, 5) == 101_000.0


def test_price_units_and_cloids() -> None:
    assert core.price_unit("kPEPE") == 1000.0 and core.price_unit("BTC") == 1.0
    assert core.price_unit("KAITO") == 1.0
    cloid = core.cloid_for(CFG, SUB, "BTC:long:2026-09-27", "entry", 1)
    assert cloid.startswith("0xd15e") and len(cloid) == 34
    int(cloid[2:], 16)
    assert cloid == core.cloid_for(
        CFG, "0x" + SUB[2:].upper(), "BTC:long:2026-09-27", "entry", 1
    )
    others = {
        core.cloid_for(CFG, SUB, "BTC:long:2026-09-27", role, n)
        for role in ("entry", "stop", "exit")
        for n in (1, 2, 3)
    }
    assert len(others) == 9
    assert core.is_owned_cloid(CFG, cloid)
    assert core.is_owned_cloid(CFG, "0x" + cloid[2:].upper())
    assert not core.is_owned_cloid(CFG, "0x" + "1" * 32)
    assert not core.is_owned_cloid(CFG, None)
    with pytest.raises(core.TechnicalError):
        core.cloid_for(CFG, SUB, "x", "transfer", 1)
    from hyperliquid.utils.types import Cloid

    assert Cloid.from_str(cloid).to_raw() == cloid


# ----------------------------------------------------------------- sizing


def test_btc_worked_example() -> None:
    sizing = size(entry_of(), 100_000.0, market())
    assert sizing.take
    assert sizing.risk_usd == pytest.approx(48.0)
    assert sizing.stop_dist == pytest.approx(4000.0)
    assert sizing.stop_fraction == pytest.approx(0.04)
    assert sizing.want == pytest.approx(1200.0)
    assert sizing.mmr == pytest.approx(0.0125)
    assert sizing.leverage == 3 == min(3, math.floor(1 / (0.0125 + 0.1)))
    assert sizing.sz == 0.012 and not sizing.scaled
    assert core.normalize_price(100_100.0 - 1 * sizing.stop_dist, 5) == 96_100.0


def test_kpepe_worked_example_uses_the_1000x_unit() -> None:
    entry = entry_of("kPEPE", entry_px=1.0e-5, atr=4.0e-7, max_leverage=10.0)
    sizing = size(entry, 0.0101, market("kPEPE", szd=0, max_leverage=10.0))
    assert sizing.take and sizing.unit == 1000.0
    assert sizing.stop_dist == pytest.approx(0.0008)
    assert sizing.stop_fraction == pytest.approx(0.0008 / 0.0101)
    assert sizing.stop_fraction == pytest.approx(0.0792, abs=1e-4)
    assert sizing.want == pytest.approx(606.0, abs=0.1)
    assert sizing.leverage == 3
    assert sizing.liq_distance == pytest.approx(1 / 3 - 0.05)
    assert sizing.liq_distance >= 2.5 * sizing.stop_fraction and sizing.buffer_ok
    assert sizing.sz == math.floor(sizing.want / 0.0101)


def test_short_leverage_is_capped_at_two() -> None:
    entry = entry_of("ETH", direction=-1, entry_px=2000.0, atr=40.0)
    sizing = size(entry, 2000.0, market("ETH", szd=4, max_leverage=25.0))
    assert sizing.take and sizing.leverage == 2
    assert sizing.rule_stop == pytest.approx(2080.0)
    long = size(
        entry_of("ETH", entry_px=2000.0, atr=40.0),
        2000.0,
        market("ETH", szd=4, max_leverage=25.0),
    )
    assert long.leverage == 3


def test_venue_max_leverage_sets_the_leverage() -> None:
    entry = entry_of(max_leverage=40.0)
    assert size(entry, 100_000.0, market(max_leverage=2.0)).leverage == 2
    assert size(entry, 100_000.0, market(max_leverage=40.0)).leverage == 3


@pytest.mark.parametrize(
    ("entry", "mid", "info", "reason", "critical"),
    [
        (
            entry_of("PEPE", entry_px=1.0e-5, atr=4e-7),
            0.0101,
            market("PEPE", szd=0),
            "unit_mismatch",
            True,
        ),
        (
            entry_of(entry_px=100.0, atr=2.0),
            95.0,
            market(szd=2),
            "rule_stop_breached",
            False,
        ),
        (entry_of(atr=float("nan")), 100_000.0, market(), "invalid_stop", False),
        (entry_of(atr=0.0), 100_000.0, market(), "invalid_stop", False),
        (
            entry_of(entry_px=100.0, atr=0.1),
            100.0,
            market(szd=2),
            "sizing_sanity",
            True,
        ),
    ],
)
def test_terminal_sizing_skips(
    entry: core.VirtualEntry,
    mid: float,
    info: core.MarketInfo,
    reason: str,
    critical: bool,
) -> None:
    sizing = size(entry, mid, info)
    assert not sizing.take and sizing.reason == reason
    assert sizing.retryable is False and sizing.critical is critical


def test_slots_count_every_sub_position() -> None:
    sizing = size(entry_of(), 100_000.0, market(), slots=10)
    assert sizing.reason == "slots_full" and not sizing.retryable


def test_gross_cap_scales_down_to_a_quarter_then_skips() -> None:
    entry = entry_of()
    scaled = size(entry, 100_000.0, market(), gross=7200.0 - 600.0)
    assert scaled.take and scaled.scaled and scaled.sz == 0.006
    refused = size(entry, 100_000.0, market(), gross=7200.0 - 200.0)
    assert refused.reason == "gross_cap" and not refused.retryable


def test_sub_collateral_is_retryable_with_the_shortfall() -> None:
    sizing = size(entry_of(), 100_000.0, market(), free=150.0, equity=2000.0)
    assert sizing.reason == "sub_collateral" and sizing.retryable
    reserve = 0.05 * 2000.0
    assert sizing.collateral_shortfall_usd == pytest.approx(
        1200.0 / 3 - (150.0 - reserve)
    )


def test_below_min_notional_uses_the_stop_price() -> None:
    entry = entry_of(entry_px=100.0, atr=2.0)
    # want 11.2 at 4%: 0.11 units = $11.00 at the mid but $10.56 at the stop.
    sizing = size(entry, 100.0, market(szd=2), book=44.8)
    assert sizing.want == pytest.approx(11.2)
    assert sizing.reason == "below_min_notional" and not sizing.retryable


# ----------------------------------------------------------------- shadow view


def _base_ledger() -> ShadowLedger:
    ledger = ShadowLedger()
    ledger.entry("AAA", D - timedelta(days=5), rank=1)
    ledger.entry("BBB", D - timedelta(days=5), rank=2, taken=False)
    ledger.entry("CCC", D - timedelta(days=4), rank=1)
    return ledger


def test_view_open_trades_pending_exits_and_todays_entries() -> None:
    ledger = _base_ledger()
    aaa = vtrade("AAA", entry_date=(D - timedelta(days=5)).isoformat())
    bbb = vtrade("BBB", entry_date=(D - timedelta(days=5)).isoformat(), taken=False)
    ccc = vtrade("CCC", entry_date=(D - timedelta(days=4)).isoformat())
    ledger.mark(
        D,
        trades=[aaa, bbb, ccc],
        pending=[
            pending_order("AAA", signal_date=D.isoformat(), exit_direction=1),
            pending_order("EEE", signal_date=D.isoformat(), entry_direction=1),
            pending_order("FFF", signal_date=D.isoformat(), entry_direction=-1),
            pending_order("GGG", signal_date=D.isoformat(), entry_direction=1),
        ],
    )
    ledger.close(ccc["trade_id"], T, reason="gap_stop", exit_px=95.0, net_r=-1.2)
    ledger.entry("FFF", T, side="short", rank=1)
    ledger.entry("EEE", T, rank=2, taken=False)
    ledger.entry("GGG", T, rank=3, skip_reason="invalid_stop", atr=None)
    view = core.build_shadow_view(ledger.finalized(), NOW, CFG)

    assert view.fresh and view.state == "fresh" and view.mark_date == D
    assert view.entries_complete and view.pending_entries == 3
    assert aaa["trade_id"] not in view.open_ids
    assert view.pending_exits == {aaa["trade_id"]: "channel_exit"}
    assert bbb["trade_id"] in view.open_ids
    assert ccc["trade_id"] not in view.open_ids
    assert view.closed_index[ccc["trade_id"]].exit_reason == "gap_stop"
    assert [e.coin for e in view.entries_today] == ["FFF", "EEE"]
    assert (
        view.entries_today[0].direction == -1 and view.entries_today[1].taken is False
    )
    assert "GGG:long:2026-09-27" not in view.open_ids
    assert {"FFF:short:2026-09-27", "EEE:long:2026-09-27"} <= view.open_ids
    assert view.open_virtual == len(view.open_ids)
    assert view.chain_head == runner.ledger_chain(ledger.finalized())


def test_view_is_stale_when_the_mark_is_older_than_yesterday() -> None:
    ledger = ShadowLedger()
    ledger.mark(
        D - timedelta(days=1),
        pending=[
            pending_order(
                "EEE",
                signal_date=(D - timedelta(days=1)).isoformat(),
                entry_direction=1,
            )
        ],
    )
    ledger.entry("EEE", D)
    view = core.build_shadow_view(ledger.finalized(), NOW, CFG)
    assert not view.fresh and view.state == "stale" and view.entries_today == ()
    # The same ledger was fresh on the previous day.
    view = core.build_shadow_view(ledger.finalized(), NOW - timedelta(days=1), CFG)
    assert view.fresh and [e.coin for e in view.entries_today] == ["EEE"]


def test_view_waits_for_the_open_step() -> None:
    ledger = ShadowLedger()
    ledger.mark(
        D,
        pending=[
            pending_order("EEE", signal_date=D.isoformat(), entry_direction=1),
            pending_order("FFF", signal_date=D.isoformat(), entry_direction=1),
        ],
    )
    ledger.entry("EEE", T)
    view = core.build_shadow_view(ledger.finalized(), NOW, CFG)
    assert view.fresh and not view.entries_complete and view.state == "pending"
    assert view.entries_today == ()


def test_backfill_mode_entries_are_never_today_entries() -> None:
    ledger = ShadowLedger()
    ledger.mark(
        D,
        mode="backfill",
        pending=[pending_order("EEE", signal_date=D.isoformat(), entry_direction=1)],
    )
    ledger.entry("EEE", T, mode="backfill")
    view = core.build_shadow_view(ledger.finalized(), NOW, CFG)
    assert view.fresh and view.entries_complete and view.entries_today == ()
    assert "EEE:long:2026-09-27" in view.open_ids


def test_view_refuses_another_shadow_config_and_a_missing_mark() -> None:
    ledger = ShadowLedger()
    ledger.mark(D, fingerprint="0000000000000000")
    with pytest.raises(core.ShadowConfigMismatch):
        core.build_shadow_view(ledger.finalized(), NOW, CFG)
    with pytest.raises(core.ShadowViewError):
        core.build_shadow_view([], NOW, CFG)


def test_view_from_a_real_runner_ledger(tmp_path: Path) -> None:
    breakout = D
    index = pd.date_range(date(2026, 5, 1), breakout + timedelta(days=1), freq="D")
    frame = pd.DataFrame(
        {
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "quote_volume": 1e6,
        },
        index=index,
    )
    frame.loc[pd.Timestamp(breakout), ["open", "high", "low", "close"]] = [
        100.0,
        106.0,
        100.0,
        105.0,
    ]
    frame.loc[pd.Timestamp(T), ["open", "high", "low", "close"]] = [
        105.5,
        106.5,
        104.5,
        106.0,
    ]
    census = tmp_path / "census.csv"
    pd.DataFrame(
        [{"dex": "main", "coin": "AAA", "maxLeverage": 10, "dayNtlVlm": 5e7}]
    ).to_csv(census, index=False)

    def fetch(symbol: str, *, start: date | None, limit: int) -> pd.DataFrame:
        if symbol != "AAAUSDT":
            raise runner.SymbolUnavailableError(symbol)
        return frame.copy()

    ledger = tmp_path / "ledger.jsonl"
    report = runner.run_shadow(
        ledger_path=ledger,
        census_path=census,
        config=runner.ShadowConfig(),
        fetcher=fetch,
        now=datetime(2026, 9, 27, 0, 30, tzinfo=UTC),
    )
    assert report.ok, report.error
    view = core.build_shadow_view(runner.load_ledger(ledger), NOW, CFG)
    (entry,) = view.entries_today
    assert entry.coin == "AAA" and entry.entry_px == 105.5 and entry.direction == 1
    assert entry.atr_signal == pytest.approx(2.2) and entry.taken is True


# ----------------------------------------------------------------- planning


def test_exit_plan_holds_closes_or_flags_unknown() -> None:
    ledger = _base_ledger()
    aaa = vtrade("AAA", entry_date=(D - timedelta(days=5)).isoformat())
    bbb = vtrade("BBB", entry_date=(D - timedelta(days=5)).isoformat())
    ledger.close(
        "CCC:long:" + (D - timedelta(days=4)).isoformat(),
        D - timedelta(days=2),
        reason="stop_intrabar",
        exit_px=96.0,
        net_r=-1.0,
    )
    ledger.mark(
        D,
        trades=[aaa, bbb],
        pending=[pending_order("AAA", signal_date=D.isoformat(), exit_direction=1)],
    )
    view = core.build_shadow_view(ledger.finalized(), NOW, CFG)
    assert core.plan_exit(bbb["trade_id"], view).action == "hold"
    decision = core.plan_exit(aaa["trade_id"], view)
    assert (decision.action, decision.reason) == ("close", "channel_exit")
    assert core.late_exit_days(decision, T) == 0
    stop = core.plan_exit("CCC:long:" + (D - timedelta(days=4)).isoformat(), view)
    assert (stop.action, stop.reason) == ("close", "shadow_stop")
    assert stop.virtual == {
        "exit_reason": "stop_intrabar",
        "exit_px": 96.0,
        "net_r": -1.0,
    }
    assert core.late_exit_days(stop, T) == 2  # hit on the 24th, known on the 25th
    assert core.plan_exit("ZZZ:long:2026-01-01", view).action == "unknown"


def _position(
    coin: str = "BTC", szi: float = 0.012, entry: float = 100_100.0
) -> core.VenuePosition:
    return core.VenuePosition(
        coin, szi, entry, abs(szi) * entry, None, "isolated", 3, 400.0
    )


def _stop(
    oid: int,
    *,
    px: float = 96_100.0,
    sz: float = 0.012,
    is_buy: bool = False,
    coin: str = "BTC",
) -> core.VenueOrder:
    return core.VenueOrder(
        coin, oid, f"0xd15e{oid:028x}", is_buy, sz, True, px, True, "Stop Market", True
    )


def test_protection_plan_covers_every_repair() -> None:
    position, info = _position(), market()
    ok = core.plan_protection(position, 96_100.0, [_stop(7)], 100_000.0, info)
    assert ok.action == "ok" and ok.keep.oid == 7 and ok.cancel == ()
    missing = core.plan_protection(position, 96_100.0, [], 100_000.0, info)
    assert missing.action == "place" and missing.expected_px == 96_100.0
    assert missing.size == 0.012 and missing.is_buy is False
    wrong_size = core.plan_protection(
        position, 96_100.0, [_stop(3, sz=0.02)], 100_000.0, info
    )
    assert wrong_size.action == "place" and [o.oid for o in wrong_size.cancel] == [3]
    wrong_price = core.plan_protection(
        position, 96_100.0, [_stop(4, px=95_000.0)], 100_000.0, info
    )
    assert wrong_price.action == "place" and [o.oid for o in wrong_price.cancel] == [4]
    wrong_side = core.plan_protection(
        position, 96_100.0, [_stop(5, is_buy=True)], 100_000.0, info
    )
    assert wrong_side.action == "place"
    limit_stop = replace(_stop(6), order_type="Stop Limit")
    not_market = core.plan_protection(position, 96_100.0, [limit_stop], 100_000.0, info)
    assert not_market.action == "place" and [o.oid for o in not_market.cancel] == [6]
    no_type = replace(_stop(7), order_type="")  # the field absent: still accepted
    assert core.plan_protection(position, 96_100.0, [no_type], 1e5, info).action == "ok"
    duplicate = core.plan_protection(
        position, 96_100.0, [_stop(9), _stop(8)], 100_000.0, info
    )
    assert duplicate.action == "ok" and duplicate.keep.oid == 8
    assert [o.oid for o in duplicate.cancel] == [9]
    breach = core.plan_protection(position, 96_100.0, [], 96_000.0, info)
    assert breach.action == "breach"
    short = _position(szi=-0.012, entry=100_000.0)
    placed = core.plan_protection(short, 104_000.0, [], 100_000.0, info)
    assert placed.action == "place" and placed.is_buy is True
    assert (
        core.plan_protection(short, 104_000.0, [], 104_500.0, info).action == "breach"
    )
    flat = core.plan_flat_cancels({"BTC": position}, [_stop(1), _stop(2, coin="ETH")])
    assert [o.oid for o in flat] == [2]


def test_stop_coverage_is_one_closing_side_stop_of_the_whole_size() -> None:
    """A2: covered means ONE resting reduce-only stop trigger (not a
    take-profit) on the closing side that closes the whole position, whoever
    placed it (an unowned stop without a cloid counts)."""
    long, szd = _position(), 5
    assert core.stop_covers(long, [_stop(1)], szd)
    unowned = replace(_stop(2, px=90_000.0), cloid=None, has_cloid_field=False)
    assert core.stop_covers(long, [unowned], szd)  # any price, any owner
    assert core.stop_covers(long, [_stop(3, sz=0.0120000001)], szd)  # half a lot
    assert core.stop_covers(long, [_stop(3, sz=0.02)], szd)  # over-covering
    assert not core.stop_covers(long, [_stop(4, sz=0.011)], szd)
    assert not core.stop_covers(long, [_stop(4, sz=0.006), _stop(5, sz=0.006)], szd)
    assert not core.stop_covers(long, [_stop(6, is_buy=True)], szd)  # wrong side
    assert not core.stop_covers(long, [_stop(7, coin="ETH")], szd)
    assert not core.stop_covers(long, [replace(_stop(8), reduce_only=False)], szd)
    assert not core.stop_covers(long, [replace(_stop(8), is_trigger=False)], szd)
    tp = replace(_stop(9, px=110_000.0), order_type="Take Profit Market")
    assert not core.stop_covers(long, [tp], szd)
    assert core.stop_covers(long, [replace(_stop(9), order_type="Stop Limit")], szd)
    short = _position(szi=-0.012)
    assert core.stop_covers(short, [_stop(10, is_buy=True)], szd)
    assert not core.stop_covers(short, [_stop(11)], szd)


def test_guard_stop_price_is_protective_and_inside_the_liquidation() -> None:
    """A2: the guard sits at ``desired`` (the rule stop, or entry -/+ dist),
    moves to mark -/+ dist when the mark is already at or beyond it, and to
    halfway between the liquidation price and the mark when it would sit at
    or beyond the liquidation price; None when no such price exists."""
    long = _position(entry=100_000.0)
    assert core.guard_stop_px(long, 101_000.0, 96_000.0, 4_000.0, 5) == 96_000.0
    assert core.guard_stop_px(long, 95_000.0, 96_000.0, 4_000.0, 5) == 91_000.0
    assert core.guard_stop_px(long, 96_000.0, 96_000.0, 4_000.0, 5) == 92_000.0
    assert core.guard_stop_px(long, None, 96_000.0, 4_000.0, 5) == 96_000.0
    assert core.guard_stop_px(long, 100_000.0, 96_123.456, 4_000.0, 5) == 96_123.0
    liq = replace(long, liquidation_px=97_000.0)  # the stop would be behind it
    assert core.guard_stop_px(liq, 100_000.0, 96_000.0, 4_000.0, 5) == 98_500.0
    assert core.guard_stop_px(liq, 97_000.0, 96_000.0, 4_000.0, 5) is None
    assert core.guard_stop_px(liq, 96_500.0, 96_000.0, 4_000.0, 5) is None
    far = core.guard_stop_px(long, 3_000.0, 96_000.0, 4_000.0, 5)
    assert far is None  # mark - dist is not a price
    short = _position(szi=-0.012, entry=100_000.0)
    assert core.guard_stop_px(short, 99_000.0, 104_000.0, 4_000.0, 5) == 104_000.0
    assert core.guard_stop_px(short, 105_000.0, 104_000.0, 4_000.0, 5) == 109_000.0
    short_liq = replace(short, liquidation_px=103_000.0)
    assert core.guard_stop_px(short_liq, 99_000.0, 104_000.0, 4_000.0, 5) == 101_000.0
    for px in (96_000.0, 91_000.0, 98_500.0):  # every answer is a venue price
        assert px == core.normalize_price(px, 5)
    assert core.GUARD_FALLBACK_FRACTION == 0.15 and "guard" in core.ORDER_ROLES
    cloid = core.cloid_for(
        core.SleeveConfig(), "0x" + "b2" * 20, "guard:AAA", "guard", 1
    )
    assert cloid.startswith("0xd15e") and len(cloid) == 34


# ----------------------------------------------------------------- parsers


def test_account_values_follow_the_abstraction() -> None:
    spot = {"balances": [{"coin": "USDC", "total": "2500.5", "hold": "400.5"}]}
    value = core.parse_account_value("unifiedAccount", {}, spot)
    assert value == core.AccountValue(2500.5, 2100.0)
    with pytest.raises(core.TechnicalError, match="hold exceeds"):
        core.parse_account_value(
            "unifiedAccount",
            {},
            {"balances": [{"coin": "USDC", "total": "1", "hold": "2"}]},
        )
    with pytest.raises(core.TechnicalError, match="exactly one USDC"):
        core.parse_account_value("unifiedAccount", {}, {"balances": []})
    perp = {"marginSummary": {"accountValue": "1000"}, "withdrawable": "750"}
    assert core.parse_account_value("disabled", perp, None) == core.AccountValue(
        1000.0, 750.0
    )
    for mode in ("default", "portfolioMargin", "dexAbstraction"):
        with pytest.raises(core.RefusalError):
            core.parse_account_value(mode, perp, spot)
        with pytest.raises(core.RefusalError):
            core.parse_account_mode(mode)
    assert core.parse_account_mode("unifiedAccount") == "unifiedAccount"


def test_position_and_open_order_parsers() -> None:
    state = {
        "assetPositions": [
            {
                "position": {
                    "coin": "BTC",
                    "szi": "0.012",
                    "entryPx": "100100.0",
                    "positionValue": "1200",
                    "liquidationPx": "70000",
                    "leverage": {"type": "isolated", "value": 3},
                    "marginUsed": "400",
                }
            },
            {
                "position": {
                    "coin": "ETH",
                    "szi": "-0.5",
                    "entryPx": "2000",
                    "positionValue": "1000",
                    "liquidationPx": None,
                    "leverage": {"type": "cross", "value": 5},
                    "marginUsed": "200",
                }
            },
            {
                "position": {
                    "coin": "SOL",
                    "szi": "0",
                    "entryPx": "1",
                    "leverage": {"type": "cross", "value": 1},
                }
            },
        ]
    }
    positions = core.parse_positions(state)
    assert set(positions) == {"BTC", "ETH"}
    assert (
        positions["BTC"].liquidation_px == 70000.0 and positions["BTC"].direction == 1
    )
    assert (
        positions["ETH"].liquidation_px is None
        and positions["ETH"].leverage_type == "cross"
    )
    orders = core.parse_open_orders(
        [
            {
                "coin": "BTC",
                "oid": 11,
                "side": "A",
                "sz": "0.012",
                "origSz": "0.012",
                "isTrigger": True,
                "triggerPx": "96100.0",
                "reduceOnly": True,
                "orderType": "Stop Market",
                "cloid": "0xD15E" + "a" * 28,
            },
            {
                "coin": "ETH",
                "oid": 12,
                "side": "B",
                "sz": "0.2",
                "origSz": "0.5",
                "isTrigger": False,
                "triggerPx": "0.0",
                "reduceOnly": False,
                "orderType": "Limit",
            },
        ]
    )
    assert orders[0].cloid == "0xd15e" + "a" * 28 and orders[0].has_cloid_field
    assert orders[0].trigger_px == 96100.0 and not orders[0].is_buy
    assert orders[1].cloid is None and not orders[1].has_cloid_field
    assert orders[1].sz == 0.5 and orders[1].trigger_px is None and orders[1].is_buy
    with pytest.raises(core.TechnicalError):
        core.parse_positions({"assetPositions": "nope"})


def _ok(*statuses: object) -> dict:
    return {
        "status": "ok",
        "response": {"type": "order", "data": {"statuses": list(statuses)}},
    }


def test_order_ack_parser() -> None:
    (filled,) = core.parse_order_statuses(
        _ok({"filled": {"totalSz": "0.012", "avgPx": "100100", "oid": 5}})
    )
    assert (filled.status, filled.oid, filled.filled_sz, filled.avg_px) == (
        "filled",
        5,
        0.012,
        100100.0,
    )
    (resting,) = core.parse_order_statuses(_ok({"resting": {"oid": 6}}))
    assert resting.status == "resting" and resting.oid == 6
    (no_fill,) = core.parse_order_statuses(
        _ok({"error": "Order could not immediately match against any resting orders."})
    )
    assert no_fill.status == "no_fill"
    (error,) = core.parse_order_statuses(
        _ok({"error": "Insufficient margin 0x" + "a" * 40})
    )
    assert error.status == "error" and "0x<addr>" in error.error
    with pytest.raises(core.TechnicalError):
        core.parse_order_statuses(_ok("waitingForTrigger"))
    (top,) = core.parse_order_statuses(
        {"status": "err", "response": "User or API Wallet does not exist."}
    )
    assert top.status == "error"
    with pytest.raises(core.TechnicalError):
        core.parse_order_statuses({"error": "Could not parse JSON"})
    with pytest.raises(core.TechnicalError):
        core.parse_order_statuses(_ok({"resting": {"oid": 1}}, "waitingForTrigger"))
    assert core.parse_cancel_ack(
        {"status": "ok", "response": {"data": {"statuses": ["success"]}}}
    ) == (True, None)
    ok, err = core.parse_cancel_ack(
        {
            "status": "ok",
            "response": {"data": {"statuses": [{"error": "already canceled"}]}},
        }
    )
    assert not ok and "already canceled" in err
    assert core.parse_leverage_ack(
        {"status": "ok", "response": {"type": "default"}}
    ) == (True, None)
    assert core.parse_leverage_ack({"status": "err", "response": "bad"})[0] is False


def test_grouped_entry_acks_never_let_the_child_make_the_send_ambiguous() -> None:
    """A1: an entry IOC with its stop child (normalTpsl). The parent is parsed
    as strictly as any order; the child is resting (oid when given), error,
    or waiting for anything else (the child rests iff the parent filled)."""
    filled = {"filled": {"totalSz": "12", "avgPx": "100", "oid": 5}}
    parent, child = core.parse_grouped_statuses(_ok(filled, "waitingForTrigger"))
    assert (parent.status, parent.filled_sz, child.status) == (
        "filled",
        12.0,
        "waiting",
    )
    _, child = core.parse_grouped_statuses(_ok(filled, "waitingForFill"))
    assert child.status == "waiting" and child.oid is None
    _, child = core.parse_grouped_statuses(_ok(filled, {"resting": {"oid": 9}}))
    assert (child.status, child.oid) == ("resting", 9)
    _, child = core.parse_grouped_statuses(_ok(filled, {"resting": {}}))
    assert (child.status, child.oid) == ("resting", None)
    _, child = core.parse_grouped_statuses(_ok(filled, {"error": "bad 0x" + "c" * 40}))
    assert child.status == "error" and "0x<addr>" in child.error
    _, child = core.parse_grouped_statuses(_ok(filled, {"surprise": 1}))
    assert child.status == "waiting"
    parent, child = core.parse_grouped_statuses(_ok(filled))  # no child status
    assert parent.status == "filled" and child.status == "waiting"
    parent, child = core.parse_grouped_statuses(
        _ok({"error": "Order could not immediately match. asset=1"}, "waitingForFill")
    )
    assert (parent.status, child.status) == ("no_fill", "waiting")
    parent, child = core.parse_grouped_statuses(
        {"status": "err", "response": "Invalid TP/SL price."}
    )
    assert parent.status == child.status == "error"
    for bad in (
        _ok("waitingForTrigger", "waitingForTrigger"),  # an unknown parent status
        _ok(filled, "waitingForTrigger", "waitingForTrigger"),
        _ok(),
        {"status": "ok"},
        {"status": "weird"},
    ):
        with pytest.raises(core.TechnicalError):
            core.parse_grouped_statuses(bad)


def test_order_status_parser() -> None:
    assert core.parse_order_status({"status": "unknownOid"}).status == "never_landed"
    filled = core.parse_order_status(
        {
            "status": "order",
            "order": {
                "order": {"oid": 9, "sz": "0.0", "origSz": "0.012"},
                "status": "filled",
            },
        }
    )
    assert (filled.status, filled.oid, filled.filled_sz) == ("filled", 9, 0.012)
    partial = core.parse_order_status(
        {
            "status": "order",
            "order": {
                "order": {"oid": 9, "sz": "0.002", "origSz": "0.012"},
                "status": "canceled",
            },
        }
    )
    assert partial.status == "partial" and partial.filled_sz == pytest.approx(0.01)
    rejected = core.parse_order_status(
        {
            "status": "order",
            "order": {
                "order": {"oid": 9, "sz": "0.012", "origSz": "0.012"},
                "status": "marginCanceled",
            },
        }
    )
    assert rejected.status == "canceled" and rejected.venue_status == "marginCanceled"
    unmatched = core.parse_order_status(
        {
            "status": "order",
            "order": {
                "order": {"oid": 9, "sz": "0.012", "origSz": "0.012"},
                "status": "iocCancelRejected",
            },
        }
    )
    # An ambiguous IOC resolved as "found nothing to match" is retried in the
    # same run, exactly like a directly acked no-match.
    assert (
        unmatched.status == "no_fill" and unmatched.venue_status == "iocCancelRejected"
    )


def test_size_remainder_is_exact_and_rounds_down_to_the_lot() -> None:
    assert 0.3 - 0.1 < 0.2  # the float subtraction a partial fill used to take
    assert core.size_remainder(0.3, 0.1, 1) == 0.2
    assert core.size_remainder(12.0, 6.0, 2) == 6.0
    assert core.size_remainder(0.012, 0.00355, 5) == 0.00845
    assert core.size_remainder(1.0, 1.0, 2) == 0.0
    assert core.size_remainder(1.0, 1.5, 2) == 0.0
    for bad in (float("nan"), float("inf")):
        with pytest.raises(core.TechnicalError):
            core.size_remainder(bad, 0.1, 2)
        with pytest.raises(core.TechnicalError):
            core.round_size_down(bad, 2)


def test_a_cancel_of_an_order_that_no_longer_rests_is_recognised() -> None:
    gone = {
        "status": "ok",
        "response": {
            "type": "cancel",
            "data": {
                "statuses": [
                    {"error": "Order was never placed, already canceled, or filled."}
                ]
            },
        },
    }
    ok, error = core.parse_cancel_ack(gone)
    assert not ok and core.cancel_target_gone(error)
    assert not core.cancel_target_gone("rate limited")
    assert not core.cancel_target_gone(None)


def test_agent_and_sub_account_parsers() -> None:
    agent = "0x" + "c3" * 20
    agents = core.parse_extra_agents(
        [
            {
                "name": "d1-sleeve valid_until 1790000000000",
                "address": agent.upper().replace("0X", "0x"),
                "validUntil": 1790000000000,
            },
            {
                "name": "hl-api",
                "address": "0x" + "d4" * 20,
                "validUntil": 1780000000000,
            },
            {"name": "junk", "address": "nope"},
        ]
    )
    assert [(a.base_name, a.address) for a in agents] == [
        ("d1-sleeve", agent),
        ("hl-api", "0x" + "d4" * 20),
    ]
    assert core.parse_sub_accounts(None) == []
    master = "0x" + "a1" * 20
    assert core.parse_sub_accounts(
        [
            {
                "name": "d1",
                "subAccountUser": SUB.upper().replace("0X", "0x"),
                "master": master,
            }
        ]
    ) == [(SUB, master)]


# ----------------------------------------------------------------- journal


def _journal(
    tmp_path: Path, payloads: list[tuple[str, dict]], run_id: str = "r1"
) -> Path:
    path = tmp_path / "journal.jsonl"
    events = core.load_journal(path)
    chain = core.journal_chain(events)
    for seq, (kind, payload) in enumerate(payloads, start=1):
        body = dict(payload)
        if kind == "run_end":
            body["journal_chain_before"] = chain
        event = core.make_journal_event(
            run_id, seq, kind, body, "2026-09-27T00:15:00+00:00"
        )
        core.append_journal(path, [event])
        chain = core.journal_step(chain, event)
    return path


def _intent(
    cloid: str, role: str, trade_id: str, n: int, coin: str = "BTC", **context: object
) -> tuple[str, dict]:
    return (
        "intent",
        {
            "action": "order",
            "cloid": cloid,
            "role": role,
            "trade_id": trade_id,
            "coin": coin,
            "is_buy": True,
            "sz": 0.012,
            "limit_px": 1.0,
            "trigger_px": None,
            "reduce_only": role != "entry",
            "tif": "Ioc",
            "n": n,
            "expires_after_ms": 1,
            "context": dict(context),
        },
    )


def test_journal_digest_chain_and_book(tmp_path: Path) -> None:
    tid = "BTC:long:2026-09-27"
    path = _journal(
        tmp_path,
        [
            ("run_start", {"mode": "armed", "cmd": "run"}),
            _intent("0xd15e01", "entry", tid, 1, d=1, stop_dist=4000.0),
            ("outcome", {"action": "order", "cloid": "0xd15e01", "status": "no_fill"}),
            _intent("0xd15e02", "entry", tid, 2, d=1, stop_dist=4000.0),
            (
                "outcome",
                {
                    "action": "order",
                    "cloid": "0xd15e02",
                    "status": "filled",
                    "oid": 77,
                    "filled_sz": 0.012,
                },
            ),
            (
                "trade_opened",
                {
                    "trade_id": tid,
                    "coin": "BTC",
                    "direction": 1,
                    "sz": 0.012,
                    "entry_px": 100100.0,
                    "stop_px": 96100.0,
                    "stop_dist": 4000.0,
                },
            ),
            _intent("0xd15e03", "stop", tid, 1),
            (
                "outcome",
                {
                    "action": "order",
                    "cloid": "0xd15e03",
                    "status": "resting",
                    "oid": 78,
                },
            ),
            (
                "skip",
                {
                    "trade_id": "ETH:long:2026-09-27",
                    "coin": "ETH",
                    "reason": "slots_full",
                    "retryable": False,
                },
            ),
            (
                "skip",
                {
                    "trade_id": "SOL:long:2026-09-27",
                    "coin": "SOL",
                    "reason": "sub_collateral",
                    "retryable": True,
                },
            ),
            _intent("0xd15e04", "entry", "DOGE:long:2026-09-27", 1, coin="DOGE", d=1),
            ("run_end", {"status": "ok"}),
        ],
    )
    events = core.load_journal(path)
    assert [e["seq"] for e in events] == list(range(1, 13))
    assert all(e["content_digest"] == core.journal_digest(e) for e in events)
    assert events[-1]["journal_chain_before"] == core.journal_chain(events[:-1])
    book = core.derive_book(events)
    assert (
        set(book.open_trades) == {"BTC"} and book.open_trades["BTC"].stop_px == 96100.0
    )
    assert book.attempts[(tid, "entry")] == 2 and book.stop_version(tid) == 1
    assert book.terminal_skips == {"ETH:long:2026-09-27": "slots_full"}
    assert book.last_skip["SOL:long:2026-09-27"] == "sub_collateral"
    assert book.known_oids[77] == (tid, "entry") and book.known_oids[78] == (
        tid,
        "stop",
    )
    assert book.stop_oids[tid] == {78}
    assert set(book.unresolved) == {"0xd15e04"} and book.unresolved_coins() == {"DOGE"}
    assert set(book.pending_opens()) == {"DOGE"}
    assert book.open_run_start is None and book.last_run_end["status"] == "ok"
    closed = _journal(
        tmp_path,
        [("trade_closed", {"trade_id": tid, "coin": "BTC", "reason": "channel_exit"})],
        run_id="r2",
    )
    book = core.derive_book(core.load_journal(closed))
    assert book.open_trades == {} and tid in book.closed_ids


def test_book_tracks_canary_residue(tmp_path: Path) -> None:
    canary = "canary:BTC:2026-09-27"
    filled = {"action": "order", "cloid": "0xd15e11", "status": "filled", "oid": 5}
    kind, intent = _intent("0xd15e11", "canary_entry", canary, 1)
    path = _journal(
        tmp_path,
        [
            ("run_start", {"mode": "armed", "cmd": "canary"}),
            (kind, {**intent, "kind": "canary"}),
            ("outcome", {**filled, "kind": "canary"}),
        ],
    )
    book = core.derive_book(core.load_journal(path))
    assert set(book.canary_residue()) == {"BTC"}  # killed before canary_result
    assert book.pending_opens() == {}  # a canary is never a sleeve trade
    result = {"kind": "canary", "coin": "BTC", "checks": {}, "numbers": {}}
    left = _journal(tmp_path, [("canary_result", {**result, "residue": True})], "r2")
    assert set(core.derive_book(core.load_journal(left)).canary_residue()) == {"BTC"}
    done = _journal(tmp_path, [("canary_result", {**result, "residue": False})], "r3")
    assert core.derive_book(core.load_journal(done)).canary_residue() == {}


def test_book_tracks_the_sized_entry_and_growth_raised_once_per_size(
    tmp_path: Path,
) -> None:
    """sized_entry: the largest size any sleeve entry attempt of the trade was
    sized for (canaries and other roles excluded). position_grew keeps the
    largest venue size already raised as entry_overfill after the open."""
    tid = "BTC:long:2026-09-27"
    kind, canary = _intent("0xd15e24", "entry", tid, 3, sizing_sz=9.0)
    path = _journal(
        tmp_path,
        [
            _intent("0xd15e21", "entry", tid, 1, sizing_sz=0.012),
            _intent("0xd15e22", "entry", tid, 2, sizing_sz=0.013),
            _intent("0xd15e23", "stop", tid, 1, sizing_sz=5.0),
            (kind, {**canary, "kind": "canary"}),
            _intent("0xd15e25", "entry", "ETH:long:2026-09-27", 1, sizing_sz=2.0),
            ("position_grew", {"trade_id": tid, "coin": "BTC", "sz": 0.024}),
            ("position_grew", {"trade_id": tid, "coin": "BTC", "sz": 0.020}),
        ],
    )
    book = core.derive_book(core.load_journal(path))
    assert book.sized_entry(tid) == 0.013
    assert book.sized_entry("SOL:long:2026-09-27") is None
    assert book.grown_sz == {tid: 0.024}
    assert "position_grew" in core.JOURNAL_EVENTS


def test_journal_refuses_a_torn_tail_an_edit_and_a_deleted_line(tmp_path: Path) -> None:
    path = _journal(
        tmp_path,
        [
            ("run_start", {"mode": "armed"}),
            (
                "skip",
                {
                    "trade_id": "X",
                    "coin": "X",
                    "reason": "slots_full",
                    "retryable": False,
                },
            ),
            ("run_end", {"status": "ok"}),
        ],
    )
    good = path.read_bytes()
    path.write_bytes(good + b'{"schema":"d1_sleeve_journal_v1","ev')
    with pytest.raises(
        core.JournalError, match=f"truncate the file to {len(good)} bytes"
    ):
        core.load_journal(path)
    os.truncate(path, len(good))
    assert len(core.load_journal(path)) == 3
    path.write_text(good.decode().replace("slots_full", "gross_cap"))
    with pytest.raises(core.JournalError, match="does not match its digest"):
        core.load_journal(path)
    lines = good.decode().splitlines(keepends=True)
    path.write_text(lines[0] + lines[2])
    with pytest.raises(core.JournalError, match="breaks the chain"):
        core.load_journal(path)


# ----------------------------------------------------------------- static


def test_core_is_pure() -> None:
    source = _CORE.read_text()
    tree = ast.parse(source)
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    assert roots - stdlib == {"d1_shadow_runner"}, roots - stdlib
    assert roots.isdisjoint({"subprocess", "socket", "requests", "urllib", "http"})
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "os":
                assert node.attr == "fsync", node.attr
        if isinstance(node, ast.Name):
            assert node.id not in {"__import__", "eval", "exec", "compile"}
    for token in ("hyperliquid.exchange", "eth_account", "os.environ", "getenv"):
        assert token not in source
