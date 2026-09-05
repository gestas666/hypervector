"""Outcome-blind BTC liquidation treatment-episode construction."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
import json
from pathlib import Path
from typing import Literal

from hypervector.data.oxa_api import parse_utc_timestamp_ms, positive_decimal
from hypervector.data.oxa_storage import open_text_reader, verify_file_evidence

LiquidatedDirection = Literal["long", "short"]
BurstArm = Literal["5s_p95", "5s_p99", "15s_p95", "15s_p99"]
_MAX_EPISODE_GAP_MS = 2_000
_NORMALIZATION_VERSION = "explicit_vendor_direction_v2"
_SOURCE = "0xarchive_hyperliquid_liquidations"


@dataclass(frozen=True)
class LiquidationLabel:
    """One normalized liquidation treatment label."""

    ts_exchange_ms: int
    direction: LiquidatedDirection
    price: Decimal
    size: Decimal
    trade_id: int

    @property
    def notional_usd(self) -> Decimal:
        """Return exact price-times-size notional."""
        return self.price * self.size


@dataclass(frozen=True)
class LiquidationEpisode:
    """One same-direction cluster of causally observed liquidation labels."""

    direction: LiquidatedDirection
    start_ms: int
    end_ms: int
    trade_count: int
    total_size: Decimal
    notional_usd: Decimal
    trailing_5s_notional_usd: Decimal
    trailing_15s_notional_usd: Decimal

    @property
    def volume_weighted_price(self) -> Decimal:
        """Return the exact-decimal episode notional divided by total size."""
        return self.notional_usd / self.total_size


@dataclass(frozen=True)
class _LoadedBundle:
    start_ms: int
    end_ms: int
    labels: tuple[LiquidationLabel, ...]


@dataclass(frozen=True)
class LiquidationBurstAssessment:
    """Strictly prior rolling burst thresholds for one treatment episode."""

    episode: LiquidationEpisode
    prior_episode_count: int
    threshold_5s_p95_usd: Decimal | None
    threshold_5s_p99_usd: Decimal | None
    threshold_15s_p95_usd: Decimal | None
    threshold_15s_p99_usd: Decimal | None
    eligible_arms: tuple[BurstArm, ...]


class _RankWindow:
    def __init__(self, values: tuple[Decimal, ...]) -> None:
        self._values = tuple(sorted(set(values)))
        self._indexes = {value: index + 1 for index, value in enumerate(self._values)}
        self._tree = [0] * (len(self._values) + 1)
        self.count = 0

    def add(self, value: Decimal) -> None:
        self._change(value, 1)

    def remove(self, value: Decimal) -> None:
        self._change(value, -1)

    def nearest_rank(self, percentile: int) -> Decimal | None:
        if self.count == 0:
            return None
        rank = (percentile * self.count + 99) // 100
        index = 0
        bit = 1 << (len(self._values).bit_length() - 1)
        while bit:
            candidate = index + bit
            if candidate < len(self._tree) and self._tree[candidate] < rank:
                index = candidate
                rank -= self._tree[candidate]
            bit >>= 1
        return self._values[index]

    def _change(self, value: Decimal, delta: int) -> None:
        index = self._indexes[value]
        while index < len(self._tree):
            self._tree[index] += delta
            index += index & -index
        self.count += delta


def assess_rolling_bursts(
    episodes: tuple[LiquidationEpisode, ...],
    *,
    source_start_ms: int,
    lookback_ms: int = 30 * 24 * 60 * 60 * 1_000,
) -> tuple[LiquidationBurstAssessment, ...]:
    """Apply exact prior-window p95/p99 arms without strategy outcomes."""
    if lookback_ms <= 0:
        raise ValueError("liquidation burst lookback_ms must be positive")
    if any(row.start_ms < source_start_ms for row in episodes):
        raise ValueError("liquidation episode precedes source coverage")
    assessments = [
        assessment
        for direction in ("long", "short")
        for assessment in _assess_direction(
            tuple(row for row in episodes if row.direction == direction),
            source_start_ms,
            lookback_ms,
        )
    ]
    return tuple(
        sorted(
            assessments, key=lambda row: (row.episode.start_ms, row.episode.direction)
        )
    )


def _assess_direction(
    episodes: tuple[LiquidationEpisode, ...],
    source_start_ms: int,
    lookback_ms: int,
) -> list[LiquidationBurstAssessment]:
    five = _RankWindow(tuple(row.trailing_5s_notional_usd for row in episodes))
    fifteen = _RankWindow(tuple(row.trailing_15s_notional_usd for row in episodes))
    output: list[LiquidationBurstAssessment] = []
    left = 0
    for index, episode in enumerate(episodes):
        boundary = episode.end_ms - lookback_ms
        while left < index and episodes[left].end_ms < boundary:
            five.remove(episodes[left].trailing_5s_notional_usd)
            fifteen.remove(episodes[left].trailing_15s_notional_usd)
            left += 1
        complete = episode.end_ms - source_start_ms >= lookback_ms and five.count > 0
        thresholds = _thresholds(five, fifteen, complete)
        output.append(
            LiquidationBurstAssessment(
                episode,
                index - left,
                *thresholds,
                _eligible_arms(episode, thresholds),
            )
        )
        five.add(episode.trailing_5s_notional_usd)
        fifteen.add(episode.trailing_15s_notional_usd)
    return output


def _thresholds(
    five: _RankWindow,
    fifteen: _RankWindow,
    complete: bool,
) -> tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None]:
    if not complete:
        return None, None, None, None
    return (
        five.nearest_rank(95),
        five.nearest_rank(99),
        fifteen.nearest_rank(95),
        fifteen.nearest_rank(99),
    )


def _eligible_arms(
    episode: LiquidationEpisode,
    thresholds: tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None],
) -> tuple[BurstArm, ...]:
    candidates: tuple[tuple[BurstArm, Decimal, Decimal | None], ...] = (
        ("5s_p95", episode.trailing_5s_notional_usd, thresholds[0]),
        ("5s_p99", episode.trailing_5s_notional_usd, thresholds[1]),
        ("15s_p95", episode.trailing_15s_notional_usd, thresholds[2]),
        ("15s_p99", episode.trailing_15s_notional_usd, thresholds[3]),
    )
    if episode.trade_count < 3:
        return ()
    return tuple(
        arm
        for arm, value, threshold in candidates
        if threshold is not None and value >= threshold
    )


def load_liquidation_bundles(
    bundles: tuple[Path, ...],
    *,
    symbol: str,
) -> tuple[LiquidationLabel, ...]:
    """Verify, order, and merge immutable liquidation normalization bundles."""
    if not bundles:
        raise ValueError("at least one liquidation bundle is required")
    loaded = sorted(
        (_load_bundle(path, symbol) for path in bundles),
        key=lambda row: row.start_ms,
    )
    for prior, current in zip(loaded, loaded[1:]):
        if prior.end_ms != current.start_ms:
            raise ValueError("liquidation bundle windows must be contiguous")
    labels = tuple(row for bundle in loaded for row in bundle.labels)
    _validate_labels(labels)
    return labels


def _load_bundle(path: Path, symbol: str) -> _LoadedBundle:
    manifest = _mapping(
        json.loads((path / "manifest.json").read_text(encoding="utf-8")),
        "liquidation manifest",
    )
    if manifest.get("schema_version") != 2:
        raise ValueError("liquidation manifest schema_version must be 2")
    if manifest.get("normalization_version") != _NORMALIZATION_VERSION:
        raise ValueError("liquidation normalization version is unsupported")
    if manifest.get("source") != _SOURCE or manifest.get("symbol") != symbol:
        raise ValueError("liquidation manifest source or symbol is inconsistent")
    if (
        manifest.get("complete") is not True
        or manifest.get("continuation_cursor") is not None
    ):
        raise ValueError("liquidation bundle must be complete")
    verify_file_evidence(path, manifest.get("files"))
    start_ms = parse_utc_timestamp_ms(
        _text(manifest.get("requested_start"), "requested_start"),
        label="liquidation requested_start",
    )
    end_ms = parse_utc_timestamp_ms(
        _text(manifest.get("requested_end"), "requested_end"),
        label="liquidation requested_end",
    )
    labels = _load_rows(path / "liquidations.jsonl.gz", symbol, start_ms, end_ms)
    if len(labels) != _integer(manifest.get("event_count"), "event_count"):
        raise ValueError("liquidation manifest event_count mismatch")
    return _LoadedBundle(start_ms, end_ms, labels)


def _load_rows(
    path: Path,
    symbol: str,
    start_ms: int,
    end_ms: int,
) -> tuple[LiquidationLabel, ...]:
    labels: list[LiquidationLabel] = []
    with open_text_reader(path) as handle:
        for line in handle:
            labels.append(_parse_label(json.loads(line), symbol, start_ms, end_ms))
    return tuple(labels)


def _parse_label(
    value: object,
    symbol: str,
    start_ms: int,
    end_ms: int,
) -> LiquidationLabel:
    row = _mapping(value, "liquidation row")
    if row.get("source") != _SOURCE or row.get("symbol") != symbol:
        raise ValueError("liquidation row source or symbol is inconsistent")
    if row.get("normalization_version") != _NORMALIZATION_VERSION:
        raise ValueError("liquidation row normalization version is unsupported")
    timestamp = _integer(row.get("ts_exchange_ms"), "ts_exchange_ms")
    if not start_ms <= timestamp < end_ms:
        raise ValueError("liquidation row is outside its half-open bundle window")
    direction = _direction(row.get("liquidated_direction"))
    price = positive_decimal(_text(row.get("price"), "price"), label="price")
    size = positive_decimal(_text(row.get("size"), "size"), label="size")
    notional = positive_decimal(
        _text(row.get("notional_usd"), "notional_usd"), label="notional_usd"
    )
    if notional != price * size:
        raise ValueError("liquidation row notional does not equal price times size")
    trade_id = _integer(row.get("trade_id"), "trade_id")
    return LiquidationLabel(timestamp, direction, price, size, trade_id)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be nonempty text")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _direction(value: object) -> LiquidatedDirection:
    if value == "long":
        return "long"
    if value == "short":
        return "short"
    raise ValueError("liquidated_direction must be long or short")


def build_liquidation_episodes(
    labels: tuple[LiquidationLabel, ...],
) -> tuple[LiquidationEpisode, ...]:
    """Cluster labels by direction with a two-second maximum inter-fill gap."""
    _validate_labels(labels)
    episodes = [
        episode
        for direction in ("long", "short")
        for episode in _direction_episodes(labels, direction)
    ]
    return tuple(sorted(episodes, key=lambda row: (row.start_ms, row.direction)))


def _validate_labels(labels: tuple[LiquidationLabel, ...]) -> None:
    trade_ids = [row.trade_id for row in labels]
    if len(trade_ids) != len(set(trade_ids)):
        raise ValueError("duplicate liquidation trade_id")
    keys = [(row.ts_exchange_ms, row.trade_id) for row in labels]
    if keys != sorted(keys):
        raise ValueError("liquidation labels must be chronological")


def _direction_episodes(
    labels: tuple[LiquidationLabel, ...],
    direction: LiquidatedDirection,
) -> list[LiquidationEpisode]:
    rows = [row for row in labels if row.direction == direction]
    episodes: list[LiquidationEpisode] = []
    for row in rows:
        if (
            not episodes
            or row.ts_exchange_ms - episodes[-1].end_ms > _MAX_EPISODE_GAP_MS
        ):
            episodes.append(
                LiquidationEpisode(
                    direction,
                    row.ts_exchange_ms,
                    row.ts_exchange_ms,
                    1,
                    row.size,
                    row.notional_usd,
                    Decimal(),
                    Decimal(),
                )
            )
            continue
        previous = episodes[-1]
        episodes[-1] = LiquidationEpisode(
            direction,
            previous.start_ms,
            row.ts_exchange_ms,
            previous.trade_count + 1,
            previous.total_size + row.size,
            previous.notional_usd + row.notional_usd,
            Decimal(),
            Decimal(),
        )
    trailing_5s = _trailing_notionals(rows, episodes, 5_000)
    trailing_15s = _trailing_notionals(rows, episodes, 15_000)
    return [
        LiquidationEpisode(
            row.direction,
            row.start_ms,
            row.end_ms,
            row.trade_count,
            row.total_size,
            row.notional_usd,
            trailing_5s[index],
            trailing_15s[index],
        )
        for index, row in enumerate(episodes)
    ]


def _trailing_notionals(
    labels: list[LiquidationLabel],
    episodes: list[LiquidationEpisode],
    window_ms: int,
) -> list[Decimal]:
    totals: list[Decimal] = []
    left = 0
    right = 0
    running = Decimal()
    for episode in episodes:
        while right < len(labels) and labels[right].ts_exchange_ms <= episode.end_ms:
            running += labels[right].notional_usd
            right += 1
        boundary = episode.end_ms - window_ms
        while left < right and labels[left].ts_exchange_ms <= boundary:
            running -= labels[left].notional_usd
            left += 1
        totals.append(running)
    return totals
