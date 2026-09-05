"""Immutable outcome-blind BTC liquidation treatment-episode storage."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Literal, TypedDict

from hypervector.data.oxa_storage import (
    file_evidence,
    gzip_text_writer,
    open_text_reader,
    publish_immutable_directory,
    verify_file_evidence,
    write_json,
)
from hypervector.research.btc_liquidation_episodes import (
    BurstArm,
    LiquidatedDirection,
    LiquidationBurstAssessment,
    assess_rolling_bursts,
    build_liquidation_episodes,
    load_liquidation_bundles,
)

CandidateBranch = Literal["continuation_long", "exhaustion_reclaim_long"]
_SCHEMA = "btc_liquidation_treatment_episode_bundle_v1"
_EPISODE_SCHEMA = "btc_liquidation_treatment_episode_v1"
_EPISODE_GAP_MS = 2_000
_MINIMUM_TRADE_COUNT = 3
_ARMS = frozenset({"5s_p95", "5s_p99", "15s_p95", "15s_p99"})


class _EpisodeRow(TypedDict):
    schema_version: str
    episode_id: str
    symbol: str
    liquidated_direction: LiquidatedDirection
    candidate_branch: CandidateBranch
    start_ms: int
    end_ms: int
    trade_count: int
    total_size: str
    notional_usd: str
    volume_weighted_price: str
    trailing_5s_notional_usd: str
    trailing_15s_notional_usd: str
    prior_episode_count: int
    threshold_5s_p95_usd: str | None
    threshold_5s_p99_usd: str | None
    threshold_15s_p95_usd: str | None
    threshold_15s_p99_usd: str | None
    eligible_arms: list[BurstArm]


def publish_liquidation_episode_bundle(
    source_bundles: tuple[Path, ...],
    output: Path,
    *,
    symbol: str,
    lookback_ms: int = 30 * 24 * 60 * 60 * 1_000,
) -> Path:
    """Build and atomically publish an outcome-blind treatment cohort."""
    labels = load_liquidation_bundles(source_bundles, symbol=symbol)
    if not labels:
        raise ValueError("treatment source contains no liquidation labels")
    source_start_ms = labels[0].ts_exchange_ms
    assessments = assess_rolling_bursts(
        build_liquidation_episodes(labels),
        source_start_ms=source_start_ms,
        lookback_ms=lookback_ms,
    )
    rows = tuple(_assessment_row(symbol, row) for row in assessments)
    sources = _source_manifest_evidence(source_bundles)

    def writer(staging: Path) -> None:
        episodes_path = staging / "episodes.jsonl.gz"
        eligible_path = staging / "eligible_episodes.jsonl.gz"
        _write_rows(episodes_path, rows)
        _write_rows(
            eligible_path,
            tuple(row for row in rows if row["eligible_arms"]),
        )
        files = {
            path.name: file_evidence(path) for path in (episodes_path, eligible_path)
        }
        write_json(
            staging / "manifest.json",
            _manifest(
                symbol,
                labels[-1].ts_exchange_ms,
                source_start_ms,
                lookback_ms,
                rows,
                sources,
                files,
            ),
        )

    publish_immutable_directory(output, writer)
    return output


def verify_liquidation_episode_bundle(bundle: Path) -> Mapping[str, object]:
    """Verify the immutable files and report-only outcome-blind contract."""
    manifest_path = bundle / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or payload.get("schema_version") != _SCHEMA:
        raise ValueError("liquidation episode manifest schema is unsupported")
    if (
        payload.get("execution_authority") != "none"
        or payload.get("report_only") is not True
    ):
        raise ValueError("liquidation episode artifact acquired execution authority")
    if payload.get("strategy_outcomes_inspected") is not False:
        raise ValueError("liquidation episode artifact inspected strategy outcomes")
    if payload.get("market_covariates_acquired") is not False:
        raise ValueError("liquidation episode artifact acquired market covariates")
    verify_file_evidence(bundle, payload.get("files"))
    sources = _verify_source_manifests(payload.get("source_manifests"))
    episodes, eligible = _verify_row_counts(bundle, payload)
    _verify_reproduction(payload, sources, episodes, eligible)
    return payload


def _verify_source_manifests(value: object) -> tuple[Path, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("liquidation episode source manifests are missing")
    paths: list[Path] = []
    for record in value:
        if not isinstance(record, Mapping):
            raise ValueError("liquidation source manifest evidence is malformed")
        raw_path = record.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            raise ValueError("liquidation source manifest path is invalid")
        path = Path(raw_path)
        observed = file_evidence(path)
        if observed.get("bytes") != record.get("bytes") or observed.get(
            "sha256"
        ) != record.get("sha256"):
            raise ValueError(f"source manifest evidence mismatch: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError(f"liquidation source manifest is malformed: {path}")
        verify_file_evidence(path.parent, payload.get("files"))
        paths.append(path.parent)
    return tuple(paths)


def _verify_row_counts(
    bundle: Path,
    manifest: Mapping[str, object],
) -> tuple[tuple[Mapping[str, object], ...], tuple[Mapping[str, object], ...]]:
    counts = manifest.get("counts")
    if not isinstance(counts, Mapping):
        raise ValueError("liquidation episode manifest counts must be an object")
    episodes = _load_published_rows(bundle / "episodes.jsonl.gz")
    eligible = _load_published_rows(bundle / "eligible_episodes.jsonl.gz")
    if counts.get("episodes") != len(episodes):
        raise ValueError("liquidation episode count mismatch")
    if counts.get("eligible_episodes") != len(eligible):
        raise ValueError("eligible liquidation episode count mismatch")
    _verify_eligible_subset(episodes, eligible)
    direction_counts, arm_counts = _published_composition(episodes)
    if (
        counts.get("by_liquidated_direction") != direction_counts
        or counts.get("by_eligible_arm") != arm_counts
    ):
        raise ValueError("liquidation episode composition count mismatch")
    return episodes, eligible


def _verify_reproduction(
    manifest: Mapping[str, object],
    sources: tuple[Path, ...],
    observed: tuple[Mapping[str, object], ...],
    observed_eligible: tuple[Mapping[str, object], ...],
) -> None:
    symbol = manifest.get("symbol")
    contract = manifest.get("contract")
    if not isinstance(symbol, str) or not isinstance(contract, Mapping):
        raise ValueError("liquidation episode reproduction contract is malformed")
    lookback_ms = contract.get("rolling_lookback_ms")
    if isinstance(lookback_ms, bool) or not isinstance(lookback_ms, int):
        raise ValueError("liquidation episode lookback is invalid")
    labels = load_liquidation_bundles(sources, symbol=symbol)
    if not labels:
        raise ValueError("treatment source contains no liquidation labels")
    assessments = assess_rolling_bursts(
        build_liquidation_episodes(labels),
        source_start_ms=labels[0].ts_exchange_ms,
        lookback_ms=lookback_ms,
    )
    expected = tuple(_assessment_row(symbol, row) for row in assessments)
    expected_eligible = tuple(row for row in expected if row["eligible_arms"])
    if expected != observed or expected_eligible != observed_eligible:
        raise ValueError("liquidation episode artifact does not reproduce from sources")


def _verify_eligible_subset(
    episodes: tuple[Mapping[str, object], ...],
    eligible: tuple[Mapping[str, object], ...],
) -> None:
    by_id: dict[str, Mapping[str, object]] = {}
    for row in episodes:
        episode_id = row.get("episode_id")
        if not isinstance(episode_id, str) or not episode_id:
            raise ValueError("liquidation episode_id must be nonempty text")
        if episode_id in by_id:
            raise ValueError("duplicate liquidation episode_id")
        by_id[episode_id] = row
    for row in eligible:
        episode_id = row.get("episode_id")
        if not isinstance(episode_id, str) or by_id.get(episode_id) != row:
            raise ValueError("eligible episode is absent from complete episode rows")


def _load_published_rows(path: Path) -> tuple[Mapping[str, object], ...]:
    rows: list[Mapping[str, object]] = []
    with open_text_reader(path) as handle:
        for line in handle:
            payload = json.loads(line)
            if not isinstance(payload, Mapping):
                raise ValueError(f"liquidation episode row is not an object: {path}")
            rows.append(payload)
    return tuple(rows)


def _write_rows(path: Path, rows: tuple[_EpisodeRow, ...]) -> None:
    with gzip_text_writer(path) as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def _assessment_row(
    symbol: str,
    assessment: LiquidationBurstAssessment,
) -> _EpisodeRow:
    episode = assessment.episode
    return {
        "schema_version": _EPISODE_SCHEMA,
        "episode_id": _episode_id(symbol, assessment),
        "symbol": symbol,
        "liquidated_direction": episode.direction,
        "candidate_branch": _candidate_branch(episode.direction),
        "start_ms": episode.start_ms,
        "end_ms": episode.end_ms,
        "trade_count": episode.trade_count,
        "total_size": str(episode.total_size),
        "notional_usd": str(episode.notional_usd),
        "volume_weighted_price": str(episode.volume_weighted_price),
        "trailing_5s_notional_usd": str(episode.trailing_5s_notional_usd),
        "trailing_15s_notional_usd": str(episode.trailing_15s_notional_usd),
        "prior_episode_count": assessment.prior_episode_count,
        "threshold_5s_p95_usd": _decimal(assessment.threshold_5s_p95_usd),
        "threshold_5s_p99_usd": _decimal(assessment.threshold_5s_p99_usd),
        "threshold_15s_p95_usd": _decimal(assessment.threshold_15s_p95_usd),
        "threshold_15s_p99_usd": _decimal(assessment.threshold_15s_p99_usd),
        "eligible_arms": list(assessment.eligible_arms),
    }


def _episode_id(symbol: str, assessment: LiquidationBurstAssessment) -> str:
    episode = assessment.episode
    identity = "|".join(
        (
            _EPISODE_SCHEMA,
            symbol,
            episode.direction,
            str(episode.start_ms),
            str(episode.end_ms),
            str(episode.trade_count),
            str(episode.total_size),
            str(episode.notional_usd),
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _candidate_branch(direction: LiquidatedDirection) -> CandidateBranch:
    if direction == "short":
        return "continuation_long"
    return "exhaustion_reclaim_long"


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _source_manifest_evidence(
    bundles: tuple[Path, ...],
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for bundle in bundles:
        path = bundle / "manifest.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError(f"liquidation source manifest is not an object: {path}")
        records.append(
            {
                "path": str(path.resolve()),
                "requested_start": payload.get("requested_start"),
                "requested_end": payload.get("requested_end"),
                **file_evidence(path),
            }
        )
    return sorted(records, key=lambda row: str(row["requested_start"]))


def _manifest(
    symbol: str,
    observed_end_ms: int,
    observed_start_ms: int,
    lookback_ms: int,
    rows: tuple[_EpisodeRow, ...],
    sources: list[dict[str, object]],
    files: dict[str, dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA,
        "symbol": symbol,
        "report_only": True,
        "execution_authority": "none",
        "strategy_outcomes_inspected": False,
        "market_covariates_acquired": False,
        "contract": _contract(lookback_ms),
        "coverage": {
            "observed_start_ms": observed_start_ms,
            "observed_end_ms": observed_end_ms,
        },
        "counts": _counts(rows),
        "source_manifests": sources,
        "files": files,
    }


def _contract(lookback_ms: int) -> dict[str, object]:
    return {
        "same_direction_maximum_inter_fill_gap_ms": _EPISODE_GAP_MS,
        "trailing_windows_ms": [5_000, 15_000],
        "trailing_window_interval": "open_left_closed_right",
        "rolling_lookback_ms": lookback_ms,
        "percentiles": [95, 99],
        "percentile_method": "nearest_rank",
        "minimum_trade_count": _MINIMUM_TRADE_COUNT,
        "threshold_observations": "strictly_prior_same_direction_episodes",
    }


def _counts(rows: tuple[_EpisodeRow, ...]) -> dict[str, object]:
    eligible = tuple(row for row in rows if row["eligible_arms"])
    direction_counts, arm_counts = _published_composition(rows)
    return {
        "episodes": len(rows),
        "eligible_episodes": len(eligible),
        "by_liquidated_direction": direction_counts,
        "by_eligible_arm": arm_counts,
    }


def _published_composition(
    rows: tuple[Mapping[str, object], ...],
) -> tuple[dict[str, int], dict[str, int]]:
    directions: Counter[str] = Counter()
    arms: Counter[str] = Counter()
    for row in rows:
        direction = row.get("liquidated_direction")
        if direction not in {"long", "short"}:
            raise ValueError("published liquidated_direction is invalid")
        raw_arms = row.get("eligible_arms")
        if not isinstance(raw_arms, list) or any(arm not in _ARMS for arm in raw_arms):
            raise ValueError("published eligible_arms are invalid")
        directions[str(direction)] += 1
        arms.update(str(arm) for arm in raw_arms)
    return dict(sorted(directions.items())), dict(sorted(arms.items()))
