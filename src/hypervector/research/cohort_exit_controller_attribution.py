"""Entry-owner and exit-controller attribution for closed cohort lifecycles."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence

from hypervector.research.cohort_live_audit_execution import trade_group_summary

Record = Mapping[str, object]


def build_exit_controller_attribution(
    trades: Sequence[Record],
) -> dict[str, object]:
    """Partition resolved economics by exact entry and exit strategy identities."""
    grouped: dict[str, list[Record]] = defaultdict(list)
    cross_provider = 0
    for trade in trades:
        entry = _text(trade.get("entry_strategy_id"), "entry strategy")
        controller = _text(trade.get("exit_controller_strategy_id"), "exit controller")
        cross = trade.get("cross_provider_exit")
        if not isinstance(cross, bool) or cross != (entry != controller):
            raise ValueError("cross-provider exit attribution is inconsistent")
        grouped[f"{entry}|{controller}"].append(trade)
        cross_provider += int(cross)
    return {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "performance_gate": False,
            "automatic_strategy_changes": False,
        },
        "closed_trades": len(trades),
        "cross_provider_exits": cross_provider,
        "same_provider_exits": len(trades) - cross_provider,
        "by_entry_and_exit_controller": {
            key: _route_summary(values) for key, values in sorted(grouped.items())
        },
    }


def _route_summary(trades: Sequence[Record]) -> dict[str, object]:
    summary = trade_group_summary(trades)
    summary["sides"] = dict(
        sorted(
            Counter(_text(trade.get("side"), "trade side") for trade in trades).items()
        )
    )
    summary["exit_reasons"] = dict(
        sorted(
            Counter(
                _text(trade.get("exit_reason"), "trade exit reason") for trade in trades
            ).items()
        )
    )
    return summary


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()
