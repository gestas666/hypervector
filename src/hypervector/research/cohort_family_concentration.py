"""Report-only joint-risk topology for a risk-normalized cohort."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

Record = Mapping[str, object]
ProviderScopes = Mapping[str, Sequence[str]]


def build_family_concentration_report(
    allocation: Record,
    provider_scopes: ProviderScopes,
    *,
    target_equity_usd: float,
) -> dict[str, object]:
    """Measure p99 loss concentration induced by overlapping provider scopes."""
    _validate_allocation_contract(allocation)
    equity = _positive(target_equity_usd, "target equity")
    losses = _asset_losses(allocation)
    scopes = _provider_scopes(provider_scopes, frozenset(losses))
    total_loss = sum(losses.values())
    clusters = _cluster_rows(losses, scopes, total_loss, equity)
    return {
        "schema_version": 1,
        "mode": "cohort_provider_family_concentration_v1",
        "status": "report_only_diagnostic",
        "contract": _contract(),
        "source_identity": allocation.get("source_identity"),
        "by_provider": _provider_rows(losses, scopes, total_loss, equity),
        "clusters": clusters,
        "portfolio": {
            "target_equity_usd": equity,
            "p99_stop_wave_loss_usd": total_loss,
            "p99_stop_wave_loss_pct_equity": total_loss / equity * 100.0,
            "connected_cluster_count": len(clusters),
            "largest_cluster_share_pct": max(
                row["share_of_portfolio_stop_wave_pct"] for row in clusters
            ),
        },
        "limitations": _limitations(),
    }


def _validate_allocation_contract(allocation: Record) -> None:
    if allocation.get("mode") != "cohort_p99_risk_normalized_exact_reprice_v1":
        raise ValueError("allocation mode must be exact p99 reprice v1")
    contract = _mapping(allocation.get("contract"), "allocation contract")
    invalid = (
        contract.get("report_only") is not True
        or contract.get("execution_authority") != "none"
        or contract.get("automatic_sizing_change") is not False
        or contract.get("performance_gate") is not False
        or contract.get("balance_gate") is not False
    )
    if invalid:
        raise ValueError("allocation contract must remain report-only and ungated")


def _asset_losses(allocation: Record) -> dict[str, float]:
    assets = _mapping(allocation.get("by_asset"), "allocation assets")
    losses = {
        _text(symbol, "asset symbol"): _positive(
            _mapping(row, f"asset {symbol}").get("repriced_p99_loss_usd"),
            f"{symbol} repriced p99 loss",
        )
        for symbol, row in assets.items()
    }
    if not losses:
        raise ValueError("allocation assets must not be empty")
    return losses


def _provider_scopes(
    provider_scopes: ProviderScopes,
    assets: frozenset[str],
) -> dict[str, frozenset[str]]:
    scopes: dict[str, frozenset[str]] = {}
    for raw_provider, raw_symbols in provider_scopes.items():
        provider = _text(raw_provider, "provider id")
        symbols = frozenset(
            _text(symbol, f"{provider} symbol") for symbol in raw_symbols
        )
        if not symbols:
            raise ValueError(f"{provider} execution scope must not be empty")
        unknown = symbols - assets
        if unknown:
            raise ValueError(
                f"{provider} references unknown assets: {_joined(unknown)}"
            )
        scopes[provider] = symbols
    omitted = assets - frozenset().union(*scopes.values()) if scopes else assets
    if omitted:
        raise ValueError(f"provider scopes omit allocation assets: {_joined(omitted)}")
    return scopes


def _cluster_rows(
    losses: Mapping[str, float],
    scopes: Mapping[str, frozenset[str]],
    total_loss: float,
    equity: float,
) -> list[dict[str, object]]:
    remaining = set(losses)
    rows: list[dict[str, object]] = []
    while remaining:
        connected = _connected_symbols(min(remaining), scopes)
        remaining -= connected
        providers = sorted(
            provider for provider, symbols in scopes.items() if symbols & connected
        )
        loss = sum(losses[symbol] for symbol in connected)
        rows.append(
            {
                "cluster_id": f"cluster_{len(rows) + 1}",
                "symbols": sorted(connected),
                "providers": providers,
                "p99_loss_usd": loss,
                "p99_loss_pct_equity": loss / equity * 100.0,
                "share_of_portfolio_stop_wave_pct": loss / total_loss * 100.0,
            }
        )
    return rows


def _connected_symbols(
    start: str,
    scopes: Mapping[str, frozenset[str]],
) -> set[str]:
    connected = {start}
    changed = True
    while changed:
        expanded = set().union(
            *(symbols for symbols in scopes.values() if symbols & connected)
        )
        changed = not expanded.issubset(connected)
        connected |= expanded
    return connected


def _provider_rows(
    losses: Mapping[str, float],
    scopes: Mapping[str, frozenset[str]],
    total_loss: float,
    equity: float,
) -> dict[str, dict[str, object]]:
    return {
        provider: {
            "symbols": sorted(symbols),
            "p99_loss_usd": (loss := sum(losses[symbol] for symbol in symbols)),
            "p99_loss_pct_equity": loss / equity * 100.0,
            "share_of_portfolio_stop_wave_pct": loss / total_loss * 100.0,
        }
        for provider, symbols in sorted(scopes.items())
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_sizing_change": False,
        "automatic_promotion": False,
        "performance_gate": False,
        "balance_gate": False,
        "profit_forecast": False,
    }


def _limitations() -> list[str]:
    return [
        "provider overlap identifies joint-loss capacity, not joint probability",
        "one-position-per-asset means overlapping providers do not duplicate asset loss",
        "the report does not estimate route expectancy or authorize performance weights",
        "no live profile, route authority, or sizing is changed",
    ]


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{label} must be finite and positive")
    return number


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _joined(values: set[str] | frozenset[str]) -> str:
    return ", ".join(sorted(values))
