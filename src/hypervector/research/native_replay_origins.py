"""Recover economic decision clocks from actual native durable order intents."""

from collections.abc import Mapping
from datetime import datetime, timedelta

from hypervector.live.asset_ledger import AssetLiveLedger, AssetLiveLedgerCursor
from hypervector.research.native_replay_clock import EPOCH, ReplayClock
from hypervector.research.native_replay_events import require_clock


class NativeReplayOrigins:
    """Read incremental native ledgers instead of supplying prescribed entry timestamps."""

    def __init__(self, clock: ReplayClock, ledgers: Mapping[str, AssetLiveLedger]) -> None:
        """Bind exact writers; existing rows are validated on the first request."""
        self.clock, self.ledgers = clock, dict(ledgers)
        self._cursors = {symbol: AssetLiveLedgerCursor(0, 1) for symbol in ledgers}
        self._decisions: dict[str, int] = {}
        self._intents: dict[str, dict[str, object]] = {}

    def __call__(self, symbol: str, reduce_only: bool) -> int:
        """Require the native intent and retain entry decision or close submission clocks."""
        rows, cursor = self.ledgers[symbol].read_from_cursor(self._cursors[symbol])
        for row in rows:
            payload = _payload(row)
            if row["event_type"] == "regime_decision" and "decision_time_ms" in payload:
                self._decisions[symbol] = _clock(payload["decision_time_ms"])
            if row["event_type"] == "order_intent":
                self._intents[symbol] = row
        self._cursors[symbol] = cursor
        intent = self._intents.get(symbol)
        operation = "reduce_only_close" if reduce_only else "entry"
        if intent is None or _payload(intent).get("operation") != operation:
            raise ValueError(
                f"{symbol} replay {operation} requires its durable native order intent"
            )
        if reduce_only:
            value = _observed_ms(intent)
        else:
            deadline = _payload(intent).get("entry_deadline")
            value = (
                _clock(deadline.get("decision_time_ms"))
                if isinstance(deadline, Mapping)
                else self._decisions.get(symbol)
            )
            if value is None:
                raise ValueError(f"{symbol} replay entry has no durable decision clock")
        if value > self.clock.now_ms:
            raise ValueError("native replay decision cannot follow current dispatch time")
        self._intents.pop(symbol)
        if not reduce_only:
            self._decisions.pop(symbol, None)
        return value


def _clock(value: object) -> int:
    if type(value) is not int:
        raise ValueError("native replay decision clock must be an exact integer")
    require_clock(value, "native decision time")
    return value


def _payload(row: Mapping[str, object]) -> Mapping[str, object]:
    value = row["payload"]
    if not isinstance(value, Mapping):
        raise ValueError("native replay ledger payload must be an object")
    return value


def _observed_ms(row: Mapping[str, object]) -> int:
    value = row["observed_at_utc"]
    if not isinstance(value, str):
        raise ValueError("native replay intent must retain its observed UTC clock")
    delta = datetime.fromisoformat(value) - EPOCH
    if delta % timedelta(milliseconds=1):
        raise ValueError("native replay intent clock must use exact milliseconds")
    return _clock(delta // timedelta(milliseconds=1))
