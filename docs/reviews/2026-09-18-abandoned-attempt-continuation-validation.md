# Explicit continuation after incomplete-body owner loss

The isolated candidate permits a newly declared study to continue collecting after
its service owner is killed during incomplete response bodies. It retains the
failed original requests as failures, then gives subsequent requests new identities.
Previously the five original collectors stopped on those unresolved witnesses.
This is a technical recovery result; no trading improvement or live deployment is
inferred. Confidence is high within the tested failure contract on this host.

Source: `24babd99171b180805ee216a5c17647dcc34c76a`, branch
`research/v89-abandoned-attempt-recovery-20260918`, based on `3e9e9e0`.
The source worktree is
`/Users/gestas/Prototypes/hypervector-v89-abandoned-attempt-recovery-20260918`.
Evidence root:
`data/logs/research/bidirectional_cohort/v89_public_abandoned_attempt_recovery_20260918_v1`.

## Contract and implementation

- `failure_resolution_version=1` is selected before declaration hashing. The
  default unresolved-attempt rejection remains intact for unselected studies.
- The service issues a separate, immutable failure resolution only after checking
  the original local witness, admission, worker identity, retained body-prefix
  hashes, terminal abandoned/expired outcome, and absence of a completed receipt.
  A live worker, inaccessible liveness evidence, or contradictory data rejects it.
- Resolution does not create an original API return, raw body, observation, or
  ingestion permission. Original missing evidence stays visible in telemetry.
- Recovery revalidates the authority before allowing subsequent collection.
  The five original schedulers keep their original configuration, cutoff,
  native-minute reservation spacing, and durable quarter-hour budget obligations.
- A separate verifier checks raw/index/source grids, old row and history prefixes,
  both process phases, failure records, reservation weights, and new request IDs.

## Executed validation

| Evidence | Committed source | Independent archive |
|---|---:|---:|
| Regression tests | 227 passed, 1 skipped | 227 passed, 1 skipped |
| Suite wall time | 436.34 seconds | 596.04 seconds |
| Original failed requests retained | 5 | 5 |
| Abandoned shared transports | 4 | 3 |
| Subsequent requests, original five-collector order | 10 / 56 / 10 / 56 / 1 | 5 / 40 / 5 / 40 / 4 |

Both actual SIGKILL studies use an unchanged 300-second declared collection window
with original workers and clocks. Different request counts reflect their respective
wall-time scheduling boundaries; deadlines were not extended to obtain activity.
Network access and writes to live state were denied by the qualification sandbox.
The explicit retained-evidence-only alternative test is skipped in these runs.
The two new failure validators have 84/84 statements and 32/32 branches covered;
this is not whole-system coverage. Negative controls include live workers,
inaccessible process state, changed clocks/scopes/hashes, missing admission,
fabricated returns, and immutable-resolution conflicts.

`terminal_qualification.json` re-executes the independent verifier for each run and
compares its result with the retained study report. All 5,836 tracked files match
in both source trees: 11,672 matches, zero changed or missing. The compressed
archive is 33,894,358 bytes, SHA-256
`95ea733b3081905957742828879500b9e95b4dabd470ee65c131013a432454a8`.

## Limitations and next investigation

Each suite reports 70 summarized SQLite resource warnings plus five additional
unclosed-connection messages. A separately retained probe traced the missing
explicit close to the offline `committed_index` helper. Preserve this candidate
and its warnings; qualify the repair in the successor reader-cleanup worktree.
Do not represent these runs as warning-free tooling acceptance.

Actual process death with synthetic HTTP does not prove host power-loss recovery,
real network headroom, or all damaged-state repairs. The interrupted in-memory
request counter is unavailable; durable obligations and the new process counter
are reported separately. Hashes do not protect a compromised host.

The next investigation is whole-study startup and recovery cost after the reader
repair. A metadata-only sample at 05:05:46 UTC observed 102,967 raw files totaling
824,087,768 bytes across the five existing studies. It read no sealed response
bodies or economic outcomes. Use explicitly synthetic histories to measure scale.
Operational new-study declaration, installation, migration and rollback remain
unqualified; preserve the running backend, TUI and frozen studies. Any live
adoption requires a concrete proposal and the user's explicit approval.
