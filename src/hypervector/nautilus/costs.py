"""Export cost model and conviction for the Phase 2 Nautilus runner (import-light).

The research VectorBT path charges ``taker_fee`` plus ``slippage`` on every
fill (entries, signal exits, stop/take-profit exits) and subtracts a funding
estimate of ``|entry notional| x hourly rate x hold hours``. The Nautilus sim
reproduces that by:

* setting both instrument fee rates to ``taker_fee + slippage_frac``
  (slippage folded into the per-side fee; a bracket take-profit LIMIT fill is
  billed the same as VectorBT bills it), and
* subtracting the same funding estimate from mark-to-market PnL after the run.

Funding uses Hyperliquid's hourly period: ``funding_rate_1h`` (or
``funding_rate_hourly``), else ``funding_rate_8h / 8`` — identical to the
paper cost provider. A legacy ``minutes_per_funding=480`` next to an 8h rate is
ignored because the 8h rate is already converted to an hourly one.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from hypervector.nautilus.load_export import StrategyLoadout

_LEGACY_MAKER_FEE = 0.00015
_LEGACY_TAKER_FEE = 0.00045
_DEFAULT_CONVICTION = 0.5


@dataclass(frozen=True)
class Phase2CostModel:
    """Costs the Nautilus sim applies, plus where they came from."""

    source: str
    taker_fee: float
    slippage_frac: float
    funding_rate_hourly: float
    instrument_maker_fee: float
    instrument_taker_fee: float
    slippage_model: str
    funding_model: str

    def funding_cost(self, notional: float, hold_minutes: float) -> float:
        """Funding paid holding ``notional`` for ``hold_minutes`` (hourly periods)."""
        if notional <= 0 or hold_minutes <= 0 or self.funding_rate_hourly == 0:
            return 0.0
        return abs(notional) * abs(self.funding_rate_hourly) * (hold_minutes / 60.0)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _f(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    return float(value)


def resolve_phase2_costs(loadout: StrategyLoadout) -> Phase2CostModel:
    """Resolve the cost model the export was researched with."""
    meta: Mapping[str, Any] = loadout.meta or {}
    if meta.get("apply_costs") is False:
        return Phase2CostModel(
            source="apply_costs_false",
            taker_fee=0.0,
            slippage_frac=0.0,
            funding_rate_hourly=0.0,
            instrument_maker_fee=0.0,
            instrument_taker_fee=0.0,
            slippage_model="none",
            funding_model="none",
        )

    costs: Mapping[str, Any] | None = loadout.costs
    source = "export_costs"
    if not costs:
        fee_model = meta.get("fee_model")
        if fee_model:
            from hypervector.sweep.costs import resolve_cost_model

            costs = resolve_cost_model(str(fee_model)).to_dict()
            source = "fee_model_preset"
        else:
            return Phase2CostModel(
                source="legacy_default",
                taker_fee=_LEGACY_TAKER_FEE,
                slippage_frac=0.0,
                funding_rate_hourly=0.0,
                instrument_maker_fee=_LEGACY_MAKER_FEE,
                instrument_taker_fee=_LEGACY_TAKER_FEE,
                slippage_model="none",
                funding_model="none",
            )

    taker = _f(costs.get("taker_fee"), _LEGACY_TAKER_FEE)
    if costs.get("slippage_frac") is not None:
        slip = _f(costs.get("slippage_frac"))
    else:
        slip = _f(costs.get("slippage_bps")) / 10_000.0
    if costs.get("funding_rate_1h") is not None:
        funding_hourly = _f(costs.get("funding_rate_1h"))
    elif costs.get("funding_rate_hourly") is not None:
        funding_hourly = _f(costs.get("funding_rate_hourly"))
    elif costs.get("funding_rate_8h") is not None:
        funding_hourly = _f(costs.get("funding_rate_8h")) / 8.0
    else:
        funding_hourly = 0.0
    if taker < 0 or slip < 0:
        raise ValueError(
            f"export costs must be non-negative (taker_fee={taker}, slippage={slip})"
        )
    per_side = taker + slip
    return Phase2CostModel(
        source=source,
        taker_fee=taker,
        slippage_frac=slip,
        funding_rate_hourly=funding_hourly,
        instrument_maker_fee=per_side,
        instrument_taker_fee=per_side,
        slippage_model="folded_into_per_side_fee",
        funding_model=(
            "post_run_entry_notional_x_hourly_rate_x_hold_hours"
            if funding_hourly
            else "none"
        ),
    )


def resolve_phase2_conviction(
    loadout: StrategyLoadout,
    explicit: float | None,
) -> tuple[float, str]:
    """Explicit value, else export ``meta.conviction``, else ``risk.default_conviction``."""
    if explicit is not None:
        return float(explicit), "explicit"
    meta = loadout.meta or {}
    if meta.get("conviction") is not None:
        return float(meta["conviction"]), "export_meta"
    risk = loadout.risk or {}
    if risk.get("default_conviction") is not None:
        return float(risk["default_conviction"]), "export_risk_default"
    return _DEFAULT_CONVICTION, "default"


def estimate_funding(
    holdings: Iterable[tuple[float, float]],
    cost: Phase2CostModel,
) -> float:
    """Sum funding over ``(entry_notional, hold_minutes)`` pairs (min 1 minute)."""
    total = 0.0
    for notional, hold_minutes in holdings:
        total += cost.funding_cost(abs(float(notional)), max(float(hold_minutes), 1.0))
    return total
