"""Read-only summaries for causally attributed shadow trade lifecycles."""

from __future__ import annotations

from pathlib import Path

import duckdb


def shadow_trade_attribution_summary(database_path: Path) -> dict[str, object]:
    """Summarize completed shadow trades without changing execution authority."""
    with duckdb.connect(str(database_path), read_only=True) as connection:
        row = connection.execute(
            """
            SELECT
                count(*) AS completed_trades,
                count(*) FILTER (
                    WHERE exit_reason LIKE 'take_profit%'
                ) AS targets,
                count(*) FILTER (
                    WHERE terminal_action IN (
                        'liquidation', 'backstop_liquidation'
                    )
                      AND liquidation_evidence_status = 'verified'
                ) AS liquidations,
                count(*) FILTER (
                    WHERE liquidation_evidence_status = 'unverified_legacy'
                ) AS unverified_legacy_liquidations,
                count(*) FILTER (WHERE direction = 'long') AS long_trades,
                count(*) FILTER (WHERE direction = 'short') AS short_trades,
                coalesce(sum(gross_pnl_usd), 0.0) AS gross_pnl_usd,
                coalesce(sum(fees_usd), 0.0) AS fees_usd,
                coalesce(sum(funding_payment_usd), 0.0)
                    AS funding_payment_usd,
                coalesce(sum(net_pnl_usd), 0.0) AS net_pnl_usd
            FROM shadow_completed_trade_attribution
            """
        ).fetchone()
    if row is None or len(row) != 10:
        raise RuntimeError("shadow trade attribution returned an invalid summary")
    return {
        "report_only": True,
        "execution_authority": "none",
        "completed_trades": _integer(row[0], "completed_trades"),
        "targets": _integer(row[1], "targets"),
        "liquidations": _integer(row[2], "liquidations"),
        "unverified_legacy_liquidations": _integer(
            row[3],
            "unverified_legacy_liquidations",
        ),
        "long_trades": _integer(row[4], "long_trades"),
        "short_trades": _integer(row[5], "short_trades"),
        "gross_pnl_usd": _number(row[6], "gross_pnl_usd"),
        "fees_usd": _number(row[7], "fees_usd"),
        "funding_payment_usd": _number(row[8], "funding_payment_usd"),
        "net_pnl_usd": _number(row[9], "net_pnl_usd"),
    }


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(f"shadow trade summary returned invalid {field}")
    return value


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"shadow trade summary returned invalid {field}")
    return float(value)
