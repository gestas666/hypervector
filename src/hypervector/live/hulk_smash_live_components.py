"""Construction of collaborating Hulk Smash live lifecycle components."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from hypervector.live.hulk_smash_live_close import HulkSmashCloseCoordinator
from hypervector.live.hulk_smash_live_config import HulkSmashLiveConfig
from hypervector.live.hulk_smash_live_entry import HulkSmashEntryCoordinator
from hypervector.live.hulk_smash_live_ledger import HulkSmashLiveLedger
from hypervector.live.hulk_smash_live_orders import HulkSmashOrderGateway
from hypervector.live.hulk_smash_live_protocol import HulkSmashVenueProtocol
from hypervector.live.hulk_smash_live_reconcile import HulkSmashReconciler
from hypervector.live.hulk_smash_live_telemetry import HulkSmashLiveTelemetry


@dataclass(frozen=True)
class HulkSmashLiveComponents:
    """Fully wired collaborators owned by one live engine instance."""

    telemetry: HulkSmashLiveTelemetry
    reconciler: HulkSmashReconciler
    orders: HulkSmashOrderGateway
    closer: HulkSmashCloseCoordinator
    entry: HulkSmashEntryCoordinator


def build_hulk_smash_live_components(
    *,
    config: HulkSmashLiveConfig,
    adapter: HulkSmashVenueProtocol,
    ledger: HulkSmashLiveLedger,
    now_fn: Callable[[], datetime],
    client_order_id_fn: Callable[[], str],
    attempts: int,
    delay_seconds: float,
    sleep_fn: Callable[[float], None],
) -> HulkSmashLiveComponents:
    """Build one shared telemetry, retry, order, entry, and close graph."""
    telemetry = HulkSmashLiveTelemetry(
        config=config,
        ledger=ledger,
        armed=True,
        wallet_configured=True,
        signing_key_configured=True,
        now_fn=now_fn,
    )
    reconciler = HulkSmashReconciler(
        adapter=adapter,
        telemetry=telemetry,
        attempts=attempts,
        delay_seconds=delay_seconds,
        sleep_fn=sleep_fn,
    )
    orders = HulkSmashOrderGateway(
        adapter=adapter,
        telemetry=telemetry,
        client_order_id_fn=client_order_id_fn,
        recovery_attempts=attempts,
        recovery_delay_seconds=delay_seconds,
        sleep_fn=sleep_fn,
    )
    return HulkSmashLiveComponents(
        telemetry=telemetry,
        reconciler=reconciler,
        orders=orders,
        closer=HulkSmashCloseCoordinator(
            adapter=adapter,
            orders=orders,
            reconciler=reconciler,
        ),
        entry=HulkSmashEntryCoordinator(orders=orders, reconciler=reconciler),
    )
