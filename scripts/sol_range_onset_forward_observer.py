"""Record SOL range-onset signals and venue tape without execution authority."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import pandas as pd

from hypervector.data.hl import fetch_hl_ohlcv
from hypervector.data.hl_event_stream import RecordedEvent
from hypervector.data.hl_events import (
    AssetContextEvent,
    L2SnapshotEvent,
    PublicTradeEvent,
    StreamGap,
)
from hypervector.paper.event_stream_pump import HypervelocityEventStreamPump
from hypervector.live.sol_range_onset_config import load_sol_range_onset_config
from hypervector.regime.composite import classify_multitimeframe
from hypervector.research.btc_shadow_capital import BtcShadowCapitalReader
from hypervector.research.range_onset_forward_observer import (
    ObserverSessionIdentity,
    RangeOnsetForwardObserver,
)
from hypervector.research.range_onset_event_models import EventSignal
from hypervector.research.range_onset_observation import (
    index_range_onset_bars,
    prepare_completed_range_onset_frames,
)
from hypervector.research.range_onset_signals import build_range_onset_signals
from hypervector.research.sol_range_onset_backend_telemetry import (
    build_sol_backend_rows,
)
from hypervector.research.sol_range_onset_shadow import SolRangeOnsetShadowEngine
from hypervector.research.sol_range_onset_shadow_ledger import SolShadowLedger
from hypervector.research.sol_range_onset_shadow_models import (
    SharedCapitalSnapshot,
    SolShadowConfig,
)
from hypervector.runtime_env import (
    credential_presence_from_env,
    load_dotenv_if_present,
)

_DEFAULT_LEDGER = Path("data/research/forward/sol_range_onset/decisions.jsonl")
_DEFAULT_SHADOW_LEDGER = Path("data/research/forward/sol_range_onset/shadow.jsonl")
_DEFAULT_BTC_LEDGER = Path("data/paper/decisions/decisions.jsonl")
_DEFAULT_STOP = Path("data/research/forward/sol_range_onset/STOP")
_RETAIN_DAYS = 7
_ARCHIVE_BATCH_SIZE = 100


@dataclass(frozen=True)
class _ResolvedRuntime:
    """Resolved no-submit capital, config, identity, and file boundaries."""

    config: SolShadowConfig
    ledger: Path
    shadow_ledger: Path
    stop_file: Path
    btc_ledger: Path | None
    identity: ObserverSessionIdentity
    standalone_equity_usd: float | None = None

    def capital_snapshot(self, recorded_at_ms: int) -> SharedCapitalSnapshot | None:
        """Return fresh standalone canary capital or defer to the shared reader."""
        if self.standalone_equity_usd is None:
            return None
        return SharedCapitalSnapshot(
            recorded_at_ms,
            self.standalone_equity_usd,
            0.0,
            "sol-canary-standalone",
        )


class _BatchPump(Protocol):
    def pump(self, consumer: _ShadowConsumer) -> int:
        """Deliver one buffered public event batch."""


@dataclass
class _ShadowConsumer:
    """Route archived SOL lifecycle evidence into the no-submit engine."""

    engine: SolRangeOnsetShadowEngine

    delivered: int = 0
    latest_book: L2SnapshotEvent | None = None
    latest_context: AssetContextEvent | None = None

    def ingest_hyperliquid_event(self, event: RecordedEvent) -> str | None:
        """Apply execution-relevant public evidence without order authority."""
        self.delivered += 1
        if isinstance(event, PublicTradeEvent):
            return None
        if not isinstance(event, (L2SnapshotEvent, AssetContextEvent, StreamGap)):
            raise TypeError(f"unsupported SOL shadow event {type(event).__name__}")
        if isinstance(event, L2SnapshotEvent):
            self.latest_book = event
        elif isinstance(event, AssetContextEvent):
            self.latest_context = event
        self.engine.ingest_event(event)
        return None


@dataclass(frozen=True)
class _ObserverComponents:
    """Constructed observer collaborators with no execution authority."""

    observer: RangeOnsetForwardObserver
    pump: HypervelocityEventStreamPump
    ledger: SolShadowLedger
    engine: SolRangeOnsetShadowEngine
    capital_reader: BtcShadowCapitalReader | None
    consumer: _ShadowConsumer
    resumed: bool


def build_parser() -> argparse.ArgumentParser:
    """Build the no-submit SOL observer command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument(
        "--config",
        type=Path,
        help="strict $150 canary shadow profile; does not enable live execution",
    )
    parser.add_argument("--ledger", type=Path, default=_DEFAULT_LEDGER)
    parser.add_argument("--shadow-ledger", type=Path, default=_DEFAULT_SHADOW_LEDGER)
    parser.add_argument("--btc-ledger", type=Path, default=_DEFAULT_BTC_LEDGER)
    parser.add_argument("--stop-file", type=Path, default=_DEFAULT_STOP)
    parser.add_argument("--poll-seconds", type=float, default=15.0)
    parser.add_argument("--lookback-days", type=int, default=5)
    parser.add_argument("--max-polls", type=int)
    parser.add_argument("--once", action="store_true")
    return parser


def prepare_observation_frames(
    raw_bars: pd.DataFrame,
    *,
    observed_at: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return complete causal bars with the frozen signal and regime frames."""
    return prepare_completed_range_onset_frames(
        raw_bars,
        observed_at=observed_at,
        signal_builder=build_range_onset_signals,
        regime_builder=classify_multitimeframe,
    )


def observe_cycle(
    observer: RangeOnsetForwardObserver,
    raw_bars: pd.DataFrame,
    *,
    observed_at: pd.Timestamp,
) -> tuple[dict[str, object], ...]:
    """Compute and persist one causally completed observation cycle."""
    bars, signals, regimes = prepare_observation_frames(
        raw_bars,
        observed_at=observed_at,
    )
    return observer.observe(
        bars,
        observed_at=observed_at,
        signals=signals,
        regimes=regimes,
    )


def run_observer(args: argparse.Namespace) -> int:
    """Run the public-data observer until bounded completion or interruption."""
    _validate_args(args)
    runtime = _resolve_runtime(args)
    runtime.stop_file.unlink(missing_ok=True)
    parts = _build_observer_components(args, runtime)
    polls = 0
    parts.pump.start()
    try:
        bars = fetch_hl_ohlcv("SOL", "1m", args.lookback_days)
        _persist_session_state(parts.ledger, parts.engine, parts.resumed)
        while not runtime.stop_file.exists():
            observed = pd.Timestamp(datetime.now(UTC))
            recorded_at_ms = int(observed.timestamp() * 1_000)
            decisions = observe_cycle(parts.observer, bars, observed_at=observed)
            _process_shadow_batch(
                engine=parts.engine,
                ledger=parts.ledger,
                observer=parts.observer,
                consumer=parts.consumer,
                pump=parts.pump,
                decisions=decisions,
                capital=_read_capital(runtime, parts.capital_reader, recorded_at_ms),
                recorded_at_ms=recorded_at_ms,
            )
            _print_status(observed, decisions, parts.consumer.delivered, parts.engine)
            polls += 1
            if args.once or (args.max_polls is not None and polls >= args.max_polls):
                break
            time.sleep(args.poll_seconds)
            tail = fetch_hl_ohlcv("SOL", "1m", 1)
            bars = _merge_bars(bars, tail, observed)
    finally:
        parts.pump.close()
    return 0


def _build_observer_components(
    args: argparse.Namespace,
    runtime: _ResolvedRuntime,
) -> _ObserverComponents:
    credential_status = credential_presence_from_env()
    observer = RangeOnsetForwardObserver(
        symbol="SOL",
        activated_at=pd.Timestamp(datetime.now(UTC)),
        ledger_path=runtime.ledger,
        config=runtime.config,
        wallet_configured=credential_status.wallet_configured,
        signing_key_configured=credential_status.signing_key_configured,
        identity=runtime.identity,
    )
    pump = HypervelocityEventStreamPump(
        data_root=args.data_root,
        symbol="SOL",
        archive_batch_size=_ARCHIVE_BATCH_SIZE,
    )
    ledger = SolShadowLedger(runtime.shadow_ledger, runtime.config)
    engine = ledger.restore_engine()
    capital_reader = (
        BtcShadowCapitalReader(runtime.btc_ledger)
        if runtime.btc_ledger is not None
        else None
    )
    return _ObserverComponents(
        observer,
        pump,
        ledger,
        engine,
        capital_reader,
        _ShadowConsumer(engine),
        runtime.shadow_ledger.exists(),
    )


def _resolve_runtime(args: argparse.Namespace) -> _ResolvedRuntime:
    if args.config is None:
        config = SolShadowConfig()
        identity = ObserverSessionIdentity(
            profile_id="sol_range_onset_research_shadow_v1",
            capital_source="btc_shadow_shared_portfolio",
            portfolio_purpose="research_validation",
            profile_fingerprint=config.fingerprint,
            run_fingerprint=config.fingerprint,
            backend_ledger_path=str(args.ledger),
        )
        return _ResolvedRuntime(
            config,
            args.ledger,
            args.shadow_ledger,
            args.stop_file,
            args.btc_ledger,
            identity,
        )
    _reject_profile_path_overrides(args)
    profile = load_sol_range_onset_config(args.config, mode="shadow")
    return _ResolvedRuntime(
        profile.shadow_engine_config(),
        profile.backend_ledger,
        profile.shadow_ledger,
        profile.stop_file,
        None,
        ObserverSessionIdentity(
            profile_id=profile.profile_id,
            capital_source=profile.capital_source,
            portfolio_purpose=profile.portfolio_purpose,
            profile_fingerprint=profile.profile_fingerprint,
            run_fingerprint=profile.run_fingerprint,
            backend_ledger_path=str(profile.backend_ledger),
        ),
        profile.initial_shadow_equity_usd,
    )


def _reject_profile_path_overrides(args: argparse.Namespace) -> None:
    values = {
        "--ledger": (args.ledger, _DEFAULT_LEDGER),
        "--shadow-ledger": (args.shadow_ledger, _DEFAULT_SHADOW_LEDGER),
        "--btc-ledger": (args.btc_ledger, _DEFAULT_BTC_LEDGER),
        "--stop-file": (args.stop_file, _DEFAULT_STOP),
    }
    changed = [
        name for name, (actual, expected) in values.items() if actual != expected
    ]
    if changed:
        raise ValueError(f"--config cannot be combined with path overrides: {changed}")


def _read_capital(
    runtime: _ResolvedRuntime,
    reader: BtcShadowCapitalReader | None,
    recorded_at_ms: int,
) -> SharedCapitalSnapshot | None:
    standalone = runtime.capital_snapshot(recorded_at_ms)
    if standalone is not None:
        return standalone
    return None if reader is None else reader.read_latest()


def _process_shadow_batch(
    *,
    engine: SolRangeOnsetShadowEngine,
    ledger: SolShadowLedger,
    observer: RangeOnsetForwardObserver,
    consumer: _ShadowConsumer,
    pump: _BatchPump,
    decisions: tuple[dict[str, object], ...],
    capital: SharedCapitalSnapshot | None,
    recorded_at_ms: int,
) -> tuple[dict[str, object], ...]:
    if capital is not None:
        engine.update_shared_capital(capital)
    for decision in decisions:
        engine.ingest_decision(
            _event_signal(decision),
            fresh_at_observation=_decision_bool(decision, "fresh_at_observation"),
        )
    pump.pump(consumer)
    records = engine.drain_records()
    ledger.append(records, engine, recorded_at_ms=recorded_at_ms)
    observer.append_backend_rows(
        build_sol_backend_rows(
            records=records,
            snapshot=engine.snapshot,
            capital=capital,
            latest_book=consumer.latest_book,
            latest_context=consumer.latest_context,
            recorded_at_ms=recorded_at_ms,
        )
    )
    return records


def _event_signal(decision: dict[str, object]) -> EventSignal:
    if decision.get("symbol") != "SOL":
        raise ValueError("SOL shadow decisions must have symbol SOL")
    timestamp = _utc_timestamp(pd.Timestamp(str(decision.get("decision_time_utc"))))
    return EventSignal(
        int(timestamp.value // 1_000_000),
        float(decision.get("reference_price", 0.0)),
        _decision_bool(decision, "long_entry"),
        _decision_bool(decision, "short_entry"),
        _decision_bool(decision, "long_exit"),
        _decision_bool(decision, "short_exit"),
    )


def _decision_bool(decision: dict[str, object], key: str) -> bool:
    value = decision.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"SOL shadow decision {key} must be boolean")
    return value


def _persist_session_state(
    ledger: SolShadowLedger,
    engine: SolRangeOnsetShadowEngine,
    resumed: bool,
) -> None:
    now_ms = int(datetime.now(UTC).timestamp() * 1_000)
    record = {
        "schema_version": 1,
        "action": "shadow_session_resumed" if resumed else "shadow_session_started",
        "event_time_ms": now_ms,
        "execution_authority": "none",
        "submitted": False,
        "place_attempted": False,
    }
    ledger.append((record,), engine, recorded_at_ms=now_ms)


def _indexed_bars(frame: pd.DataFrame) -> pd.DataFrame:
    return index_range_onset_bars(frame)


def _merge_bars(
    prior: pd.DataFrame,
    tail: pd.DataFrame,
    observed_at: pd.Timestamp,
) -> pd.DataFrame:
    combined = pd.concat([prior, tail], ignore_index=True)
    indexed = _indexed_bars(combined)
    cutoff = _utc_timestamp(observed_at) - pd.Timedelta(days=_RETAIN_DAYS)
    return indexed.loc[indexed.index >= cutoff].reset_index()


def _print_status(
    observed_at: pd.Timestamp,
    decisions: tuple[dict[str, object], ...],
    archived_events: int,
    engine: SolRangeOnsetShadowEngine,
) -> None:
    latest = decisions[-1] if decisions else None
    payload = {
        "observed_at_utc": _utc_timestamp(observed_at).isoformat(),
        "new_decisions": len(decisions),
        "latest_decision": latest,
        "archived_public_events": archived_events,
        "shadow_status": engine.snapshot.status,
        "shadow_position": (
            engine.snapshot.position.direction
            if engine.snapshot.position is not None
            else "flat"
        ),
        "shadow_completed_trades": len(engine.snapshot.completed_trades),
        "execution_authority": "none",
    }
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True), flush=True)


def _validate_args(args: argparse.Namespace) -> None:
    if args.poll_seconds <= 0.0:
        raise ValueError("poll-seconds must be positive")
    if args.lookback_days < 3:
        raise ValueError("lookback-days must be at least three for 30-hour SMA warmup")
    if args.max_polls is not None and args.max_polls <= 0:
        raise ValueError("max-polls must be positive")


def _utc_timestamp(value: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("observer timestamps must be timezone-aware")
    return timestamp.tz_convert("UTC")


def main() -> int:
    """Run the no-submit SOL observer from command-line arguments."""
    load_dotenv_if_present()
    try:
        return run_observer(build_parser().parse_args())
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
