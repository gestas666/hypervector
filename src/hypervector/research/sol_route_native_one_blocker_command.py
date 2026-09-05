"""Report-only I/O adapter for the v51 SOL one-blocker forward shadow."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path

import pandas as pd

from hypervector.data.hl import fetch_hl_funding_pages
from hypervector.data.hl_events import (
    AssetContextEvent,
    L2SnapshotEvent,
    PublicTradeEvent,
    StreamGap,
)
from hypervector.data.event_archive import EventArchive
from hypervector.data.oxa_storage import file_evidence
from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.research.cohort_signal_candidates import (
    SignalCandidate,
    evaluation_candidates,
)
from hypervector.research.cohort_eligible_policy_funding import (
    parse_official_funding_history,
)
from hypervector.research.cohort_candidate_portfolio_journal import (
    CandidatePortfolioJournalSpec,
    build_candidate_portfolio_journal,
)
from hypervector.research.market_depth_fill import DepthLevel
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger
from hypervector.research.sol_route_native_one_blocker_shadow import (
    MarkObservation,
    SolFundingEvidence,
    SolRouteNativeShadowSpec,
    build_sol_route_native_one_blocker_shadow,
)
from hypervector.research.cohort_one_blocker_execution_types import Book

Record = Mapping[str, object]
PublicEvent = L2SnapshotEvent | PublicTradeEvent | AssetContextEvent | StreamGap
FundingEvidenceFetcher = Callable[[int, int], SolFundingEvidence]
FundingPageFetcher = Callable[[str, int, int], Sequence[Sequence[Mapping[str, object]]]]
_STRATEGY = "range_onset_bidirectional_v1"
_CANDIDATE_STRATEGY = "sol_hourly_cross_relaxed_route_native_shadow_v1"
_SYMBOL = "SOL"
_MAXIMUM_NEGATIVE_CLOCK_SKEW_MS = 1_000
_VenueInputs = tuple[
    tuple[Book, ...], tuple[MarkObservation, ...], tuple[StreamGap, ...], int, int
]


@dataclass(frozen=True)
class SolRouteNativeSourceBundle:
    """Validated source inputs for one zero-authority replay snapshot."""

    spec: SolRouteNativeShadowSpec
    candidates: tuple[SignalCandidate, ...]
    books: tuple[Book, ...]
    marks: tuple[MarkObservation, ...]
    funding_evidence: SolFundingEvidence | None
    gaps: tuple[StreamGap, ...]
    source_counts: Mapping[str, int]
    maximum_positions: int


def build_sol_route_native_source_bundle(
    *,
    config_path: Path,
    cohort_rows: Sequence[Record],
    events: Sequence[PublicEvent],
    funding_evidence: SolFundingEvidence | None,
    source_run_id: str,
    capture_start_ms: int,
    taker_fee_rate: float,
) -> SolRouteNativeSourceBundle:
    """Bind exact v51 route identity to causal public venue evidence."""
    config = load_multi_asset_live_config(config_path, mode="observe")
    _validate_identity(config, cohort_rows, source_run_id)
    asset = _validate_route(config)
    candidates, _, _ = evaluation_candidates(cohort_rows)
    selected = tuple(row for row in candidates if row.source_run_id == source_run_id)
    books, marks, gaps, skew_count, maximum_skew_ms = _event_inputs(
        events, capture_start_ms
    )
    spec = SolRouteNativeShadowSpec(
        source_run_id=source_run_id,
        source_profile_id=config.profile_id,
        source_profile_fingerprint=config.profile_fingerprint,
        cutoff_time_ms=capture_start_ms,
        notional_usd=asset.max_notional_usd,
        taker_fee_rate=taker_fee_rate,
    )
    return SolRouteNativeSourceBundle(
        spec,
        selected,
        books,
        marks,
        funding_evidence,
        gaps,
        {
            "l2": len(books),
            "marks": len(marks),
            "gaps": len(gaps),
            "clock_skew_adjusted_l2": skew_count,
            "maximum_negative_clock_skew_ms": maximum_skew_ms,
        },
        config.maximum_positions,
    )


def build_sol_route_native_report(
    bundle: SolRouteNativeSourceBundle,
) -> dict[str, object]:
    """Build one bounded report without adding live execution authority."""
    report = build_sol_route_native_one_blocker_shadow(
        candidates=bundle.candidates,
        books=bundle.books,
        marks=bundle.marks,
        funding_evidence=bundle.funding_evidence,
        gaps=bundle.gaps,
        spec=bundle.spec,
    )
    coverage = report["coverage"]
    if not isinstance(coverage, dict):
        raise ValueError("SOL route-native report coverage is malformed")
    report["status"] = _report_status(coverage, report["attempts"])
    report["source_counts"] = dict(bundle.source_counts)
    return report


def run_sol_route_native_snapshot(
    *,
    config_path: Path,
    cohort_ledger: Path,
    asset_ledger: Path,
    data_root: Path,
    source_run_id: str,
    capture_start_ms: int,
    observed_at_ms: int,
    output: Path,
    funding_fetcher: FundingEvidenceFetcher,
) -> dict[str, object]:
    """Read exact bounded inputs and atomically publish one report-only snapshot."""
    if observed_at_ms <= capture_start_ms:
        raise ValueError("SOL shadow observation must follow capture start")
    with _run_ledger_snapshots(cohort_ledger, asset_ledger, source_run_id) as source:
        report = _build_snapshot_report(
            config_path=config_path,
            data_root=data_root,
            source_run_id=source_run_id,
            capture_start_ms=capture_start_ms,
            observed_at_ms=observed_at_ms,
            funding_fetcher=funding_fetcher,
            source=source,
        )
    write_atomic_json(output, report)
    return report


@contextmanager
def _run_ledger_snapshots(
    cohort_path: Path,
    asset_path: Path,
    run_id: str,
) -> Iterator[
    tuple[tuple[Record, ...], dict[str, object], tuple[Record, ...], dict[str, object]]
]:
    """Yield immutable exact-run suffixes and source-bound evidence."""
    with (
        snapshot_decision_ledger(
            cohort_path, allow_incomplete_tail=True, run_id=run_id
        ) as cohort,
        snapshot_decision_ledger(
            asset_path, allow_incomplete_tail=True, run_id=run_id
        ) as asset,
    ):
        cohort_rows, cohort_evidence = cohort
        asset_rows, asset_evidence = asset
        yield (
            tuple(cohort_rows),
            _source_snapshot_evidence(cohort_path, cohort_rows, cohort_evidence),
            tuple(asset_rows),
            _source_snapshot_evidence(asset_path, asset_rows, asset_evidence),
        )


def _source_snapshot_evidence(
    source: Path,
    rows: Sequence[Record],
    evidence: Mapping[str, object],
) -> dict[str, object]:
    """Replace ephemeral temp identity with the append-only source identity."""
    return {"path": str(source.resolve()), **evidence, "rows": len(rows)}


def _build_snapshot_report(
    *,
    config_path: Path,
    data_root: Path,
    source_run_id: str,
    capture_start_ms: int,
    observed_at_ms: int,
    funding_fetcher: FundingEvidenceFetcher,
    source: tuple[
        tuple[Record, ...], dict[str, object], tuple[Record, ...], dict[str, object]
    ],
) -> dict[str, object]:
    """Build a report from two already-frozen live-ledger suffixes."""
    cohort_rows, cohort_evidence, asset_rows, asset_evidence = source
    config_evidence = file_evidence(config_path)
    events = _archive_events(data_root, capture_start_ms, observed_at_ms)
    funding = funding_fetcher(capture_start_ms, observed_at_ms)
    bundle = build_sol_route_native_source_bundle(
        config_path=config_path,
        cohort_rows=cohort_rows,
        events=events,
        funding_evidence=funding,
        source_run_id=source_run_id,
        capture_start_ms=capture_start_ms,
        taker_fee_rate=_effective_taker_fee(asset_rows, source_run_id),
    )
    report = build_sol_route_native_report(bundle)
    report["portfolio_journal"] = _portfolio_journal(
        cohort_rows, report, bundle.maximum_positions
    )
    report.update(
        observed_at_utc=_iso(observed_at_ms),
        capture_start_utc=_iso(capture_start_ms),
        input_evidence=_input_evidence(
            config_path,
            config_evidence,
            cohort_evidence,
            asset_evidence,
            events,
            funding,
        ),
    )
    if file_evidence(config_path) != config_evidence:
        raise ValueError("SOL shadow config changed during evaluation")
    return report


def _portfolio_journal(
    rows: Sequence[Record], report: Record, maximum_positions: int
) -> dict[str, object]:
    """Classify shadow attempts against the causal live portfolio snapshot."""
    return build_candidate_portfolio_journal(
        rows,
        report,
        spec=CandidatePortfolioJournalSpec(
            source_strategy_id=_STRATEGY,
            candidate_strategy_id=_CANDIDATE_STRATEGY,
            symbol=_SYMBOL,
            maximum_positions=maximum_positions,
        ),
    )


def fetch_official_sol_funding_evidence(
    start_ms: int,
    end_ms: int,
    *,
    page_fetcher: FundingPageFetcher | None = None,
) -> SolFundingEvidence:
    """Fetch and strictly parse complete public SOL funding-history rows."""
    fetcher = page_fetcher or _fetch_official_funding_pages
    pages = fetcher(_SYMBOL, start_ms, end_ms)
    rows = tuple(row for page in pages for row in page)
    parsed = parse_official_funding_history(
        rows,
        symbol=_SYMBOL,
        requested_start_ms=start_ms,
        requested_end_ms=end_ms,
    )
    events = tuple((event.timestamp_ms, event.funding_rate) for event in parsed.events)
    return SolFundingEvidence(start_ms, end_ms, events)


def _fetch_official_funding_pages(
    symbol: str, start_ms: int, end_ms: int
) -> tuple[tuple[dict[str, object], ...], ...]:
    start = pd.Timestamp(start_ms, unit="ms", tz="UTC")
    end = pd.Timestamp(end_ms, unit="ms", tz="UTC")
    return fetch_hl_funding_pages(symbol, start_time=start, end_time=end)


def _archive_events(
    data_root: Path, start_ms: int, end_ms: int
) -> tuple[PublicEvent, ...]:
    archive = EventArchive(data_root=data_root, symbol=_SYMBOL, batch_size=1)
    start = datetime.fromtimestamp(start_ms / 1_000, UTC)
    end = datetime.fromtimestamp(end_ms / 1_000, UTC) + timedelta(milliseconds=1)
    return archive.replay_window(start, end)


def _effective_taker_fee(rows: Sequence[Record], source_run_id: str) -> float:
    schedules = [
        row
        for row in rows
        if row.get("event_type") == "fee"
        and row.get("run_id") == source_run_id
        and isinstance(row.get("payload"), dict)
        and row["payload"].get("source") == "venue_fee_schedule"
    ]
    if len(schedules) != 1:
        raise ValueError("SOL shadow requires one exact run fee schedule")
    payload = schedules[0]["payload"]
    if payload.get("effective_fee_status") != "resolved_core_after_referral":
        raise ValueError("SOL effective taker fee is unresolved")
    value = payload.get("effective_taker_fee_rate")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("SOL effective taker fee must be numeric")
    return float(value)


def _input_evidence(
    config_path: Path,
    config: Mapping[str, object],
    cohort: Mapping[str, object],
    asset: Mapping[str, object],
    events: Sequence[PublicEvent],
    funding: SolFundingEvidence,
) -> dict[str, object]:
    encoded = json.dumps(
        [asdict(event) for event in events],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "config": {"path": str(config_path), **config},
        "cohort_prefix": dict(cohort),
        "asset_prefix": dict(asset),
        "public_events": {
            "source": "hyperliquid_public_event_archive",
            "events": len(events),
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "bytes": len(encoded),
        },
        "funding": _funding_evidence(funding),
    }


def _funding_evidence(evidence: SolFundingEvidence) -> dict[str, object]:
    payload = asdict(evidence)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {
        "source": evidence.source,
        "requested_start_ms": evidence.requested_start_ms,
        "requested_end_ms": evidence.requested_end_ms,
        "events": len(evidence.events),
        "rows": [list(event) for event in evidence.events],
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "bytes": len(encoded),
    }


def _iso(timestamp_ms: int) -> str:
    """Return one UTC millisecond timestamp in stable text form."""
    return datetime.fromtimestamp(timestamp_ms / 1_000, UTC).isoformat()


def _report_status(coverage: Mapping[str, object], attempts: object) -> str:
    """Label evidence maturity without success-shaped numeric performance."""
    if coverage.get("exact_candidates") == 0:
        return "waiting_future_exact_candidate"
    if coverage.get("resolved_executions", 0) != 0:
        return "resolved_evidence_available"
    if isinstance(attempts, list) and any(
        isinstance(row, dict) and row.get("status") == "exit_pending"
        for row in attempts
    ):
        return "candidate_lifecycle_pending"
    return "candidate_technically_unresolved"


def _validate_identity(
    config: MultiAssetLiveConfig,
    rows: Sequence[Record],
    source_run_id: str,
) -> None:
    identities = [
        row
        for row in rows
        if row.get("event_type") == "configuration_identity"
        and row.get("run_id") == source_run_id
    ]
    if len(identities) != 1:
        raise ValueError("SOL shadow requires one exact source-run identity")
    identity = identities[0]
    if identity.get("live_armed") is not True:
        raise ValueError("SOL shadow source run must be armed live evidence")
    if identity.get("profile_id") != config.profile_id:
        raise ValueError("SOL shadow source profile id does not match config")
    if identity.get("profile_fingerprint") != config.profile_fingerprint:
        raise ValueError("SOL shadow source profile fingerprint does not match config")


def _validate_route(config: MultiAssetLiveConfig) -> AssetLiveConfig:
    assets = [asset for asset in config.assets if asset.symbol == _SYMBOL]
    providers = [
        provider for provider in config.providers if provider.strategy_id == _STRATEGY
    ]
    if len(assets) != 1 or len(providers) != 1:
        raise ValueError("SOL shadow requires one exact asset and provider route")
    asset, provider = assets[0], providers[0]
    execution = provider.execution_for(_SYMBOL)
    if (
        _SYMBOL not in provider.execution_symbols
        or provider.executable_sides(_SYMBOL) != frozenset({"long", "short"})
        or provider.timeframe != "1m"
        or provider.maximum_entry_delay_seconds != 60
        or provider.position_policy != "enter_and_close"
        or execution.entry_liquidity != "taker_ioc"
        or execution.stop_policy != "fixed_bps"
        or execution.stop_bps != 80.0
        or execution.target_policy != "none"
        or execution.maximum_hold_seconds != 172_800
        or execution.maximum_hold_policy != "fixed"
        or execution.profit_lock_policy != "none"
    ):
        raise ValueError("SOL route no longer matches frozen v51 replay mechanics")
    return asset


def _event_inputs(events: Sequence[PublicEvent], capture_start_ms: int) -> _VenueInputs:
    if any(event.symbol != _SYMBOL for event in events):
        raise ValueError("SOL shadow public event has the wrong symbol")
    l2_events = tuple(
        event
        for event in events
        if isinstance(event, L2SnapshotEvent)
        and _l2_availability_ms(event) >= capture_start_ms
    )
    books = tuple(_book(event) for event in l2_events)
    marks = tuple(
        MarkObservation(
            event.observed_ts_ms,
            event.mark_price,
            event.source,
            event.timestamp_source,
            event.received_ts_ns,
        )
        for event in events
        if isinstance(event, AssetContextEvent)
        and event.observed_ts_ms >= capture_start_ms
    )
    gaps = tuple(event for event in events if isinstance(event, StreamGap))
    skews = tuple(_negative_clock_skew_ms(event) for event in l2_events)
    return books, marks, gaps, sum(skew > 0 for skew in skews), max(skews, default=0)


def _negative_clock_skew_ms(event: L2SnapshotEvent) -> int:
    """Return a nonnegative exchange-clock lead over local receipt time."""
    receipt_ms = event.received_ts_ns // 1_000_000
    return max(0, event.exchange_ts_ms - receipt_ms)


def _l2_availability_ms(event: L2SnapshotEvent) -> int:
    """Conservatively reconcile bounded local and exchange clock skew."""
    receipt_ms = event.received_ts_ns // 1_000_000
    skew_ms = _negative_clock_skew_ms(event)
    if skew_ms > _MAXIMUM_NEGATIVE_CLOCK_SKEW_MS:
        raise ValueError("SOL shadow L2 clock skew exceeds 1000ms sanity bound")
    return max(receipt_ms, event.exchange_ts_ms)


def _book(event: L2SnapshotEvent) -> Book:
    """Convert one exact WS book while retaining finite visible depth."""
    if event.symbol != _SYMBOL or event.source != "hyperliquid_ws_l2Book":
        raise ValueError("SOL shadow L2 source identity is invalid")
    available_ms = _l2_availability_ms(event)
    bids = tuple(DepthLevel(level.price, level.size) for level in event.bids)
    asks = tuple(DepthLevel(level.price, level.size) for level in event.asks)
    if bids[0].price >= asks[0].price:
        raise ValueError("SOL shadow L2 book is crossed or locked")
    bid_depth = sum(level.size for level in bids)
    ask_depth = sum(level.size for level in asks)
    return Book(
        available_ms,
        (bid_depth - ask_depth) / (bid_depth + ask_depth),
        bids[0].price,
        bids[0].size,
        asks[0].price,
        asks[0].size,
        bids,
        asks,
    )
