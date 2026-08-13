"""Strict-source target-only versus opposite-entry close/reverse comparison."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace

import pandas as pd

from hypervector.research.hypervelocity_margin_stop_compare import (
    margin_stop_candidate_configs,
    summarize_margin_stop_grid,
)
from hypervector.research.maker_replay_models import (
    MakerReplayConfig,
    MakerReplayReport,
)

_CONTROL = "tp_only_strict_source_control"
_CANDIDATE = "opposite_entry_close_reverse"


def close_reverse_candidate_configs() -> dict[str, MakerReplayConfig]:
    """Return the frozen target-only control and one close/reverse candidate."""
    control = margin_stop_candidate_configs()["no_stop_control"]
    candidate = replace(control, opposite_entry_close_reverse=True)
    differences = {
        name
        for name, value in asdict(control).items()
        if value != asdict(candidate)[name]
    }
    if differences != {"opposite_entry_close_reverse"}:
        raise RuntimeError(f"close/reverse candidate config drift: {differences}")
    return {_CONTROL: control, _CANDIDATE: candidate}


def summarize_close_reverse_grid(
    reports: Mapping[str, MakerReplayReport],
    configs: Mapping[str, MakerReplayConfig],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, object]:
    """Summarize both candidates while retaining reversal lifecycle identity."""
    expected = [_CONTROL, _CANDIDATE]
    if list(configs) != expected or set(reports) != set(expected):
        raise ValueError("close/reverse comparison requires the frozen candidate pair")
    summary = summarize_margin_stop_grid(
        reports,
        configs,
        start=start,
        end=end,
    )
    candidates = summary["candidates"]
    if not isinstance(candidates, dict):
        raise RuntimeError("close/reverse candidate summary is invalid")
    for name, config in configs.items():
        candidate = candidates[name]
        if not isinstance(candidate, dict):
            raise RuntimeError(f"close/reverse candidate summary missing: {name}")
        candidate["opposite_entry_close_reverse"] = config.opposite_entry_close_reverse
    return summary


def _candidate_block_metrics(candidate: Mapping[str, object]) -> dict[str, object]:
    replay = candidate.get("replay")
    if not isinstance(replay, Mapping):
        raise ValueError("close/reverse block is missing replay metrics")
    initial = float(replay["initial_equity"])
    final = float(replay["final_equity"])
    trades = replay.get("trades")
    if not isinstance(trades, Sequence):
        raise ValueError("close/reverse block is missing trade rows")
    return {
        "initial_equity": initial,
        "final_equity": final,
        "net_pnl": final - initial,
        "liquidations": int(replay["liquidations"]),
        "close_reversals": int(replay["close_reversals"]),
        "fees": sum(float(row["fees"]) for row in trades),
        "funding_cashflow": float(replay["funding_cashflow"]),
        "status_counts": candidate.get("status_counts", {}),
    }


def _aggregate_candidate(
    blocks: Sequence[Mapping[str, object]],
    name: str,
) -> dict[str, object]:
    metrics: list[dict[str, object]] = []
    statuses: Counter[str] = Counter()
    for block in blocks:
        candidates = block.get("candidates")
        if not isinstance(candidates, Mapping) or name not in candidates:
            raise ValueError(f"close/reverse aggregate missing candidate: {name}")
        candidate = candidates[name]
        if not isinstance(candidate, Mapping):
            raise ValueError(f"close/reverse aggregate candidate is invalid: {name}")
        item = _candidate_block_metrics(candidate)
        metrics.append(item)
        counts = item["status_counts"]
        if not isinstance(counts, Mapping):
            raise ValueError("close/reverse status counts are invalid")
        statuses.update({str(key): int(value) for key, value in counts.items()})
    total_net = sum(float(item["net_pnl"]) for item in metrics)
    return {
        "initial_equity_sum": sum(float(item["initial_equity"]) for item in metrics),
        "final_equity_sum": sum(float(item["final_equity"]) for item in metrics),
        "total_net_pnl": total_net,
        "positive_blocks": sum(float(item["net_pnl"]) > 0.0 for item in metrics),
        "liquidations": sum(int(item["liquidations"]) for item in metrics),
        "close_reversals": sum(int(item["close_reversals"]) for item in metrics),
        "fees": sum(float(item["fees"]) for item in metrics),
        "funding_cashflow": sum(float(item["funding_cashflow"]) for item in metrics),
        "status_counts": dict(sorted(statuses.items())),
        "aggregate_development_profitable": total_net > 0.0,
    }


def aggregate_close_reverse_blocks(
    blocks: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Aggregate reset-block economics without inventing a path across gaps."""
    if not blocks:
        raise ValueError("close/reverse aggregate requires at least one block")
    names = tuple(close_reverse_candidate_configs())
    return {
        "block_count": len(blocks),
        "portfolio_paths_stitched_across_gaps": False,
        "candidates": {name: _aggregate_candidate(blocks, name) for name in names},
    }
