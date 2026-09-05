"""Exact local inputs for the BRENTOIL funding-exhaustion screen."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import math

import duckdb
import numpy as np
import pandas as pd

from hypervector.research.funding_price_exhaustion_development import (
    FundingExhaustionCosts,
    FundingExhaustionDevelopmentSpec,
)
from hypervector.research.funding_price_exhaustion_signals import (
    FundingPriceExhaustionConfig,
)
from hypervector.research.hip3_development_provenance import require_unchanged_file

_HYPOTHESIS = "V58_BRENTOIL_FUNDING_PRICE_EXHAUSTION_DEVELOPMENT_V1"
_SYMBOL = "xyz:BRENTOIL"


@dataclass(frozen=True)
class FundingExhaustionSourceReference:
    """One preregistered local evidence file and its immutable identity."""

    role: str
    recorded_path: str
    resolved_path: Path
    sha256: str
    bytes: int

    def evidence(self) -> dict[str, object]:
        """Return the path-free identity expected by the checksum verifier."""
        return {"sha256": self.sha256, "bytes": self.bytes}

    def report(self) -> dict[str, object]:
        """Return the preregistered portable evidence representation."""
        return {
            "role": self.role,
            "path": self.recorded_path,
            "sha256": self.sha256,
            "bytes": self.bytes,
        }


@dataclass(frozen=True)
class BrentFundingExhaustionInputs:
    """Validated development inputs and frozen evaluation contracts."""

    preregistration_path: Path
    preregistration: dict[str, object]
    source_references: tuple[FundingExhaustionSourceReference, ...]
    bars: pd.DataFrame
    funding: pd.DataFrame
    start_utc: pd.Timestamp
    end_utc: pd.Timestamp
    config: FundingPriceExhaustionConfig
    costs: FundingExhaustionCosts
    spec: FundingExhaustionDevelopmentSpec


def load_brentoil_funding_exhaustion_inputs(
    preregistration_path: Path,
    database_path: Path,
    funding_path: Path,
) -> BrentFundingExhaustionInputs:
    """Load only source-bound BRENTOIL development evidence from local files."""
    preregistration = _load_json(preregistration_path)
    _require_report_only_contract(preregistration)
    references = _source_references(preregistration_path, preregistration)
    _require_declared_path(database_path, references, "database")
    _require_declared_path(funding_path, references, "funding")
    _require_sources_unchanged(references)
    start, end = _window(preregistration)
    config = _config(preregistration)
    costs = _costs(preregistration)
    spec = _spec(preregistration)
    bars = _load_bars(database_path, start, end)
    funding = _load_funding(funding_path, start, end)
    return BrentFundingExhaustionInputs(
        preregistration_path.resolve(),
        preregistration,
        references,
        bars,
        funding,
        start,
        end,
        config,
        costs,
        spec,
    )


def require_brentoil_inputs_unchanged(inputs: BrentFundingExhaustionInputs) -> None:
    """Fail when preregistered evidence changes before artifact publication."""
    _require_sources_unchanged(inputs.source_references)


def _load_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"BRENTOIL preregistration does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"BRENTOIL preregistration is invalid JSON: {path}") from exc
    return _mapping(value, "BRENTOIL preregistration")


def _require_report_only_contract(value: dict[str, object]) -> None:
    expected = {
        "hypothesis_id": _HYPOTHESIS,
        "status": "proposed",
        "symbol": _SYMBOL,
        "mode": "development_only_report_only",
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }
    for key, expected_value in expected.items():
        if value.get(key) != expected_value:
            raise ValueError(f"BRENTOIL preregistration has invalid {key}")


def _source_references(
    preregistration_path: Path, value: dict[str, object]
) -> tuple[FundingExhaustionSourceReference, ...]:
    raw_sources = value.get("source_evidence")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError("BRENTOIL preregistration requires source evidence")
    output: list[FundingExhaustionSourceReference] = []
    for raw in raw_sources:
        source = _mapping(raw, "BRENTOIL source evidence")
        recorded = _text(source.get("path"), "BRENTOIL source path")
        path = Path(recorded)
        if not path.is_absolute():
            path = preregistration_path.parent / path
        output.append(
            FundingExhaustionSourceReference(
                _text(source.get("role"), "BRENTOIL source role"),
                recorded,
                path.resolve(),
                _text(source.get("sha256"), "BRENTOIL source sha256"),
                _integer(source.get("bytes"), "BRENTOIL source bytes"),
            )
        )
    paths = [source.resolved_path for source in output]
    if len(set(paths)) != len(paths):
        raise ValueError("BRENTOIL source evidence paths must be unique")
    return tuple(output)


def _require_declared_path(
    path: Path,
    references: tuple[FundingExhaustionSourceReference, ...],
    label: str,
) -> None:
    if path.resolve() not in {source.resolved_path for source in references}:
        raise ValueError(f"BRENTOIL {label} path is not preregistered")


def _require_sources_unchanged(
    references: tuple[FundingExhaustionSourceReference, ...],
) -> None:
    for source in references:
        require_unchanged_file(source.resolved_path, source.evidence())


def _window(value: dict[str, object]) -> tuple[pd.Timestamp, pd.Timestamp]:
    window = _mapping(value.get("frozen_window"), "BRENTOIL frozen window")
    start = pd.Timestamp(_text(window.get("start_utc"), "BRENTOIL start"))
    end = pd.Timestamp(_text(window.get("end_exclusive_utc"), "BRENTOIL end"))
    if start.tz is None or end.tz is None:
        raise ValueError("BRENTOIL window must be timezone-aware")
    start, end = start.tz_convert("UTC"), end.tz_convert("UTC")
    if start >= end:
        raise ValueError("BRENTOIL window start must precede end")
    return start, end


def _config(value: dict[str, object]) -> FundingPriceExhaustionConfig:
    mechanism = _mapping(value.get("frozen_mechanism"), "BRENTOIL mechanism")
    return FundingPriceExhaustionConfig(
        funding_lookback_events=_integer(
            mechanism.get("funding_lookback_events"), "funding lookback"
        ),
        minimum_funding_history_events=_integer(
            mechanism.get("minimum_funding_history_events"), "funding minimum"
        ),
        lower_funding_quantile=_number(
            mechanism.get("lower_funding_quantile"), "lower quantile"
        ),
        upper_funding_quantile=_number(
            mechanism.get("upper_funding_quantile"), "upper quantile"
        ),
        minimum_previous_extension_bps=_number(
            mechanism.get("minimum_previous_extension_bps_from_ema21"),
            "minimum price extension",
        ),
        clean_history_bars=_integer(
            mechanism.get("clean_history_bars"), "clean history"
        ),
    )


def _costs(value: dict[str, object]) -> FundingExhaustionCosts:
    costs = _mapping(value.get("frozen_cost_contract"), "BRENTOIL costs")
    return FundingExhaustionCosts(
        _number(costs.get("nominal_round_trip_bps_before_funding"), "nominal costs"),
        _number(costs.get("stress_round_trip_bps_before_funding"), "stress costs"),
    )


def _spec(value: dict[str, object]) -> FundingExhaustionDevelopmentSpec:
    mechanism = _mapping(value.get("frozen_mechanism"), "BRENTOIL mechanism")
    criteria = _mapping(value.get("success_criteria"), "BRENTOIL success criteria")
    raw_horizons = mechanism.get("fixed_horizons")
    if not isinstance(raw_horizons, list):
        raise ValueError("BRENTOIL fixed horizons must be a list")
    horizons = tuple(_horizon_minutes(item) for item in raw_horizons)
    return FundingExhaustionDevelopmentSpec(
        horizons_minutes=horizons,
        minimum_observations=_integer(
            criteria.get("minimum_non_overlapping_observations"),
            "minimum observations",
        ),
    )


def _horizon_minutes(value: object) -> int:
    label = _text(value, "BRENTOIL horizon")
    if label.endswith("m") and label[:-1].isdigit():
        return int(label[:-1])
    if label.endswith("h") and label[:-1].isdigit():
        return int(label[:-1]) * 60
    raise ValueError(f"unsupported BRENTOIL horizon: {label}")


def _load_bars(path: Path, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    connection = duckdb.connect(str(path), read_only=True)
    try:
        frame = connection.execute(
            """
            SELECT bar_open_at AS timestamp, open, high, low, close, volume
            FROM canonical_trade_5m_bars
            WHERE symbol = ? AND bar_open_at >= ? AND bar_open_at < ?
            ORDER BY bar_open_at
            """,
            [_SYMBOL, start.to_pydatetime(), end.to_pydatetime()],
        ).fetchdf()
    finally:
        connection.close()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True).dt.as_unit("ns")
    _require_bar_bounds(frame, start, end)
    return frame


def _require_bar_bounds(
    frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> None:
    if frame.empty:
        raise ValueError("BRENTOIL database contains no frozen-window bars")
    if frame.iloc[0]["timestamp"] != start:
        raise ValueError("BRENTOIL bars do not begin at the frozen start")
    if frame.iloc[-1]["timestamp"] + pd.Timedelta(minutes=5) != end:
        raise ValueError("BRENTOIL bars do not end at the frozen boundary")
    numeric = frame.loc[:, ["open", "high", "low", "close", "volume"]].to_numpy(float)
    if not np.isfinite(numeric).all():
        raise ValueError("BRENTOIL bars contain non-finite values")


def _load_funding(path: Path, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    required = {"timestamp", "funding_rate", "source", "event_ts_ms"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"BRENTOIL funding missing columns: {missing}")
    output = frame.loc[:, sorted(required)].copy()
    output["timestamp"] = pd.to_datetime(output["timestamp"], utc=True).dt.as_unit("ns")
    expected = pd.date_range(start.ceil("h"), end, freq="h", inclusive="left")
    if not pd.DatetimeIndex(output["timestamp"]).equals(expected):
        raise ValueError("BRENTOIL funding does not exactly cover the frozen hours")
    if not output["source"].astype(str).eq("hl_funding_history").all():
        raise ValueError("BRENTOIL funding source is not official history")
    return output


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a mapping")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError(f"{label} must be non-empty text")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TypeError(f"{label} must be a non-negative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    output = float(value)
    if not math.isfinite(output):
        raise ValueError(f"{label} must be finite")
    return output
