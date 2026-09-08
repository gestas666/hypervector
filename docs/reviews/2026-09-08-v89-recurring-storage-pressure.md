# V89 recurring reporting storage pressure

High confidence: transient filesystem pressure recurred after the verified debug
cache cleanup, then recovered without another cleanup. The earlier cleanup
recovered real capacity but did not establish durable protection from subsequent
pressure. The responsible writer remains unconfirmed. Attribution would require
allocated growth or temporary-file ownership observed during the next event.

## Measurements

Two completed, metadata-only samples each contain 31 observations at ten-second
intervals. They do not read account secrets or database contents.

| Window, UTC | First sample: 03:36:32–03:41:32 | Second sample: 03:44:49–03:49:49 |
| --- | ---: | ---: |
| Minimum free bytes | 5,264,166,912 | 12,230,299,648 |
| Maximum free bytes | 12,548,931,584 | 12,414,955,520 |
| Observed range | 7,284,764,672 | 184,655,872 |
| Samples below importer's 8 GiB requirement | 14 | 0 |
| Live ledger logical growth | 1,349,937 bytes | 1,353,355 bytes |
| Live ledger allocated growth | 0 | 0 |
| Research database net growth | −9,437,184 bytes | 0 |
| Docker allocated range | Not sampled | 0 |

The first sample recovered 7,216,861,184 bytes from its minimum to its endpoint.
These measured persistent files do not explain that transient change. Sampling
can miss short-lived files, and the watch list is not a complete filesystem
inventory. Allocated block counts also do not uniquely attribute all APFS space
accounting effects.

Docker's sparse image had approximately 994.7 GB of logical size but 31.8 GB of
allocated blocks. Its allocated count stayed constant throughout the second
window. That quieter window cannot prove or disprove Docker involvement in the
earlier event. SocratiCode reported an older completed Hypervector index, not a
contemporaneous active indexing operation. Watcher responses differed in local
versus other-process scope; no container, watcher or index was altered.

## Runtime acceptance and disposition

At 04:04:11 UTC, the checkpoint showed the same two open positions, zero
completed trades and zero reported faults. Research sync was ready, with its
last successful import at 04:03:02 UTC. Free space measured 16,041,304,064 bytes
at the later capture. The live supervisor, backend, original TUI, reporting
owner, reporter and public collector retained their observed process lifetimes.
The live configuration and installed TUI binary hashes matched the preceding
acceptance; `target/debug` remained absent.

Preserve the verified backup and current reporting behavior. Do not lower the
importer's capacity requirement or delete unrelated indexes based on this
inconclusive attribution. The next discriminating investigation is a bounded
capture of allocated growth and temporary-file ownership during another
multi-gigabyte free-space fall. The simpler alternative is observation without
further cleanup; its trade-off is potential renewed import deferral.

The original five-minute capture scripts are preserved byte-for-byte beside
their samples. Their duplicate working copies were removed only after checksum
verification. No database, log, journal, live control or Docker data was deleted.

Artifacts under `data/logs/research/bidirectional_cohort/`:
`v89_storage_growth_20260908_v1/`, `v89_storage_growth_20260908_v2/`,
`v89_storage_pressure_analysis_20260908_v1.json`,
`v89_storage_socraticode_observations_20260908_v1.json`,
`v89_storage_sampler_source_consolidation_20260908_v1.json`, and
`v89_storage_spcx_runtime_20260908_v1/`. The journal revision preserves the earlier
recovery claim and adds this recurrence, uncertainty and runtime evidence.
