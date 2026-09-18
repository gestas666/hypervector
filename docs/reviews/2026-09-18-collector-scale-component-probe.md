# Initial study-scale telemetry measurement

The actual `runtime_status` implementation scans and authenticates the complete
retained attempt list on each call. The research observation wrapper calls it
on normal publication and at capture checkpoints. This probe measures that
component before choosing an optimization; it does not measure the full recovery
path or establish a live trading defect. Confidence is high for the measurements
on this host, limited for operational impact.

Source: `b2c7436d88ee202a867db3c9723798b05c02fc89`.
Evidence root:
`data/logs/research/bidirectional_cohort/v89_public_collector_scale_20260918_v1`.
`declaration.json` preceded generation and measurement, SHA-256
`dddf7c9b5a30c5893c8d4fb04a6e8a5dd29f7addca4b0cc9e87c51367e46bdb8`.

The upper count comes from a metadata-only observation of the largest existing
collector: 46,807 indexed raw receipts. The five-study sample totaled 102,967 raw
files and 824,087,768 bytes; no sealed response bodies or economic outcomes were
read. The probe creates explicitly synthetic begin-only entries through the real
journal API and FULL-synchronous SQLite commits. It does not bypass integrity
checks or claim those entries are authentic venue requests or scheduler runs.

| Retained attempts | Median status call, five samples | Process peak RSS |
|---:|---:|---:|
| 0 | 0.057 ms | 30.4 MB |
| 100 | 1.19 ms | 30.6 MB |
| 1,000 | 11.35 ms | 35.0 MB |
| 10,000 | 120.15 ms | 62.3 MB |
| 46,807 | 565.46 ms | 169.4 MB |

At the largest count, samples ranged from 548.42 to 593.59 ms. The journal was
23,134,208 bytes; the final 36,807 entries took 26.81 seconds to create. Open file
descriptors stayed at six across every measured call. Each result was checked
for exact attempts, weights and unresolved IDs, with zero API returns,
authorizations, observations or invented successful captures. The sandbox denied
network access and changes to live state.

These are repeated warm-cache reads in one process on a shared macOS host. Peak
RSS is cumulative process peak, not bytes exclusively attributable to one call.
The fixture excludes completed responses, raw-file probes, service permission
validation, IPC, failure-resolution histories, original replay and realistic
mixed receipt sizes. It cannot substitute for those measurements or predict
end-to-end deadline misses. No execution or telemetry policy was changed.

The highest-value next experiment is a complete/mixed synthetic history with
the observed five-source counts and byte-size distributions, using genuine
original normalization and valid service authorization. Measure bridge startup,
raw/service verification, original replay, per-phase status cost, peak memory,
and first eligible request timing with unchanged deadlines. Any optimization
must retain missing/changed evidence detection and pass corruption controls.
Operational new-study declaration, installation and rollback remain required.
