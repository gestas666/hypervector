#!/usr/bin/env python3
"""Publish an immutable replay of the deployed BTC source-follow mechanics."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import asdict
import json
from pathlib import Path
from typing import TypeVar

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.research.hypertrader_label_evidence import load_label_evidence
from hypervector.research.hypertrader_source_adapter import (
    load_hyperliquid_candles,
    resample_hyperliquid_5m,
)
from hypervector.research.source_follow_event_frequency import (
    SourceFollowFrequencyPolicy,
    audit_source_follow_event_frequency,
)
from hypervector.research.source_follow_live_shape_models import (
    SourceLiveShapeConfig,
    SourceLiveShapeFunding,
    SourceLiveShapeSignal,
    SourceSide,
)
from hypervector.research.source_follow_live_shape_replay import (
    replay_source_live_shape,
)
from hypervector.strategies.source_follow_profile import (
    SourceFollowHypervelocityProfile,
    load_source_follow_profile,
)

_STRATEGY_ID = "hypervelocity_source_follow_bidirectional_5m_v1"
_SYMBOL = "BTC"
_INITIAL_EQUITY = 500.0
_ENTRY_FEE_RATE = 0.00045
_TARGET_FEE_RATE = 0.00015
_MARKET_EXIT_FEE_RATE = 0.00045
_LIQUIDATION_PENALTY_RATE = 0.01
_ENTRY_SLIPPAGE_BPS = 2.0
_MARKET_EXIT_SLIPPAGE_BPS = 2.0
_BTC_SIZE_DECIMALS = 5
_T = TypeVar("_T")


def build_parser() -> argparse.ArgumentParser:
    """Return the report-only immutable replay CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort-config", type=Path, required=True)
    parser.add_argument("--source-profile", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--labels-metadata", type=Path, required=True)
    parser.add_argument("--candles", type=Path, required=True)
    parser.add_argument("--funding", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def build_report(args: argparse.Namespace) -> dict[str, object]:
    """Build one execution-incapable report from immutable venue inputs."""
    cohort = load_multi_asset_live_config(args.cohort_config, mode="observe")
    profile = load_source_follow_profile(args.source_profile)
    replay_config, deployed = _deployed_contract(cohort, profile, args.source_profile)
    evidence = load_label_evidence(args.labels, args.labels_metadata)
    if evidence.revision != profile.source_revision:
        raise ValueError(
            "source labels do not match the configured classifier revision"
        )
    labels = pd.read_parquet(args.labels)
    minute_bars, five_minute_bars = _load_candles(args.candles)
    signal_audit = audit_source_follow_event_frequency(
        labels,
        five_minute_bars,
        _frequency_policy(profile),
    )
    signals = _signals(signal_audit, five_minute_bars)
    funding = _load_funding(args.funding)
    replay = replay_source_live_shape(minute_bars, funding, signals, replay_config)
    return _report_payload(
        args,
        cohort,
        profile,
        deployed,
        evidence.files,
        signal_audit,
        replay.to_dict(),
    )


def _deployed_contract(
    cohort: MultiAssetLiveConfig,
    profile: SourceFollowHypervelocityProfile,
    profile_path: Path,
) -> tuple[SourceLiveShapeConfig, dict[str, object]]:
    provider = _single(
        [item for item in cohort.providers if item.strategy_id == _STRATEGY_ID],
        "source-follow provider",
    )
    asset = _single(
        [item for item in cohort.assets if item.symbol == _SYMBOL],
        "BTC asset",
    )
    if (
        provider.source_profile is None
        or provider.source_profile.resolve() != profile_path.resolve()
    ):
        raise ValueError("cohort source profile differs from the replay profile")
    execution = provider.execution
    _validate_execution_shape(execution.as_payload())
    config = SourceLiveShapeConfig(
        initial_equity=_INITIAL_EQUITY,
        margin_fraction=asset.margin_fraction,
        leverage=asset.leverage,
        venue_max_leverage=asset.venue_max_leverage,
        maximum_notional_usd=asset.max_notional_usd,
        stop_bps=float(execution.stop_bps),
        target_bps=float(execution.target_bps),
        maximum_hold_minutes=execution.maximum_hold_seconds // 60,
        entry_fee_rate=_ENTRY_FEE_RATE,
        target_fee_rate=_TARGET_FEE_RATE,
        market_exit_fee_rate=_MARKET_EXIT_FEE_RATE,
        liquidation_penalty_rate=_LIQUIDATION_PENALTY_RATE,
        entry_slippage_bps=_ENTRY_SLIPPAGE_BPS,
        market_exit_slippage_bps=_MARKET_EXIT_SLIPPAGE_BPS,
        size_decimals=_BTC_SIZE_DECIMALS,
    )
    return config, _contract_payload(cohort, profile, execution.as_payload(), config)


def _validate_execution_shape(value: Mapping[str, object]) -> None:
    expected = {
        "entry_liquidity": "taker_ioc",
        "stop_policy": "fixed_bps",
        "target_policy": "fixed_bps",
        "maximum_hold_seconds": 86_400,
        "safety_stop_overlay": True,
    }
    mismatches = {
        key: value.get(key)
        for key, wanted in expected.items()
        if value.get(key) != wanted
    }
    if mismatches or value.get("stop_bps") is None or value.get("target_bps") is None:
        raise ValueError(
            f"deployed source-follow execution shape is unsupported: {mismatches}"
        )


def _contract_payload(
    cohort: MultiAssetLiveConfig,
    profile: SourceFollowHypervelocityProfile,
    execution: Mapping[str, object],
    config: SourceLiveShapeConfig,
) -> dict[str, object]:
    return {
        "strategy_id": _STRATEGY_ID,
        "symbol": _SYMBOL,
        "cohort_profile_id": cohort.profile_id,
        "cohort_profile_fingerprint": cohort.profile_fingerprint,
        "source_profile_id": profile.profile_id,
        "source_revision": profile.source_revision,
        **execution,
        **asdict(config),
        "maximum_hold_seconds": config.maximum_hold_minutes * 60,
        "one_position_per_symbol": True,
    }


def _frequency_policy(
    profile: SourceFollowHypervelocityProfile,
) -> SourceFollowFrequencyPolicy:
    return SourceFollowFrequencyPolicy(
        minimum_confidence=profile.minimum_confidence,
        minimum_range_bps=profile.minimum_range_bps,
        maximum_range_bps=profile.maximum_range_bps,
    )


def _load_candles(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.read_parquet(path)
    required = {"timestamp", "open", "high", "low", "close", "volume", "source"}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise ValueError(f"source replay candles missing columns: {missing}")
    sources = set(raw["source"].astype(str))
    if not sources.issubset({"hl", "hl_gap_fill"}):
        raise ValueError(
            f"source replay candles contain unsupported sources: {sorted(sources)}"
        )
    minute = raw.loc[:, list(required)].copy()
    five_minute = resample_hyperliquid_5m(load_hyperliquid_candles((path,)))
    return minute, five_minute


def _signals(
    audit: Mapping[str, object],
    five_minute_bars: pd.DataFrame,
) -> tuple[SourceLiveShapeSignal, ...]:
    raw_events = audit.get("events")
    if not isinstance(raw_events, list):
        raise ValueError("source event audit is missing event rows")
    signals: list[SourceLiveShapeSignal] = []
    for value in raw_events:
        if not isinstance(value, Mapping):
            raise ValueError("source event row must be an object")
        label_time = pd.Timestamp(value.get("label_time_utc"))
        reference = float(five_minute_bars.loc[label_time, "close"])
        signals.append(
            SourceLiveShapeSignal(
                pd.Timestamp(value.get("available_at_utc")),
                _side(value.get("direction")),
                reference,
                float(value.get("confidence")),
                float(value.get("range_bps")),
            )
        )
    return tuple(signals)


def _load_funding(path: Path) -> tuple[SourceLiveShapeFunding, ...]:
    frame = pd.read_parquet(path)
    required = {"timestamp", "funding_rate", "source"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"source replay funding missing columns: {missing}")
    if not frame["source"].astype(str).eq("hl_funding_history").all():
        raise ValueError("source replay funding contains a non-Hyperliquid source")
    timestamps = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True))
    if timestamps.has_duplicates or not timestamps.is_monotonic_increasing:
        raise ValueError("source replay funding timestamps must be ordered and unique")
    cadence = timestamps.to_series(index=range(len(timestamps))).diff().dropna()
    if not cadence.eq(pd.Timedelta(hours=1)).all():
        raise ValueError("source replay funding must have complete hourly cadence")
    return tuple(
        SourceLiveShapeFunding(timestamp, float(rate))
        for timestamp, rate in zip(timestamps, frame["funding_rate"], strict=True)
    )


def _report_payload(
    args: argparse.Namespace,
    cohort: MultiAssetLiveConfig,
    profile: SourceFollowHypervelocityProfile,
    deployed: dict[str, object],
    label_evidence: Mapping[str, object],
    signal_audit: dict[str, object],
    replay: dict[str, object],
) -> dict[str, object]:
    audit_summary = {
        key: value for key, value in signal_audit.items() if key != "events"
    }
    return {
        "schema_version": 1,
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "performance_gate": False,
        "balance_gate": False,
        "strategy_id": _STRATEGY_ID,
        "symbol": _SYMBOL,
        "deployed_contract": deployed,
        "signal_audit": audit_summary,
        "replay": replay,
        "interpretation": {
            "friction_shape": "deployed_runtime_shape",
            "promotion_authority": "none",
            "profit_forecast": False,
            "edge_conclusion": "descriptive_historical_replay_only",
        },
        "evidence": {
            **label_evidence,
            "cohort_config": file_evidence(args.cohort_config),
            "source_profile": file_evidence(args.source_profile),
            "candles": file_evidence(args.candles),
            "funding": file_evidence(args.funding),
        },
        "identity": {
            "cohort_profile_id": cohort.profile_id,
            "source_profile_id": profile.profile_id,
            "source_revision": profile.source_revision,
        },
    }


def _side(value: object) -> SourceSide:
    if value == "long" or value == "short":
        return value
    raise ValueError(f"source event direction is unsupported: {value!r}")


def _single(values: Sequence[_T], label: str) -> _T:
    if len(values) != 1:
        raise ValueError(f"cohort config requires exactly one {label}")
    return values[0]


def publish(args: argparse.Namespace) -> dict[str, object]:
    """Write one immutable report without execution authority."""
    if args.out.exists():
        raise FileExistsError(f"immutable replay output exists: {args.out}")
    report = build_report(args)
    write_immutable_json(args.out, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Publish the replay and print only its report-only summary."""
    args = build_parser().parse_args(argv)
    report = publish(args)
    replay = report.get("replay")
    if not isinstance(replay, Mapping):
        raise RuntimeError("published replay is missing its summary")
    print(
        json.dumps(
            {
                "out": str(args.out),
                "completed_trades": replay["completed_trades"],
                "net_pnl_usd": replay["net_pnl_usd"],
                "profit_factor": replay["profit_factor"],
                "execution_authority": report["execution_authority"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
