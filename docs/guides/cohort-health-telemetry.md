# Cohort backend health and market clocks

Interpret health from backend-authored run-bound heartbeat and lifecycle evidence.
Copying or touching a ledger, or appending an operator acknowledgement, does not
renew the backend heartbeat. Monitor attachment has an explicit maximum evidence
age (`cohort monitor --help`); source candles and book timestamps have their own
clocks. File modification time cannot substitute for either source clock.

`runtime_fault` is terminal for its run. Normal observer return records
`runtime_stopped` with `operator_stop` or `bounded_run_complete`. A new run needs
its own health evidence. Abrupt process death without a terminal event is only
observable after inactivity or another independent process check.

A stopped checkpoint remains a dated snapshot. Refreshing its report does not
produce strategy decisions or prove that a backend is running. Missing, malformed,
unsupported or future timestamps must remain unavailable or fail validation.
Inspect the selected run/profile, backend heartbeat, source one-minute candle
close and book venue timestamp separately from the configured strategy timeframe.

Monitoring owns no execution process. Operator request publication and backend
acceptance are separate events; neither proves venue execution without receipts.
The current JSON monitor replaces former terminal health labels and screenshots.
Historical native display captures remain dated evidence rather than current
software acceptance.

Validation:

```sh
.venv/bin/python -m pytest tests/test_multi_asset_observer_lifecycle.py tests/test_cohort_monitor_stale_attachment.py tests/test_monitor_validation_edges.py tests/test_cohort_supervisor_degraded_freshness.py -q
```

Confidence is bounded by those controlled lifecycle/freshness cases. An unrelated
write renewing backend health, or a stale snapshot represented as live authority,
would require a correction and additional regression coverage.
