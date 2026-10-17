"""Run explicit captured native poll packets with an inspectable offline SDK scenario.

Packet gaps are not continuous historical polling. Economic inputs remain
declared assumptions; authenticated execution depth does not prove queue priority.
"""

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from decimal import Decimal
from functools import lru_cache, partial
from hashlib import sha256
import json
from pathlib import Path

from hypervector.data.oxa_history import (
    DEFAULT_BOOK_MAX_PAGES,
    OxaBookRequest,
    output_directory,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.native_replay_book_source import (
    AuthenticatedBookBundle,
    RecordedBookUnavailable,
    authenticate_book_bundle,
)
from hypervector.research.native_replay_clock import EPOCH, ReplayClock
from hypervector.research.native_replay_depth import RecordedBook
from hypervector.research.native_replay_events import require_clock
from hypervector.research.native_replay_runner import build_native_replay_runner
from hypervector.research.native_replay_sdk import ReplaySdk, ReplaySdkTiming
from hypervector.research.native_replay_unified import MaintenanceTier
from hypervector.research.native_runner_recorded_fetch import RecordedRunnerFetch


def run_packet_scenario(scenario: Path, output: Path) -> dict[str, object]:
    """Authenticate configuration/packets and retain native telemetry without live clients."""
    raw = scenario.read_bytes()
    body = _mapping(json.loads(raw))
    if (
        body.get("schema") != "native-packet-replay-v1"
        or body.get("economic_inputs") != "declared_scenario"
    ):
        raise ValueError(
            "native packet replay requires an explicitly declared v1 economic scenario"
        )
    packets = _rows(body["packets"])
    if not packets:
        raise ValueError("native packet replay requires at least one source packet")
    config_path = _verified_path(body["config"])
    config = load_multi_asset_live_config(
        config_path, mode="live", enabled=True, accepts_live_risk=True
    )
    replay = _sdk(body, config.symbols)
    fetch = RecordedRunnerFetch(replay.runtime_clock)
    native = build_native_replay_runner(
        config=config,
        replay=replay,
        fetch_bars=fetch,
        output_root=output,
        finish_poll=fetch.finish_poll,
    )
    actions = []
    for index, row in enumerate(packets):
        path = _verified_path(row)
        packet = _mapping(json.loads(path.read_bytes()))
        cutoff = _utc_ms(packet["observed_cutoff_utc"])
        replay.advance_to(cutoff)
        fetch.load_packet(path, _text(_mapping(row)["sha256"]))
        if index == 0:
            native.runner.start(activation_time_ms=cutoff)
        actions.append(native.runner.poll_once())
    result = _report(replay, actions, fetch.completed_packets)
    result.update(
        scenario_sha256=sha256(raw).hexdigest(),
        config_sha256=sha256(config_path.read_bytes()).hexdigest(),
    )
    with (output / "run_report.json").open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
    return result


def _report(replay: ReplaySdk, actions: list[int], packets: int) -> dict[str, object]:
    view = replay.account.snapshot()
    return {
        "scope": "declared recorded polls; not continuous historical portfolio validation",
        "economic_inputs": "declared_scenario",
        "actions_per_poll": actions,
        "completed_packets": packets,
        "filled_orders": len({row["oid"] for _, row in replay.fill_rows}),
        "fill_rows": [row for _, row in replay.fill_rows],
        "funding_rows": [row for _, row in replay.funding_rows],
        "equity_usd": str(view.equity_usd),
        "open_symbols": sorted(view.positions),
        "final_time_ms": replay.clock.now_ms,
        "execution_authority": "none",
    }


def _sdk(body: Mapping[str, object], symbols: tuple[str, ...]) -> ReplaySdk:
    clock = ReplayClock(_clock(body["initial_time_ms"]))
    maximum = _clock(body["maximum_book_delay_ms"])
    replay = ReplaySdk(
        clock=clock,
        initial_cash=_decimal(body["initial_cash_usd"]),
        symbols=symbols,
        metadata_by_dex=_mapping(body["metadata_by_dex"]),
        dexes=body["dexes"],
        fees=body["fees"],
        maintenance={
            s: tuple(_tier(row) for row in _rows(rows))
            for s, rows in _mapping(body["maintenance"]).items()
        },
        execution_book=_execution_source(_rows(body["execution_sources"]), maximum),
        timing=ReplaySdkTiming(**{k: _clock(v) for k, v in _mapping(body["timing"]).items()}),
        decision_time=_missing_origin,
        maximum_book_delay_ms=maximum,
    )
    initial = _rows(body["initial_observations"])
    if len(initial) != len(symbols) or {_text(_mapping(r)["symbol"]) for r in initial} != set(
        symbols
    ):
        raise ValueError(
            "initial replay observations must cover the exact configured universe once"
        )
    for row in initial:
        _observe(replay, _mapping(row))
    for value in _rows(body["events"]):
        row = _mapping(value)
        replay.schedule(_clock(row["time_ms"]), _text(row["event_id"]), partial(_event, row=row))
    return replay


def _execution_source(
    sources: list[object],
    maximum: int,
) -> Callable[[str, int, Decimal], RecordedBook]:
    """Load only authenticated source hours covering the declared execution sampling window."""

    @lru_cache(maxsize=8)
    def load(index: int) -> AuthenticatedBookBundle:
        row = _mapping(sources[index])
        symbol = _text(row["symbol"])
        request = OxaBookRequest(
            symbol,
            datetime.fromisoformat(_text(row["start"])),
            datetime.fromisoformat(_text(row["end"])),
            max_pages=DEFAULT_BOOK_MAX_PAGES,
            market_family="hip3" if ":" in symbol else "core",
        )
        root = Path(_text(row["data_root"]))
        _verified_path(
            {
                "path": str(output_directory(root, request) / "manifest.json"),
                "sha256": row["manifest_sha256"],
            }
        )
        return authenticate_book_bundle(root, request)

    def execution(symbol: str, arrival: int, step: Decimal) -> RecordedBook:
        choices = []
        for index, value in enumerate(sources):
            row = _mapping(value)
            if row["symbol"] != symbol or not _utc_ms(row["start"]) <= arrival < _utc_ms(
                row["end"]
            ):
                continue
            bundle = load(index)
            choices.append(
                bundle.execution_book(arrival, maximum_delay_ms=maximum, quantity_step=step)
            )
        if not choices:
            raise RecordedBookUnavailable(
                f"no declared authenticated execution source for {symbol} at {arrival}"
            )
        if len(choices) != 1:
            raise ValueError("overlapping replay execution sources require explicit resolution")
        return choices[0]

    return execution


def _observe(replay: ReplaySdk, row: Mapping[str, object]) -> None:
    symbol = _text(row["symbol"])
    replay.observe_prices(
        symbol,
        source_time_ms=_clock(row["time_ms"]),
        mark=_decimal(row["mark"]),
        mid=None if row["mid"] is None else _decimal(row["mid"]),
    )
    if "book" in row:
        replay.observe_book(symbol, row["book"])


def _event(replay: ReplaySdk, *, row: Mapping[str, object]) -> None:
    if row["kind"] == "price":
        _observe(replay, row)
    elif row["kind"] == "funding":
        replay.settle_funding(
            _text(row["event_id"]),
            _text(row["symbol"]),
            rate=_decimal(row["rate"]),
            oracle_price=_decimal(row["oracle_price"]),
            effective_time_ms=_clock(row["time_ms"]),
            visible_delay_ms=_clock(row["visible_delay_ms"]),
        )
    else:
        raise ValueError("packet replay supports declared price and funding source events only")


def _tier(value: object) -> MaintenanceTier:
    row = _mapping(value)
    return MaintenanceTier(
        *(_decimal(row[key]) for key in ("lower_notional_usd", "rate", "deduction_usd"))
    )


def _verified_path(value: object) -> Path:
    row = _mapping(value)
    path = Path(_text(row["path"]))
    if sha256(path.read_bytes()).hexdigest() != row["sha256"]:
        raise ValueError(f"native replay input checksum mismatch: {path}")
    return path


def _missing_origin(symbol: str, reduce_only: bool) -> int:
    raise ValueError("native ledger decision origins must be installed before SDK execution")


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(k, str) for k in value):
        raise ValueError("native replay scenario requires an object with text keys")
    return value


def _rows(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("native replay scenario requires an explicit list")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("native replay scenario requires nonempty text")
    return value


def _decimal(value: object) -> Decimal:
    return Decimal(_text(value))


def _clock(value: object) -> int:
    if type(value) is not int:
        raise ValueError("native replay scenario clocks must be exact integers")
    require_clock(value, "scenario clock")
    return value


def _utc_ms(value: object) -> int:
    delta = datetime.fromisoformat(_text(value)) - EPOCH
    if delta % timedelta(milliseconds=1):
        raise ValueError("native replay source timestamp must use exact milliseconds")
    return _clock(delta // timedelta(milliseconds=1))
