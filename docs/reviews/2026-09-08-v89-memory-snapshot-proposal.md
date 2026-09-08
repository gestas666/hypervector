# V89 reporting snapshot experiment — deployment rejected

Recommendation: do not deploy this candidate. Repeated publication exposed
candidate-specific memory retention despite exact output parity and lower writes.
The implementation is isolated in commit `00237bb`
of `agent/v89-storage-spcx-audit-20260908`; it is not installed in the live checkout.
No live process was restarted, signaled, armed, or reconfigured for this experiment.

## Problem, evidence, and mechanism

The completed process capture measured 3,632,705,536 reporter-written bytes in
15 minutes and identified writable `live-ledger-*.jsonl` temporary copies. That
accounts for repeat copy traffic, not the larger unexplained filesystem capacity
swings. See `2026-09-08-v89-process-storage-completion.md`.

The active reporter uses full current-run snapshots. The proposed reader copies
the same observed bytes into a spool, retains complete-line boundaries and raw
SHA-256 provenance, and releases raw storage before yielding decoded records.
Each snapshot spills to disk after 128 MiB. Legacy path-projector callers retain
the named-file implementation. Compatible-history reporting can consume the
same frozen stream through its existing event projection. Snapshot scope,
sequence validation, cross-asset causal cutoff, and accounting remain unchanged.

The experiment froze eight exact ledger intervals from the
2026-09-08T05:06:10.452241+00:00 checkpoint: 149,966,790 total bytes. Every copy
matched the existing checkpoint hash and original source byte interval. Config
and external report inputs were frozen too. Source inventories covered 1,336
baseline and 1,337 candidate Python modules; their only differences were the
five intended reporting modules. Socket connections and DNS were denied in each
measurement process; bytecode writes were disabled.

## Completed validation

- 124 offline regression tests passed in 6.39 seconds. The new snapshot I/O
  module has 100% statement and branch coverage. Controls cover torn/corrupt
  input, source mutation, invalid projected sequences, no scratch space, spill
  failure, Unicode across copy chunks, and resource release.
- Three baseline and three candidate processes used identical frozen inputs in
  order baseline, candidate, candidate, baseline, baseline, candidate. Every
  complete checkpoint was structurally equal and had canonical SHA-256
  `ceef8502961088c9cee5df448fa8c50cba934df8a59326a6bf030f4fb054318f`.
- Ruff passed. New files and functions satisfy the 500/50-line limits.

| Measurement | Existing reader | Candidate reader |
| --- | ---: | ---: |
| Native disk writes per publication | 122,908,672–152,768,512 bytes | 2,781,184 bytes |
| Median peak RSS | 1,120,043,008 bytes | 1,246,887,936 bytes |
| Elapsed time, including imports | 4.49–5.08 seconds | 4.48–4.51 seconds |
| Entire checkpoint equality | Reference | Exact in every run |

Median measured writes decreased 98.18%; median peak RSS increased 126,844,928
bytes (about 121 MiB). Darwin's installed `getrusage(2)` manual specifies bytes
for `ru_maxrss`. Native physical-write counters can vary with writeback and
temporary-file deletion; their values are not logical copied bytes or net
allocated capacity. Three runs per variant do not establish a latency advantage.

### Repeated publication changes the verdict

The same process published the frozen checkpoint eight times, first with the
candidate and then with the baseline. All 16 outputs retained the same canonical
hash. Candidate peak RSS increased from 1,255,817,216 to 2,174,156,800 bytes;
baseline peak RSS increased from 1,115,963,392 to 1,127,759,872 bytes. Before the
eighth publication, candidate resident memory was 1,416,790,016 bytes versus
498,073,600 baseline bytes. The growth is not explained by the modest single-run
overhead, and this experiment does not establish a safe plateau.

This falsifies readiness for deployment. The mechanism of retained memory is
unverified: allocator retention, object ownership, or another interaction needs
attribution. The next experiment should compare live Python allocations and
native resident memory while releasing each frozen snapshot. It should retain
these failed results and use a new source revision for any correction.

## Alternatives and approval scope

| Alternative | Upside | Trade-off |
| --- | --- | --- |
| Keep the existing reporter | No deployment change | Continues measured temporary-copy traffic |
| Use bounded memory snapshots | Preserves complete output and reduces measured disk writes | Roughly 121 MiB more peak RSS in this fixture; larger snapshots still spill |
| Reduce reporting frequency | Fewer full publications | Staler TUI data; does not repair per-publication overhead |

Applicable market regime: none; this is reporting infrastructure. Expected
upside is lower routine reporting I/O. It is not a strategy, sizing, leverage,
trade-frequency, or profitability recommendation.

Potential live change after a corrected implementation passes validation: install
the five reporting modules and replace only the reporting process using its
existing arguments. Keep a hash-verified backup of
the prior modules and reporter launch record. Deployment approval is still
required by the user's continuous-agent instructions; this report does not
grant execution authority.

Success metrics: identical checkpoint fields on identical input, intact
current-run identity and evidence hashes, fresh TUI checkpoints, lower measured
reporter writes while snapshots fit the cap, and stable process memory.
Reject or roll back this reporting change if rows/checksums diverge, parsing
failures appear, publication becomes stale, or memory grows across steady-state
cycles. Restore the saved reporting modules and its prior launch arguments.

Validation still required before requesting approval: identify and correct the
candidate-specific memory growth, repeat the same-process baseline comparison,
and recheck complete checkpoint parity and spill failure behavior. After any
future approved installation, observe the actual
long-lived reporter through growing prefixes and the memory-to-disk rollover;
verify the active monitor consumes fresh output. Unit tests verify spill
correctness, but this frozen fixture does not reproduce an entire future run.
The separate filesystem capacity issue remains unattributed.

Confidence: high for tested checkpoint parity, disk-write reduction, and observed
candidate-specific memory growth; low for its underlying cause. Changed evidence hashes,
new snapshot corruption, or sustained memory growth would update this assessment.

Evidence root: `data/logs/research/bidirectional_cohort/` in the live checkout.
Inputs: `v89_memory_snapshot_inputs_20260908_v1/`.
Measurements and comparison: `v89_memory_snapshot_benchmark_20260908_v1/`.
Tests: `v89_memory_snapshot_regression_20260908_v2.log`.
Repeated-process evidence: `v89_memory_snapshot_soak_20260908_v1/` and
`v89_memory_snapshot_soak_baseline_20260908_v1/`.
