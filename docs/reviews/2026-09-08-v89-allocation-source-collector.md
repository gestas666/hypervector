# Seven-asset prospective source collector: observed cadence qualified

As of September 8, 2026, 20:03 UTC, the new research collector is running as
PID **15448**, with its own output directory and singleton lock. The existing
SNDK/Brent collector, PID **75062**, remains running in its original worktree.
Both experiments remain sealed against early economic outcome inspection.

## Source and scope

Capture source: `a84f310c34cad768b4577a33f1aab5a8ba04a6fd`.
Independent reconciliation: `a47e4d3ab8ae8eb7dd9d8f04c18447ced5fb2610`.
Research worktree: `/Users/gestas/Prototypes/hypervector-v89-storage-spcx-20260908`.
The capture manifest pins fifteen implementation/shared-helper files. Preserve
those files while this collector runs; additional research must not alter its
source identity. The economic protocol remains source `1e720d5`, journal revision
`7f8a42b272ee2309f69a233520d98e4d709b8c85e5ac63cd7d1841f343e4acd7`.

Window: **September 9 00:00–September 23 00:00 UTC**, exclusive end. BTC, ETH, SOL
and HYPE use 1m candles; SPCX, SNDK and Brent use 15m candles; funding is hourly.
Core and XYZ metadata are separate. The source collector has no credentials,
account endpoints, order clients or execution authority. It reads only public
mainnet candleSnapshot, fundingHistory and meta.

The new schema explicitly rejects the older collector's database. Immutable raw
attempts retain exact response bytes, hashes and request/receipt clocks. The
index tracks the first and latest receipt of each distinct value, including
A→B→A reversions. Health reads only identities/timing. Funding coverage excludes
the study end hour; final grace observations may remain in raw storage.

## Evidence observed — high confidence

- **126 collector tests passed**, including strict grids, scope, malformed data,
  reversion/recovery, metadata separation, exclusive end, rate budgeting,
  interruption, overrun and singleton lifecycle. The archived source independently
  ran the same 126 tests successfully. All 5,184 Git blobs match the archive.
- **Nine independent reconciliation tests passed**, including deliberate raw,
  indexed-value and first/latest-clock corruption. The auditor imports no
  Hypervector implementation code.
- Statement/branch coverage is 100% for the contract, transport, budget, envelope,
  schema, manifest, schedule, store and warmup modules. Runtime coverage is 98%;
  uncovered branches are the missing-schedule guard and a wait boundary crossing.
- All **18 registered warmup files** passed exact hash, schema, finite-value and
  grid checks: **143,712 prefix rows** across the declared variants, August 26
  through September 7 exclusive. Historical hybrid receipts are not relabeled as
  timely prospective captures; the September 7–9 bridge is collected separately.
- First real capture: **34 requests, zero incomplete**, 66.427 seconds including
  rate-budget waiting, **2,056,766 raw bytes**, maximum HTTP latency **873 ms**.
  Independent raw/index reconstruction matched **11,313 value versions**.
- Resume: **20 requests, zero incomplete**, 9.807 seconds. All original value
  versions and first receipts survived; 20 new values were added. Reconciliation
  matched **54 cumulative requests / 11,333 versions**. Maximum independently
  calculated rolling-minute weight was **596**.
- Persistent launch: **19:48:04.091 UTC**. PID/start/command and owned lock were
  verified. The actual **19:49 UTC minute** completed all four core streams in
  **2.082 seconds**, with no incomplete/deferred requests or next-minute overrun.
  All four first receipts met the sixty-second publication allowance.

## Scheduled coarse/hourly qualification — high confidence in observed cycle

The actual **20:00 UTC** cycle completed **20 requests in 9.734 seconds**,
with no incomplete/deferred requests or next-minute overrun. All seven completed
candle identities and all seven actual funding settlements were indexed with
first receipts within sixty seconds: maximum observed candle delay **7.587 s**,
maximum funding delay **13.949 s**. Core metadata was read at 20:00:14.319 UTC;
XYZ metadata at 20:00:14.684 UTC. Metadata freshness means successful reads;
its exchange-publication lag is unknown, so zero lag is not inferred.

A consistent immutable SQLite/raw snapshot at **20:03:32 UTC** independently
reconciled **154 requests / 11,429 value versions**, with maximum rolling-minute
weight **596** and **5,693,676 raw bytes**. This snapshot permits later audit while
the original collector continues writing. Collector source hashes, PID/start,
owned lock and the separate original collector were verified.

This qualifies the observed collection and restart behavior. Sustained future
coverage remains subject to monitoring. Prospective replay implementation and
economic evaluation remain separate outstanding work; no new-study outcomes
have been calculated. Keep the frozen calendar and both outcome seals intact.

Measured response sizes project approximately **971 MB for fourteen days**,
including a conservative cycle-file allowance and two SQLite value versions per
identity. Free space was 8.72 GB at the estimate. This is an estimate, subject to
retries, revisions, response growth and other filesystem writers. The local
600-weight/minute budget survives process restarts; other clients sharing the IP
remain unmeasured. Hyperliquid documents a shared 1,200-weight/minute IP limit and
per-item Info charges in its [rate-limit specification](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits).

Technical faults, source/hash mismatches, sustained late/missing rows, cadence
or storage overruns would lower qualification confidence. Preserve raw evidence
and isolate a revision before changing a running collector. Equal millisecond
receipts have deterministic filename ordering; raw attempts remain the source
of occurrence evidence. No conclusion about future profitability follows from
collector qualification.

## Evidence locations and next work

Qualification artifacts:
`data/logs/research/bidirectional_cohort/v89_equal_cap_source_qualification_20260908_v1/`.
Capture directory:
`data/logs/research/bidirectional_cohort/v89_equal_cap_market_capture_20260908_v1/`.
Key records: `source_freeze.json`, `source_archive_verification.json`,
`collector_coverage_final.json`, `warmup_prefix_qualification.json`,
`independent_one_shot_audit.json`, `independent_resume_audit.json`,
`resume_preservation.json`, `request_storage_projection.json`,
`persistent_launch.json`, `persistent_initial_verification.json` and
`scheduled_minute_qualification.json`, `scheduled_hour_qualification.json`,
`scheduled_hour_interpretation.json`, `qualification_snapshot_manifest.json` and
`independent_qualification_snapshot_audit.json`.

Next: qualify the preregistered replay using older pinned controls while keeping
both prospective outcomes sealed. The inspected historical evaluator supplies
fixed completed lifecycles; the new account contract requires dynamic equity,
rounded quantities, native funding clocks and terminal open positions. The
implementation/acceptance plan is
`docs/plans/2026-09-08-v89-prospective-replay-qualification.md`.
The continuous goal remains active. Existing deployment proposals remain pending;
this public-source research launch does not apply a live allocation or strategy.


The source qualification was appended as prospective hypothesis revision 2:
`f14aae1bfa13f2a41a75d11f21e53230ddfc5698eabd74c4506f0760c6ba5198`.
Its record is `docs/research-journal/v89-equal-cap-prospective-20260909-v2.json`,
SHA-256 `e01f1eaea09f7c0aa765f8ca4ff23fa544d75e5b96dedfdbf55b02090e84695a`,
112,077 bytes and 221 evidence files. DuckDB readback verified the revision,
record hash/length, qualified collector, unqualified replay and null outcomes
at September 8 20:08:21 UTC. The immutable qualification review in the evidence
directory preserves the report as it stood at registration.
