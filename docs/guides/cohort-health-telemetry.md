# Cohort backend health and market clocks

Judge health from the heartbeat and lifecycle events the backend writes for its
own run.

- **Heartbeat.** Copying or touching a ledger does not renew it, and neither
  does appending an operator acknowledgement.
- **Monitor age limit.** `live monitor` attaches only to a checkpoint younger
  than `--maximum-age-seconds` (default 90).
- **Separate clocks.** Source candles and book timestamps each have their own
  clock. File modification time cannot stand in for either.

## Lifecycle

- **`runtime_fault`** is terminal for its run.
- **Normal return.** An observer that returns normally records
  `runtime_stopped`, with `operator_stop` or `bounded_run_complete`.
- **New runs.** A new run needs its own health evidence.
- **Abrupt death.** If the process dies without a terminal event, that is
  visible only after inactivity, or through an independent process check.

## Reading a checkpoint

- **Stopped runs.** A stopped run's checkpoint is a snapshot of when it stopped.
  Refreshing its report produces no strategy decisions and does not show that a
  backend is running.
- **Bad timestamps.** Missing, malformed, unsupported or future timestamps stay
  unavailable, or fail validation.
- **Separate readings.** Inspect each of these on its own, apart from the
  configured strategy timeframe:
  - the selected run and profile;
  - the backend heartbeat;
  - the source one-minute candle close;
  - the book venue timestamp.

## Supervision

The supervisor watches the heartbeat, checkpoint freshness, roster freshness and
free disk; it alerts below about 14 GiB free and treats less than 10 GiB as a
problem. Inspect it with:

```sh
.venv/bin/python -m hypervector live supervisor status
```

Monitoring owns no execution process. Publishing an operator request and the
backend accepting it are separate events. Neither proves venue execution
without venue receipts.

## Validation

```sh
.venv/bin/python -m pytest tests/test_multi_asset_observer_lifecycle.py tests/test_cohort_monitor_stale_attachment.py tests/test_monitor_validation_edges.py tests/test_cohort_supervisor_degraded_freshness.py -q
```

Confidence is bounded by those lifecycle and freshness cases. Either of these
would need a fix and new regression coverage:

- an unrelated write renewing backend health;
- a stale snapshot presented as live authority.
