"""Declaration-bound audit for the four older SOL exact replay blocks."""

from __future__ import annotations

from datetime import datetime
import math
from pathlib import Path
from typing import Mapping, Sequence

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.sol_range_onset_capacity_shape_audit import (
    _Block,
    _Replay,
    _aggregate,
    _block_summary,
    _mapping,
    _number,
    _parse_replay,
    _read_mapping,
    _select_replay,
    _sequence,
    _timestamp,
    _validate_blocks,
)

_EXPECTED_BLOCKS = 4
_INITIAL_EQUITY_USD = 15_000.0
_MARGIN_FRACTION = 0.03
_LEVERAGE = 5.0
_EXPOSURE = 0.15
_MAX_HOLD_MS = 48 * 60 * 60 * 1_000
_TAKER_FEE_RATE = 0.00045
_REENTRY_COOLDOWN_MS = 60_000
_VENUE_MAX_LEVERAGE = 20.0
_STOPS = (60.0, 80.0)


def audit_backward_exact_blocks(
    declaration_path: Path,
    artifact_paths: Sequence[Path],
) -> dict[str, object]:
    """Validate four exact blocks and apply the predeclared interpretation."""
    declaration = _read_mapping(declaration_path)
    declared = _declared_blocks(declaration)
    _validate_artifact_request(artifact_paths, declared)
    numbered = tuple(_load_declared_artifact(path, declared) for path in artifact_paths)
    if (
        len({number for number, _public, _mark, _reason in numbered})
        != _EXPECTED_BLOCKS
    ):
        raise ValueError("backward exact artifacts do not cover four unique blocks")
    ordered = tuple(sorted(numbered, key=lambda item: item[0]))
    public_blocks = tuple(item[1] for item in ordered)
    public = _complete_surface(public_blocks)
    mark = _mark_surface(ordered)
    return _report(declaration_path, artifact_paths, public_blocks, public, mark)


def _declared_blocks(
    declaration: Mapping[str, object],
) -> dict[datetime, tuple[int, Mapping[str, object]]]:
    expected = {
        "mode": "sol_range_onset_backward_exact_replay_declaration",
        "symbol": "SOL",
        "execution_authority": "none",
        "model_authority": "none",
    }
    if any(declaration.get(key) != value for key, value in expected.items()):
        raise ValueError("backward exact declaration identity differs")
    _validate_fixed_trial(_mapping(declaration.get("fixed_trial"), "fixed trial"))
    rows = _sequence(declaration.get("blocks"), "declared blocks")
    if len(rows) != _EXPECTED_BLOCKS:
        raise ValueError("backward exact declaration requires four blocks")
    result: dict[datetime, tuple[int, Mapping[str, object]]] = {}
    for row in rows:
        block = _mapping(row, "declared block")
        number = _block_number(block)
        start = _timestamp(block.get("development_start_utc"), "block start")
        if start in result:
            raise ValueError("backward exact declaration repeats a block start")
        result[start] = (number, block)
    if {number for number, _block in result.values()} != set(range(1, 5)):
        raise ValueError("backward exact declaration block numbers must be 1-4")
    return result


def _validate_fixed_trial(fixed: Mapping[str, object]) -> None:
    expected = {
        "effective_exposure": _EXPOSURE,
        "initial_equity_per_block": _INITIAL_EQUITY_USD,
        "leverage": _LEVERAGE,
        "margin_fraction": _MARGIN_FRACTION,
        "maximum_hold_hours": 48.0,
        "price_partition_hours": 1.0,
    }
    if any(
        not math.isclose(_number(fixed, key), value) for key, value in expected.items()
    ):
        raise ValueError("backward exact fixed trial differs")
    stops = _sequence(fixed.get("stop_bps"), "fixed stops")
    if tuple(float(value) for value in stops) != _STOPS:
        raise ValueError("backward exact fixed stops differ")


def _validate_artifact_request(
    paths: Sequence[Path],
    declared: Mapping[datetime, tuple[int, Mapping[str, object]]],
) -> None:
    if len(paths) != len(declared) or len(set(paths)) != len(paths):
        raise ValueError("backward exact audit requires four unique artifacts")


def _load_declared_artifact(
    path: Path,
    declared: Mapping[datetime, tuple[int, Mapping[str, object]]],
) -> tuple[int, _Block, _Block | None, str | None]:
    payload = _read_mapping(path)
    _validate_artifact_header(payload, path)
    continuous = _mapping(payload.get("continuous"), "continuous")
    start = _timestamp(continuous.get("start_utc"), "continuous start")
    if start not in declared:
        raise ValueError(f"backward exact block was not declared: {path}")
    number, declaration = declared[start]
    end = _validate_boundaries(payload, payload, declaration, path)
    sixty = _load_replay(continuous, 60.0, path)
    eighty = _load_replay(continuous, 80.0, path)
    public = _Block(path, path, start, end, sixty, eighty)
    mark, reason = _load_mark_block(payload, declaration, path, start, end)
    return number, public, mark, reason


def _load_mark_block(
    payload: Mapping[str, object],
    declaration: Mapping[str, object],
    path: Path,
    start: datetime,
    end: datetime,
) -> tuple[_Block | None, str | None]:
    mark = _mapping(payload.get("sampled_mark_surface"), "sampled mark surface")
    price = _mapping(mark.get("price_archive"), "price archive")
    if not math.isclose(_number(price, "partition_hours"), 1.0):
        raise ValueError(f"backward exact mark partition differs: {path}")
    status = mark.get("mark_validation_status")
    if status == "censored":
        reason = mark.get("censor_reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"backward exact censored mark reason is missing: {path}")
        return None, reason
    if status != "complete":
        raise ValueError(f"backward exact mark status is invalid: {path}")
    continuous = _mapping(mark.get("continuous"), "mark continuous")
    mark_start = _timestamp(continuous.get("start_utc"), "mark continuous start")
    mark_end = _validate_boundaries(payload, mark, declaration, path)
    if mark_start != start or mark_end != end:
        raise ValueError(f"backward exact public and mark boundaries differ: {path}")
    return (
        _Block(
            path,
            path,
            mark_start,
            mark_end,
            _load_replay(continuous, 60.0, path),
            _load_replay(continuous, 80.0, path),
        ),
        None,
    )


def _validate_artifact_header(payload: Mapping[str, object], path: Path) -> None:
    expected = {
        "schema_version": 3,
        "symbol": "SOL",
        "execution_authority": "none",
        "model_authority": "none",
        "trial_surface": "capacity-shape",
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError(f"backward exact artifact identity differs: {path}")


def _validate_boundaries(
    payload: Mapping[str, object],
    mark: Mapping[str, object],
    declared: Mapping[str, object],
    path: Path,
) -> datetime:
    keys = (
        ("signal_warmup_start_utc", "signal_warmup_start_utc"),
        ("development_start_utc", "development_start_utc"),
    )
    for actual, expected in keys:
        source = payload if actual == "signal_warmup_start_utc" else mark["continuous"]
        value = (
            _mapping(source, actual).get("start_utc")
            if source is not payload
            else source.get(actual)
        )
        if _timestamp(value, actual) != _timestamp(declared.get(expected), expected):
            raise ValueError(f"backward exact declared boundary differs: {path}")
    expected_segments = {
        "development": ("development_start_utc", "development_end_utc"),
        "validation": ("development_end_utc", "validation_end_utc"),
        "pseudo_holdout": ("validation_end_utc", "pseudo_holdout_end_utc"),
        "continuous": ("development_start_utc", "pseudo_holdout_end_utc"),
    }
    for name, (start_key, end_key) in expected_segments.items():
        segment = _mapping(mark.get(name), name)
        _assert_segment_boundary(segment, declared, start_key, end_key, path)
    return _timestamp(declared.get("pseudo_holdout_end_utc"), "declared end")


def _assert_segment_boundary(
    segment: Mapping[str, object],
    declared: Mapping[str, object],
    start_key: str,
    end_key: str,
    path: Path,
) -> None:
    actual = (
        _timestamp(segment.get("start_utc"), "segment start"),
        _timestamp(segment.get("end_utc"), "segment end"),
    )
    expected = (
        _timestamp(declared.get(start_key), start_key),
        _timestamp(declared.get(end_key), end_key),
    )
    if actual != expected:
        raise ValueError(f"backward exact declared segment differs: {path}")


def _load_replay(
    segment: Mapping[str, object],
    stop_bps: float,
    path: Path,
) -> _Replay:
    trials = [
        _mapping(value, "trial") for value in _sequence(segment.get("trials"), "trials")
    ]
    trial_id = f"stop={stop_bps:g}__exposure={_EXPOSURE:g}"
    matches = [trial for trial in trials if trial.get("trial_id") == trial_id]
    if len(matches) != 1:
        raise ValueError(f"backward exact trial is missing: {path}")
    _validate_replay_config(matches[0], stop_bps, path)
    return _parse_replay(_select_replay(segment, stop_bps, path), path)


def _validate_replay_config(
    trial: Mapping[str, object],
    stop_bps: float,
    path: Path,
) -> None:
    config = _mapping(trial.get("replay_config"), "replay config")
    expected = {
        "initial_equity": _INITIAL_EQUITY_USD,
        "margin_fraction": _MARGIN_FRACTION,
        "leverage": _LEVERAGE,
        "venue_max_leverage": _VENUE_MAX_LEVERAGE,
        "stop_bps": stop_bps,
        "max_hold_ms": float(_MAX_HOLD_MS),
        "taker_fee_rate": _TAKER_FEE_RATE,
        "reentry_cooldown_ms": float(_REENTRY_COOLDOWN_MS),
    }
    if any(
        not math.isclose(_number(config, key), value) for key, value in expected.items()
    ):
        raise ValueError(f"backward exact replay config differs: {path}")


def _block_number(values: Mapping[str, object]) -> int:
    value = values.get("number")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("backward exact block number must be an integer")
    return value


def _fragility(
    blocks: tuple[_Block, ...],
    stop_bps: float,
    metrics: Mapping[str, object],
) -> list[str]:
    flags: list[str] = []
    if _number(metrics, "leave_one_block_out_min_net_pnl_usd") <= 0.0:
        flags.append("aggregate profit depends on one block")
    trades = [
        trade
        for block in blocks
        for trade in (
            block.sixty if math.isclose(stop_bps, 60.0) else block.eighty
        ).trades
    ]
    winners = [trade.net_pnl_usd for trade in trades if trade.net_pnl_usd > 0.0]
    net = _number(metrics, "reset_block_net_pnl_usd")
    if winners and net - max(winners) <= 0.0:
        flags.append("aggregate profit depends on one trade")
    return flags


def _complete_surface(blocks: tuple[_Block, ...]) -> dict[str, object]:
    expected_trades = sum(len(block.sixty.trades) for block in blocks)
    _validate_blocks(blocks, expected_trades)
    stops = {f"{stop:g}": _aggregate(blocks, stop_bps=stop) for stop in _STOPS}
    fragility = {
        key: _fragility(blocks, float(key), metrics) for key, metrics in stops.items()
    }
    return {
        "status": "complete",
        "completed_blocks": len(blocks),
        "stops": stops,
        "fragility": fragility,
        "disposition": {
            key: _disposition(metrics, fragility[key]) for key, metrics in stops.items()
        },
    }


def _mark_surface(
    artifacts: tuple[tuple[int, _Block, _Block | None, str | None], ...],
) -> dict[str, object]:
    completed = tuple(mark for _number, _public, mark, _reason in artifacts if mark)
    censored = [number for number, _public, mark, _reason in artifacts if mark is None]
    reasons = {
        str(number): reason
        for number, _public, mark, reason in artifacts
        if mark is None and reason is not None
    }
    if censored:
        return {
            "status": "censored",
            "completed_blocks": len(completed),
            "censored_blocks": censored,
            "censor_reasons": reasons,
            "stops": None,
            "interpretation": "no pooled sampled-mark result from incomplete evidence",
        }
    return _complete_surface(completed)


def _report(
    declaration_path: Path,
    artifact_paths: Sequence[Path],
    blocks: tuple[_Block, ...],
    public: dict[str, object],
    mark: dict[str, object],
) -> dict[str, object]:
    stops = _mapping(public.get("stops"), "public stops")
    fragility = _mapping(public.get("fragility"), "public fragility")
    disposition = _mapping(public.get("disposition"), "public disposition")
    return {
        "schema_version": 2,
        "mode": "sol_range_onset_backward_exact_audit",
        "execution_authority": "none",
        "model_authority": "none",
        "runtime_strategy_changed": False,
        "declaration_evidence": {
            "path": str(declaration_path),
            **file_evidence(declaration_path),
        },
        "artifact_evidence": [
            {"path": str(path), **file_evidence(path)} for path in artifact_paths
        ],
        "blocks": [_block_summary(block) for block in blocks],
        "surfaces": {
            "public_trade": public,
            "sampled_mark": mark,
        },
        "stops": stops,
        "fragility": fragility,
        "disposition": disposition,
        "no_implicit_abort_gate": True,
    }


def _disposition(metrics: Mapping[str, object], fragility: list[str]) -> str:
    profit_factor = metrics.get("profit_factor")
    pf = float(profit_factor) if isinstance(profit_factor, (int, float)) else 0.0
    falsified = (
        pf <= 1.0
        or _number(metrics, "product_return_pct") <= 0.0
        or _number(metrics, "liquidations") > 0.0
    )
    if falsified:
        return "falsified"
    supportive = _number(metrics, "positive_blocks") >= 2.0
    if supportive and fragility:
        return "supportive_but_fragile"
    return "supportive" if supportive else "inconclusive"
