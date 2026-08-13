#!/usr/bin/env python3
"""Generate report-only BTC 5m labels with the pinned Hypertrader classifier."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections import deque
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Protocol, cast

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from hypervector.data.oxa_storage import (  # noqa: E402
    file_evidence,
    write_immutable_json,
)
from hypervector.research.hypertrader_source_adapter import (  # noqa: E402
    SOURCE_HASHES_BY_REVISION,
    PINNED_HYPERTRADER_REVISION,
    extract_selective_recipe_events,
    load_hyperliquid_candle_segments,
    load_hyperliquid_candles,
    resample_hyperliquid_5m,
    source_hashes_for_revision,
    verify_source_files,
)
from hypervector.research.hypertrader_label_checkpoint import (  # noqa: E402
    seed_label_state as _seed_state,
)
from hypervector.research.research_database_replay import (  # noqa: E402
    canonical_trade_bars,
)


class _Config(Protocol):
    warmup_bars: int
    confirmation_bars: int
    min_duration_bars: int
    breakout_confirmation_bars: int
    breakout_ttl_bars: int
    breakout_cooldown_bars: int


class _Regime(Protocol):
    primary: object
    secondary: str | None
    confidence: float
    indicators: Mapping[str, object]


class _Classifier(Protocol):
    def classify(self, bar: object, history: list[object]) -> _Regime: ...


class _StateMachine(Protocol):
    current: _Regime | None
    pending: _Regime | None
    pending_count: int
    transition_blocked_until: float
    _breakout_expires_at: float
    _breakout_cooldown_until: float
    _pre_breakout: _Regime | None

    def update(self, regime: _Regime) -> _Regime | None: ...


class _UpstreamComponents:
    """Pinned source constructors needed for deterministic offline labeling."""

    def __init__(
        self,
        classifier_factory: Callable[..., object],
        state_factory: Callable[..., object],
        bar_factory: Callable[..., object],
        regime_factory: Callable[..., object],
        primary_factory: Callable[[str], object],
        config: _Config,
    ) -> None:
        self.classifier_factory = classifier_factory
        self.state_factory = state_factory
        self.bar_factory = bar_factory
        self.regime_factory = regime_factory
        self.primary_factory = primary_factory
        self.config = config


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-backend", type=Path, required=True)
    parser.add_argument(
        "--source-revision",
        choices=tuple(SOURCE_HASHES_BY_REVISION),
        default=PINNED_HYPERTRADER_REVISION,
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--bars", type=Path, action="append")
    source.add_argument("--research-database", type=Path)
    parser.add_argument("--start", type=_utc_datetime)
    parser.add_argument("--end", type=_utc_datetime)
    parser.add_argument("--prior-labels", type=Path)
    parser.add_argument(
        "--reset-at-gaps",
        action="store_true",
        help="split native candles at gaps and rewarm each segment independently",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--metadata-out", type=Path, required=True)
    return parser


def _utc_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid UTC timestamp: {value}") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset or Z")
    return parsed.astimezone(UTC)


def _experiment_contract(
    source_revision: str = PINNED_HYPERTRADER_REVISION,
) -> dict[str, object]:
    return {
        "upstream_revision": source_revision,
        "report_only": True,
        "runtime_strategy_changed": False,
        "timeframe": "5m",
        "decision_delay_seconds": 300,
        "model_authority": "observe",
    }


def _module(name: str) -> ModuleType:
    return importlib.import_module(name)


def _isolate_regime_namespace(backend: Path) -> None:
    package_paths = {
        "app": backend / "app",
        "app.services": backend / "app" / "services",
        "app.services.regime": backend / "app" / "services" / "regime",
    }
    loaded = [name for name in sys.modules if name.startswith("app.services.regime")]
    if loaded:
        raise RuntimeError("Hypertrader regime modules are already loaded")
    for name, path in package_paths.items():
        module = ModuleType(name)
        module.__path__ = [str(path)]  # type: ignore[attr-defined]
        sys.modules[name] = module


def _upstream_components(
    backend: Path,
) -> _UpstreamComponents:
    backend_text = str(backend.resolve())
    if backend_text not in sys.path:
        sys.path.insert(0, backend_text)
    _isolate_regime_namespace(backend.resolve())
    classifier_module = _module("app.services.regime.classifier")
    config_module = _module("app.services.regime.config")
    models_module = _module("app.services.regime.models")
    state_module = _module("app.services.regime.state")
    config = cast(_Config, config_module.COIN_CONFIGS["BTC"])
    return _UpstreamComponents(
        classifier_factory=cast(
            Callable[..., object], classifier_module.SecondaryClassifier
        ),
        state_factory=cast(Callable[..., object], state_module.RegimeStateMachine),
        bar_factory=cast(Callable[..., object], models_module.BarData),
        regime_factory=cast(Callable[..., object], models_module.MarketRegime),
        primary_factory=cast(Callable[[str], object], models_module.PrimaryRegime),
        config=config,
    )


def _enum_text(value: object) -> str:
    return str(getattr(value, "value", value))


def _label_row(
    timestamp: pd.Timestamp,
    raw: _Regime,
    confirmed: _Regime | None,
) -> dict[str, object]:
    effective = confirmed
    indicators = {} if effective is None else effective.indicators
    return {
        "timestamp": timestamp,
        "available_at": timestamp + pd.Timedelta(minutes=5),
        "primary_code": "UNKNOWN"
        if effective is None
        else _enum_text(effective.primary),
        "secondary_code": None if effective is None else effective.secondary,
        "confidence": 0.0 if effective is None else float(effective.confidence),
        "raw_primary_code": _enum_text(raw.primary),
        "raw_secondary_code": raw.secondary,
        "raw_confidence": float(raw.confidence),
        "volume_ratio": indicators.get("volume_ratio"),
    }


def _new_state(components: _UpstreamComponents) -> _StateMachine:
    config = components.config
    return cast(
        _StateMachine,
        components.state_factory(
            confirmation_bars=config.confirmation_bars,
            min_duration_bars=config.min_duration_bars,
            coin="BTC",
            breakout_confirmation_bars=config.breakout_confirmation_bars,
            breakout_ttl_bars=config.breakout_ttl_bars,
            breakout_cooldown_bars=config.breakout_cooldown_bars,
            enable_hooks=False,
        ),
    )


def _generate_labels(
    bars: pd.DataFrame,
    components: _UpstreamComponents,
    prior: pd.DataFrame | None = None,
    output_start: pd.Timestamp | None = None,
) -> pd.DataFrame:
    config = components.config
    classifier = cast(_Classifier, components.classifier_factory(config))
    state = cast(_StateMachine, _new_state(components))
    if prior is not None and output_start is not None:
        _seed_state(
            state,
            prior,
            config,
            components.regime_factory,
            components.primary_factory,
            output_start,
        )
    history: deque[object] = deque(maxlen=config.warmup_bars)
    rows: list[dict[str, object]] = []
    for timestamp, values in bars.iterrows():
        stamp = pd.Timestamp(timestamp).tz_convert("UTC")
        bar = components.bar_factory(
            coin="BTC",
            timeframe="5m",
            timestamp_ms=int(stamp.timestamp() * 1000),
            open=float(values["open"]),
            high=float(values["high"]),
            low=float(values["low"]),
            close=float(values["close"]),
            volume=float(values["volume"]),
        )
        history.append(bar)
        if output_start is not None and stamp < output_start:
            continue
        raw = classifier.classify(bar, list(history))
        confirmed = state.update(raw)
        rows.append(_label_row(stamp, raw, confirmed))
    frame = pd.DataFrame(rows)
    frame.index = pd.DatetimeIndex(frame.pop("timestamp"))
    if prior is None:
        return frame
    if frame.empty or prior.index[-1] >= frame.index[0]:
        raise ValueError("prior and incremental labels must be non-overlapping")
    return pd.concat([prior, frame])


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    payload = json.loads(frame.to_json(orient="records", date_format="iso"))
    if not isinstance(payload, list):
        raise RuntimeError("Hypertrader recipe event serialization failed")
    return payload


def _write_outputs(
    args: argparse.Namespace,
    labels: pd.DataFrame,
    source_evidence: dict[str, object],
    input_evidence: list[dict[str, object]],
    segmentation: list[dict[str, object]] | None = None,
) -> None:
    if args.out.exists() or args.metadata_out.exists():
        raise FileExistsError("Hypertrader label output already exists")
    events = extract_selective_recipe_events(labels)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    published = False
    try:
        labels.to_parquet(args.out)
        metadata = {
            **_experiment_contract(str(source_evidence["revision"])),
            "source": source_evidence,
            "inputs": input_evidence,
            "cadence_policy": (
                "continuous" if segmentation is None else "reset_at_native_gap"
            ),
            "requested_window": None
            if getattr(args, "start", None) is None
            or getattr(args, "end", None) is None
            else {
                "start_utc": args.start.isoformat(),
                "end_utc": args.end.isoformat(),
            },
            "segments": [] if segmentation is None else segmentation,
            "gap_resets": 0 if segmentation is None else max(len(segmentation) - 1, 0),
            "incremental_checkpoint": None
            if getattr(args, "prior_labels", None) is None
            else cast(datetime, args.start).isoformat(),
            "output": file_evidence(args.out),
            "bars": len(labels),
            "confirmed_bars": int(labels["primary_code"].ne("UNKNOWN").sum()),
            "primary_distribution": labels["primary_code"].value_counts().to_dict(),
            "recipe_event_count": len(events),
            "recipe_events": _records(events),
        }
        write_immutable_json(args.metadata_out, metadata)
        published = True
    finally:
        if not published:
            args.out.unlink(missing_ok=True)
            args.metadata_out.unlink(missing_ok=True)


def _database_bars(
    args: argparse.Namespace,
    warmup_bars: int,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    path = cast(Path | None, args.research_database)
    start = cast(datetime | None, args.start)
    end = cast(datetime | None, args.end)
    if path is None or start is None or end is None:
        raise ValueError(
            "database labels require --research-database, --start, and --end"
        )
    query_start = start
    if args.prior_labels is not None:
        query_start -= timedelta(minutes=5 * (warmup_bars - 1))
    bars = canonical_trade_bars(path, "BTC", query_start, end)
    expected = pd.date_range(query_start, end, freq="5min", inclusive="left")
    if not bars.index.equals(expected):
        missing = expected.difference(bars.index)
        raise ValueError(
            f"canonical trade bars are not contiguous; missing={len(missing)}"
        )
    return bars.loc[:, ["open", "high", "low", "close", "volume"]], [
        {
            "data_source": "duckdb_canonical_public_trades",
            "window_start_utc": query_start.isoformat(),
            "window_end_utc": end.isoformat(),
            "decision_window_start_utc": start.isoformat(),
            **file_evidence(path),
        }
    ]


def _input_bars(
    args: argparse.Namespace,
    warmup_bars: int,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    if args.research_database is not None:
        return _database_bars(args, warmup_bars)
    if args.prior_labels is not None:
        raise ValueError("--prior-labels requires --research-database")
    if args.start is not None or args.end is not None:
        raise ValueError("--start and --end are only valid with --research-database")
    paths = cast(list[Path], args.bars)
    candles = load_hyperliquid_candles(paths)
    return resample_hyperliquid_5m(candles), [file_evidence(path) for path in paths]


def _segmented_input(
    args: argparse.Namespace,
) -> tuple[tuple[pd.DataFrame, ...], list[dict[str, object]]]:
    if args.research_database is not None:
        raise ValueError("--reset-at-gaps requires --bars")
    if args.prior_labels is not None:
        raise ValueError("--reset-at-gaps does not support --prior-labels")
    bounds = _segmented_bounds(args)
    paths = cast(list[Path], args.bars)
    segments = tuple(
        resample_hyperliquid_5m(frame)
        for frame in load_hyperliquid_candle_segments(paths)
    )
    if bounds is not None:
        segments = _clip_segments(segments, *bounds)
    return segments, [file_evidence(path) for path in paths]


def _segmented_bounds(
    args: argparse.Namespace,
) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    start = cast(datetime | None, args.start)
    end = cast(datetime | None, args.end)
    if start is None and end is None:
        return None
    if start is None or end is None:
        raise ValueError("--reset-at-gaps requires both --start and --end")
    if end <= start:
        raise ValueError("segmented label end must follow start")
    if any(
        value.minute % 5 or value.second or value.microsecond for value in (start, end)
    ):
        raise ValueError("segmented label bounds must be five-minute aligned")
    return pd.Timestamp(start), pd.Timestamp(end)


def _clip_segments(
    segments: tuple[pd.DataFrame, ...],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[pd.DataFrame, ...]:
    clipped = tuple(
        frame.loc[(frame.index >= start) & (frame.index < end)] for frame in segments
    )
    clipped = tuple(frame for frame in clipped if not frame.empty)
    if not clipped:
        raise ValueError("native candle segments do not overlap the requested window")
    if clipped[0].index[0] != start:
        raise ValueError("native candle segments do not cover the requested start")
    expected_last = end - pd.Timedelta(minutes=5)
    if clipped[-1].index[-1] != expected_last:
        raise ValueError("native candle segments do not cover the requested end")
    return clipped


def _generate_segmented_labels(
    segments: tuple[pd.DataFrame, ...],
    components: _UpstreamComponents,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    labels = tuple(_generate_labels(frame, components) for frame in segments)
    combined = pd.concat(labels).sort_index(kind="stable")
    if not combined.index.is_unique:
        raise ValueError("segmented labels contain overlapping timestamps")
    metadata = [
        _segment_metadata(bars, segment_labels, components.config.warmup_bars)
        for bars, segment_labels in zip(segments, labels, strict=True)
    ]
    return combined, metadata


def _segment_metadata(
    bars: pd.DataFrame,
    labels: pd.DataFrame,
    warmup_bars: int,
) -> dict[str, object]:
    confirmed = labels["primary_code"].ne("UNKNOWN")
    first_confirmed = (
        labels.index[confirmed][0].isoformat() if confirmed.any() else None
    )
    return {
        "start_utc": bars.index[0].isoformat(),
        "end_exclusive_utc": (bars.index[-1] + pd.Timedelta(minutes=5)).isoformat(),
        "bars": len(bars),
        "warmup_bars": warmup_bars,
        "confirmed_bars": int(confirmed.sum()),
        "first_confirmed_utc": first_confirmed,
    }


def _prior_labels(args: argparse.Namespace) -> pd.DataFrame | None:
    path = cast(Path | None, args.prior_labels)
    if path is None:
        return None
    if args.start is None:
        raise ValueError("--prior-labels requires --start")
    labels = pd.read_parquet(path)
    if not isinstance(labels.index, pd.DatetimeIndex):
        raise ValueError("prior label artifact must use a DatetimeIndex")
    return labels


def main(argv: list[str] | None = None) -> int:
    """Validate pinned source, generate labels, and retain immutable evidence."""
    args = _parser().parse_args(argv)
    expected_hashes = source_hashes_for_revision(args.source_revision)
    source_evidence = verify_source_files(
        args.upstream_backend,
        expected_hashes=expected_hashes,
        revision=args.source_revision,
    )
    components = _upstream_components(args.upstream_backend)
    segmentation = None
    if args.reset_at_gaps:
        segments, input_evidence = _segmented_input(args)
        labels, segmentation = _generate_segmented_labels(segments, components)
    else:
        bars, input_evidence = _input_bars(args, components.config.warmup_bars)
        prior = _prior_labels(args)
        output_start = None if args.start is None else pd.Timestamp(args.start)
        labels = _generate_labels(bars, components, prior, output_start)
    if args.prior_labels is not None:
        input_evidence.append(file_evidence(args.prior_labels))
    _write_outputs(args, labels, source_evidence, input_evidence, segmentation)
    print(f"wrote labels={args.out} metadata={args.metadata_out} bars={len(labels)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
