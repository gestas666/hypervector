# Cohort backend health and market clocks

The file-backed cohort TUI derives current health from the latest run-bound
backend heartbeat. Copying or touching a ledger, or appending an operator
acknowledgement, does not renew that heartbeat. The existing 60-second inactivity
limit now applies to observer and live cohort ledgers. A fresh running heartbeat
restores the connection; degraded, missing, malformed, unsupported, or future
health evidence cannot present a healthy connection.

`runtime_fault` remains terminal for its run. A normal observer return appends
`runtime_stopped` with `operator_stop` or `bounded_run_complete`. This distinct
event preserves existing polling counts and cadence statistics. A later actual
heartbeat may resume the same normally stopped observer; an unrelated write
cannot. A new run starts with its own health evidence. Abrupt process death
without a terminal event is detected through heartbeat inactivity, not instantly.

The header labels the actual heartbeat clock as `HEARTBEAT`. The strategy chart
inspector reports age since the latest source one-minute candle closed and age
since the book's venue timestamp. These source clocks remain separate from the
configured strategy chart timeframe, file modification time, and operator events.
Unavailable and invalid clocks are explicit; no market values are synthesized.

An explicitly stopped backend is labeled `BACKEND STOPPED`. A stale or unknown
backend does not claim current live authority. Detached-monitor quit labels
describe quitting the monitor without claiming that an unknown backend is alive.
Manual requests continue to require a connected backend and the existing live
authority checks. These display changes do not alter automatic strategy routing,
position sizing, leverage, stops, or order submission.

Focused validation:

```bash
cargo test -p hypervector-tui --release --test cohort_heartbeat_freshness_test
uv run pytest tests/test_multi_asset_observer_lifecycle.py -q -m "not network"
```

The research acceptance additionally checks native terminal cells against actual
source timestamps at 100x28, 120x36 and 190x52. This is technical display and
lifecycle evidence; it does not establish profitability or installed live readiness.
