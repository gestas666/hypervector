#!/usr/bin/env python3
"""Compare Apex cohort artifacts through one immutable shared balance."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Mapping, Sequence

from hypervector.research.apex_cohort_portfolio import (
    ApexAttributedOutcome,
    replay_apex_cohort,
)


_SCHEMA_VERSION = "apex_cohort_shared_compare_v1"
_MM_RESERVED_MARGIN_USD = 500.0


def _parser() -> argparse.ArgumentParser:
    """Build the immutable two-artifact comparison command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directional", type=Path)
    parser.add_argument("--market-maker", required=True, type=Path)
    parser.add_argument("--hulk", type=Path)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--out", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Replay directional trades and market-maker sessions together."""
    args = _parser().parse_args(argv)
    output = Path(args.out)
    if output.exists():
        raise FileExistsError(f"Apex shared output exists: {output}")
    directional_path = Path(args.directional) if args.directional is not None else None
    market_maker_path = Path(args.market_maker)
    directional = _payload(directional_path) if directional_path is not None else None
    market_maker = _payload(market_maker_path)
    hulk_path = Path(args.hulk) if args.hulk is not None else None
    hulk = _payload(hulk_path) if hulk_path is not None else None
    payloads = (
        *((directional,) if directional is not None else ()),
        market_maker,
        *((hulk,) if hulk is not None else ()),
    )
    segment = _matching_segment(*payloads)
    raw_outcomes = (
        *(_directional_outcomes(directional) if directional is not None else ()),
        *_market_maker_outcomes(market_maker),
        *(_hulk_outcomes(hulk) if hulk is not None else ()),
    )
    window = _common_window(args.start, args.end, hulk is not None)
    outcomes, excluded = _bounded_outcomes(raw_outcomes, window)
    report = replay_apex_cohort(outcomes)
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "segment": segment,
        "report_only": report.report_only,
        "execution_authority": report.execution_authority,
        "place_attempted": report.place_attempted,
        "input_identity": _input_identity(
            directional_path, market_maker_path, hulk_path
        ),
        "comparison_window": _window_payload(window, excluded),
        "portfolio": asdict(report),
        "assumptions": {
            "candidate_priority": [
                "hulk_expansion_short_robust_v3",
                "apex_regime_mm_v2",
                "apex_oi_trend_v2",
                "apex_mean_reversion_v2",
            ],
            "market_maker_reserved_margin_usd": _MM_RESERVED_MARGIN_USD,
            "fee_timing": "reported_total_trade_or_session_fee_reserved_at_entry",
            "same_bar_hulk_exit_ordering": "entry_timestamp_plus_one_millisecond",
        },
        "limitations": [
            "completed outcomes cannot reconstruct intratrade shared-equity drawdown",
            "all reported fees are conservatively reserved at entry for conflict accounting",
            "observer-only OI trend produces no capital intent",
            "an active market-maker session cannot be partially preempted from completed outcomes",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote report-only Apex shared artifact: {output}")
    return 0


def _directional_outcomes(
    payload: Mapping[str, object],
) -> tuple[ApexAttributedOutcome, ...]:
    if _text(payload, "candidate") != "apex_mean_reversion_v2":
        raise ValueError("directional artifact has the wrong candidate")
    result = _mapping(payload, "result")
    metrics = _mapping(result, "metrics")
    trades = _list(metrics, "trades")
    output = []
    for index, value in enumerate(trades):
        trade = _mapping_value(value, "directional trade")
        output.append(
            ApexAttributedOutcome(
                f"mr-{index:06d}",
                "apex_mean_reversion_v2",
                "BTC",
                _timestamp_ms(_text(trade, "entry_time_utc")),
                _timestamp_ms(_text(trade, "exit_time_utc")),
                _number(trade, "margin_usd"),
                _number(trade, "fees_usd"),
                _number(trade, "net_pnl_usd"),
            )
        )
    return tuple(output)


def _market_maker_outcomes(
    payload: Mapping[str, object],
) -> tuple[ApexAttributedOutcome, ...]:
    if _text(payload, "candidate") != "apex_regime_mm_v2":
        raise ValueError("market-maker artifact has the wrong candidate")
    sessions = _list(_mapping(payload, "result"), "sessions")
    output = []
    for index, value in enumerate(sessions):
        session = _mapping_value(value, "market-maker session")
        output.append(
            ApexAttributedOutcome(
                f"mm-{index:06d}",
                "apex_regime_mm_v2",
                "BTC",
                _timestamp_ms(_text(session, "start_utc")),
                _timestamp_ms(_text(session, "end_utc")),
                _MM_RESERVED_MARGIN_USD,
                _number(session, "fees_usd"),
                _number(session, "net_pnl_usd"),
            )
        )
    return tuple(output)


def _hulk_outcomes(
    payload: Mapping[str, object],
) -> tuple[ApexAttributedOutcome, ...]:
    profile = _mapping(payload, "profile")
    candidate = _text(profile, "name")
    if candidate != "hulk_expansion_short_robust_v3":
        raise ValueError("Hulk artifact has the wrong candidate")
    trades = _list(_mapping(payload, "replay"), "trades")
    output = []
    for index, value in enumerate(trades):
        trade = _mapping_value(value, "Hulk trade")
        entry = _timestamp_ms(_text(trade, "entry_time_utc"))
        exit_time = max(_timestamp_ms(_text(trade, "exit_time_utc")), entry + 1)
        output.append(
            ApexAttributedOutcome(
                f"hulk-{index:06d}",
                candidate,
                _text(trade, "symbol"),
                entry,
                exit_time,
                _number(trade, "isolated_margin_usd"),
                _hulk_entry_fee(trade),
                _number(trade, "net_pnl_usd"),
            )
        )
    return tuple(output)


def _hulk_entry_fee(trade: Mapping[str, object]) -> float:
    total = _number(trade, "fees_usd")
    exit_fees = sum(
        _number(_mapping_value(value, "Hulk exit leg"), "fee_usd")
        for value in _list(trade, "exit_legs")
    )
    entry_fee = total - exit_fees
    if entry_fee < -1e-9:
        raise ValueError("Hulk exit fees exceed total trade fees")
    return max(entry_fee, 0.0)


def _matching_segment(*payloads: Mapping[str, object]) -> str:
    segments = {_text(payload, "segment") for payload in payloads}
    if len(segments) != 1:
        raise ValueError("Apex artifacts must cover the same segment")
    return segments.pop()


def _input_identity(
    directional: Path | None,
    market_maker: Path,
    hulk: Path | None,
) -> dict[str, object]:
    identity = {"market_maker": _identity(market_maker)}
    if directional is not None:
        identity["directional"] = _identity(directional)
    if hulk is not None:
        identity["hulk"] = _identity(hulk)
    return identity


def _common_window(
    start_value: str | None,
    end_value: str | None,
    hulk_present: bool,
) -> tuple[int, int] | None:
    if start_value is None and end_value is None and not hulk_present:
        return None
    if start_value is None or end_value is None:
        raise ValueError("Hulk comparison requires an explicit common window")
    start, end = _timestamp_ms(start_value), _timestamp_ms(end_value)
    if start >= end:
        raise ValueError("shared comparison start must precede end")
    return start, end


def _bounded_outcomes(
    outcomes: tuple[ApexAttributedOutcome, ...],
    window: tuple[int, int] | None,
) -> tuple[tuple[ApexAttributedOutcome, ...], int]:
    if window is None:
        return outcomes, 0
    start, end = window
    selected = tuple(
        outcome
        for outcome in outcomes
        if outcome.entry_time_ms >= start and outcome.exit_time_ms <= end
    )
    return selected, len(outcomes) - len(selected)


def _window_payload(
    window: tuple[int, int] | None,
    excluded: int,
) -> dict[str, object] | None:
    if window is None:
        return None
    start, end = window
    return {
        "start_utc": datetime.fromtimestamp(start / 1_000, UTC).isoformat(),
        "end_utc": datetime.fromtimestamp(end / 1_000, UTC).isoformat(),
        "excluded_outcomes": excluded,
    }


def _payload(path: Path) -> Mapping[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"Apex artifact does not exist: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    return _mapping_value(value, f"artifact {path}")


def _identity(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "size_bytes": len(data),
        "sha256": sha256(data).hexdigest(),
    }


def _timestamp_ms(value: str) -> int:
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("Apex artifact timestamps must be timezone-aware")
    return int(timestamp.timestamp() * 1_000)


def _mapping(parent: Mapping[str, object], key: str) -> Mapping[str, object]:
    return _mapping_value(parent.get(key), key)


def _mapping_value(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} keys must be strings")
    return value


def _list(parent: Mapping[str, object], key: str) -> list[object]:
    value = parent.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def _text(parent: Mapping[str, object], key: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be non-empty text")
    return value


def _number(parent: Mapping[str, object], key: str) -> float:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    return float(value)


if __name__ == "__main__":
    raise SystemExit(main())
