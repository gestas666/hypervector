# Seven-asset prospective source collection

Implement the collector for the already frozen economic study
`v89_equal_cap_prospective_20260909_v1`, September 9 00:00–September 23 00:00 UTC.
Economic protocol source `1e720d5`, journal revision
`7f8a42b272ee2309f69a233520d98e4d709b8c85e5ac63cd7d1841f343e4acd7`,
record SHA-256 `df22dabfb4acf17cbd7ad5cd7f12bca885b3b9fff85ef98594689ada92c429c3`.
Do not change the calendar, allocation, routes, costs or outcome seal.

Research-only public collection is already authorized. Do not load credentials,
construct order clients, change trading processes or the existing SNDK/Brent
collector, write active config, or inspect either study's early outcomes.
The staging source correction and other deployment proposals remain separate.

## Reuse and qualification

The existing collector in `hypervector-v89-prospective-20260908` uses a strict
two-symbol/15m contract, immutable raw attempts, a private SQLite value-version
index, first-receipt preservation, a singleton lock and bounded retries. Its
process was last verified alive as PID 75062. Inspect code without changing its
worktree, manifest, raw data or running process.

Bring its already tested source modules and focused tests into the isolated
research worktree with explicit source provenance; that worktree currently has
none of these modules. Adapt them for the separate seven-symbol study rather
than creating a duplicate transport/store implementation in the same tree.
Use a new schema and output/lock identity so the new code cannot silently resume
the old sealed database. Preserve the existing shared checkpoint/locking helpers
after confirming their interfaces and hashes; do not overwrite different helpers.

## Capture contract

- Core BTC/ETH/SOL/HYPE: 1m; XYZ SPCX/SNDK/Brent: 15m. Funding: hourly.
  Metadata: separate core and XYZ. Allow only `candleSnapshot`, `fundingHistory`
  and `meta` at the fixed mainnet Info endpoint. No account/order methods.
- Bootstrap seam September 7 00:00 UTC. Authenticate the registered historical
  first/latest core and XYZ warmup sources through that seam. Validate the
  August 26–September 7 prefix of the fourteen-day warmup, then separately
  capture the September 7–9 bridge. Late bootstrap receipts stay labeled late.
- Poll five seconds after minute boundaries. Prioritize the most recent ten
  core minutes each cycle; collect XYZ at quarters and funding/metadata at hours.
  Initial qualification includes every stream. Refresh core's preceding day
  once hourly for revisions, and retain each XYZ preceding day each quarter.
  Recover at most one older missing day per stream per cycle, after recent data.
- Bound all requests to a day and retain the three-attempt/ten-second timeout
  structure. Add a conservative per-collector 600-weight/minute budget using
  documented Info weights and requested item bounds. Record actual intervals,
  overruns, retries, failures and storage estimates; other IP clients remain an
  explicitly unmeasured contribution. Never claim missing/late data is timely.
- Preserve exact raw bytes, request/receipt clocks, source identity and hashes.
  Track both first and latest receipt per distinct value version. Test A→B→A
  reversion: a unique-value index containing A and B alone cannot identify the
  final observed value without a last-receipt record. Existing raw evidence is
  retained; this is a new-index requirement, not proof of loss in the old study.
- Calculate health coverage from source identities/receipt times without reading
  prices or outcomes into the status view. Distinguish unique value revisions,
  missing intervals, late first receipts and latest metadata by dex. Enforce the
  exclusive study end for prospective funding/candles and retain final grace
  data separately. No outcome calculation occurs in the collector.

## Evidence required before calling collection qualified

1. Red/green offline tests for scope, mixed grids, boundary clocks, bounded
   scheduling/rate accounting, malformed/failed responses, revision reversion,
   recovery ordering/tampering, metadata freshness, exclusive end, and singleton
   lifecycle. Network is mocked in tests.
2. Registered warmup hashes and exact source/grid/schema validation. Explicit
   missing bridge data; no price/funding imputation.
3. Frozen source manifest before real capture, request/storage budget and a
   one-shot real capture. Validate raw/index parity and actual first receipts.
4. A safe one-shot resume proving old observations and first/latest identities
   survive; qualify source/manifest mismatch rejection. Freeze source before
   persistent launch; a running process must match its expected PID/start/lock.
5. Observe at least one actual scheduled minute and quarter/hour slot, including
   the relevant streams, while keeping outcomes sealed. Report any unqualified
   stream rather than calling the whole system complete.
6. Journal the exact source, commands, counts/timing/storage evidence and
   limitations. Keep the continuous goal active; prospective replay and economic
   results remain separate outstanding work.

Confidence is medium in this implementation plan and high in the inspected old
source contract. Failed grid/clock/hash/revision tests or measured cadence/storage
overruns require a technical revision before a qualification claim. Unfavorable
future strategy performance remains a result, not an implicit collection gate.
