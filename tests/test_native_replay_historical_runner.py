"""Continuous completed-candle acquisition through the real seven-asset runner."""

from decimal import Decimal
import json
from pathlib import Path

from test_native_replay_adapter import deny_external_ports
from test_native_replay_sdk_engines import cohort_sdk

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.native_replay_historical_fetch import (
    HistoricalCandleSource,
    HistoricalFetchReceipt,
    HistoricalNativeFetch,
)
from hypervector.research.native_replay_runner import build_native_replay_runner
from hypervector.research.native_runner_recorded_fetch import _load_packet

__all__ = ["deny_external_ports"]
INPUTS = Path(__file__).parent / "fixtures/native_runner_cold_warm_20260911"
MINUTE_MS = 60_000
FETCH_MS = 17
POLLS = 8


def _sources() -> tuple[int, dict[str, HistoricalCandleSource], dict[str, int]]:
    """Use hash-verified captured bars as a declared control, excluding its forming candle."""
    manifest = json.loads((INPUTS / "manifest.json").read_text())
    checksum = next(r["sha256"] for r in manifest["files"] if r["relative"] == "profile_cold.json")
    packet = _load_packet(INPUTS / "profile_cold.json", checksum)
    start = packet.cutoff_ms - 2 * MINUTE_MS
    sources, spans = {}, {}
    for symbol, frame in packet.frames.items():
        first = int(frame.timestamp.iloc[0].timestamp() * 1000)
        assert int(frame.timestamp.iloc[-1].timestamp() * 1000) == packet.cutoff_ms
        complete = frame.iloc[:-1].copy()
        sources[symbol] = HistoricalCandleSource(
            f"captured-control:{checksum}:{symbol}", first, packet.cutoff_ms, complete
        )
        spans[symbol] = start - first
    return start, sources, spans


def test_continuous_fetch_drives_actual_runner_and_events_inside_acquisition(
    tmp_path: Path,
) -> None:
    """Eight native polls retain every acquisition cutoff while processing an intervening mark."""
    config = load_multi_asset_live_config(
        "configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    replay = cohort_sdk(config, {})
    start, sources, spans = _sources()
    replay.advance_to(start)
    receipts: list[HistoricalFetchReceipt] = []
    fetch = HistoricalNativeFetch(
        clock=replay.runtime_clock,
        sources=sources,
        cold_span_ms=spans,
        elapsed_ms=lambda symbol, cold: FETCH_MS,
        record_request=receipts.append,
    )
    event_at = start + 2 * FETCH_MS + 1
    replay.schedule(
        event_at,
        "mark-during-third-source-request",
        lambda sdk: sdk.observe_prices(
            "BTC", source_time_ms=sdk.clock.now_ms, mark=Decimal(101), mid=Decimal(101)
        ),
    )
    native = build_native_replay_runner(
        config=config, replay=replay, fetch_bars=fetch, output_root=tmp_path / "run"
    )
    assert native.runner.run(max_polls=POLLS) == POLLS
    assert len(receipts) == POLLS * len(config.symbols)
    for index, receipt in enumerate(receipts):
        poll, asset = divmod(index, len(config.symbols))
        assert receipt.cutoff_ms == start + poll * int(config.poll_seconds * 1000)
        assert receipt.dispatched_ms == receipt.cutoff_ms + asset * FETCH_MS
        assert receipt.received_ms == receipt.dispatched_ms + FETCH_MS
        assert receipt.symbol == config.symbols[asset] and receipt.cold == (poll == 0)
    assert replay.account.snapshot().mark_prices["BTC"] == Decimal(101)
    assert (
        not replay.orders and not replay.fill_rows and replay.account.snapshot().equity_usd == 5000
    )
    rows = native.cohort_ledger.read_all()
    snapshots = [row["payload"] for row in rows if row["event_type"] == "cohort_snapshot"]
    assert len(snapshots) >= POLLS
    assert all([a["symbol"] for a in s["assets"]] == list(config.symbols) for s in snapshots)
